"""
miner_deepagent.py

MinerDeepAgent: A LangChain Deep Agent wrapper for Oracle SQL code mining.

Uses deepagents.create_deep_agent under the hood. Includes colored loguru
middleware that logs tool calls, subagent invocations, and agent actions
without flooding the console with full message bodies.

References:
  - https://docs.langchain.com/oss/python/deepagents/overview
  - https://github.com/langchain-ai/deepagents
"""

import os
import sys
from pathlib import Path
from typing import Any, Callable, List, Optional, Sequence

from deepagents import create_deep_agent
from langchain.agents.middleware import wrap_tool_call
from loguru import logger
from src.agents.llm import get_llm

import sys
logger.remove()
logger.add(sys.stderr, colorize=True, format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>")

logger.level("Agent Action",no=15,color="<light-blue>",icon="🛠️")
logger.level("Agent Setup",no=18,color="<light-red>",icon="💾")

# ---------------------------------------------------------------------------
# Loguru setup: configure colored console + file sink
# ---------------------------------------------------------------------------

def _configure_logger(log_dir: str) -> None:
    """
    Configure loguru with:
      - A colorized console sink (stderr) with custom format.
      - A plain-text file sink in log_dir/miner_agent.log.
    """
    logger.remove()  # Remove default handler

    # Console: colorized, concise format
    console_format = (
        "<green>{time:HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>[MinerAgent]</cyan> "
        "{message}"
    )
    logger.add(
        sys.stderr,
        format=console_format,
        colorize=True,
        level="DEBUG",
    )

    # File: plain text, full timestamp
    log_path = os.path.join(log_dir, "miner_agent.log")
    os.makedirs(log_dir, exist_ok=True)
    logger.add(
        log_path,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | [MinerAgent] {message}",
        level="DEBUG",
        rotation="50 MB",
        retention="10 days",
        encoding="utf-8",
    )
    logger.info(f"Logger initialized. Log file: {log_path}")


def _truncate_message(text: str, head_words: int = 10, tail_words: int = 20) -> str:
    """
    Return the first `head_words` words + '...' + last `tail_words` words of text.
    If the text is short enough, return it as-is.
    """
    if not text:
        return ""
    words = text.split()
    total = len(words)
    if total <= head_words + tail_words:
        return text
    head = " ".join(words[:head_words])
    tail = " ".join(words[-tail_words:])
    return f"{head} ... {tail}"


def _build_logging_middleware() -> Callable:
    """
    Build a wrap_tool_call middleware that logs:
      - Which tool was called (yellow)
      - The tool's input arguments (truncated)
      - Completion of the tool call (green)
      - Any errors (red)
    """

    @wrap_tool_call
    def _log_tool_calls(request: Any, handler: Callable) -> Any:
        """Intercept every tool call and log it via loguru."""
        # The request is a ToolMessage instance — extract the tool_call
        # object first, then pull name and args from it.
        tool_call = getattr(request, "tool_call", None)
        if tool_call is not None:
            tool_name = getattr(tool_call, "name", None) or (
                tool_call.get("name") if isinstance(tool_call, dict) else None
            ) or "Common Tool"
            raw_args = getattr(tool_call, "args", None) or (
                tool_call.get("args") if isinstance(tool_call, dict) else None
            ) or {}
        else:
            tool_name = getattr(request, "name", "Common Tool")
            raw_args = getattr(request, "args", {})

        # Ensure raw_args is a dict
        if not isinstance(raw_args, dict):
            raw_args = {}

        # Summarize arguments for logging (truncate long strings)
        args_summary: dict = {}
        for k, v in raw_args.items():
            v_str = str(v)
            args_summary[k] = _truncate_message(v_str, head_words=10, tail_words=10)

        logger.opt(colors=True).info(
            f"<yellow>TOOL CALL</yellow> → <bold>{tool_name}</bold> | args: {args_summary}"
        )

        try:
            result = handler(request)
            result_str = str(result) if result is not None else ""
            result_preview = _truncate_message(result_str, head_words=5, tail_words=10)
            logger.opt(colors=True).success(
                f"<green>TOOL DONE</green> ← <bold>{tool_name}</bold> | result: {result_preview}"
            )
            return result
        except Exception as exc:
            logger.opt(colors=True).error(
                f"<red>TOOL ERROR</red> ← <bold>{tool_name}</bold> | {exc}"
            )
            raise

    return _log_tool_calls


# ---------------------------------------------------------------------------
# MinerDeepAgent
# ---------------------------------------------------------------------------


class MinerDeepAgent:
    """
    Orchestrates SQL mining using a deepagents DeepAgent.

    The agent reads its system prompt from prompts/miner_prompt.md (relative
    to the project root, resolved automatically). Middleware intercepts every
    tool call and logs it with colored loguru output and to a log file.

    Usage::

        from src.miner.miner_deepagent import MinerDeepAgent
        from src.miner.miner_tools import RegistryManager
        from src.miner.miner_subagents import build_default_subagents

        registry = RegistryManager("/path/to/workspace")
        tools = registry.get_all_tools()

        tool_map = {
            "read_current_chunk": registry.get_read_current_chunk_tool(),
            "get_recent_chunk_details": registry.get_recent_chunk_details_tool(),
            "write_chunk_detail": registry.get_write_chunk_detail_tool(),
        }
        subagents = build_default_subagents(tool_map)

        miner = MinerDeepAgent(
            model="google_genai:gemini-2.5-flash",
            tools=tools,
            subagents=subagents,
            log_dir="/path/to/workspace/mining/logs",
        )

        result = miner.invoke("Start mining the current chunk.")
    """

    #: Default location of the prompt file relative to this module's package root.
    _PROMPT_RELATIVE_PATH = Path(__file__).parent.parent / "prompts" / "miner_prompt.md"

    def __init__(
        self,
        model: Any = get_llm(),
        tools: Optional[List[Callable]] = None,
        subagents: Optional[List[Any]] = None,
        log_dir: Optional[str] = None,
        prompt_path: Optional[str] = None,
        output_mode: str = "json",
    ):
        """
        Initialize the MinerDeepAgent.

        Args:
            model: A LangChain BaseChatModel instance or a model string
                   (e.g. 'google_genai:gemini-2.5-flash').
            tools: List of LangChain tool callables to give the main agent.
            subagents: List of subagent dicts (from SubAgentConfig.to_subagent_dict())
                       or CompiledSubAgent instances.
            log_dir: Directory where miner_agent.log will be written.
                     Defaults to './mining/logs'.
            prompt_path: Explicit path to the system prompt .md file.
                         Defaults to src/prompts/miner_prompt.md.
            output_mode: Either "json" (default, legacy regex parsing) or
                         "pydantic" (structured output via MiningResult).
        """
        from src.miner.models import MiningResult

        self.output_mode = output_mode

        # Resolve log directory
        self._log_dir = log_dir or os.path.join(os.getcwd(), "mining", "logs")
        _configure_logger(self._log_dir)

        # Load system prompt
        resolved_prompt_path = Path(prompt_path) if prompt_path else self._PROMPT_RELATIVE_PATH
        if resolved_prompt_path.exists():
            system_prompt = resolved_prompt_path.read_text(encoding="utf-8")
            logger.info(f"Loaded system prompt from {resolved_prompt_path}")
        else:
            system_prompt = (
                "You are an expert Oracle SQL code mining agent. "
                "Extract entities, relationships, and flows from the provided SQL code chunks."
            )
            logger.warning(
                f"Prompt file not found at {resolved_prompt_path}. Using fallback prompt."
            )

        # Build middleware
        logging_mw = _build_logging_middleware()

        logger.info(
            f"Creating MinerDeepAgent | model={model} | "
            f"tools={len(tools or [])} | subagents={len(subagents or [])} | "
            f"output_mode={output_mode}"
        )

        # Build create_deep_agent kwargs — add response_format for pydantic mode
        agent_kwargs = dict(
            model=model,
            tools=list(tools or []),
            subagents=list(subagents or []),
            system_prompt=system_prompt,
            middleware=[logging_mw],
        )
        if output_mode == "pydantic":
            agent_kwargs["response_format"] = MiningResult

        # Create the deep agent
        self._agent = create_deep_agent(**agent_kwargs)

        logger.success("MinerDeepAgent created successfully.")

    def invoke(self, message: str, **kwargs: Any) -> Any:
        """
        Invoke the miner agent with a user message.

        Args:
            message: The task/user message to send to the agent.
            **kwargs: Additional keyword arguments forwarded to the
                      underlying LangGraph agent's .invoke().

        Returns:
            The agent result dict (contains 'messages' and optionally
            'structured_response').
        """
        logger.opt(colors=True).info(
            f"<magenta>INVOKE</magenta> | message preview: "
            f"{_truncate_message(message, head_words=10, tail_words=20)}"
        )

        payload = {"messages": [{"role": "user", "content": message}]}
        result = self._agent.invoke(payload, **kwargs)

        # Log final output preview
        final_msgs = result.get("messages", [])
        if final_msgs:
            last = final_msgs[-1]
            content = getattr(last, "content", str(last))
            logger.opt(colors=True).info(
                f"<cyan>RESULT</cyan> | preview: "
                f"{_truncate_message(str(content), head_words=10, tail_words=20)}"
            )

        return result

    def stream(self, message: str, **kwargs: Any):
        """
        Stream the agent's output for the given message.

        Args:
            message: The task/user message to send to the agent.
            **kwargs: Additional keyword arguments forwarded to the
                      underlying LangGraph agent's .stream().

        Yields:
            Streamed chunks from the agent.
        """
        logger.opt(colors=True).info(
            f"<magenta>STREAM</magenta> | message preview: "
            f"{_truncate_message(message, head_words=10, tail_words=20)}"
        )

        payload = {"messages": [{"role": "user", "content": message}]}
        for chunk in self._agent.stream(payload, **kwargs):
            yield chunk

    @property
    def graph(self):
        """Access the underlying compiled LangGraph for advanced usage."""
        return self._agent
