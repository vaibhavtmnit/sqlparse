"""
separator.py — CodeSeparator: Main orchestrator for entity-scoped
SQL code segmentation.

Takes an iterable of chunks (from SQLChunker) and produces an
EntityRegistry with all entities segmented along natural code boundaries.

Usage::

    from src.separator.separator import CodeSeparator
    from src.utils.chunker import SQLChunker
    from src.agents.llm import get_llm

    llm = get_llm()
    chunks = SQLChunker(sql_code, window_size=120, overlap=15)

    separator = CodeSeparator(llm)
    registry = separator.process(chunks)

    # Get the tree
    tree = registry.get_tree()

    # Save to file
    registry.save_to_file("output/entity_registry.json")
"""

from __future__ import annotations

from typing import Any, Iterable

from loguru import logger
from rich.console import Console

from src.separator.logger_config import configure_separator_logger

# Configure logger ONCE before any other separator imports
configure_separator_logger()

from src.separator.agent import SeparatorAgent  # noqa: E402
from src.separator.models import EntityEntry, OpenEntity  # noqa: E402
from src.separator.processor import ChunkProcessor  # noqa: E402
from src.separator.registry import EntityRegistry  # noqa: E402
from src.separator.state import SeparatorState  # noqa: E402
from src.utils.chunker import Chunk  # noqa: E402

console = Console()


