"""
router.py

MiningRouter: The supervisor orchestrator that manages the entire mining
pipeline for a single SQL chunk. It replaces the old MinerDeepAgent +
5-subagent architecture with a cleaner, state-managed design.

Architecture:
  1. Python logic pre-loads context into RouterAgentState
  2. Context subagent analyzes chunk continuity + writes description
  3. Mining deep agent extracts entities/relationships/flows with full state access
  4. Output processor persists results via RegistryManager

The supervisor is deterministic Python logic (not an LLM) — the LLM
intelligence is focused on the context agent and mining agent where it
adds real value.
"""

import json
import sys
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from src.miner.models import MiningResult
from src.miner.miner_tools import RegistryManager
from src.miner.router_context_agent import RouterContextAgent
from src.miner.router_mining_agent import RouterMiningAgent
from src.miner.router_output import process_mining_output
from src.miner.router_state import RouterAgentState
from src.miner.router_tools import build_state_tools

logger.remove()
logger.add(
    sys.stderr,
    colorize=True,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
)


class MiningRouter:
    """
    Supervisor-based agentic router for the SQL mining pipeline.

    Manages agent state, coordinates subagents, and handles output processing
    for a single SQL chunk.

    Usage::

        from src.miner.router import MiningRouter
        from src.miner.miner_tools import RegistryManager
        from src.agents.llm import get_llm

        llm = get_llm()
        registry = RegistryManager("/path/to/workspace")
        router = MiningRouter(llm=llm, registry=registry, output_mode="pydantic")

        result = router.process_chunk("SELECT 1 FROM DUAL;", chunk_index=0)
    """

    def __init__(
        self,
        llm: Any,
        registry: RegistryManager,
        output_mode: str = "pydantic",
    ):
        """
        Initialize the MiningRouter.

        Args:
            llm: A LangChain BaseChatModel instance.
            registry: The RegistryManager for file I/O and tool generation.
            output_mode: Either "pydantic" (structured output) or "json"
                         (regex-parsed from text). Default: "pydantic".
        """
        self.llm = llm
        self.registry = registry
        self.output_mode = output_mode

        # Create the agent instances (reused across chunks)
        self._context_agent = RouterContextAgent(model=llm)
        self._mining_agent = RouterMiningAgent(model=llm, output_mode=output_mode)

        logger.info(
            f"MiningRouter initialised | output_mode={output_mode}"
        )

    def process_chunk(self, chunk_text: str, chunk_index: int) -> dict:
        """
        Run the full mining pipeline for a single SQL chunk.

        Steps:
          1. Create RouterAgentState with chunk_text and chunk_index
          2. Pre-load last 5 flows from registry
          3. Pre-load last 3 chunk descriptions from registry
          4. Run context subagent → analysis + description
          5. Build state tools for mining agent
          6. Run mining deep agent → entities/relationships/flows
          7. Process and persist output
          8. Return the result as a dict

        Args:
            chunk_text: The raw SQL code for this chunk.
            chunk_index: Zero-based index of the chunk.

        Returns:
            Dict with keys ``entities``, ``relationships``, ``flows``
            — each a list of dicts (persisted records).
        """
        chunk_id = str(chunk_index)
        logger.info(f"Router: processing chunk {chunk_id} ({len(chunk_text)} chars)")

        # ── Step 1: Create agent state ────────────────────────────────
        state = RouterAgentState(
            current_chunk=chunk_text,
            chunk_index=chunk_index,
        )

        # ── Step 2: Pre-load last 5 flows ────────────────────────────
        state.last_five_flows = self._load_last_flows(n=5)
        logger.debug(
            f"Router: loaded {len(state.last_five_flows)} previous flow(s)"
        )

        # ── Step 3: Pre-load last 3 chunk descriptions ───────────────
        state.last_three_chunk_descriptions = self._load_last_descriptions(n=3)
        logger.debug(
            f"Router: loaded {len(state.last_three_chunk_descriptions)} "
            f"previous description(s)"
        )

        logger.debug(f"Router: state ready — {state.summary()}")

        # ── Step 4: Run context subagent ──────────────────────────────
        logger.info("Router: Step 4 — running context subagent...")
        context_tools = self._build_context_tools(state)
        write_chunk_detail_tool = self.registry.get_write_chunk_detail_tool()

        context_result = self._context_agent.run(
            state_tools=context_tools,
            write_tool=write_chunk_detail_tool,
        )

        state.chunk_context_analysis = context_result.get("context_analysis", "")
        state.chunk_description = context_result.get("chunk_description", "")
        logger.info(
            f"Router: context analysis done — "
            f"{len(state.chunk_context_analysis)} chars analysis, "
            f"{len(state.chunk_description)} chars description"
        )

        # ── Step 5 + 6: Build tools and run mining agent ──────────────
        logger.info("Router: Step 5/6 — running mining deep agent...")
        mining_tools = build_state_tools(state, registry=self.registry)

        mining_result = self._mining_agent.run(tools=mining_tools)

        # Store the result in state
        state.mining_result = mining_result

        # ── Step 7: Process and persist output ────────────────────────
        logger.info("Router: Step 7 — processing and persisting output...")
        process_mining_output(
            result=mining_result,
            chunk_id=chunk_id,
            registry=self.registry,
            llm=self.llm,
        )

        # ── Step 8: Return result as dict ─────────────────────────────
        if isinstance(mining_result, MiningResult):
            result_dict = mining_result.to_dict()
        elif isinstance(mining_result, dict):
            result_dict = mining_result
        else:
            result_dict = {"entities": [], "relationships": [], "flows": []}

        logger.info(
            f"Router: chunk {chunk_id} complete — "
            f"{len(result_dict.get('entities', []))} entities, "
            f"{len(result_dict.get('relationships', []))} relationships, "
            f"{len(result_dict.get('flows', []))} flows"
        )

        return result_dict

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_last_flows(self, n: int = 5) -> list:
        """Load the last N flow records from flows.json."""
        return self.registry._read_last_n(self.registry.flows_path, n)

    def _load_last_descriptions(self, n: int = 3) -> list:
        """Load the last N chunk description texts from chunk_details/."""
        details_dir = Path(self.registry.chunk_details_dir)
        if not details_dir.exists():
            return []

        files = sorted(details_dir.glob("*.txt"))
        if not files:
            return []

        selected = files[-n:] if n > 0 else files
        texts = []
        for f in selected:
            with open(f, "r", encoding="utf-8") as fh:
                texts.append(fh.read())

        return texts

    def _build_context_tools(self, state: RouterAgentState) -> list:
        """
        Build a subset of state tools for the context subagent.

        The context agent only needs:
          - get_current_chunk
          - get_state_descriptions
          - get_state_flows
        """
        all_tools = build_state_tools(state, registry=None)
        # Filter to only the tools the context agent needs
        context_tool_names = {
            "get_current_chunk",
            "get_state_descriptions",
            "get_state_flows",
        }
        return [t for t in all_tools if t.name in context_tool_names]
