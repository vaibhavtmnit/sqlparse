import os
import json
import argparse
import pandas as pd
from pathlib import Path
from loguru import logger

from src.separator.registry import EntityRegistry
from src.enricher.core import GraphEnricher

def run_lineage_enrichment(miner_dir: str, registry_dir: str, output_dir: str):
    """
    Orchestrates the aggregation of raw miner results into enriched lineage files.
    """
    # 1. Paths & Validation
    miner_path = Path(miner_dir)
    reg_path = Path(registry_dir)
    out_path = Path(output_dir)
    
    ent_json = miner_path / "entities.json"
    rel_json = miner_path / "relationships.json"
    flo_json = miner_path / "flows.json"
    ast_json = reg_path / "registry.json"
    
    if not ast_json.exists():
        logger.error(f"Missing registry: {ast_json}")
        return
        
    # Create output dir
    out_path.mkdir(parents=True, exist_ok=True)
    
    logger.info(f"Loading Registry from: {ast_json}")
    try:
        registry = EntityRegistry.load_from_file(str(ast_json))
        logger.success(f"Registry loaded with {registry.count} entities.")
    except Exception as e:
        logger.critical(f"Failed to load registry: {e}")
        return

    # 2. Enricher Execution
    logger.info("Initializing GraphEnricher...")
    enricher = GraphEnricher(
        registry=registry,
        entities_json=str(ent_json),
        relationships_json=str(rel_json),
        flows_json=str(flo_json)
    )
    
    # 3. Data Persistence
    # Goal: Save the aggregated DataFrames as JSON records for easy downstream reading.
    
    files_saved = 0
    
    if not enricher.entities_df.empty:
        ent_out = out_path / "enriched_entities.json"
        enricher.entities_df.to_json(ent_out, orient="records", indent=2)
        logger.info(f"Saved Enriched Entities: {ent_out}")
        files_saved += 1
        
    if not enricher.relationships_df.empty:
        rel_out = out_path / "enriched_relationships.json"
        enricher.relationships_df.to_json(rel_out, orient="records", indent=2)
        logger.info(f"Saved Enriched Relationships: {rel_out}")
        files_saved += 1
        
    if not enricher.flows_df.empty:
        flo_out = out_path / "enriched_flows.json"
        enricher.flows_df.to_json(flo_out, orient="records", indent=2)
        logger.info(f"Saved Enriched Flows: {flo_out}")
        files_saved += 1
        
    if files_saved > 0:
        logger.success(f"Enrichment Complete. {files_saved} files written to {output_dir}")
    else:
        logger.warning("Enrichment finished but no aggregated data found (Empty results?).")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SQL Lineage Graph Enricher CLI")
    parser.add_argument("--miner_dir", required=True, help="Folder containing entities.json, relationships.json, etc.")
    parser.add_argument("--registry_dir", required=True, help="Folder containing registry.json")
    parser.add_argument("--output_dir", required=True, help="Folder to save enriched JSON results")
    
    args = parser.parse_args()
    
    try:
        run_lineage_enrichment(args.miner_dir, args.registry_dir, args.output_dir)
    except Exception as e:
        logger.critical(f"Enricher Module CRASHED: {e}")
        import traceback
        traceback.print_exc()
