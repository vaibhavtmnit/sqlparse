import json
from loguru import logger
from typing import Dict, Any, List
from pydantic import BaseModel, Field

class AliasMapping(BaseModel):
    source_table: str = Field(description="The upstream origin table providing the data.")
    source_field: str = Field(description="The upstream origin field providing the data.")

class AliasExtractionOutput(BaseModel):
    lineages: List[AliasMapping] = Field(description="A list of strict source-to-target lineages discovered.")

class AliasAndLineageAgent:
    """
    Consumes bounded SQL blocks from the Scout and handles complex alias resolution,
    returning structured Upstream targets so the Harness queue can advance smoothly.
    """
    def __init__(self, llm, enricher):
        self.llm = llm
        self.enricher = enricher

    def run(self, table_name: str, field_name: str, context: Dict[str, Any], wiki_context: str) -> List[Dict[str, str]]:
        
        progression_data = "\n\n=== NATIVE AST CODE BLOCKS ===\n"
        for idx, block in enumerate(context.get("raw_code_blocks", [])):
            progression_data += f"\n--- BLOCK {idx+1} ---\n```sql\n{block}\n```\n"
            
        desc = context.get("description_resolved")
        if desc:
            progression_data += f"\n=== AST RESOLVED DESCRIPTION ===\n{desc}\n"
            
        explicit = context.get("explicit_mappings")
        if explicit:
            progression_data += f"\n=== AST EXPLICIT MAP HINTS ===\n{json.dumps(explicit, indent=2)}\n"
            
        wiki_block = ""
        if wiki_context:
            wiki_block = f"\n=== GLOBAL LINEAGE WIKI ===\n(Do not get stuck in infinite loops. Avoid mapping dependencies that are already fully mapped below.)\n{wiki_context}\n"
            
        prompt = (
            f"You are a master Oracle SQL Data Lineage extraction tool.\n\n"
            f"TARGET FIELD: `{field_name}`\n"
            f"TARGET TABLE: `{table_name}`\n\n"
            "Your objective is to find the exact UPSTREAM SOURCE(S) of the TARGET FIELD from the provided context.\n"
            "1. Pay rigorous attention to ALIASES (`SELECT A.ID AS TARGET_ID FROM SOURCE A`). You must unmask the target to its true source.\n"
            "2. If multiple source fields contribute to the target (e.g. `col_a + col_b`), extract ALL of them separately.\n"
            "3. Look for explicit `INSERT INTO`, `MERGE`, or `CREATE VIEW` statements connecting the source tables to the target table.\n"
            "4. Only return data if you are explicitly confident. If it's a raw scalar function like SYSDATE, return nothing.\n"
            "5. CRITICAL: The Context JSON structures may contain arrays/lists of entities or merged relationships. This occurs because the Enricher combines identical Source-Target table relationships across multiple distinct extracted chunks. Treat each item in these lists as a potentially distinct, independent transformation pathway.\n\n"
            f"Here is the scoped context representing the bounds of this transformation:\n"
            f"{progression_data}"
            f"{wiki_block}"
        )
        
        try:
             structured_llm = self.llm.with_structured_output(AliasExtractionOutput)
             response = structured_llm.invoke(prompt)
             return [d.model_dump() for d in response.lineages]
        except Exception as e:
             logger.error(f"LLM Alias extraction failed: {e}")
             return []
