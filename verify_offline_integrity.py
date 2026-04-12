import os
import json
import pandas as pd
from pathlib import Path
from loguru import logger
from typing import Any, List
from unittest.mock import MagicMock, patch

# Components to test
from src.separator.registry import EntityRegistry, EntityEntry
from src.separator.logger_config import configure_separator_logger
from src.utils.chunker import SQLChunker
from src.miner_advanced.state import MinerStateContext
from src.enricher.core import GraphEnricher
from src.explorer.graph_native.agents.network_analyzer import NetworkXAnalyzer
from src.explorer.tree_native.agents.navigator import TreeNodeNavigator
from src.miner_advanced.orchestrator import MinerAdvancedOrchestrator

# Initialize custom logger levels
configure_separator_logger()

def test_tool_invocations():
    logger.info("--- Testing Tool Invocation Signatures ---")
    from src.miner_advanced.tools import extract_field_candidates, fetch_entity_code
    
    # Verify extract_field_candidates
    try:
        # We use a dict input as required by LangChain BaseTool.invoke
        res = extract_field_candidates.invoke({"sql_text": "SELECT * FROM DUAL"})
        assert "EXTRACTION" in res
        logger.success("✓ extract_field_candidates.invoke works with dict")
    except Exception as e:
        logger.error(f"❌ extract_field_candidates.invoke failed: {e}")
        raise
        
    # Verify fetch_entity_code (requires registry)
    reg = EntityRegistry()
    reg.register(EntityEntry(entity_id="e1", entity_name="DUAL", entity_type="TABLE", resolved_code="CODE", chunk_ids=[0]))
    from src.miner_advanced.tools import _set_global_registry
    _set_global_registry(reg)
    
    try:
        res = fetch_entity_code.invoke({"entity_name": "DUAL"})
        assert "CODE" in res
        logger.success("✓ fetch_entity_code.invoke works with dict")
    except Exception as e:
        logger.error(f"❌ fetch_entity_code.invoke failed: {e}")
        raise

def test_registry_and_navigator():
    logger.info("--- Testing Registry & Navigator ---")
    reg = EntityRegistry()
    
    e1 = EntityEntry(
        entity_id="ent_001",
        entity_name="EMPLOYEES",
        entity_type="TABLE",
        resolved_code="CREATE TABLE EMPLOYEES (SALARY NUMBER);",
        chunk_ids=[0],
        nesting_level=0
    )
    reg.register(e1)
    
    e2 = EntityEntry(
        entity_id="ent_002",
        entity_name="UPDATE_SALARY",
        entity_type="PROCEDURE",
        resolved_code="UPDATE EMPLOYEES SET SALARY = 100;",
        parent_id="ent_001",
        chunk_ids=[0],
        nesting_level=1
    )
    reg.register(e2)
    
    nav = TreeNodeNavigator(reg)
    nodes = nav.find_relevant_nodes("EMPLOYEES", "SALARY")
    assert len(nodes) > 0
    assert nodes[0].entity_name == "UPDATE_SALARY"
    
    logger.success("✓ Registry & Navigator Pass")
    return reg

def test_chunker_and_state(registry):
    logger.info("--- Testing Chunker & State ---")
    long_sql = "\n".join([f"LINE {i}" for i in range(100)])
    chunker = SQLChunker(long_sql, window_size=50, overlap=10)
    chunks = list(chunker)
    assert len(chunks) == 3
    
    state = MinerStateContext(registry)
    state.push_breadcrumb("ent_001")
    ctx_str = state.get_context_string()
    assert "EMPLOYEES" in ctx_str
    
    logger.success("✓ Chunker & State Pass")

def test_enricher_and_graph(registry):
    logger.info("--- Testing Enricher & NetworkX ---")
    entities_p = "offline_test_workspace/entities.json"
    relations_p = "offline_test_workspace/relationships.json"
    flows_p = "offline_test_workspace/flows.json"
    
    enricher = GraphEnricher(registry, entities_p, relations_p, flows_p)
    assert not enricher.entities_df.empty
    
    analyzer = NetworkXAnalyzer(enricher)
    logger.success("✓ Enricher & NetworkX Pass")

def test_mocked_orchestration(registry):
    logger.info("--- Testing Mocked Orchestration ---")
    with patch("src.miner_advanced.orchestrator.DualModeMiningDirector") as MockDirector:
        orch = MinerAdvancedOrchestrator(
            registry=registry,
            llm=MagicMock(),
            workspace_dir="offline_test_results"
        )
        agg = {"entities": [], "relationships": [], "flows": []}
        orch._traverse_and_mine("ent_001", agg)
    logger.success("✓ Orchestration Traversal Pass (Mocked)")

def test_field_scout_fallback():
    logger.info("--- Testing Field Scout Fallback (Hard Failure) ---")
    from src.miner_advanced.agents.director import MiningDirector
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = MagicMock()
    mock_llm.invoke.return_value = MagicMock(content="SCOUT_COL")
    
    director = MiningDirector(llm=mock_llm)
    from src.miner_advanced.models import AdvancedMiningResult, AdvancedRelationshipRecord
    dummy_res = AdvancedMiningResult(relationships=[
        AdvancedRelationshipRecord(
            source="A", target="B", relationship_tag="READ", 
            relationship_description="Dummy", confidence_score=1.0, source_mapping_id="ent_001"
        )
    ])
    
    with patch("src.miner_advanced.agents.director.extract_field_candidates") as mock_tool:
        mock_tool.invoke.return_value = "PROGRAMMATIC_PARSER_FAILED. NEEDS_AGENTIC_FALLBACK."
        director._extract_field_lineage(dummy_res, "SYNTAX_ERROR", "ent_001")
        assert director.llm.invoke.called
        logger.success("✓ Field Scout Fallback Logic Verified (Hard Failure)")

def test_aggressive_fallback_on_empty():
    logger.info("--- Testing Aggressive Fallback on Empty Results ---")
    from src.miner_advanced.agents.director import MiningDirector
    from src.miner_advanced.models import AdvancedMiningResult, AdvancedRelationshipRecord
    
    mock_llm = MagicMock()
    mock_llm.with_structured_output.return_value = MagicMock()
    mock_llm.invoke.return_value = MagicMock(content="SCOUT_COL")
    
    director = MiningDirector(llm=mock_llm)
    dummy_res = AdvancedMiningResult(relationships=[
        AdvancedRelationshipRecord(
            source="A", target="B", relationship_tag="READ", 
            relationship_description="Dummy", confidence_score=1.0, source_mapping_id="ent_001"
        )
    ])

    with patch("src.miner_advanced.agents.director.extract_field_candidates") as mock_tool:
        mock_tool.invoke.return_value = "No columns detected by programmatic parser. NEEDS_AGENTIC_FALLBACK: reason over query."
        director._extract_field_lineage(dummy_res, "SELECT * FROM UNKNOWN", "ent_001")
        assert director.llm.invoke.called
        logger.success("✓ Aggressive Fallback Verified (Triggered on Empty)")

if __name__ == "__main__":
    try:
        test_tool_invocations()
        reg = test_registry_and_navigator()
        test_chunker_and_state(reg)
        test_enricher_and_graph(reg)
        test_mocked_orchestration(reg)
        test_field_scout_fallback()
        test_aggressive_fallback_on_empty()
        logger.info("\n=== ALL OFFLINE INTEGRITY CHECKS PASSED ===")
    except Exception as e:
        logger.critical(f"FATAL INTEGRITY FAILURE: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
