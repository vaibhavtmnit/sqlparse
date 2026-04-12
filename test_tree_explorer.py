import os
from src.agents.llm import get_llm
from src.separator.registry import EntityRegistry
from src.separator.models import EntityEntry
from src.explorer.tree_native.harness import TreeNativeHarness

# Mock EntityRegistry for fast testing
class MockRegistry(EntityRegistry):
    def get_all(self):
        return [
            EntityEntry(
                entity_id="mock_01",
                entity_name="LOAD_DATA",
                entity_type="PROCEDURE",
                nesting_level=1,
                resolved_code="""
                INSERT INTO TARGET_TABLE (id, net_salary)
                SELECT 
                    src.id,
                    src.gross_amount * 0.9 AS net_salary
                FROM EMP_SOURCE src;
                """,
                description="Procedure to load data into TARGET_TABLE from EMP_SOURCE.",
                chunk_ids=[0]
            )
        ]

def test_run():
    print("Initializing LLM...")
    llm = get_llm()
    registry = MockRegistry()
    
    print("\nStarting Tree-Native Explorer Harness...")
    harness = TreeNativeHarness(registry, llm)
    
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
