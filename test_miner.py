import shutil
from pathlib import Path
from src.miner.miner import SQLMiner
from src.agents.llm import get_llm
from loguru import logger

def test_run():
    # Setup workspace
    workspace = Path("./test_workspace")
    if workspace.exists():
        shutil.rmtree(workspace)
    
    # Simple SQL sample
    sample_sql = """
    CREATE OR REPLACE PACKAGE BODY PKG_ETL_LOADER AS
        PROCEDURE LOAD_STAGING IS
        BEGIN
            INSERT INTO STG_TABLE (ID, NAME)
            SELECT ID, NAME FROM SOURCE_TABLE;
            
            COMMIT;
        END LOAD_STAGING;
    END PKG_ETL_LOADER;
    /
    """
    
    logger.info("Initializing Miner...")
    llm = get_llm()
    miner = SQLMiner(llm=llm, workspace=str(workspace), window_size=150, overlap=10)
    
    logger.info("Running Miner...")
    miner.run(sample_sql)

if __name__ == "__main__":
    test_run()
