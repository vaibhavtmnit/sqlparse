"""
models.py — Advanced Miner Pydantic Models.

Extended from legacy miner to support `source_mapping_id`, chunk trace-ability,
and field-level lineage details.
"""

from typing import Optional, List
from pydantic import BaseModel, Field


class FieldMapping(BaseModel):
    """Lineage rule connecting specific columns between two related entities."""
    target_field: str = Field(
        ..., 
        description="The field/column in the target entity (includes alias if used)."
    )
    source_fields: List[str] = Field(
        ..., 
        description="The field(s) in the source entity providing data/logic."
    )
    transformation_logic: str = Field(
        default="", 
        description="Logic tying source to target (e.g., CASE WHEN, SUM(), or direct mapping)."
    )


class AdvancedEntityRecord(BaseModel):
    """A single named Oracle SQL object extracted from a Code Separator block."""
    entity_name: str = Field(...)
    entity_type: str = Field(...)
    entity_description: str = Field(...)
    
    source_mapping_id: str = Field(
        ..., 
        description="Unique tag linking to the orchestrator cycle (e.g., ent_0012#chk_1)."
    )
    raw_chunk_ids: List[int] = Field(
        default_factory=list,
        description="The raw separator chunk IDs."
    )


class AdvancedRelationshipRecord(BaseModel):
    """A directional relationship (Target <- Source) with field-level lineage."""
    target: str = Field(..., description="The entity modified/created (Target).")
    source: str = Field(..., description="The entity queried/providing data (Source).")
    
    relationship_tag: str = Field(
        ..., 
        description="String tag loosely identifying relationship (e.g., INSERTS_INTO, READS_FROM)."
    )
    relationship_description: str = Field(...)
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    
    field_mappings: List[FieldMapping] = Field(
        default_factory=list, 
        description="Field level lineage mapping columns from source to target."
    )
    source_mapping_id: str = Field(
        ..., 
        description="Unique tag linking to the orchestrator cycle."
    )


class AdvancedFlowRecord(BaseModel):
    """A single step in the structural code flow graph."""
    flow_id: str = Field(...)
    flow_description: str = Field(...)
    parent_flow_id: Optional[str] = Field(None)
    flow_entity_name: str = Field(...)
    flow_entity_type: str = Field(...)
    flow_entity_description: str = Field(...)
    flow_entity_role: str = Field(...)
    flow_entity_parent_relation: Optional[str] = Field(None)
    
    source_mapping_id: str = Field(
        ..., 
        description="Unique tag linking to the orchestrator cycle."
    )


class AdvancedMiningResult(BaseModel):
    """Aggregated output for a single chunk or entity execution phase."""
    entities: List[AdvancedEntityRecord] = Field(default_factory=list)
    relationships: List[AdvancedRelationshipRecord] = Field(default_factory=list)
    flows: List[AdvancedFlowRecord] = Field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "entities": [e.model_dump() for e in self.entities],
            "relationships": [r.model_dump() for r in self.relationships],
            "flows": [f.model_dump() for f in self.flows],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AdvancedMiningResult":
        return cls(
            entities=[AdvancedEntityRecord(**e) for e in data.get("entities", [])],
            relationships=[AdvancedRelationshipRecord(**r) for r in data.get("relationships", [])],
            flows=[AdvancedFlowRecord(**f) for f in data.get("flows", [])],
        )
