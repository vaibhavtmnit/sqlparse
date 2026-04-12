import os
import sys
from pathlib import Path
from loguru import logger

# Add src to sys.path for direct execution
sys.path.append(str(Path(__file__).parent))

from src.agents.llm import get_llm
from src.pipeline.batch_processor import DirectoryBatchProcessor

def main():
    # Setup LLM
    try:
        # Ensure .env is loaded (get_llm handles this)
        llm = get_llm()
    except Exception as e:
        logger.error(f"Failed to initialize LLM: {e}")
        return

    # Constants
    INPUT_FILE = "dummy_complex.sql"
    OUTPUT_BASE = "test_batch_output"
    
    logger.info(f"Targeting dummy file: {INPUT_FILE}")
    
    # In order to use DirectoryBatchProcessor, we need a directory.
    # We'll create a temp dir and put our dummy file there.
    temp_input_dir = Path("temp_test_sql")
    if temp_input_dir.exists():
        import shutil
        shutil.rmtree(temp_input_dir)
    temp_input_dir.mkdir(exist_ok=True)
    
    # Read the dummy file we just created
    dummy_path = Path(INPUT_FILE)
    if not dummy_path.exists():
        logger.error(f"Dummy file {INPUT_FILE} not found!")
        return
        
    code = dummy_path.read_text(encoding='utf-8')
    
    # Write it to the temp directory
    (temp_input_dir / INPUT_FILE).write_text(code, encoding='utf-8')

    # Initialize Processor
    processor = DirectoryBatchProcessor(output_base_dir=OUTPUT_BASE, llm=llm)
    
    # Process
    logger.info("Starting Batch Processing...")
    try:
        processor.process_directory(str(temp_input_dir))
        logger.info("Batch Processing Finished.")
    except Exception as e:
        logger.error(f"Batch Processing failed: {e}")

if __name__ == "__main__":
    main()
