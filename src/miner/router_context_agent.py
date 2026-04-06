"""
router_context_agent.py

Context subagent for the MiningRouter. This agent:
  1. Reads the current chunk + previous chunk descriptions from agent state
  2. Analyzes continuity — how the new chunk relates to previous chunks
  3. Writes a rich description summarising the connection
  4. Stores the analysis and description into agent state
  5. Calls write_chunk_detail to persist the description to disk

This replaces and merges the old ChunkContextSubAgent and
ChunkDescriptionWriterSubAgent into a single, focused agent step.
"""

import sys
from pathlib import Path
from typing import Any, List, Optional

from deepagents import create_deep_agent
from langchain.agents.middleware import wrap_tool_call
from loguru import logger

logger.remove()
logger.add(
    sys.stderr,
    colorize=True,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
)


# ---------------------------------------------------------------------------
# System prompt for the context + description agent
# ---------------------------------------------------------------------------

_CONTEXT_AGENT_PROMPT = """\
You are a SQL code context analyst and documentation specialist. Your job is
to understand the current SQL chunk in relation to previous chunks and produce
a rich contextual description.

## PROCESS

1. Use the **get_current_chunk** tool to read the SQL code being processed.
2. Use the **get_state_descriptions** tool to read the last 3 chunk descriptions
   (if they exist — if none exist, note that and analyze the current chunk alone).
3. Use the **get_state_flows** tool to read the last 5 flow steps for structural
   context (optional but helpful for understanding the execution hierarchy).

4. Perform your analysis and write TWO outputs:

   **A. CONTEXT ANALYSIS** (100-200 words):
   - What major constructs appear in the current chunk?
   - How does this chunk continue from or diverge from previous chunks?
   - Key entities that bridge between this chunk and previous chunks.
   - Whether the chunk is a continuation, a new section, or standalone.

   **B. CHUNK DESCRIPTION** (200-350 words in clear prose):
   - MAJOR OPERATIONS: What operations are being performed?
   - KEY ACTORS: What packages, procedures, functions, or triggers execute them?
   - KEY OBJECTS: What tables, views, CTEs, sequences are acted upon?
   - OVERALL PURPOSE: Business/technical purpose of this chunk.
   - CONTINUITY: How does this connect to what came before?

5. Use the **write_chunk_detail** tool to save the CHUNK DESCRIPTION (part B only).

6. Return your FULL response in this exact format:

   === CONTEXT ANALYSIS ===
   <your context analysis text here>

   === CHUNK DESCRIPTION ===
   <your chunk description text here>

## IMPORTANT RULES

- If prior chunk details do not exist (first chunk), clearly say so and analyze
  only the current chunk.
- Write in clear, concise prose (not bullet points) for the description.
- Do NOT include raw SQL code in the description.
- Keep the context analysis under 200 words and the description under 350 words.
"""


# ---------------------------------------------------------------------------
# Context agent runner
# ---------------------------------------------------------------------------


class RouterContextAgent:
    """
    Runs the context analysis + description writing step.

    This agent receives state tools (for reading chunk/descriptions) and
    the write_chunk_detail tool (for persisting), then invokes a deep agent
    to produce the analysis and description.
    """

    def __init__(self, model: Any):
        """
        Args:
            model: A LangChain BaseChatModel instance.
        """
        self.model = model

    def run(self, state_tools: list, write_tool: Any) -> dict:
        """
        Execute the context agent.

        Args:
            state_tools: List of LangChain tools for reading state
                         (get_current_chunk, get_state_descriptions,
                          get_state_flows).
            write_tool: The write_chunk_detail tool from RegistryManager.

        Returns:
            Dict with keys:
              - ``context_analysis``: str — the continuity analysis
              - ``chunk_description``: str — the rich description
        """
        all_tools = list(state_tools) + [write_tool]

        agent = create_deep_agent(
            model=self.model,
            tools=all_tools,
            subagents=[],
            system_prompt=_CONTEXT_AGENT_PROMPT,
            middleware=[],
        )

        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Analyze the current SQL chunk and write a contextual description. "
                        "Follow the process in your system prompt exactly."
                    ),
                }
            ]
        }

        logger.info("RouterContextAgent: invoking deep agent for context analysis...")
        result = agent.invoke(payload)

        # Extract the final message content
        messages = result.get("messages", []) if isinstance(result, dict) else []
        content = ""
        for msg in reversed(messages):
            c = getattr(msg, "content", None) or (
                msg.get("content") if isinstance(msg, dict) else None
            )
            if c and isinstance(c, str) and c.strip():
                content = c
                break

        # Parse the two sections from the response
        context_analysis = ""
        chunk_description = ""

        if "=== CONTEXT ANALYSIS ===" in content:
            parts = content.split("=== CONTEXT ANALYSIS ===", 1)
            if len(parts) > 1:
                remainder = parts[1]
                if "=== CHUNK DESCRIPTION ===" in remainder:
                    ctx_part, desc_part = remainder.split(
                        "=== CHUNK DESCRIPTION ===", 1
                    )
                    context_analysis = ctx_part.strip()
                    chunk_description = desc_part.strip()
                else:
                    context_analysis = remainder.strip()
        else:
            # Fallback: treat the whole content as context analysis
            context_analysis = content.strip()

        logger.info(
            f"RouterContextAgent: analysis={len(context_analysis)} chars, "
            f"description={len(chunk_description)} chars"
        )

        return {
            "context_analysis": context_analysis,
            "chunk_description": chunk_description,
        }
