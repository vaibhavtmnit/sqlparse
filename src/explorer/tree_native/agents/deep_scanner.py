import os
from loguru import logger
from typing import List, Dict, Any
from pydantic import BaseModel, Field

from src.separator.models import EntityEntry

class TreeAliasMapping(BaseModel):
    source_table: str = Field(description="The upstream origin table providing the data.")
    source_field: str = Field(description="The upstream origin field providing the data.")

class TreeAliasExtractionOutput(BaseModel):
    lineages: List[TreeAliasMapping] = Field(description="List of strict source-to-target lineages discovered.")

class DeepScannerAgent:
    """
    Ingests deeply scoped raw AST code and loads contextual Skill guidelines
    to extract lineages without relying on pre-computed relationships.
    """
    def __init__(self, llm):
        self.llm = llm

    def _load_skills(self) -> str:
        skill_path = os.path.join(os.path.dirname(__file__), "..", "skills", "oracle_lineage_core.md")
        try:
             with open(skill_path, "r", encoding="utf-8") as f:
                  return f.read()
        except Exception as e:
             logger.warning(f"Could not load Oracle Core Skills: {e}")
             return "Follow standard SQL Lineage extraction rules."

    def run(self, table_name: str, field_name: str, nodes: List[EntityEntry], wiki_context: str) -> List[Dict[str, str]]:
        if not nodes:
             return []
             
        progression = ""
        for n in nodes:
            progression += f"\n=== AST BLOCK: {n.entity_name} ({n.entity_type}) ===\n"
            if n.description:
                progression += f"Description: {n.description}\n"
            progression += f"Code:\n```sql\n{n.resolved_code}\n```\n"

        oracle_skills = self._load_skills()
        
        wiki_block = ""
        if wiki_context:
            wiki_block = f"\n=== GLOBAL LINEAGE WIKI ===\n(Do not get stuck in infinite loops. Avoid mapping dependencies that are already fully mapped below.)\n{wiki_context}\n"

        prompt = (
            f"You are the Apex Oracle SQL Deep Scanner.\n"
            f"TARGET FIELD: `{field_name}`\n"
            f"TARGET TABLE: `{table_name}`\n\n"
            f"Your objective is to scan the raw SQL text manually to locate where the TARGET FIELD originates upstream.\n\n"
            f"=== AGENT SKILLS ===\n{oracle_skills}\n\n"
            f"=== CONTEXT BLOCKS ===\n{progression}\n"
            f"{wiki_block}\n"
            "CRITICAL: If the value is a scalar or sequence function (like SYSDATE or NEXTVAL), DO NOT MAP IT! There is no source DB table!"
        )
        
        try:
             structured_llm = self.llm.with_structured_output(TreeAliasExtractionOutput)
             response = structured_llm.invoke(prompt)
             return [d.model_dump() for d in response.lineages]
        except Exception as e:
             logger.error(f"LLM Deep Scanner extraction failed: {e}")
             return []
