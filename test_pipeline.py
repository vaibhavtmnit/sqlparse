import os
import json
import pandas as pd
from src.agents.llm import get_llm
from src.enricher.core import GraphEnricher
from src.pipeline.daisy_chain import DaisyChainOrchestrator

class MockEnricherStage1:
    def __init__(self):
        self.entities_df = pd.DataFrame([{"entity_name": "RAW_DATA", "description": "System upstream raw tables."},
                                         {"entity_name": "STG_TABLE", "description": "The staging table holding early load loads."}])
        self.relationships_df = pd.DataFrame([{
            "source": "RAW_DATA",
            "target": "STG_TABLE",
            "field_mappings": [{"source_field": "RAW_TOTAL", "target_field": "GROSS"}],
            "source_mapping_id": "stg1"
        }])
    def find_relationships_by_field(self, t, f):
        res = self.relationships_df[(self.relationships_df["target"] == t)]
        return res.to_dict('records')
    def get_entity_info(self, t):
        matches = self.entities_df[self.entities_df["entity_name"] == t]
        if not matches.empty: return {"description": matches.iloc[0]["description"]}
        return None

class MockEnricherStage2:
    def __init__(self):
        # Stage 2 calls the input "STG_CLEAN" instead of "STG_TABLE" !
        self.entities_df = pd.DataFrame([{"entity_name": "STG_CLEAN", "description": "The staging table holding early load loads (Note the name changed globally!)."},
                                         {"entity_name": "CORE_TABLE", "description": "Final destination table."}])
        self.relationships_df = pd.DataFrame([{
            "source": "STG_CLEAN",
            "target": "CORE_TABLE",
            "field_mappings": [{"source_field": "GROSS", "target_field": "NET_SALARY"}],
            "source_mapping_id": "stg2"
        }])
    def find_relationships_by_field(self, t, f):
        res = self.relationships_df[(self.relationships_df["target"] == t)]
        return res.to_dict('records')
    def get_entity_info(self, t):
        matches = self.entities_df[self.entities_df["entity_name"] == t]
        if not matches.empty: return {"description": matches.iloc[0]["description"]}
        return None

def test_run():
    print("Initializing LLM...")
    llm = get_llm()
    stage1 = MockEnricherStage1()
    stage2 = MockEnricherStage2()
    
    # Notice we pass [Stage1, Stage2]. It will evaluate Stage2 FIRST natively.
    ordered_stages = [stage1, stage2]
    
    print("\nStarting Daisy Chain Orchestrator...")
    orchestrator = DaisyChainOrchestrator(llm)
    
    # We ask for NET_SALARY in CORE_TABLE (which is in Stage 2)
    results = orchestrator.execute("CORE_TABLE", "NET_SALARY", ordered_stages, explorer_type="graph_native")
    
    print("\n\n=== FINAL GLOBAL TRACE (ACROSS SCRIPTS) ===")
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    if not os.getenv("GOOGLE_API_KEY") and not os.getenv("OPENAI_API_KEY"):
         print("Missing Keys.")
    else:
         test_run()
