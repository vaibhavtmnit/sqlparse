"""
models.py — Data models for the Code Separator.

Defines:
  - EntityEntry:   A single entity in the registry (resolved or in-progress).
  - OpenEntity:    A mutable entity currently being accumulated across chunks.
  - CodeSegment:   One ordered code fragment from the LLM's chunk analysis.
  - ChunkAnalysis: The complete structured output from the LLM for one chunk.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Registry record (immutable once resolved)
# ---------------------------------------------------------------------------


@dataclass
class EntityEntry:
    """
    A single entity in the registry. Represents a fully resolved or
    in-progress code block extracted from the SQL script.

    The tree structure is encoded via ``parent_id``: each entry points to
    its parent (or None for top-level entities). Children can be found by
    querying the registry for entries whose ``parent_id`` matches this
    entry's ``entity_id``.
    """

    entity_id: str
    entity_name: str
    entity_type: str
    # PACKAGE_SPEC, PACKAGE_BODY, PROCEDURE, FUNCTION, TRIGGER, VIEW,
    # TABLE_OP, CTE_OP, ANONYMOUS_BLOCK, DYNAMIC_SQL, UNCLASSIFIED

    operation_type: Optional[str] = None
    # For TABLE_OP / CTE_OP: INSERT, MERGE, UPDATE, DELETE, CREATE,
    # TRUNCATE, SELECT, DROP, ALTER

    parent_id: Optional[str] = None
    nesting_level: int = 0
    chunk_ids: list[int] = field(default_factory=list)
    resolved_code: str = ""
    is_resolved: bool = False
    description: str = ""
    trigger_target: Optional[str] = None


# ---------------------------------------------------------------------------
# Mutable open entity (while accumulating code across chunks)
# ---------------------------------------------------------------------------


@dataclass
class OpenEntity:
    """
    Represents an entity that is currently being accumulated across one or
    more chunks. When the entity is fully resolved, it is converted to an
    ``EntityEntry`` and registered.

    ``code_parts`` collects the ordered code fragments that belong to THIS
    entity specifically (not to its children). When resolved, the entity's
    ``resolved_code`` is ``"\\n".join(code_parts)``.
    """

    entity_id: str
    entity_name: str
    entity_type: str
    operation_type: Optional[str] = None
    parent_id: Optional[str] = None
    nesting_level: int = 0
    chunk_ids: list[int] = field(default_factory=list)
    code_parts: list[str] = field(default_factory=list)
    trigger_target: Optional[str] = None

    def append_code(self, code: str, chunk_id: int, deduplicate_overlap: bool = False) -> None:
        """Append a code fragment and track the chunk it came from.
        If deduplicate_overlap is True, checks for line-based overlap between
        the end of existing code and the start of the new code.
        """
        if not code.strip():
            return

        if deduplicate_overlap and self.code_parts:
            existing_lines = self.build_resolved_code().splitlines()
            new_lines = code.splitlines()
            
            # Find the largest k where existing_lines[-k:] == new_lines[:k]
            max_k = min(len(existing_lines), len(new_lines))
            for k in range(max_k, 0, -1):
                if existing_lines[-k:] == new_lines[:k]:
                    # Stripping overlapping lines from new_lines
                    new_lines = new_lines[k:]
                    # Reconstruct the code string if we removed lines
                    code = "\n".join(new_lines)
                    # If this reconstructed a string but the original code had trailing/leading newlines,
                    # splitlines drops trailing newlines. This is usually fine for deduplication,
                    # but we can optionally add back a trailing newline if it was there and it was entirely removed.
                    break
            
            if not code.strip():
                # All new code was duplicated
                if chunk_id not in self.chunk_ids:
                    self.chunk_ids.append(chunk_id)
                return

        self.code_parts.append(code)
        if chunk_id not in self.chunk_ids:
            self.chunk_ids.append(chunk_id)

    def build_resolved_code(self) -> str:
        """Join all code parts into the final resolved code string."""
        return "\n".join(self.code_parts)

    def to_entry(self, is_resolved: bool = True) -> EntityEntry:
        """Convert to an immutable EntityEntry for the registry."""
        return EntityEntry(
            entity_id=self.entity_id,
            entity_name=self.entity_name,
            entity_type=self.entity_type,
            operation_type=self.operation_type,
            parent_id=self.parent_id,
            nesting_level=self.nesting_level,
            chunk_ids=list(self.chunk_ids),
            resolved_code=self.build_resolved_code(),
            is_resolved=is_resolved,
            description="",
            trigger_target=self.trigger_target,
        )


# ---------------------------------------------------------------------------
# LLM structured output models (Pydantic)
# ---------------------------------------------------------------------------


class CodeSegment(BaseModel):
    """
    One ordered code fragment found in a chunk, attributed to a specific
    entity. The LLM returns a list of these in the order they appear in
    the chunk text.

    **Key principle**: Each segment's ``code`` belongs to exactly ONE entity.
    Parent entities' segments contain only their OWN code (declarations,
    interstitial logic, END statements) — never the code of their children.
    Children have their own segments.
    """

    entity_name: str = Field(
        ...,
        description=(
            "Exact entity name from the SQL. For TABLE_OP/CTE_OP, use the "
            "TARGET table/CTE name. For DYNAMIC_SQL, create a descriptive "
            "name like 'DYN_CREATE_TABLE_X'. For ANONYMOUS_BLOCK, use "
            "'ANON_BLOCK_NNN'. For UNCLASSIFIED, use a descriptive name like 'ENV_CONFIG'."
        ),
    )
    entity_type: str = Field(
        ...,
        description=(
            "One of: PACKAGE_SPEC, PACKAGE_BODY, PROCEDURE, FUNCTION, "
            "TRIGGER, VIEW, TABLE_OP, CTE_OP, ANONYMOUS_BLOCK, DYNAMIC_SQL, UNCLASSIFIED"
        ),
    )
    operation_type: Optional[str] = Field(
        None,
        description=(
            "For TABLE_OP/CTE_OP only: INSERT, MERGE, UPDATE, DELETE, "
            "CREATE, TRUNCATE, SELECT, DROP, ALTER. Null for other types."
        ),
    )
    trigger_target: Optional[str] = Field(
        None,
        description="For TRIGGER only: the table name the trigger fires on.",
    )
    nesting_parent: Optional[str] = Field(
        None,
        description=(
            "The entity_name of the parent entity this is nested inside. "
            "Null for top-level entities. E.g., a PROCEDURE inside a "
            "PACKAGE_BODY would have nesting_parent = the package name."
        ),
    )
    code: str = Field(
        ...,
        description=(
            "The EXACT SQL code fragment for this segment, copied verbatim "
            "from the chunk. Do NOT paraphrase, summarize, or modify the "
            "code in any way. Include all whitespace and comments as-is."
        ),
    )
    is_entity_start: bool = Field(
        ...,
        description=(
            "True if this segment is the FIRST appearance of this entity "
            "across all chunks. False if continuing from a previous chunk."
        ),
    )
    is_entity_end: bool = Field(
        ...,
        description=(
            "True if this entity's code is FULLY COMPLETE in this segment "
            "(i.e., the closing END, semicolon, or final statement is here). "
            "False if more code is expected in the next chunk."
        ),
    )


class ChunkAnalysis(BaseModel):
    """
    Complete structured analysis of one chunk. Contains an ordered list of
    code segments covering ALL code in the chunk.

    **Critical invariant**: The concatenation of all segment ``code`` fields
    (joined with newlines) must reproduce the ENTIRE chunk text. No code
    may be omitted.
    """

    segments: list[CodeSegment] = Field(
        ...,
        description=(
            "Ordered list of code segments found in the chunk. Must cover "
            "ALL code in the chunk with no gaps or omissions. Order must "
            "match the order of appearance in the chunk text."
        ),
    )
    reasoning: str = Field(
        "",
        description=(
            "Brief explanation of how boundaries were identified, any "
            "ambiguities resolved, and any dynamic SQL or edge cases handled."
        ),
    )
