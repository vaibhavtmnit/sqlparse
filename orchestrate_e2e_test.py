import os
import json
import time
from pathlib import Path
from loguru import logger
from typing import Any

from src.separator.registry import EntityRegistry, EntityEntry
from src.separator.logger_config import configure_separator_logger
from src.miner_advanced.orchestrator import MinerAdvancedOrchestrator
from src.agents.llm import get_llm

# Initialize custom logger levels
configure_separator_logger()
base_logger = logger # Preserve reference

def setup_dummy_registry() -> EntityRegistry:
    reg = EntityRegistry()
    
    # 1. EMPLOYEES Table
    reg.register(EntityEntry(
        entity_id="ent_001",
        entity_name="EMPLOYEES",
        entity_type="TABLE",
        resolved_code="CREATE TABLE EMPLOYEES (EMP_ID NUMBER, EMP_NAME VARCHAR2(100), SALARY NUMBER, DEPARTMENT_ID NUMBER);",
        chunk_ids=[0]
    ))
    
    # 2. DEPARTMENTS Table
    reg.register(EntityEntry(
        entity_id="ent_002",
        entity_name="DEPARTMENTS",
        entity_type="TABLE",
        resolved_code="CREATE TABLE DEPARTMENTS (DEPT_ID NUMBER, DEPT_NAME VARCHAR2(100));",
        chunk_ids=[0]
    ))
    
    # 3. SALARY_HISTORY Table
    reg.register(EntityEntry(
        entity_id="ent_003",
        entity_name="SALARY_HISTORY",
        entity_type="TABLE",
        resolved_code="CREATE TABLE SALARY_HISTORY (EMP_ID NUMBER, OLD_SALARY NUMBER, NEW_SALARY NUMBER, CHANGE_DATE DATE);",
        chunk_ids=[0]
    ))
    
    # 4. HR_UTILS Package
    pkg_code = """
CREATE OR REPLACE PACKAGE HR_UTILS AS
    PROCEDURE PROCESS_ANNUAL_INCREMENT(p_dept_id NUMBER, p_percent NUMBER);
END HR_UTILS;
    """
    reg.register(EntityEntry(
        entity_id="ent_004",
        entity_name="HR_UTILS",
        entity_type="PACKAGE",
        resolved_code=pkg_code.strip(),
        chunk_ids=[0]
    ))
    
    # 5. HR_UTILS Package Body (Child of HR_UTILS)
    body_code = """
CREATE OR REPLACE PACKAGE BODY HR_UTILS AS
    PROCEDURE PROCESS_ANNUAL_INCREMENT(p_dept_id NUMBER, p_percent NUMBER) IS
    BEGIN
        INSERT INTO SALARY_HISTORY (EMP_ID, OLD_SALARY, NEW_SALARY, CHANGE_DATE)
        SELECT e.EMP_ID, e.SALARY, e.SALARY * (1 + p_percent/100), SYSDATE
        FROM EMPLOYEES e
        WHERE e.DEPARTMENT_ID = p_dept_id;

        UPDATE EMPLOYEES
        SET SALARY = SALARY * (1 + p_percent/100)
        WHERE DEPARTMENT_ID = p_dept_id;
    END PROCESS_ANNUAL_INCREMENT;
END HR_UTILS;
    """
    reg.register(EntityEntry(
        entity_id="ent_005",
        entity_name="HR_UTILS",
        entity_type="PACKAGE_BODY",
        resolved_code=body_code.strip(),
        parent_id="ent_004",
        chunk_ids=[0]
    ))
    
    return reg

def main():
    llm = get_llm()
    registry = setup_dummy_registry()
    
    # Save to JSON for testing file-based init
    registry_path = "e2e_test_registry.json"
    registry.save_to_file(registry_path)
    logger.info(f"Phase 1: Registry saved to {registry_path}")

    # Phase 2: Router Mode (using object)
    logger.info("Phase 2: Running Router Miner...")
    orchestrator_router = MinerAdvancedOrchestrator(
        registry=registry,
        llm=llm,
        execution_mode="router",
        workspace_dir="e2e_workspace_router"
    )
    res_router = orchestrator_router.run()
    logger.info(f"Router Mining Complete. Found {len(res_router['relationships'])} relationships.")

    # Phase 3: DeepAgent Mode (using file path)
    logger.info("Phase 3: Running DeepAgent Miner...")
    orchestrator_deep = MinerAdvancedOrchestrator.from_registry_file(
        registry_path=registry_path,
        llm=llm,
        execution_mode="deepagent",
        workspace_dir="e2e_workspace_deep"
    )
    res_deep = orchestrator_deep.run()
    logger.info(f"DeepAgent Mining Complete. Found {len(res_deep['relationships'])} relationships.")

    # Phase 4: Enricher
    logger.info("Phase 4: Running Enricher...")
    from src.enricher.core import GraphEnricher
    enricher = GraphEnricher(
        registry=orchestrator_deep.registry,
        entities_json="e2e_workspace_deep/entities.json",
        relationships_json="e2e_workspace_deep/relationships.json",
        flows_json="e2e_workspace_deep/flows.json"
    )
    logger.info(f"Enricher Loaded: {len(enricher.entities_df)} entities, {len(enricher.relationships_df)} edges.")

    # Phase 5: Explorer (Hybrid)
    logger.info("Phase 5: Running Hybrid Explorer...")
    from src.explorer.harness import ExplorerHarness
    hybrid_explorer = ExplorerHarness(enricher=enricher, llm=llm)
    # Trace lineage for EMPLOYEES.SALARY
    hybrid_results = hybrid_explorer.run("EMPLOYEES", "SALARY")
    logger.info(f"Hybrid Exploration Complete. Mapped {len(hybrid_results['tree'])} nodes.")

    # Phase 6: Explorer (Tree-Native)
    logger.info("Phase 6: Running Tree-Native Explorer...")
    from src.explorer.tree_native.harness import TreeNativeHarness
    tree_explorer = TreeNativeHarness(registry=orchestrator_deep.registry, llm=llm)
    tree_results = tree_explorer.run("EMPLOYEES", "SALARY")
    logger.info(f"Tree Exploration Complete. Mapped {len(tree_results['tree'])} nodes.")

    # Phase 7: Explorer (Graph-Native)
    logger.info("Phase 7: Running Graph-Native Explorer...")
    from src.explorer.graph_native.harness import GraphNativeHarness
    graph_explorer = GraphNativeHarness(enricher=enricher, llm=llm)
    graph_results = graph_explorer.run("EMPLOYEES", "SALARY")
    logger.info(f"Graph Exploration Complete. Mapped {len(graph_results['tree'])} nodes.")

    logger.info("=== E2E VERIFICATION FINISHED ===")

if __name__ == "__main__":
    main()
