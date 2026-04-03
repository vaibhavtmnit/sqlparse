import pytest
from src.utils.chunker import SQLChunker

def test_sqlchunker_valid_initialization():
    sql = "SELECT * FROM dual;"
    chunker = SQLChunker(sql, window_size=5, overlap=2)
    assert chunker.window_size == 5
    assert chunker.overlap == 2

def test_sqlchunker_invalid_initialization():
    sql = "SELECT * FROM dual;"
    with pytest.raises(ValueError, match="window_size must be strictly greater than 0."):
        SQLChunker(sql, window_size=0, overlap=0)
    
    with pytest.raises(ValueError, match="overlap must be greater than or equal to 0 and less than window_size."):
        SQLChunker(sql, window_size=5, overlap=5)
        
    with pytest.raises(ValueError, match="overlap must be greater than or equal to 0 and less than window_size."):
        SQLChunker(sql, window_size=5, overlap=-1)

def test_sqlchunker_no_overlap():
    sql = "line1\nline2\nline3\nline4\nline5\nline6"
    chunker = SQLChunker(sql, window_size=2, overlap=0)
    chunks = list(chunker)
    
    assert len(chunks) == 3
    assert chunks[0].chunk_id == 0
    assert chunks[0].chunk_text == "line1\nline2"
    assert chunks[1].chunk_id == 1
    assert chunks[1].chunk_text == "line3\nline4"
    assert chunks[2].chunk_id == 2
    assert chunks[2].chunk_text == "line5\nline6"

def test_sqlchunker_with_overlap():
    sql = "line1\nline2\nline3\nline4\nline5"
    # step = 3 - 1 = 2
    # chunk 0: lines 1, 2, 3
    # chunk 1: lines 3, 4, 5
    chunker = SQLChunker(sql, window_size=3, overlap=1)
    chunks = list(chunker)
    
    assert len(chunks) == 2
    assert chunks[0].chunk_id == 0
    assert chunks[0].chunk_text == "line1\nline2\nline3"
    assert chunks[1].chunk_id == 1
    assert chunks[1].chunk_text == "line3\nline4\nline5"

def test_sqlchunker_overlap_not_exact():
    sql = "line1\nline2\nline3\nline4\nline5"
    # step = 4 - 2 = 2
    # chunk 0: lines 1, 2, 3, 4
    # chunk 1: lines 3, 4, 5
    chunker = SQLChunker(sql, window_size=4, overlap=2)
    chunks = list(chunker)
    
    assert len(chunks) == 2
    assert chunks[0].chunk_id == 0
    assert chunks[0].chunk_text == "line1\nline2\nline3\nline4"
    assert chunks[1].chunk_id == 1
    assert chunks[1].chunk_text == "line3\nline4\nline5"

def test_sqlchunker_empty_string():
    chunker = SQLChunker("", window_size=2, overlap=1)
    chunks = list(chunker)
    assert len(chunks) == 0

def test_sqlchunker_short_string():
    # String has fewer lines than window_size
    sql = "1\n2"
    chunker = SQLChunker(sql, window_size=5, overlap=2)
    chunks = list(chunker)
    
    assert len(chunks) == 1
    assert chunks[0].chunk_id == 0
    assert chunks[0].chunk_text == "1\n2"
