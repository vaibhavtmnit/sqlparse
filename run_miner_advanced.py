"""
run_miner_advanced.py  — Example runner for the new Miner Advanced suite.

Loads an already generated Separator EntityRegistry and launches the DeepAgent
Miner to systematically walk the AST tree and generate rich lineage output.
"""

import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Ensure local imports work correctly
sys.path.append(str(Path(__file__).parent.absolute()))

from langchain_openai import ChatOpenAI
from src.separator.registry import EntityRegistry
from src.miner_advanced.orchestrator import MinerAdvancedOrchestrator
from src.miner_advanced.tools import _set_global_registry

def main():
    load_dotenv()
    if not os.getenv("OPENAI_API_KEY"):
        print("Please set OPENAI_API_KEY environment variable.")
        sys.exit(1)

    # 1. Load an existing separator registry
    # Change this path to wherever your latest separator output is stored.
    registry_path = Path("sample_registry_output.json")
    
    if not registry_path.exists():
        print(f"Error: Could not find {registry_path}.")
        print("Please run 'example_separator_from_file.py' first to generate a registry.")
        sys.exit(1)

    print(f"Loading Separator Registry from {registry_path}...")
    registry = EntityRegistry.load_from_json(str(registry_path))
    
    # Ensure Tools have access to the AST
    _set_global_registry(registry)
    
    # 2. Configure LLM for the mining agents
    llm = ChatOpenAI(model="gpt-4o", temperature=0)

    print("Initializing MinerAdvancedOrchestrator...")
    # Initialize the Orchestrator (It creates its own workspace directory)
    orchestrator = MinerAdvancedOrchestrator(
        registry=registry, 
        llm=llm, 
        chunk_threshold=600,   # User threshold for when to chunk massive entities
        overlap=20
    )
    
    # 3. Execute Mining Pipeline
    print("Starting Advanced Mining Run...")
    results = orchestrator.run()
    
    # Display summary
    print("\n" + "="*50)
    print(" MINING COMPLETE")
    print("="*50)
    print(f"Entities discovered: {len(results.get('entities', []))}")
    print(f"Relationships traced: {len(results.get('relationships', []))}")
    print(f"Code Flows mapped: {len(results.get('flows', []))}")
    print(f"Outputs and logs saved to: {orchestrator.workspace_dir}")
    print("="*50)


if __name__ == "__main__":
    main()
