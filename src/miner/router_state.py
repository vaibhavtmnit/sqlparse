"""
router_state.py

RouterAgentState: A mutable state container that the MiningRouter populates
before agent invocations. Agents interact with this state through dedicated
LangChain tools (see router_tools.py).

Design rationale:
  - The router pre-loads context (flows, descriptions) BEFORE any LLM call,
    so agents don't waste tokens on I/O.
  - Agents can read state freely and write scratch notes.
  - The final mining result (Pydantic or dict) is stored here for the
    output processor to consume.
"""

from dataclasses import dataclass, field
from typing import Any, Optional

from src.miner.models import MiningResult


@dataclass
class RouterAgentState:
    """
    Mutable state container shared across all agents in a single chunk's
    processing lifecycle.

    Attributes:
        current_chunk:
            The raw SQL code for the chunk being processed.
        chunk_index:
            Zero-based index of the current chunk in the overall SQL script.

        last_five_flows:
            The most recent 5 flow records from ``flows.json``, loaded by the
            router before processing begins.
        last_three_chunk_descriptions:
            The most recent 3 chunk description texts, loaded from
            ``chunk_details/`` by the router.

        chunk_context_analysis:
            Set by the context subagent — describes how this chunk relates
            to previous chunks.
        chunk_description:
            Set by the context subagent — the rich description written for
            this chunk.

        agent_notes:
            Scratch space for the mining deep agent to keep temporary working
            notes during complex reasoning passes.

        mining_result:
            The structured mining output, set by the mining deep agent.
            Can be a ``MiningResult`` (Pydantic mode) or a plain dict
            (JSON mode).
    """

    # ── Core data ──────────────────────────────────────────────────────────
    current_chunk: str = ""
    chunk_index: int = 0

    # ── Pre-loaded context ─────────────────────────────────────────────────
    last_five_flows: list[dict] = field(default_factory=list)
    last_three_chunk_descriptions: list[str] = field(default_factory=list)

    # ── Set by context subagent ────────────────────────────────────────────
    chunk_context_analysis: str = ""
    chunk_description: str = ""

    # ── Scratch space ──────────────────────────────────────────────────────
    agent_notes: list[str] = field(default_factory=list)

    # ── Output ─────────────────────────────────────────────────────────────
    mining_result: Optional[Any] = None  # MiningResult or dict

    # ── Convenience helpers ────────────────────────────────────────────────

    def add_note(self, note: str) -> None:
        """Append a temporary note to the scratch space."""
        self.agent_notes.append(note)

    def get_notes(self) -> list[str]:
        """Return all scratch notes."""
        return list(self.agent_notes)

    def clear_notes(self) -> None:
        """Clear all scratch notes."""
        self.agent_notes.clear()

    def summary(self) -> str:
        """Return a compact summary for logging."""
        return (
            f"RouterAgentState(chunk_index={self.chunk_index}, "
            f"chunk_len={len(self.current_chunk)}, "
            f"flows_loaded={len(self.last_five_flows)}, "
            f"descriptions_loaded={len(self.last_three_chunk_descriptions)}, "
            f"notes={len(self.agent_notes)}, "
            f"has_result={self.mining_result is not None})"
        )
