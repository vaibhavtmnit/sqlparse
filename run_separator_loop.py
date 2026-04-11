from typing import Iterable, Optional, Union
from src.utils.chunker import SQLChunker, Chunk
from src.separator.separator import CodeSeparator
from src.separator.registry import EntityRegistry
from src.separator.state import SeparatorState
from src.separator.processor import ChunkProcessor
from src.separator.agent import SeparatorAgent

class SeparatorRunner:
    """
    A utility class to run the CodeSeparator iteratively.
    
    This class allows passing chunks one by one inside a loop,
    or processing a chunker immediately, and finalizing the entity registry.

    Usage (one by one chunk):
        runner = SeparatorRunner(llm)
        for chunk in my_custom_loop():
            runner.process_chunk(chunk)
        registry = runner.finalize()

    Usage (direct chunker):
        runner = SeparatorRunner(llm)
        registry = runner.run(chunker)
    """

    def __init__(self, llm, max_retries: int = 3, skip_descriptions: bool = False, deduplicate_overlap: bool = False):
        self.separator = CodeSeparator(
            llm=llm,
            max_retries=max_retries,
            skip_descriptions=skip_descriptions,
            deduplicate_overlap=deduplicate_overlap
        )

    def process_chunk(self, chunk: Chunk) -> None:
        """
        Processes a single Chunk object.
        Retrieves state context, runs LLM analysis, and updates the registry.
        """
        text = chunk.chunk_text
        idx = chunk.chunk_id

        # Step 1: Get context from current state
        context_summary = self.separator.state.get_context_summary()

        # Step 2: Analyze chunk with LLM
        analysis = self.separator.agent.analyze_chunk(
            chunk_text=text,
            context_summary=context_summary,
            chunk_id=idx,
        )

        # Step 3: Process analysis (updates state + registry)
        self.separator.processor.process(analysis, chunk_id=idx)

    def finalize(self) -> EntityRegistry:
        """
        Force-resolves open entities and generates descriptions.
        Should be called after all chunks are processed.

        Returns:
            The finalized EntityRegistry.
        """
        # Step 4: Force-resolve any remaining open entities
        self.separator._force_resolve_open_entities()

        # Step 5: Generate descriptions for all resolved entities
        if not self.separator.skip_descriptions:
            self.separator._generate_descriptions()

        return self.separator.registry

    def run(self, chunks: Union[Iterable[Chunk], SQLChunker]) -> EntityRegistry:
        """
        Iterate over and process all chunks, then finalize.

        Args:
            chunks: An iterable of chunks or an SQLChunker.
        Returns:
            The finalized EntityRegistry.
        """
        for chunk in chunks:
            self.process_chunk(chunk)
            
        return self.finalize()

if __name__ == "__main__":
    import os
    from src.agents.llm import get_llm
    
    # Test example
    llm = get_llm()
    runner = SeparatorRunner(llm, skip_descriptions=True)
    
    # Example SQL and chunking
    sql_text = "CREATE TABLE dummy (id NUMBER); \\n/\\n"
    chunker = SQLChunker(sql_text, window_size=5, overlap=0)
    
    # Run by feeding one by one inside a loop
    for chunk in chunker:
        print(f"Processing chunk {chunk.chunk_id}...")
        runner.process_chunk(chunk)
        
    registry = runner.finalize()
    
    print("\nResulting entity tree:")
    # print_tree handles the printing nicely on the terminal
    registry.print_tree()
