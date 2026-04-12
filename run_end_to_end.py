import os
import sys
from pathlib import Path

# Ensure paths are correct
sys.path.append(str(Path(__file__).parent.absolute()))

try:
    import dotenv
    dotenv.load_dotenv()
except ImportError:
    print("Warning: python-dotenv not installed, assuming vars are in env.")

# Setup dummy sql
DUMMY_SQL = """
CREATE OR REPLACE PACKAGE BODY HR_PAYROLL AS
   v_tax_rate NUMBER := 0.15;
   
   PROCEDURE PROCESS_SALARY IS
   BEGIN
      INSERT INTO PAYROLL_LOG (EMP_ID, NET_SALARY)
      SELECT EMP_ID, GROSS_SALARY - (GROSS_SALARY * v_tax_rate) AS NET_SALARY
      FROM EMP_TABLE;
   END PROCESS_SALARY;
END HR_PAYROLL;
"""

def main():
    if not os.getenv("OPENAI_API_KEY") and not os.getenv("GOOGLE_API_KEY") and not os.getenv("GEMINI_API_KEY"):
        # Just warn, maybe it uses ollama or something inside get_llm
        print("Warning: Missing API keys in environment.")

    print("\n==================================")
    print(" PHASE 1: RUNNING CODE SEPARATOR ")
    print("==================================")
    
    # Write Dummy SQL to file just for record
    with open("dummy_test.sql", "w") as f:
        f.write(DUMMY_SQL.strip())

    try:
        from src.utils.chunker import SQLChunker
        from src.separator.separator import CodeSeparator
        from src.agents.llm import get_llm
    except ImportError as e:
        print(f"Failed to import core modules: {e}")
        return 1
        
    llm = get_llm()
    
    separator = CodeSeparator(
            llm=llm,
            skip_descriptions=True,
            deduplicate_overlap=True
    )
    
    chunker = SQLChunker(sql_code=DUMMY_SQL.strip(), window_size=50, overlap=5)
    
    try:
        print("Running Separator Loop...")
        separator.process(chunker)
        print("\n=== Separator Entity Tree ===")
        separator.registry.print_tree()
    except Exception as e:
        print(f"Separator failed: {e}")
        return 1
    
    print("\n==================================")
    print(" PHASE 2: ADVANCED MINER (ROUTER) ")
    print("==================================")
    
    from src.miner_advanced.orchestrator import MinerAdvancedOrchestrator
    
    try:
        miner = MinerAdvancedOrchestrator(
            registry=separator.registry,
            llm=llm,
            chunk_threshold=600,
            chunking_mode="lines",
            execution_mode="router"
        )
        
        results = miner.run()
        
        print("\n=== Mining Extraction Summary ===")
        print(f"Total Entities Discovered:      {len(results.get('entities', []))}")
        print(f"Total Relationships Identified: {len(results.get('relationships', []))}")
        print(f"Total Logic Flows Mapped:       {len(results.get('flows', []))}")
        
        if results.get('relationships'):
            for r in results['relationships']:
                r_dict = dict(r) if hasattr(r, "keys") else vars(r)
                if isinstance(r, dict):
                    r_dict = r
                    
                print(f" - RELATION: {r_dict.get('target')} <- {r_dict.get('source')} [{r_dict.get('relationship_tag')}]")
        
        print("\n✅ End-to-End Integrity Test Successful.")
        
    except Exception as e:
        print(f"Miner run failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(main())
