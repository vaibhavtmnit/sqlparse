"""
models.py

Pydantic BaseModel classes for structured mining output.

Provides type-safe data models for entities, relationships, and flows
extracted from SQL code chunks. These can be used as structured_output
schemas for LLM calls or as validated containers for parsed JSON data.
"""

from typing import Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Individual record models
# ---------------------------------------------------------------------------


class EntityRecord(BaseModel):
    """A single named Oracle SQL object extracted from a code chunk."""

    entity_name: str = Field(
        ...,
        description="Exact name from the SQL (e.g., PKG_ETL_LOADER, STAG_TABLE).",
    )
    entity_type: str = Field(
        ...,
        description=(
            "Uppercase type: TABLE, PROCEDURE, PACKAGE, FUNCTION, VIEW, "
            "TRIGGER, SEQUENCE, SYNONYM, CTE, TYPE, etc."
        ),
    )
    entity_description: str = Field(
        ...,
        description=(
            "150-250 word description covering purpose, operations, "
            "interactions with other entities, and data handled."
        ),
    )


class RelationshipRecord(BaseModel):
    """A directional relationship between two Oracle SQL entities."""

    source: str = Field(
        ...,
        description="The entity initiating or owning the action.",
    )
    target: str = Field(
        ...,
        description="The entity being acted upon.",
    )
    relationship_tag: str = Field(
        ...,
        description=(
            "Short uppercase tag: INSERTS_INTO, UPDATES, DELETES_FROM, "
            "READS_FROM, CALLS, EXECUTES, CREATES, DROPS, ALTERS, "
            "JOINS_WITH, DEPENDS_ON, CONTAINS, DEFINES, REFERENCES, "
            "TRIGGERS_ON, QUERIES, POPULATES, MERGES_INTO, etc."
        ),
    )
    confidence_score: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Certainty from code evidence, 0.0 to 1.0.",
    )
    relationship_description: str = Field(
        ...,
        description="Under 200 words explaining the relationship in context.",
    )


class FlowRecord(BaseModel):
    """A single step in the structural code flow graph."""

    flow_id: str = Field(
        ...,
        description="Sequential ID (e.g., flow_001). Continues from previous flows.",
    )
    flow_description: str = Field(
        ...,
        description="High-level description of what this code segment is doing.",
    )
    parent_flow_id: Optional[str] = Field(
        None,
        description="flow_id of the parent step, or null for root steps.",
    )
    flow_entity_name: str = Field(
        ...,
        description="Name of the entity central to this flow step.",
    )
    flow_entity_type: str = Field(
        ...,
        description="Entity type: TABLE, PROCEDURE, PACKAGE, etc.",
    )
    flow_entity_description: str = Field(
        ...,
        description="What this entity is doing in this flow step.",
    )
    flow_entity_role: str = Field(
        ...,
        description=(
            "Role in the flow: EXECUTOR, TARGET, DEPENDENCY, "
            "CONTAINER, or INTERMEDIARY."
        ),
    )
    flow_entity_parent_relation: Optional[str] = Field(
        None,
        description="How this relates to the parent flow step (e.g., CONTAINED_BY).",
    )


# ---------------------------------------------------------------------------
# Aggregate result model
# ---------------------------------------------------------------------------


class MiningResult(BaseModel):
    """
    Top-level structured output for the mining deep agent.

    Contains all entities, relationships, and flows extracted from a single
    SQL code chunk.
    """

    entities: list[EntityRecord] = Field(
        default_factory=list,
        description="All Oracle SQL entities found in this chunk.",
    )
    relationships: list[RelationshipRecord] = Field(
        default_factory=list,
        description="All relationships between entities in this chunk.",
    )
    flows: list[FlowRecord] = Field(
        default_factory=list,
        description="The structural code flow graph for this chunk.",
    )

    def to_dict(self) -> dict:
        """
        Convert to the dict format expected by the persistence layer.

        Returns:
            Dict with keys ``entities``, ``relationships``, ``flows``
            — each a list of plain dicts.
        """
        return {
            "entities": [e.model_dump() for e in self.entities],
            "relationships": [r.model_dump() for r in self.relationships],
            "flows": [f.model_dump() for f in self.flows],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MiningResult":
        """
        Create a MiningResult from a raw dict with lists of dicts.

        This is useful for converting regex-parsed JSON output (from the
        deepagent pipeline) into a validated Pydantic model.

        Args:
            data: Dict with keys ``entities``, ``relationships``, ``flows``
                  — each a list of plain dicts.

        Returns:
            A validated MiningResult instance.

        Example::

            raw = {"entities": [...], "relationships": [...], "flows": [...]}
            result = MiningResult.from_dict(raw)
        """
        return cls(
            entities=[
                EntityRecord(**e) for e in data.get("entities", [])
            ],
            relationships=[
                RelationshipRecord(**r) for r in data.get("relationships", [])
            ],
            flows=[
                FlowRecord(**f) for f in data.get("flows", [])
            ],
        )
