"""
tools.py — Helper tools for Advanced Miner Sub-Agents.

Includes tools exposed to the Langchain Multi-Agent system to fetch contextual
code definitions or run lightweight python syntax extraction to save tokens.
"""

import re
from typing import Any, List
from langchain_core.tools import tool

# We use a global registry reference so the Langchain @tool decorator
# can access it without complex class bindings during Agent initialization.
_GLOBAL_REGISTRY_REF = None

def _set_global_registry(registry: Any):
    global _GLOBAL_REGISTRY_REF
    _GLOBAL_REGISTRY_REF = registry

@tool
def fetch_entity_code(entity_name: str) -> str:
    """
    Useful when you need to read the definition of another related entity 
    (like a table or function) to understand context.
    
    Args:
        entity_name: The exact name of the entity.
    Returns:
        The SQL code of the entity.
    """
    if not _GLOBAL_REGISTRY_REF:
        return "Error: Registry not bound."
        
    entries = _GLOBAL_REGISTRY_REF.find_by_name(entity_name)
    if not entries:
        return f"Entity '{entity_name}' not found in the Separator Context Tree."
        
    # Return the first match's code, trim if massive
    code = entries[0].resolved_code
    if len(code) > 3000:
        return f"Code for {entity_name} (TRUNCATED to first 3000chars):\n{code[:3000]}..."
    return f"Code for {entity_name}:\n{code}"

@tool
def extract_field_candidates(sql_text: str) -> str:
    """
    A lightweight parser to hunt for SELECT, INSERT, and MERGE fields.
    Lowers the token reading burden for the LLM field-lineage agent by performing a 
    first-pass programmatic extraction.
    
    Args:
        sql_text: The SQL block to analyze.
    """
    try:
        import sqlglot
        from sqlglot import parse_one, exp
        parsed = parse_one(sql_text, read="oracle")
        
        # Try to extract base columns and aliases
        columns = []
        for c in parsed.find_all(exp.Column):
            columns.append(c.sql())
        for a in parsed.find_all(exp.Alias):
            columns.append(f"{a.this.sql()} AS {a.alias}")
            
        if not columns:
             return "No columns detected by programmatic parser. NEEDS_AGENTIC_FALLBACK: Please reason directly over the query."
             
        return f"PROGRAMMATIC EXTRACTION SUCCESS: Detected Column accesses:\n{list(set(columns))}"
        
    except ImportError:
        # Fallback to basic Regex if python packages aren't available
        select_blocks = re.findall(r'(?i)SELECT\s+(.*?)\s+FROM', sql_text, re.DOTALL)
        if select_blocks:
            return f"REGEX EXTRACTION (Raw SELECT blocks):\n{select_blocks[0][:1500]}"
        return "No SELECT targets detected by Regex. NEEDS_AGENTIC_FALLBACK: Please apply LLM inference to the raw SQL."
    except Exception as e:
        # Signal to the Director that we need the Scout Agent to step in
        return f"PROGRAMMATIC_PARSER_FAILED (Error: {str(e)}). NEEDS_AGENTIC_FALLBACK: Please reason directly over the query."
