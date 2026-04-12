import os
import sys
import pandas as pd

from src.agents.llm import get_llm
from src.enricher.core import GraphEnricher
from src.explorer.harness import ExplorerHarness
from src.explorer.vector_search import initialize_vector_search

# Mock Enricher class structure if needed or load from real JSONs
class MockEnricher:
    def __init__(self):
        self.entities_df = pd.DataFrame([
             {"entity_name": "T1", "entity_type": "TABLE", "description": ["Some desc"], "chunk_ids": [1]}
        ])
        
    def find_relationships_by_field(self, table_name, field_name):
        if table_name == "TARGET_TABLE" and field_name == "NET_SALARY":
            return [{"source_mapping_id": "ent_1"}]
        return []

    def get_code_for_source_mappings(self, mapping_ids):
        if "ent_1" in mapping_ids:
            return {"ent_1": "SELECT (SOURCE.GROSS_SALARY * 0.9) AS NET_SALARY FROM SOURCE_TABLE SOURCE;"}
        return {}

    def get_entity_info(self, table_name):
        return {}

def test_run():
    from src.agents.llm import get_embeddings
    print("Initializing LLM & Embeddings...")
    llm = get_llm()
    embeddings = get_embeddings()
    enricher = MockEnricher()
    
    # Test Vector Creation explicitly
    print("Initializing FAISS Vector Store...")
    faiss_store = initialize_vector_search(enricher, embeddings, backend="faiss")
    
    print("Starting Explorer Harness...")
    harness = ExplorerHarness(enricher, llm)
    
    results = harness.run("TARGET_TABLE", "NET_SALARY")
    
    print("\n--- LINEAGE TREE ---")
    import json
    print(json.dumps(results["tree"], indent=2))
    
    print("\n--- LLM WIKI ---")
    for k, v in results["wiki"].items():
        print(f"{k}: {v}")

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    if not os.getenv("OPENAI_API_KEY") and not os.getenv("GOOGLE_API_KEY"):
         print("Missing API Keys.")
    else:
         test_run()
