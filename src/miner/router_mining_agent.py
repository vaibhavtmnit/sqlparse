"""
router_mining_agent.py

Mining deep agent for the MiningRouter. This agent:
  1. Uses agent state tools to read chunk, context, flows, descriptions
  2. Uses cross-chunk lookup tools for entities/relationships
  3. Uses scratch note tools for intermediate reasoning
  4. Returns mining output as either Pydantic structured_output or JSON text

Supports two output modes:
  - "pydantic": Uses with_structured_output(MiningResult) for type-safe output
  - "json":     Parses JSON arrays from the agent's text response (legacy mode)
"""

import json
import re
import sys
from pathlib import Path
from typing import Any, List, Optional

from deepagents import create_deep_agent
from loguru import logger

from src.miner.models import MiningResult

logger.remove()
logger.add(
    sys.stderr,
    colorize=True,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
)


# ---------------------------------------------------------------------------
# Prompt loader
# ---------------------------------------------------------------------------

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "router_miner_prompt.md"


def _load_prompt() -> str:
    """Load the system prompt from the markdown file."""
    if _PROMPT_PATH.exists():
        return _PROMPT_PATH.read_text(encoding="utf-8")
    logger.warning(f"Prompt file not found at {_PROMPT_PATH}. Using fallback.")
    return (
        "You are an expert Oracle SQL code mining agent. "
        "Extract entities, relationships, and flows from the provided SQL code chunk."
    )


# ---------------------------------------------------------------------------
# JSON fallback parser (same logic as the old _parse_agent_result)
# ---------------------------------------------------------------------------


def _parse_json_from_text(content: str) -> dict:
    """
    Extract entities, relationships, and flows JSON arrays from agent text.

    Tries labelled extraction first (e.g. **Entities** ```json [...] ```),
    then falls back to positional extraction of all JSON arrays.
    """
    empty = {"entities": [], "relationships": [], "flows": []}

    if not content or not content.strip():
        return empty

    def _extract_labelled(label: str, text: str):
        pattern = (
            rf"(?i)(?:\*{{1,2}}{label}\*{{1,2}}|#{{1,3}}\s*{label})"
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
        results = []
        for m in re.finditer(r"(\[\s*\{[\s\S]*?\}\s*\])", text):
            try:
                results.append(json.loads(m.group(1)))
            except json.JSONDecodeError:
                pass
        return results

    entities = _extract_labelled("entities", content)
    relationships = _extract_labelled("relationships", content)
    flows = _extract_labelled("flows", content)

    if entities is None and relationships is None and flows is None:
        arrays = _extract_all_arrays(content)
        entities = arrays[0] if len(arrays) > 0 else []
        relationships = arrays[1] if len(arrays) > 1 else []
        flows = arrays[2] if len(arrays) > 2 else []
    else:
        entities = entities or []
        relationships = relationships or []
        flows = flows or []

    return {
        "entities": entities,
        "relationships": relationships,
        "flows": flows,
    }


# ---------------------------------------------------------------------------
# Mining agent
# ---------------------------------------------------------------------------


class RouterMiningAgent:
    """
    Runs the entity/relationship/flow extraction step.

    Supports two output modes:
      - ``pydantic``: The agent is given ``MiningResult`` as structured_output,
        and the LLM returns a validated Pydantic model directly.
      - ``json``: The agent produces text containing JSON arrays, which are
        parsed using regex (legacy mode, same as the old MinerDeepAgent).
    """

    def __init__(self, model: Any, output_mode: str = "pydantic"):
        """
        Args:
            model: A LangChain BaseChatModel instance.
            output_mode: Either "pydantic" or "json".
        """
        self.model = model
        self.output_mode = output_mode
        self._prompt = _load_prompt()

    def run(self, tools: list) -> Any:
        """
        Execute the mining agent with the given tools.

        Args:
            tools: List of LangChain tools (state tools + cross-chunk tools).

        Returns:
            - If output_mode == "pydantic": a ``MiningResult`` instance
            - If output_mode == "json": a dict with keys entities, relationships, flows
        """
        if self.output_mode == "pydantic":
            return self._run_pydantic(tools)
        else:
            return self._run_json(tools)

    def _run_pydantic(self, tools: list) -> MiningResult:
        """Run the agent and return a MiningResult via structured_output."""

        agent = create_deep_agent(
            model=self.model,
            tools=tools,
            subagents=[],
            system_prompt=self._prompt,
            middleware=[],
            response_format=MiningResult,
        )

        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Mine all entities, relationships, and flows from the current "
                        "SQL chunk. Follow the mining process in your system prompt exactly. "
                        "Start by loading context, then perform cross-chunk lookups, "
                        "then mine entities, relationships, and flows."
                    ),
                }
            ]
        }

        logger.info("RouterMiningAgent: invoking in PYDANTIC mode...")
        result = agent.invoke(payload)

        # With response_format, the structured response is in the result
        structured = result.get("structured_response") if isinstance(result, dict) else None

        if structured and isinstance(structured, MiningResult):
            logger.info(
                f"RouterMiningAgent: structured output received — "
                f"{len(structured.entities)} entities, "
                f"{len(structured.relationships)} relationships, "
                f"{len(structured.flows)} flows"
            )
            return structured

        # Fallback: try to parse from messages if structured_response is missing
        logger.warning(
            "RouterMiningAgent: structured_response not available, "
            "falling back to JSON text parsing."
        )
        return self._fallback_parse(result)

    def _run_json(self, tools: list) -> dict:
        """Run the agent and parse JSON from text output."""

        # Append instructions for JSON output format to the prompt
        json_prompt = self._prompt + (
            "\n\n## OUTPUT FORMAT\n\n"
            "Return your output using these exact markdown headers:\n\n"
            "**Entities**\n```json\n[...]\n```\n\n"
            "**Relationships**\n```json\n[...]\n```\n\n"
            "**Flows**\n```json\n[...]\n```\n"
        )

        agent = create_deep_agent(
            model=self.model,
            tools=tools,
            subagents=[],
            system_prompt=json_prompt,
            middleware=[],
        )

        payload = {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Mine all entities, relationships, and flows from the current "
                        "SQL chunk. Follow the mining process in your system prompt exactly. "
                        "Return your results as JSON arrays under the specified headers."
                    ),
                }
            ]
        }

        logger.info("RouterMiningAgent: invoking in JSON mode...")
        result = agent.invoke(payload)

        return self._fallback_parse(result)

    @staticmethod
    def _fallback_parse(raw_result: Any) -> dict:
        """Parse JSON arrays from the agent's final text message."""
        messages = (
            raw_result.get("messages", []) if isinstance(raw_result, dict) else []
        )
        content = ""
        for msg in reversed(messages):
            c = getattr(msg, "content", None) or (
                msg.get("content") if isinstance(msg, dict) else None
            )
            if c and isinstance(c, str) and c.strip():
                content = c
                break

        parsed = _parse_json_from_text(content)
        logger.info(
            f"RouterMiningAgent: fallback parsed — "
            f"{len(parsed['entities'])} entities, "
            f"{len(parsed['relationships'])} relationships, "
            f"{len(parsed['flows'])} flows"
        )
        return parsed
