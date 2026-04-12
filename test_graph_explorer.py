import os
import pandas as pd
from src.agents.llm import get_llm
from src.explorer.graph_native.harness import GraphNativeHarness

class MockGraphEnricher:
    def __init__(self):
        # Provide deterministic mock relationship mapped between TARGET_TABLE and EMP_SOURCE
        self.relationships_df = pd.DataFrame([
            {
                "source": "EMP_SOURCE",
                "target": "TARGET_TABLE",
                "relationship_type": "Data Flow",
                "confidence_score": 0.95,
                "field_mappings": [
                    {
                        "source_field": "GROSS_AMOUNT",
                        "target_field": "NET_SALARY",
                        "transformation_logic": "Multiplied by 0.9"
                    }
                ],
                "source_mapping_id": "mock_id"
            }
        ])
        
    def find_relationships_by_field(self, table_name, field_name):
        return self.relationships_df.to_dict('records')

    def get_entity_info(self, table_name):
        if table_name == "TARGET_TABLE":
            return {"description": "A target dataset collecting monthly salaries."}
        return {"description": "Raw employee source data."}

def test_run():
    print("Initializing LLM...")
    llm = get_llm()
    enricher = MockGraphEnricher()
    
    print("\nStarting Graph-Native Explorer Harness (Featuring NetworkX)...")
    harness = GraphNativeHarness(enricher, llm)
    
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
    if not os.getenv("GOOGLE_API_KEY") and not os.getenv("OPENAI_API_KEY"):
         print("Missing API Keys.")
    else:
         test_run()
