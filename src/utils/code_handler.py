import os
from pathlib import Path
from typing import Union, Dict

def read_sql_file(file_path: Union[str, Path]) -> str:
    """
    Read a .sql file from a string or Path object.
    
    Args:
        file_path: The path to the .sql file.
        
    Returns:
        The content of the .sql file as a string.
        
    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file is not a .sql file.
    """
    path = Path(file_path)
    
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")
        
    if path.suffix.lower() != '.sql':
        raise ValueError(f"File must be a .sql file. Received: {file_path}")
        
    return path.read_text(encoding='utf-8')

def read_all_sql_files(path: Union[str, Path]) -> Dict[Path, str]:
    """
    Read SQL code from a given file or a directory.
    If a directory is provided, it reads all nested .sql files.
    
    Args:
        path: The path to a .sql file or a directory.
        
    Returns:
        A dictionary mapping the Path object of each .sql file to its textual content.
    """
    path_obj = Path(path)
    
    if path_obj.is_file():
        return {path_obj: read_sql_file(path_obj)}
    elif path_obj.is_dir():
        sql_codes = {}
        for sql_file in path_obj.rglob('*.sql'):
            if sql_file.is_file():
                sql_codes[sql_file] = read_sql_file(sql_file)
        return sql_codes
    else:
        raise FileNotFoundError(f"Path not found: {path}")
