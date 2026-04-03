"""
miner.py

SQLMiner orchestrates the full mining pipeline:

1. Read SQL from a file path or raw string.
2. Chunk the SQL using SQLChunker.
3. For each chunk:
   a. Archive the raw chunk to mining/output/chunks/<nnnn>.sql
   b. Write the chunk to mining/state/current_chunk.sql (for agents to read)
   c. Run the miner agent (placeholder — returns structured JSON)
   d. Persist the returned entities, relationships, and flows via RegistryManager
4. Show a rich progress bar throughout the loop.
"""

import json
import os
import re
from pathlib import Path
from typing import Any, Union

from loguru import logger
from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from src.miner.miner_deepagent import MinerDeepAgent
from src.miner.miner_subagents import build_default_subagents
from src.miner.miner_tools import RegistryManager
from src.utils.chunker import SQLChunker
from src.utils.code_handler import read_sql_file

import sys

logger.remove()
logger.add(
    sys.stderr,
    colorize=True,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
)

console = Console()


# ---------------------------------------------------------------------------
# Placeholder miner — replace this with MinerDeepAgent.invoke() later
# ---------------------------------------------------------------------------

def _run_miner_placeholder(chunk_text: str, chunk_index: int) -> dict:
    """
    Placeholder miner.  Returns an empty-but-valid result structure.

    Replace the body of this function with the real MinerDeepAgent call,
    for example::

        result = miner_agent.invoke(f"Mine chunk {chunk_index}.")
        return _parse_agent_result(result)

    The returned dict must have three keys, each a list of dicts:
        entities        — list of entity records
        relationships   — list of relationship records
        flows           — list of flow step records
    """
    logger.debug(f"[Placeholder] Mining chunk {chunk_index} ({len(chunk_text)} chars) ...")
    return {
        "entities": [],
        "relationships": [],
        "flows": [],
    }


# ---------------------------------------------------------------------------
# SQLMiner
# ---------------------------------------------------------------------------


