"""
state.py — Separator State for tracking open entities.

Maintains a dict of currently open (in-progress) entities that are being
accumulated across chunks. Provides methods to open, close, and find
open entities, plus a context summary for the LLM.
"""

from __future__ import annotations

from typing import Optional

from src.separator.models import OpenEntity


class SeparatorState:
    """
    Tracks all currently open (incomplete) entities.

    Open entities are stored in insertion order. When a child entity starts,
    both the parent and child are open simultaneously. When the child
    closes, it is removed; the parent remains open.

    The state provides a ``get_context_summary()`` method that produces
    a human-readable summary of the current nesting context for the LLM.
    """

    def __init__(self) -> None:
        self._open: dict[str, OpenEntity] = {}  # entity_id → OpenEntity

    # ------------------------------------------------------------------
    # Open / close
    # ------------------------------------------------------------------

    def open_entity(self, entity: OpenEntity) -> None:
        """Start tracking a new open entity."""
        self._open[entity.entity_id] = entity

    def close_entity(self, entity_id: str) -> Optional[OpenEntity]:
        """
        Remove and return an open entity (it is being resolved).

        Returns None if the entity_id is not found.
        """
        return self._open.pop(entity_id, None)

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def find_open(
        self,
        entity_name: str,
        entity_type: Optional[str] = None,
        nesting_parent: Optional[str] = None,
    ) -> Optional[OpenEntity]:
        """
        Find the most recently opened entity matching the given criteria.

        Searches in reverse insertion order (most recent first) so that
        nested entities are found before their parents when names collide.

        Args:
            entity_name: Entity name to match (case-insensitive).
            entity_type: Optional type filter.
            nesting_parent: Optional parent name filter.

        Returns:
            The matching OpenEntity, or None.
        """
        name_upper = entity_name.strip().upper()

        for entity in reversed(list(self._open.values())):
            if entity.entity_name.strip().upper() != name_upper:
                continue
            if entity_type and entity.entity_type.strip().upper() != entity_type.strip().upper():
                continue
            if nesting_parent is not None:
                # Check if the entity's parent matches
                parent = self.get_by_id(entity.parent_id) if entity.parent_id else None
                parent_name = parent.entity_name.strip().upper() if parent else ""
                if parent_name != nesting_parent.strip().upper():
                    continue
            return entity

        return None

    def find_open_by_id(self, entity_id: str) -> Optional[OpenEntity]:
        """Get an open entity by its ID."""
        return self._open.get(entity_id)

    def get_by_id(self, entity_id: Optional[str]) -> Optional[OpenEntity]:
        """Get an open entity by ID (returns None if id is None or not found)."""
        if entity_id is None:
            return None
        return self._open.get(entity_id)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_all_open(self) -> list[OpenEntity]:
        """Return all open entities in insertion order."""
        return list(self._open.values())

    def get_open_containers(self) -> list[OpenEntity]:
        """
        Return open entities that are 'containers' (can have children).

        Containers: PACKAGE_SPEC, PACKAGE_BODY, PROCEDURE, FUNCTION,
                    TRIGGER, ANONYMOUS_BLOCK
        """
        container_types = {
            "PACKAGE_SPEC", "PACKAGE_BODY", "PROCEDURE", "FUNCTION",
            "TRIGGER", "ANONYMOUS_BLOCK",
        }
        return [
            e for e in self._open.values()
            if e.entity_type.strip().upper() in container_types
        ]

    @property
    def is_empty(self) -> bool:
        """True if no entities are currently open."""
        return len(self._open) == 0

    @property
    def count(self) -> int:
        """Number of currently open entities."""
        return len(self._open)

    # ------------------------------------------------------------------
    # Context for the LLM
    # ------------------------------------------------------------------

    def get_context_summary(self) -> str:
        """
        Build a human-readable summary of the current open entity state
        for inclusion in the LLM prompt.

        Returns a string like:
            Currently open entities:
            1. PKG_ETL (PACKAGE_BODY, level 0, started in chunks [0])
               Last code: "...g_batch NUMBER;"
            2. LOAD_DATA (PROCEDURE, level 1, parent: PKG_ETL, chunks [0])
               Last code: "...BEGIN"
        """
        if not self._open:
            return "No entities are currently open. This is the start of processing or all previous entities have been resolved."

        lines = ["Currently open entities (ordered by nesting depth):"]

        # Sort by nesting level for readability
        sorted_entities = sorted(self._open.values(), key=lambda e: e.nesting_level)

        for i, entity in enumerate(sorted_entities, 1):
            parent = self.get_by_id(entity.parent_id)
            parent_info = f", parent: {parent.entity_name}" if parent else ""

            op_info = ""
            if entity.operation_type:
                op_info = f"/{entity.operation_type}"

            # Show last 3 lines of code for context
            last_code = ""
            if entity.code_parts:
                all_code = "\n".join(entity.code_parts)
                code_lines = all_code.strip().splitlines()
                if len(code_lines) > 3:
                    last_code = "...\n" + "\n".join(code_lines[-3:])
                else:
                    last_code = "\n".join(code_lines)

            lines.append(
                f"  {i}. {entity.entity_name} ({entity.entity_type}{op_info}, "
                f"level {entity.nesting_level}{parent_info}, "
                f"chunks {entity.chunk_ids})"
            )
            if last_code:
                # Indent the code preview
                indented = "\n".join(f"       {l}" for l in last_code.splitlines())
                lines.append(f"     Last code lines:\n{indented}")

        return "\n".join(lines)

    def summary(self) -> str:
        """One-line summary for logging."""
        if not self._open:
            return "SeparatorState(empty)"
        names = [
            f"{e.entity_name}({e.entity_type})"
            for e in self._open.values()
        ]
        return f"SeparatorState({len(self._open)} open: {', '.join(names)})"
