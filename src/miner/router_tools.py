"""
router_tools.py

LangChain tools that give the mining deep agent read/write access to the
RouterAgentState. These tools are created as closures over a shared state
instance, so all agents in a single chunk's lifecycle share the same data.

Also includes tools for cross-chunk entity/relationship lookups via the
RegistryManager.
"""

import json
import sys
from typing import Optional

from langchain.tools import tool
from loguru import logger

logger.remove()
logger.add(
    sys.stderr,
    colorize=True,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
)


def build_state_tools(state, registry=None):
    """
    Build all LangChain tools that give agents access to the RouterAgentState.

    Args:
        state: A RouterAgentState instance (shared mutable reference).
        registry: Optional RegistryManager for cross-chunk entity/relationship lookups.

    Returns:
        A list of LangChain tool callables.
    """
    tools = []

    # -----------------------------------------------------------------
    # State read tools
    # -----------------------------------------------------------------

    @tool
    def get_current_chunk() -> str:
        """
        Read the current SQL chunk from the router's agent state.

        Returns:
            The raw SQL code string for the chunk being processed.
        """
        logger.debug("Tool: get_current_chunk called")
        return state.current_chunk

    tools.append(get_current_chunk)

    @tool
    def get_chunk_context() -> str:
        """
        Read the chunk context analysis from the router's agent state.
        This describes how the current chunk relates to previous chunks.

        Returns:
            The context analysis text, or a message if not yet available.
        """
        logger.debug("Tool: get_chunk_context called")
        if not state.chunk_context_analysis:
            return "No context analysis available yet for this chunk."
        return state.chunk_context_analysis

    tools.append(get_chunk_context)

    @tool
    def get_state_flows() -> str:
        """
        Read the last 5 flows from the router's agent state.
        These were pre-loaded from flows.json before processing began.

        Returns:
            JSON string of up to 5 most recent flow records, or a message
            if none are available.
        """
        logger.debug("Tool: get_state_flows called")
        if not state.last_five_flows:
            return "No previous flows available."
        return json.dumps(state.last_five_flows, indent=2)

    tools.append(get_state_flows)

    @tool
    def get_state_descriptions() -> str:
        """
        Read the last 3 chunk descriptions from the router's agent state.
        These were pre-loaded from chunk_details/ before processing began.

        Returns:
            Combined text of the last 3 chunk descriptions separated by
            boundaries, or a message if none are available.
        """
        logger.debug("Tool: get_state_descriptions called")
        if not state.last_three_chunk_descriptions:
            return "No previous chunk descriptions available. This may be the first chunk."
        separator = "\n----- Chunk boundary -------\n"
        return separator.join(state.last_three_chunk_descriptions)

    tools.append(get_state_descriptions)

    # -----------------------------------------------------------------
    # Scratch notes tools
    # -----------------------------------------------------------------

    @tool
    def add_note(note: str) -> str:
        """
        Add a temporary working note to the agent's scratch space.
        Use this to keep track of intermediate observations, entity
        candidates, or reasoning during complex mining passes.

        Args:
            note: The note text to save.

        Returns:
            Confirmation message.
        """
        state.add_note(note)
        logger.debug(f"Tool: add_note — {len(state.agent_notes)} notes total")
        return f"Note saved. You now have {len(state.agent_notes)} note(s)."

    tools.append(add_note)

    @tool
    def get_notes() -> str:
        """
        Read all temporary working notes from the scratch space.

        Returns:
            All notes as a numbered list, or a message if no notes exist.
        """
        logger.debug("Tool: get_notes called")
        notes = state.get_notes()
        if not notes:
            return "No notes saved yet."
        return "\n".join(f"{i+1}. {n}" for i, n in enumerate(notes))

    tools.append(get_notes)

    # -----------------------------------------------------------------
    # Cross-chunk entity/relationship lookup tools (need registry)
    # -----------------------------------------------------------------

    if registry is not None:

        @tool
        def get_last_n_entities(n: int = 20) -> str:
            """
            Read the last N entity records from entities.json.
            Use this to check what entities have already been mined in
            previous chunks so you can create cross-chunk relationships.

            Args:
                n: Number of recent entities to retrieve (default: 20).

            Returns:
                JSON string of the last N entity records, or a message
                if none are available.
            """
            entries = registry._read_last_n(registry.entities_path, n)
            if not entries:
                return "No previously mined entities found."
            logger.debug(f"Tool: get_last_n_entities — returned {len(entries)} entries")
            return json.dumps(entries, indent=2)

        tools.append(get_last_n_entities)

        @tool
        def get_last_n_relationships(n: int = 20) -> str:
            """
            Read the last N relationship records from relationships.json.
            Use this to check what relationships have already been mined
            in previous chunks to avoid duplicates and maintain continuity.

            Args:
                n: Number of recent relationships to retrieve (default: 20).

            Returns:
                JSON string of the last N relationship records, or a message
                if none are available.
            """
            entries = registry._read_last_n(registry.relationships_path, n)
            if not entries:
                return "No previously mined relationships found."
            logger.debug(f"Tool: get_last_n_relationships — returned {len(entries)} entries")
            return json.dumps(entries, indent=2)

        tools.append(get_last_n_relationships)

    return tools


def build_state_tool_map(state, registry=None) -> dict:
    """
    Build state tools and return them as a name→tool dict.

    This is useful for selective injection into subagents that only
    need certain tools from the state.

    Args:
        state: A RouterAgentState instance.
        registry: Optional RegistryManager for cross-chunk lookups.

    Returns:
        Dict mapping tool.name to tool callable.
    """
    tools = build_state_tools(state, registry)
    return {t.name: t for t in tools}
