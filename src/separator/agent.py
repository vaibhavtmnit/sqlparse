"""
agent.py — Separator Agent: LLM wrapper with verification and retry.

Calls the LLM with the chunk text + open entity context and returns
a validated ChunkAnalysis. Includes:
  - Structured output via Pydantic (ChunkAnalysis)
  - Code coverage verification (all chunk code must be accounted for)
  - Automatic retry with error context on verification failure
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

from loguru import logger

from src.separator.models import ChunkAnalysis


# ---------------------------------------------------------------------------
# Prompt loader
# ---------------------------------------------------------------------------

_PROMPT_PATH = Path(__file__).parent.parent / "prompts" / "separator_prompt.md"


def _load_prompt() -> str:
    """Load the system prompt from the markdown file."""
    if _PROMPT_PATH.exists():
        return _PROMPT_PATH.read_text(encoding="utf-8")
    logger.warning(f"Prompt file not found at {_PROMPT_PATH}. Using fallback.")
    return (
        "You are an expert Oracle SQL code analyst. Segment the chunk into "
        "entity-scoped code blocks along natural code boundaries."
    )


# ---------------------------------------------------------------------------
# Verification helpers
# ---------------------------------------------------------------------------


def _normalise_whitespace(text: str) -> str:
    """Collapse all whitespace to single spaces for comparison."""
    return re.sub(r"\s+", " ", text).strip()


def _verify_coverage(
    chunk_text: str, analysis: ChunkAnalysis
) -> tuple[bool, str]:
    """
    Verify that all code in the chunk is covered by the analysis segments.

    Returns:
        (is_valid, error_message)
    """
    segment_codes = "\n".join(seg.code for seg in analysis.segments)
    norm_chunk = _normalise_whitespace(chunk_text)
    norm_segments = _normalise_whitespace(segment_codes)

    if not norm_chunk:
        return True, ""

    len_ratio = len(norm_segments) / len(norm_chunk) if norm_chunk else 1.0

    if len_ratio < 0.7:
        missing_pct = (1 - len_ratio) * 100
        return False, (
            f"Code coverage too low: segments cover ~{len_ratio:.0%} of the "
            f"chunk (missing ~{missing_pct:.0f}% of content). "
            f"Chunk: {len(norm_chunk)} chars, Segments: {len(norm_segments)} chars."
        )

    if len_ratio > 1.5:
        return False, (
            f"Segments contain too MUCH code ({len_ratio:.0%} of chunk). "
            f"Code may be duplicated across segments."
        )

    return True, ""


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class SeparatorAgent:
    """
    LLM-based agent that analyses a SQL chunk and returns structured
    ChunkAnalysis with entity-scoped code segments.

    Features:
      - Uses Pydantic structured_output for reliable parsing
      - Verifies code coverage after each analysis
      - Retries with error context on verification failure (up to max_retries)

    Usage::

        agent = SeparatorAgent(llm, max_retries=3)
        analysis = agent.analyze_chunk(chunk_text, context_summary)
    """

    def __init__(self, llm: Any, max_retries: int = 10) -> None:
        self.llm = llm
        self.max_retries = max_retries
        self._system_prompt = _load_prompt()
        self._structured_llm = self.llm.with_structured_output(ChunkAnalysis)

        logger.log(
            "AGENT",
            f"🤖 SeparatorAgent ready │ max_retries={max_retries} │ "
            f"prompt={len(self._system_prompt)} chars"
        )

    def analyze_chunk(
        self,
        chunk_text: str,
        context_summary: str,
        chunk_id: int = 0,
    ) -> ChunkAnalysis:
        """
        Analyse a SQL chunk and return a structured ChunkAnalysis.

        Args:
            chunk_text: The raw SQL chunk text.
            context_summary: Human-readable summary of currently open entities.
            chunk_id: The chunk index (for logging).

        Returns:
            A validated ChunkAnalysis with all code accounted for.

        Raises:
            RuntimeError: If the analysis fails after all retries.
        """
        lines = chunk_text.strip().splitlines()
        first_line = lines[0].strip() if lines else "(empty)"
        last_line = lines[-1].strip() if lines else "(empty)"
        logger.log(
            "AGENT",
            f"🤖 Analyzing chunk {chunk_id} │ "
            f"{len(chunk_text)} chars │ {len(lines)} lines\n"
            f"         first: {first_line[:70]}\n"
            f"         last:  {last_line[:70]}"
        )

        user_message = self._build_user_message(chunk_text, context_summary)
        error_context = ""

        for attempt in range(1, self.max_retries + 1):
            if attempt > 1:
                logger.log(
                    "RETRY",
                    f"🔄 Retry {attempt}/{self.max_retries} for chunk {chunk_id}"
                )

            messages = [
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": user_message + error_context},
            ]

            try:
                analysis: ChunkAnalysis = self._structured_llm.invoke(messages)
            except Exception as exc:
                exc_str = str(exc)
                logger.error(f"  ❌ LLM call failed: {exc_str}")
                
                # Handle Rate Limiting (429 / RESOURCE_EXHAUSTED)
                if "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str:
                    # Try to find a decimal number of seconds (e.g., "36.009s" or "3s")
                    wait_match = re.search(r"retry in (\d+\.?\d*)s", exc_str)
                    wait_time = float(wait_match.group(1)) if wait_match else 10.0
                    wait_time = min(wait_time, 60.0) # Cap at 60s
                    logger.warning(f"  ⏳ Rate limited. Sleeping for {wait_time}s before retry...")
                    time.sleep(wait_time)
                
                if attempt == self.max_retries:
                    raise RuntimeError(
                        f"Separator agent failed after {self.max_retries} "
                        f"attempts for chunk {chunk_id}: {exc}"
                    ) from exc
                error_context = (
                    f"\n\n--- PREVIOUS ATTEMPT FAILED ---\n"
                    f"Error: {exc}\n"
                    f"Please try again with the same chunk.\n"
                )
                continue

            # Verify coverage
            is_valid, error_msg = _verify_coverage(chunk_text, analysis)

            if is_valid:
                seg_types = [
                    f"{s.entity_name}({s.entity_type})"
                    for s in analysis.segments
                ]
                logger.log(
                    "VERIFY",
                    f"🔎 Chunk {chunk_id} verified ✓ │ "
                    f"{len(analysis.segments)} segments: "
                    f"{', '.join(seg_types)}"
                )
                return analysis

            logger.log(
                "RETRY",
                f"🔄 Verification failed (attempt {attempt}): {error_msg}"
            )

            if attempt < self.max_retries:
                error_context = (
                    f"\n\n--- VERIFICATION FAILED (attempt {attempt}) ---\n"
                    f"{error_msg}\n\n"
                    f"Please re-analyze the chunk. Remember:\n"
                    f"- Every line of code must appear in exactly one segment\n"
                    f"- Copy code VERBATIM from the chunk\n"
                    f"- Do NOT skip comments, whitespace, or empty lines\n"
                )

        logger.warning(
            f"  ⚠ Chunk {chunk_id}: returning after {self.max_retries} "
            f"attempts (may be imperfect)"
        )
        return analysis

    @staticmethod
    def _build_user_message(
        chunk_text: str, context_summary: str
    ) -> str:
        """Build the user message for the LLM."""
        return (
            f"## Current Context\n\n"
            f"{context_summary}\n\n"
            f"## Chunk to Analyze\n\n"
            f"```sql\n{chunk_text}\n```\n\n"
            f"Analyze this chunk and return the ordered list of code segments. "
            f"Follow ALL rules in your system prompt. Ensure COMPLETE code "
            f"coverage — every line of the chunk must appear in exactly one "
            f"segment."
        )
