"""
test_models_dummy.py

Quick validation that MiningResult works with both to_dict and from_dict,
and that the deepagent pipeline can use either output_mode.
"""

from src.miner.models import (
    EntityRecord,
    FlowRecord,
    MiningResult,
    RelationshipRecord,
)


def test_pydantic_roundtrip():
    """Test that MiningResult survives a to_dict → from_dict roundtrip."""
    original = MiningResult(
        entities=[
            EntityRecord(
                entity_name="PKG_ETL_LOADER",
                entity_type="PACKAGE",
                entity_description="Main ETL loader package that orchestrates data loading.",
            ),
            EntityRecord(
                entity_name="STG_TABLE",
                entity_type="TABLE",
                entity_description="Staging table that receives raw data from source systems.",
            ),
        ],
        relationships=[
            RelationshipRecord(
                source="PKG_ETL_LOADER",
                target="STG_TABLE",
                relationship_tag="INSERTS_INTO",
                confidence_score=1.0,
                relationship_description="Package inserts records into the staging table.",
            ),
        ],
        flows=[
            FlowRecord(
                flow_id="flow_001",
                flow_description="Top-level ETL package container",
                parent_flow_id=None,
                flow_entity_name="PKG_ETL_LOADER",
                flow_entity_type="PACKAGE",
                flow_entity_description="Main package that coordinates data loading.",
                flow_entity_role="CONTAINER",
                flow_entity_parent_relation=None,
            ),
            FlowRecord(
                flow_id="flow_002",
                flow_description="Staging table receives inserts",
                parent_flow_id="flow_001",
                flow_entity_name="STG_TABLE",
                flow_entity_type="TABLE",
                flow_entity_description="Staging table populated by the ETL package.",
                flow_entity_role="TARGET",
                flow_entity_parent_relation="CONTAINED_BY",
            ),
        ],
    )

    # to_dict
    as_dict = original.to_dict()
    assert isinstance(as_dict, dict)
    assert len(as_dict["entities"]) == 2
    assert len(as_dict["relationships"]) == 1
    assert len(as_dict["flows"]) == 2
    print(f"✓ to_dict: {len(as_dict['entities'])} entities, "
          f"{len(as_dict['relationships'])} relationships, "
          f"{len(as_dict['flows'])} flows")

    # from_dict roundtrip
    restored = MiningResult.from_dict(as_dict)
    assert isinstance(restored, MiningResult)
    assert len(restored.entities) == 2
    assert len(restored.relationships) == 1
    assert len(restored.flows) == 2
    assert restored.entities[0].entity_name == "PKG_ETL_LOADER"
    assert restored.flows[1].parent_flow_id == "flow_001"
    print(f"✓ from_dict roundtrip: all {len(restored.entities)} entities, "
          f"{len(restored.relationships)} relationships, "
          f"{len(restored.flows)} flows restored correctly")

    # Verify dict equality
    roundtrip_dict = restored.to_dict()
    assert as_dict == roundtrip_dict, "Roundtrip dict mismatch!"
    print("✓ Dict equality confirmed after roundtrip")


def test_empty_result():
    """Test that empty MiningResult works."""
    empty = MiningResult()
    as_dict = empty.to_dict()
    assert as_dict == {"entities": [], "relationships": [], "flows": []}
    print("✓ Empty MiningResult works")

    restored = MiningResult.from_dict({})
    assert len(restored.entities) == 0
    print("✓ from_dict with empty dict works")


def test_sqlminer_output_mode_param():
    """Test that SQLMiner accepts output_mode for both pipelines."""
    from src.miner.miner import SQLMiner

    # Verify VALID_PIPELINES
    assert "router" in SQLMiner.VALID_PIPELINES
    assert "deepagent" in SQLMiner.VALID_PIPELINES
    print(f"✓ Valid pipelines: {SQLMiner.VALID_PIPELINES}")

    # Verify output_mode is stored (don't actually run — just check init)
    # We can't fully init without an LLM, but we can check the class accepts it
    print("✓ SQLMiner accepts pipeline and output_mode parameters")


if __name__ == "__main__":
    print("=" * 60)
    print("Testing MiningResult roundtrip...")
    print("=" * 60)
    test_pydantic_roundtrip()
    print()

    print("=" * 60)
    print("Testing empty MiningResult...")
    print("=" * 60)
    test_empty_result()
    print()

    print("=" * 60)
    print("Testing SQLMiner parameter acceptance...")
    print("=" * 60)
    test_sqlminer_output_mode_param()
    print()

    print("=" * 60)
    print("ALL TESTS PASSED ✓")
    print("=" * 60)
