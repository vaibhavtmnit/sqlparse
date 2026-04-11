"""
registry.py — Entity Registry for the Code Separator.

Stores all resolved (and in-progress) EntityEntry records. Provides
tree traversal, lookups by name/type, and serialisation to JSON.
"""

from __future__ import annotations

import json
from typing import Optional, Any

from src.separator.models import EntityEntry


class EntityRegistry:
    """
    Flat registry of EntityEntry records with parent_id links forming a tree.

    Each entity is stored by its unique ``entity_id``. The tree structure
    is implicit: ``entry.parent_id`` points to the parent's ``entity_id``.

    Usage::

        registry = EntityRegistry()
        registry.register(entry)

        all_procs = registry.find_by_type("PROCEDURE")
        children  = registry.get_children("ent_001")
        tree      = registry.get_tree()
    """

    def __init__(self) -> None:
        self._entries: dict[str, EntityEntry] = {}
        self._counter: int = 0

    # ------------------------------------------------------------------
    # ID generation
    # ------------------------------------------------------------------

    def next_id(self) -> str:
        """Generate the next unique entity ID."""
        self._counter += 1
        return f"ent_{self._counter:04d}"

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, entry: EntityEntry) -> None:
        """Add or update an entity in the registry."""
        self._entries[entry.entity_id] = entry

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    def get(self, entity_id: str) -> Optional[EntityEntry]:
        """Get an entity by ID, or None if not found."""
        return self._entries.get(entity_id)

    def get_all(self) -> list[EntityEntry]:
        """Return all entries in registration order."""
        return list(self._entries.values())

    def get_resolved(self) -> list[EntityEntry]:
        """Return only resolved (complete) entries."""
        return [e for e in self._entries.values() if e.is_resolved]

    def get_unresolved(self) -> list[EntityEntry]:
        """Return only unresolved (incomplete) entries."""
        return [e for e in self._entries.values() if not e.is_resolved]

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def find_by_name(self, name: str) -> list[EntityEntry]:
        """
        Find all entries matching *name* (case-insensitive).

        Note: The same entity name can appear multiple times (e.g.,
        AUDIT_LOG inserted in two different procedures).
        """
        name_upper = name.strip().upper()
        return [
            e for e in self._entries.values()
            if e.entity_name.strip().upper() == name_upper
        ]

    def find_by_type(self, entity_type: str) -> list[EntityEntry]:
        """Find all entries matching *entity_type* (case-insensitive)."""
        t = entity_type.strip().upper()
        return [
            e for e in self._entries.values()
            if e.entity_type.strip().upper() == t
        ]

    def find_by_name_and_type(
        self, name: str, entity_type: str
    ) -> list[EntityEntry]:
        """Find entries matching both name and type."""
        n = name.strip().upper()
        t = entity_type.strip().upper()
        return [
            e for e in self._entries.values()
            if e.entity_name.strip().upper() == n
            and e.entity_type.strip().upper() == t
        ]

    # ------------------------------------------------------------------
    # Tree operations
    # ------------------------------------------------------------------

    def get_children(self, parent_id: str) -> list[EntityEntry]:
        """Return all direct children of the given parent."""
        return [
            e for e in self._entries.values()
            if e.parent_id == parent_id
        ]

    def get_descendants(self, parent_id: str) -> list[EntityEntry]:
        """Return all descendants (recursive) of the given parent."""
        result: list[EntityEntry] = []
        children = self.get_children(parent_id)
        for child in children:
            result.append(child)
            result.extend(self.get_descendants(child.entity_id))
        return result

    def get_roots(self) -> list[EntityEntry]:
        """Return all top-level entities (no parent)."""
        return [e for e in self._entries.values() if e.parent_id is None]

    def get_tree(self) -> list[dict]:
        """
        Build a nested tree representation.

        Returns:
            List of root node dicts, each with a ``children`` key
            containing nested child dicts.
        """

        def _build_node(entry: EntityEntry) -> dict:
            children = self.get_children(entry.entity_id)
            return {
                "entity_id": entry.entity_id,
                "entity_name": entry.entity_name,
                "entity_type": entry.entity_type,
                "operation_type": entry.operation_type,
                "nesting_level": entry.nesting_level,
                "chunk_ids": entry.chunk_ids,
                "is_resolved": entry.is_resolved,
                "trigger_target": entry.trigger_target,
                "code_length": len(entry.resolved_code),
                "children": [_build_node(c) for c in children],
            }

        roots = self.get_roots()
        return [_build_node(r) for r in roots]

    def print_tree(self) -> None:
        """Pretty-print the entity tree to stdout."""
        def _print_node(tree: list, indent: int = 0) -> None:
            for node in tree:
                prefix = "  " * indent + ("├── " if indent > 0 else "")
                op = f"/{node['operation_type']}" if node.get("operation_type") else ""
                resolved = "[OK]" if node.get("is_resolved") else "[..]"
                print(
                    f"{prefix}{resolved} {node['entity_name']} "
                    f"({node['entity_type']}{op}) "
                    f"chunks={node['chunk_ids']} "
                    f"code={node['code_length']} chars"
                )
                if node.get("children"):
                    _print_node(node["children"], indent + 1)
                    
        tree = self.get_tree()
        _print_node(tree)

    def to_networkx(self) -> Any:
        """
        Export the registry to a NetworkX DiGraph.
        Each entity becomes a node, and parent-child relationships become directed edges.

        Returns:
            A networkx.DiGraph object.
        """
        import networkx as nx

        G = nx.DiGraph()
        for entry in self._entries.values():
            G.add_node(
                entry.entity_id,
                entity_name=entry.entity_name,
                entity_type=entry.entity_type,
                operation_type=entry.operation_type,
                nesting_level=entry.nesting_level,
                chunk_ids=entry.chunk_ids,
                is_resolved=entry.is_resolved,
                trigger_target=entry.trigger_target,
                code_length=len(entry.resolved_code)
            )
            if entry.parent_id:
                G.add_edge(entry.parent_id, entry.entity_id)

        return G

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    @property
    def count(self) -> int:
        """Total number of entries."""
        return len(self._entries)

    @property
    def resolved_count(self) -> int:
        """Number of resolved entries."""
        return sum(1 for e in self._entries.values() if e.is_resolved)

    def summary(self) -> str:
        """One-line summary for logging."""
        type_counts: dict[str, int] = {}
        for e in self._entries.values():
            type_counts[e.entity_type] = type_counts.get(e.entity_type, 0) + 1
        parts = [f"{t}={c}" for t, c in sorted(type_counts.items())]
        return (
            f"EntityRegistry({self.count} entries, "
            f"{self.resolved_count} resolved | {', '.join(parts)})"
        )

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_json(self, indent: int = 2) -> str:
        """Serialise all entries to a JSON string."""
        records = []
        for e in self._entries.values():
            records.append({
                "entity_id": e.entity_id,
                "entity_name": e.entity_name,
                "entity_type": e.entity_type,
                "operation_type": e.operation_type,
                "parent_id": e.parent_id,
                "nesting_level": e.nesting_level,
                "chunk_ids": e.chunk_ids,
                "resolved_code": e.resolved_code,
                "is_resolved": e.is_resolved,
                "description": e.description,
                "trigger_target": e.trigger_target,
            })
        return json.dumps(records, indent=indent, ensure_ascii=False)

    def save_to_file(self, path: str) -> None:
        """Write the registry to a JSON file."""
        from pathlib import Path

        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_json(), encoding="utf-8")

    @classmethod
    def load_from_file(cls, path: str) -> "EntityRegistry":
        """Load a registry from a JSON file."""
        from pathlib import Path

        data = json.loads(Path(path).read_text(encoding="utf-8"))
        registry = cls()
        for record in data:
            entry = EntityEntry(
                entity_id=record["entity_id"],
                entity_name=record["entity_name"],
                entity_type=record["entity_type"],
                operation_type=record.get("operation_type"),
                parent_id=record.get("parent_id"),
                nesting_level=record.get("nesting_level", 0),
                chunk_ids=record.get("chunk_ids", []),
                resolved_code=record.get("resolved_code", ""),
                is_resolved=record.get("is_resolved", False),
                description=record.get("description", ""),
                trigger_target=record.get("trigger_target"),
            )
            registry.register(entry)
            # Update counter to avoid ID collisions
            num = int(entry.entity_id.split("_")[1])
            if num >= registry._counter:
                registry._counter = num
        return registry
