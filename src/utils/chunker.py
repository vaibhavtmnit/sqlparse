from dataclasses import dataclass
from typing import Iterator

@dataclass
class Chunk:
    """Represents a chunk of SQL code."""
    chunk_id: int
    chunk_text: str

class SQLChunker:
    """
    A chunker that splits SQL script code into overlapping windows based on line counts.
    It acts as an iterable, yielding Chunk objects.
    """
    
    def __init__(self, sql_code: str, window_size: int, overlap: int, chunking_mode: str = 'lines'):
        """
        Initialize the SQLChunker.
        
        Args:
            sql_code: The raw SQL script code to be chunked.
            window_size: The number of lines each chunk should contain.
            overlap: The number of overlapping lines between consecutive chunks.
            chunking_mode: 'lines' or 'tokens' (currently only 'lines' is natively implemented here, 
                          but needed for API consistency).
        """
        if window_size <= 0:
            raise ValueError("window_size must be strictly greater than 0.")
        if overlap < 0 or overlap >= window_size:
            raise ValueError("overlap must be greater than or equal to 0 and less than window_size.")
            
        self.sql_code = sql_code
        self.window_size = window_size
        self.overlap = overlap
        self.chunking_mode = chunking_mode
        self.lines = self.sql_code.splitlines()

    def __iter__(self) -> Iterator[Chunk]:
        """
        Iterate over the lines of SQL code to generate chunks.
        
        Yields:
            Chunk objects containing the chunk text and a corresponding short numeric ID.
        """
        total_lines = len(self.lines)
        
        if total_lines == 0:
            # Handle empty strings gracefully
            return

        step = self.window_size - self.overlap
        chunk_id = 0
        
        for start_idx in range(0, total_lines, step):
            end_idx = min(start_idx + self.window_size, total_lines)
            
            chunk_lines = self.lines[start_idx:end_idx]
            chunk_text = "\n".join(chunk_lines)
            
            yield Chunk(chunk_id=chunk_id, chunk_text=chunk_text)
            
            chunk_id += 1
            
            # Stop if the end of the SQL code has been reached
            if end_idx >= total_lines:
                break