class CodeSeparator:
    """
    Orchestrates the full code separation pipeline.

    For each chunk:
      1. Builds context summary from the current state
      2. Calls the SeparatorAgent (LLM) to analyze the chunk
      3. Passes the analysis to ChunkProcessor (Python) to update state/registry
      4. Repeats for the next chunk

    After all chunks are processed:
      5. Force-resolves any remaining open entities
      6. Generates descriptions for all resolved entities (batch LLM calls)
    """

    def __init__(
        self,
        llm: Any,
        max_retries: int = 3,
        skip_descriptions: bool = False,
        deduplicate_overlap: bool = False,
    ) -> None:
        """
        Args:
            llm: A LangChain BaseChatModel instance.
            max_retries: Max retries per chunk for the separator agent.
            skip_descriptions: If True, skip AI description generation.
            deduplicate_overlap: If True, checks for line overlap between consecutive chunks and strips overlapping lines.
        """
        self.llm = llm
        self.max_retries = max_retries
        self.skip_descriptions = skip_descriptions

        self.registry = EntityRegistry()
        self.state = SeparatorState()
        self.agent = SeparatorAgent(llm, max_retries=max_retries)
        self.processor = ChunkProcessor(self.registry, self.state, deduplicate_overlap=deduplicate_overlap)

        logger.log(
            "TREE",
            "🌳 CodeSeparator initialised │ ready to segment SQL"
        )

    def process(self, chunks: Iterable[Chunk]) -> EntityRegistry:
        """
        Process all chunks and return the completed EntityRegistry.

        Args:
            chunks: An iterable of Chunk objects (from SQLChunker).

        Returns:
            The EntityRegistry with all entities segmented and described.
        """
        chunk_list = list(chunks)
        total = len(chunk_list)

        logger.log(
            "TREE",
            f"🌳 Starting code separation │ {total} chunk(s) to process"
        )
        for chunk in chunk_list:
            idx = chunk.chunk_id
            text = chunk.chunk_text

            logger.log(
                "CHUNK",
                f"{'═' * 60}\n"
                f"         📦 CHUNK {idx} ({idx + 1}/{total}) │ "
                f"{len(text)} chars │ {len(text.splitlines())} lines\n"
                f"         {'═' * 60}"
            )

            # Step 1: Get context from current state
            context_summary = self.state.get_context_summary()

            # Step 2: Analyze chunk with LLM
            analysis = self.agent.analyze_chunk(
                chunk_text=text,
                context_summary=context_summary,
                chunk_id=idx,
            )

            # Step 3: Process analysis (updates state + registry)
            self.processor.process(analysis, chunk_id=idx)

        # Step 4: Force-resolve any remaining open entities
        self._force_resolve_open_entities()

        # Step 5: Generate descriptions for all resolved entities
        self._generate_descriptions()

        # Final summary
        logger.log(
            "TREE",
            f"\n{'═' * 60}\n"
            f"         🌳 CODE SEPARATION COMPLETE\n"
            f"         {self.registry.summary()}\n"
            f"         {'═' * 60}"
        )

        return self.registry

    # ------------------------------------------------------------------
    # Post-processing
    # ------------------------------------------------------------------

    def _force_resolve_open_entities(self) -> None:
        """
        Force-resolve any entities still open after all chunks are processed.

        These are entities whose code was cut off at the end of the script
        (possibly truncated SQL or missing END statements).
        """
        remaining = self.state.get_all_open()
        if not remaining:
            logger.log("RESOLVED", "✅ All entities resolved — no orphans")
            return

        logger.warning(
            f"⚠ Force-resolving {len(remaining)} orphaned entity/entities "
            f"at end of script"
        )

        # Close in reverse order (deepest nesting first)
        sorted_remaining = sorted(
            remaining, key=lambda e: e.nesting_level, reverse=True
        )

        for entity in sorted_remaining:
            entry = entity.to_entry(is_resolved=True)
            self.registry.register(entry)
            self.state.close_entity(entity.entity_id)
            logger.log(
                "RESOLVED",
                f"  ✅ Force-resolved: {entity.entity_name} "
                f"({entity.entity_type}) │ {len(entry.resolved_code)} chars"
            )

    def _generate_descriptions(self) -> None:
        """
        Generate AI descriptions for all resolved entities in a batch.

        Each entity gets a detailed description based on its resolved code.
        """
        resolved = self.registry.get_resolved()
        if not resolved:
            logger.info("No resolved entities — skipping descriptions.")
            return

        logger.log(
            "DESCRIBE",
            f"📝 Generating descriptions for {len(resolved)} entities..."
        )

        for i, entry in enumerate(resolved):
            if entry.description:
                continue  # Already has a description

            logger.log(
                "DESCRIBE",
                f"  📝 [{i + 1}/{len(resolved)}] {entry.entity_name} "
                f"({entry.entity_type})"
            )

            try:
                description = self._describe_entity(entry)
                entry.description = description
                self.registry.register(entry)  # Update the entry
            except Exception as exc:
                logger.warning(
                    f"  Failed to describe {entry.entity_name}: {exc}"
                )
                entry.description = f"[Description generation failed: {exc}]"
                self.registry.register(entry)

        logger.log(
            "DESCRIBE",
            f"📝 Descriptions complete for {len(resolved)} entities ✓"
        )

    def _describe_entity(self, entry: EntityEntry) -> str:
        """
        Generate a detailed description for a single entity using the LLM.

        Args:
            entry: The EntityEntry to describe.

        Returns:
            A detailed description string.
        """
        # Get children info for context
        children = self.registry.get_children(entry.entity_id)
        children_info = ""
        if children:
            child_lines = [
                f"  - {c.entity_name} ({c.entity_type}"
                f"{'/' + c.operation_type if c.operation_type else ''})"
                for c in children
            ]
            children_info = (
                f"\n\nThis entity contains the following children:\n"
                + "\n".join(child_lines)
            )

        # Get parent info
        parent_info = ""
        if entry.parent_id:
            parent = self.registry.get(entry.parent_id)
            if parent:
                parent_info = (
                    f"\nThis entity is nested inside: "
                    f"{parent.entity_name} ({parent.entity_type})"
                )

        prompt = (
            "You are an Oracle SQL documentation specialist.\n\n"
            "Write a detailed description (150-300 words) of the following "
            "Oracle SQL entity. Cover:\n"
            "- PURPOSE: What does this code do?\n"
            "- OPERATIONS: What operations are performed?\n"
            "- DEPENDENCIES: What tables/objects does it interact with?\n"
            "- CONTEXT: How does it fit in the broader system?\n\n"
            f"Entity: {entry.entity_name}\n"
            f"Type: {entry.entity_type}"
            f"{'/' + entry.operation_type if entry.operation_type else ''}\n"
            f"Nesting Level: {entry.nesting_level}\n"
            f"{parent_info}\n"
            f"{children_info}\n\n"
            f"Resolved Code:\n```sql\n{entry.resolved_code}\n```\n\n"
            "Write the description in clear prose (not bullet points). "
            "Focus on what the code DOES, not what it IS."
        )

        response = self.llm.invoke(prompt)
        content = (
            response.content
            if hasattr(response, "content")
            else str(response)
        )
        return content.strip()
