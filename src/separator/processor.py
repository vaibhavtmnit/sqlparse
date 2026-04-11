"""
processor.py — Deterministic chunk processor for the Code Separator.

Takes a ChunkAnalysis (from the LLM) and updates the SeparatorState and
EntityRegistry accordingly. All logic here is pure Python — no LLM calls.

Responsibilities:
  - For CONTINUATION segments: append code to the matching open entity.
  - For NEW segments: create a new open entity, link to parent.
  - For segments with is_entity_end=True: resolve and register the entity.
  - Handle the nesting stack correctly (children close before parents).
"""

from __future__ import annotations

from loguru import logger

from src.separator.models import ChunkAnalysis, CodeSegment, OpenEntity
from src.separator.registry import EntityRegistry
from src.separator.state import SeparatorState


class ChunkProcessor:
    """
    Processes a ChunkAnalysis and updates the state and registry.

    Usage::

        processor = ChunkProcessor(registry, state)
        processor.process(analysis, chunk_id=3)
    """

    def __init__(
        self,
        registry: EntityRegistry,
        state: SeparatorState,
        deduplicate_overlap: bool = False,
    ) -> None:
        self.registry = registry
        self.state = state
        self.deduplicate_overlap = deduplicate_overlap

    def process(self, analysis: ChunkAnalysis, chunk_id: int) -> None:
        """
        Process all segments in a ChunkAnalysis.

        Segments are processed in order (matching their appearance in the
        chunk text). For each segment:
          1. If ``is_entity_start=True``: create a new OpenEntity.
          2. If ``is_entity_start=False``: find the matching open entity
             and append the code (continuation).
          3. If ``is_entity_end=True``: resolve the entity and register it.

        Args:
            analysis: The structured chunk analysis from the LLM.
            chunk_id: The chunk index this analysis belongs to.
        """
        logger.log(
            "CHUNK",
            f"Processing chunk {chunk_id} │ "
            f"{len(analysis.segments)} segment(s) found"
        )

        for i, segment in enumerate(analysis.segments):
            op_tag = f"/{segment.operation_type}" if segment.operation_type else ""
            action = "NEW" if segment.is_entity_start else "CONT"
            end_tag = " ─► CLOSES" if segment.is_entity_end else ""
            code_preview = segment.code.strip().splitlines()[0][:80] if segment.code.strip() else "(empty)"

            logger.log(
                "FOUND",
                f"  seg[{i}] {action} {segment.entity_name} "
                f"({segment.entity_type}{op_tag}){end_tag}\n"
                f"         code: {code_preview}"
            )

            if segment.is_entity_start:
                self._handle_new_entity(segment, chunk_id)
            else:
                self._handle_continuation(segment, chunk_id)

            if segment.is_entity_end:
                self._handle_entity_close(segment, chunk_id)

        # Log post-chunk state
        open_names = [
            f"{e.entity_name}(L{e.nesting_level})"
            for e in self.state.get_all_open()
        ]
        logger.log(
            "CHUNK",
            f"Chunk {chunk_id} done │ "
            f"registry={self.registry.resolved_count} resolved │ "
            f"open=[{', '.join(open_names) or 'none'}]"
        )

    # ------------------------------------------------------------------
    # Private handlers
    # ------------------------------------------------------------------

    def _handle_new_entity(
        self, segment: CodeSegment, chunk_id: int
    ) -> None:
        """Create a new OpenEntity and add it to the state."""
        parent_id = None
        nesting_level = 0

        if segment.nesting_parent:
            parent = self.state.find_open(segment.nesting_parent)
            if parent:
                parent_id = parent.entity_id
                nesting_level = parent.nesting_level + 1
            else:
                logger.warning(
                    f"  ⚠ Parent '{segment.nesting_parent}' not found in open "
                    f"entities for '{segment.entity_name}'. Treating as top-level."
                )

        entity_id = self.registry.next_id()
        open_entity = OpenEntity(
            entity_id=entity_id,
            entity_name=segment.entity_name,
            entity_type=segment.entity_type,
            operation_type=segment.operation_type,
            parent_id=parent_id,
            nesting_level=nesting_level,
            chunk_ids=[chunk_id],
            code_parts=[segment.code] if segment.code.strip() else [],
            trigger_target=segment.trigger_target,
        )

        self.state.open_entity(open_entity)

        indent = "  " * (nesting_level + 1)
        logger.log(
            "OPENED",
            f"{indent}📂 OPENED {entity_id}: {segment.entity_name} "
            f"({segment.entity_type}) at level {nesting_level}"
            + (f" under {segment.nesting_parent}" if segment.nesting_parent else "")
        )

    def _handle_continuation(
        self, segment: CodeSegment, chunk_id: int
    ) -> None:
        """Find the matching open entity and append code."""
        entity = self.state.find_open(
            entity_name=segment.entity_name,
            entity_type=segment.entity_type,
            nesting_parent=segment.nesting_parent,
        )

        if entity is None:
            logger.warning(
                f"  ⚠ No open entity for continuation: "
                f"{segment.entity_name} ({segment.entity_type}). "
                f"Creating as new entity instead."
            )
            self._handle_new_entity(
                CodeSegment(
                    entity_name=segment.entity_name,
                    entity_type=segment.entity_type,
                    operation_type=segment.operation_type,
                    trigger_target=segment.trigger_target,
                    nesting_parent=segment.nesting_parent,
                    code=segment.code,
                    is_entity_start=True,
                    is_entity_end=segment.is_entity_end,
                ),
                chunk_id,
            )
            return

        entity.append_code(segment.code, chunk_id, deduplicate_overlap=self.deduplicate_overlap)
        indent = "  " * (entity.nesting_level + 1)
        logger.log(
            "CONTINUED",
            f"{indent}🔗 CONTINUED {entity.entity_id}: {entity.entity_name} "
            f"(+chunk {chunk_id}, now {len(entity.code_parts)} parts)"
        )

    def _handle_entity_close(
        self, segment: CodeSegment, chunk_id: int
    ) -> None:
        """Resolve an open entity and register it."""
        entity = self.state.find_open(
            entity_name=segment.entity_name,
            entity_type=segment.entity_type,
            nesting_parent=segment.nesting_parent,
        )

        if entity is None:
            logger.warning(
                f"  ⚠ Cannot close '{segment.entity_name}' — "
                f"not found in open entities."
            )
            return

        entry = entity.to_entry(is_resolved=True)
        self.registry.register(entry)
        self.state.close_entity(entity.entity_id)

        indent = "  " * (entity.nesting_level + 1)
        code_lines = entry.resolved_code.strip().splitlines()
        logger.log(
            "RESOLVED",
            f"{indent}✅ RESOLVED {entity.entity_id}: {entity.entity_name} "
            f"({entity.entity_type}) │ "
            f"{len(code_lines)} lines │ chunks {entry.chunk_ids}"
        )