class SQLMiner:
    """
    Orchestrates the full SQL mining pipeline for one or more SQL source files.

    Usage::

        miner = SQLMiner(
            workspace="/path/to/workspace",
            window_size=150,
            overlap=20,
        )

        # Mine from a file path
        miner.run("/path/to/script.sql")

        # Mine from raw SQL string
        miner.run("SELECT 1 FROM DUAL;")
    """

    def __init__(
        self,
        llm: Any,
        workspace: str,
        window_size: int = 150,
        overlap: int = 20,
    ):
        """
        Initialise the SQLMiner.

        Args:
            workspace:   Root workspace directory.  All output is written
                         under ``<workspace>/mining/``.
            window_size: Lines per chunk (passed to SQLChunker).
            overlap:     Overlap lines between consecutive chunks.
        """
        self.llm = llm
        self.workspace = str(workspace)
        self.window_size = window_size
        self.overlap = overlap

        self.registry = RegistryManager(self.workspace)

        logger.info(
            f"SQLMiner initialised | workspace={self.workspace} "
            f"| window={window_size} | overlap={overlap}"
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, source: Union[str, Path]) -> None:
        """
        Mine entities, relationships, and flows from SQL source.

        Args:
            source: Either:
                    - A path (str or Path) to a ``.sql`` file, or
                    - A raw SQL code string.
        """
        sql_code = self._load_sql(source)
        if not sql_code.strip():
            logger.warning("Source is empty — nothing to mine.")
            return
            
        # Clean the workspace directories (keep folder structure)
        self.registry.clean_workspace_files()

        chunks = list(SQLChunker(sql_code, self.window_size, self.overlap))
        total = len(chunks)

        logger.info(f"Starting mining pipeline | {total} chunk(s) to process")

        progress = Progress(
            SpinnerColumn(spinner_name="dots"),
            TextColumn("[bold cyan]{task.description}"),
            BarColumn(bar_width=40, complete_style="green", finished_style="bright_green"),
            MofNCompleteColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            TextColumn("[dim]eta"),
            TimeRemainingColumn(),
            console=console,
            transient=False,
        )

        with progress:
            task = progress.add_task("Mining SQL chunks", total=total)

            for chunk in chunks:
                idx = chunk.chunk_id
                text = chunk.chunk_text

                progress.update(
                    task,
                    description=f"[bold cyan]Chunk {idx + 1}/{total}",
                )

                # Step 1: Archive the raw chunk
                archive_path = self.registry.write_chunk_to_archive(text)
                logger.debug(f"Chunk {idx} archived → {archive_path}")

                # Step 2: Write chunk to current_chunk.sql (agents read this)
                self._write_current_chunk(text)

                # Step 3: Run core mining via MinerDeepAgent
                result = self._run_core_mining(idx)

                # Step 4: Persist results via RegistryManager
                
                self._persist_result(result, chunk_id=str(idx))
                

                progress.advance(task)

        console.print(
            f"\n[bold green]✓ Mining complete![/bold green] "
            f"Processed [bold]{total}[/bold] chunk(s).\n"
            f"  Entities     → [cyan]{self.registry.entities_path}[/cyan]\n"
            f"  Relationships→ [cyan]{self.registry.relationships_path}[/cyan]\n"
            f"  Flows        → [cyan]{self.registry.flows_path}[/cyan]"
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_sql(self, source: Union[str, Path]) -> str:
        """
        Resolve *source* to a raw SQL string.

        If *source* is a readable .sql file path, read it.
        Otherwise treat it as a raw SQL code string.
        """
        try:
            path_obj = Path(source)
            if path_obj.is_file():
                logger.info(f"Reading SQL from file: {path_obj}")
                return path_obj.read_text(encoding="utf-8")
        except (OSError, ValueError):
            # Path contains characters invalid for a filesystem path (e.g. newlines in SQL)
            pass

        logger.info("Source is raw SQL code (not a file path)")
        return str(source)

    def _write_current_chunk(self, text: str) -> None:
        """Write *text* to the current_chunk.sql state file."""
        path = Path(self.registry.current_chunk_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def _run_core_mining(self, chunk_index: int) -> dict:
        """
        Wire up and invoke the MinerDeepAgent for the current chunk.

        Sets up:
          - RegistryManager tools (read/write chunk, chunk details, flow reads)
          - Five mining subagents injected with their relevant tools
          - MinerDeepAgent with the system prompt from miner_prompt.md

        Returns:
            A dict with keys ``entities``, ``relationships``, ``flows`` —
            each a list of dicts parsed from the JSON arrays in the agent's
            final response message.
        """
        # ------------------------------------------------------------------
        # Build tool map keyed by LangChain tool .name for subagent injection
        # ------------------------------------------------------------------
        all_tools = self.registry.get_all_tools()
        tool_map = {t.name: t for t in all_tools}

        subagents = build_default_subagents(tool_map)

        # ------------------------------------------------------------------
        # Create and invoke the MinerDeepAgent
        # ------------------------------------------------------------------
        agent = MinerDeepAgent(
            model=self.llm,
            tools=all_tools,
            subagents=subagents,
            log_dir=self.registry.logs_dir,
        )

        message = (
            f"Process the current SQL chunk (chunk index {chunk_index}). "
            "Follow the orchestration steps in your system prompt exactly."
        )
        raw_result = agent.invoke(message)

        # ------------------------------------------------------------------
        # Extract the agent's final text response and parse JSON arrays
        # ------------------------------------------------------------------
        return self._parse_agent_result(raw_result)

    @staticmethod
    def _parse_agent_result(raw_result: Any) -> dict:
        """
        Extract entities, relationships, and flows JSON arrays from the
        MinerDeepAgent's raw LangChain result.

        The agent's final AI message may contain any of the three arrays
        embedded in its text, either as bare JSON arrays or inside markdown
        code fences labelled ``json``.  We scan the full message content
        using a labelled-block heuristic:

            **Entities**\n```json\n[...]\n```
            **Relationships**\n```json\n[...]\n```
            **Flows**\n```json\n[...]\n```

        or as the last three bare JSON arrays in the text.

        Falls back to empty lists if no parseable arrays are found.

        Args:
            raw_result: The dict returned by MinerDeepAgent.invoke().

        Returns:
            Dict with keys ``entities``, ``relationships``, ``flows``.
        """
        empty = {"entities": [], "relationships": [], "flows": []}

        messages = raw_result.get("messages", []) if isinstance(raw_result, dict) else []
        if not messages:
            logger.warning("Agent returned no messages — returning empty result.")
            return empty

        # Use the last AI message that has content
        content = ""
        for msg in reversed(messages):
            c = getattr(msg, "content", None) or (msg.get("content") if isinstance(msg, dict) else None)
            if c and isinstance(c, str) and c.strip():
                content = c
                break

        if not content:
            logger.warning("Agent final message has no text content — returning empty result.")
            return empty

        logger.debug(f"Parsing agent response ({len(content)} chars)")

        def _extract_labelled(label: str, text: str):
            """
            Look for a section like:  **Entities** ... ```json\n[...]\n```
            matching case-insensitively on the label.
            Returns parsed list or None.
            """
            pattern = (
                rf"(?i)(?:\*{{1,2}}{label}\*{{1,2}}|#{{{1,3}}}\s*{label})"
                r"[\s\S]*?```(?:json)?\s*(\[[\s\S]*?\])\s*```"
            )
            m = re.search(pattern, text)
            if m:
                try:
                    return json.loads(m.group(1))
                except json.JSONDecodeError:
                    pass
            return None

        def _extract_all_arrays(text: str):
            """Return all top-level JSON arrays found in the text."""
            results = []
            for m in re.finditer(r"(\[\s*\{[\s\S]*?\}\s*\])", text):
                try:
                    results.append(json.loads(m.group(1)))
                except json.JSONDecodeError:
                    pass
            return results

        # --- Try labelled extraction first (most reliable) ---
        entities      = _extract_labelled("entities",      content)
        relationships = _extract_labelled("relationships", content)
        flows         = _extract_labelled("flows",         content)

        # --- Fall back: grab all arrays and assign by position ---
        if entities is None and relationships is None and flows is None:
            arrays = _extract_all_arrays(content)
            logger.debug(f"Labelled extraction found nothing; falling back to {len(arrays)} bare array(s)")
            entities      = arrays[0] if len(arrays) > 0 else []
            relationships = arrays[1] if len(arrays) > 1 else []
            flows         = arrays[2] if len(arrays) > 2 else []
        else:
            entities      = entities      or []
            relationships = relationships or []
            flows         = flows         or []

        logger.info(
            f"Parsed agent result: {len(entities)} entities, "
            f"{len(relationships)} relationships, {len(flows)} flows"
        )
        return {
            "entities":      entities,
            "relationships": relationships,
            "flows":         flows,
        }

    def _persist_result(self, result: dict, chunk_id: str) -> None:
        """
        Persist the structured mining result to the registry.

        Order of operations:
          1. Stamp chunk_id on all flow steps → persist flows.
          2. Use an LLM call to match each entity to the correct flow_id
             based on the flow hierarchy just mined (see _link_entities_to_flows).
          3. Stamp chunk_id on every entity and persist them.
          4. Persist relationships.

        Args:
            result:   Dict with keys ``entities``, ``relationships``, ``flows``.
            chunk_id: String identifier for the chunk (used to tag records).
        """
        entities      = result.get("entities", [])
        relationships = result.get("relationships", [])
        flows         = result.get("flows", [])

        # ------------------------------------------------------------------
        # Step 1: Stamp chunk_id on every flow step and write them.
        # ------------------------------------------------------------------
        for flow in flows:
            flow["flow_entity_chunk_id"] = chunk_id

        if flows:
            self.registry.write_flows(flows)
            logger.debug(f"Chunk {chunk_id}: persisted {len(flows)} flow step(s)")

        # ------------------------------------------------------------------
        # Step 2: Ask the LLM to match each entity to the right flow_id.
        #         Falls back to "unassigned" on any error or if no flows exist.
        # ------------------------------------------------------------------
        if entities:
            entities = self._link_entities_to_flows(entities, flows, chunk_id)

        # ------------------------------------------------------------------
        # Step 3: Stamp chunk_id and persist entities.
        # ------------------------------------------------------------------
        for entity in entities:
            entity["chunk_id"] = chunk_id

        if entities:
            self.registry.write_entities(entities)
            assigned = sum(1 for e in entities if e.get("flow_id", "unassigned") != "unassigned")
            logger.debug(
                f"Chunk {chunk_id}: persisted {len(entities)} entity/entities "
                f"({assigned} linked to a flow, {len(entities) - assigned} unassigned)"
            )

        # ------------------------------------------------------------------
        # Step 4: Persist relationships (no chunk_id or flow_id needed here).
        # ------------------------------------------------------------------
        if relationships:
            self.registry.write_relationships(relationships)
            logger.debug(f"Chunk {chunk_id}: persisted {len(relationships)} relationship(s)")

    def _link_entities_to_flows(self, entities: list, flows: list, chunk_id: str) -> list:
        """
        Use a direct LLM call to assign the correct flow_id to each entity.

        The LLM is given the compact flow hierarchy for this chunk and the list
        of entity names/types, and returns a JSON mapping of::

            { "ENTITY_NAME": "flow_id", ... }

        The mapping is applied in-place to each entity record.
        Entities with no confident match receive flow_id = "unassigned".

        Falls back gracefully (all "unassigned") if the LLM call fails or
        returns unparseable output.

        Args:
            entities: List of entity dicts (entity_name, entity_type, entity_description).
            flows:    List of flow step dicts already mined for this chunk.
            chunk_id: Used only for logging.

        Returns:
            The entities list with flow_id set on every record.
        """
        if not flows:
            # No flows in this chunk — nothing to link against
            for entity in entities:
                entity["flow_id"] = "unassigned"
            return entities

        # Build compact representations to keep the prompt short
        entities_payload = json.dumps(
            [{"entity_name": e["entity_name"], "entity_type": e["entity_type"]}
             for e in entities],
            indent=2,
        )
        flows_payload = json.dumps(
            [{
                "flow_id":               f["flow_id"],
                "flow_entity_name":      f["flow_entity_name"],
                "flow_entity_type":      f["flow_entity_type"],
                "flow_entity_role":      f["flow_entity_role"],
                "parent_flow_id":        f.get("parent_flow_id"),
                "flow_description":      f["flow_description"],
            } for f in flows],
            indent=2,
        )

        prompt = (
            "You are a SQL code analysis assistant.\n\n"
            "You are given two lists extracted from the same SQL code chunk:\n"
            "  1. ENTITIES  — named SQL objects found in the chunk.\n"
            "  2. FLOW STEPS — a hierarchical tree describing code structure.\n\n"
            "Task: For each entity return the flow_id of the flow step it most logically "
            "belongs to.\n\n"
            "Rules:\n"
            "- If an entity IS the flow_entity_name of a flow step (exact match, "
            "case-insensitive), assign that flow step's flow_id.\n"
            "- If an entity participates in a flow step as a TARGET, DEPENDENCY, or "
            "INTERMEDIARY (even if it is not the flow_entity_name of that step), assign "
            "the flow_id of the most specific (deepest) flow step it is part of.\n"
            "- If no confident match exists, use \"unassigned\".\n\n"
            "Return ONLY a flat JSON object — no markdown, no explanation:\n"
            "{\n"
            '  "ENTITY_NAME": "flow_id",\n'
            "  ...\n"
            "}\n\n"
            f"ENTITIES:\n{entities_payload}\n\n"
            f"FLOW STEPS:\n{flows_payload}"
        )

        try:
            response = self.llm.invoke(prompt)
            content = response.content if hasattr(response, "content") else str(response)
            content = content.strip()

            # Strip markdown fences if the model wraps its response
            if content.startswith("```"):
                lines = content.splitlines()
                # Drop first and last fence lines
                content = "\n".join(
                    line for line in lines
                    if not line.strip().startswith("```")
                ).strip()

            mapping: dict = json.loads(content)

            # Normalise keys to uppercase for case-insensitive matching
            mapping_upper = {k.strip().upper(): v for k, v in mapping.items()}

            for entity in entities:
                key = entity["entity_name"].strip().upper()
                entity["flow_id"] = mapping_upper.get(key, "unassigned")

            logger.debug(
                f"Chunk {chunk_id}: LLM linked "
                f"{sum(1 for e in entities if e['flow_id'] != 'unassigned')}/"
                f"{len(entities)} entities to flows"
            )

        except Exception as exc:
            logger.warning(
                f"Chunk {chunk_id}: entity-flow LLM linkage failed ({exc}). "
                f"Falling back to 'unassigned' for all entities."
            )
            for entity in entities:
                entity["flow_id"] = "unassigned"

        return entities
