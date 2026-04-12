import os
import json
from pathlib import Path
from loguru import logger
from typing import Dict, Any

from src.utils.code_handler import read_all_sql_files

class DirectoryBatchProcessor:
    """
    Spiders a directory of SQL files and independently acts upon them,
    running the Code Separator & Miner on each one and encasing their
    extracted JSON structures into isolated directories.
    """
    def __init__(self, output_base_dir: str, llm: Any):
        self.output_base = Path(output_base_dir)
        self.output_base.mkdir(parents=True, exist_ok=True)
        self.llm = llm
        
    def process_directory(self, input_path: str):
        logger.info(f"BATCH_PROCESSOR: Reading SQL targets from {input_path}")
        
        try:
            sql_files = read_all_sql_files(input_path)
            logger.info(f"BATCH_PROCESSOR: Discovered {len(sql_files)} `.sql` files.")
        except Exception as e:
            logger.error(f"Failed loading scripts: {e}")
            return
            
        for file_path, code in sql_files.items():
            self._process_script(file_path, code)
            
    def _process_script(self, file_path: Path, code: str):
        script_name = file_path.stem
        script_out_dir = self.output_base / script_name
        script_out_dir.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"BATCH_PROCESSOR: Initializing isolation environment for `{script_name}`...")
        
        try:
            from src.utils.chunker import SQLChunker
            from src.separator.separator import CodeSeparator
            from src.miner_advanced.orchestrator import MinerAdvancedOrchestrator
            
            # Step 1: Chunker & Separator
            chunker = SQLChunker(code, window_size=120, overlap=15, chunking_mode='tokens')
            separator = CodeSeparator(self.llm, skip_descriptions=False)
            registry = separator.process(chunker)
            
            # Save Raw AST Registry locally
            registry.save_to_file(str(script_out_dir / "entity_registry.json"))
            
            # Step 2: Extract Node Relationships out of the AST
            miner = MinerAdvancedOrchestrator(self.llm)
            miner.mine_registry(registry)
            
            # Save specific JSON Extractions
            miner.dump_results(str(script_out_dir))
            
            logger.info(f"BATCH_PROCESSOR: Execution finalized. Assets built natively in {script_out_dir}")
        except Exception as e:
            logger.error(f"BATCH_PROCESSOR: Script {script_name} failed extraction: {e}")
