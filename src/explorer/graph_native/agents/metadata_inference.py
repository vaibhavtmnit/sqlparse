import json
from loguru import logger
from typing import Dict, Any, List
from pydantic import BaseModel, Field

class MetadataAliasMapping(BaseModel):
    source_table: str = Field(description="The upstream origin table providing the data.")
    source_field: str = Field(description="The upstream origin field providing the data.")

class MetadataExtractionOutput(BaseModel):
    lineages: List[MetadataAliasMapping] = Field(description="List of strict source-to-target lineages discovered.")

class MetadataInferenceAgent:
    """
    Consumes JSON Relationship graphs and Entity Descriptions, using the AI to infer
    missing field logic explicitly without ever seeing the raw SQL code.
    """
    def __init__(self, llm):
        self.llm = llm

    def run(self, table_name: str, field_name: str, context: Dict[str, Any], wiki_context: str) -> List[Dict[str, str]]:
        rels = context.get("relationships_json", [])
        desc = context.get("entity_descriptions", {})
        
        # Check if natively solved strictly in JSON without AI!
        for rel in rels:
             source_table = rel.get("source")
             for fm in rel.get("field_mappings", []):
                  if isinstance(fm, dict):
                      if str(fm.get("target_field")).lower() == field_name.lower():
                           sf = fm.get("source_field")
                           if sf:
                               # Fast bypass AI, we natively solved it.
                               if isinstance(sf, list):
                                    return [{"source_table": source_table, "source_field": f} for f in sf]
                               return [{"source_table": source_table, "source_field": sf}]
                               
        # AI Fallback: Evaluate logic dictionaries
        progression = ""
        if rels:
             progression += f"=== PRE-COMPUTED JSON RELATIONSHIPS ===\n{json.dumps(rels, indent=2)}\n"
             
        if desc:
             progression += f"\n=== EXPERT SYSTEM ENTITY DESCRIPTIONS ===\n"
             for t, d in desc.items():
                  progression += f"[{t}]: {d}\n"
                  
        wiki_block = ""
        if wiki_context:
            wiki_block = f"\n=== GLOBAL LINEAGE WIKI (DO NOT REDUNDANTLY RE-EVALUATE THESE) ===\n{wiki_context}\n"

        prompt = (
            f"You are the Apex Graph-Metadata Lineage Analyzer.\n"
            f"TARGET FIELD: `{field_name}`\n"
            f"TARGET TABLE: `{table_name}`\n\n"
            f"Your objective is to examine the heavily structured JSON Metadata relationships and Expert text descriptions "
            f"created by the codebase, to definitively locate the UPSTREAM SOURCE of the target.\n"
            f"You will NOT receive literal code blocks. Just abstract mapping nodes and explanations.\n"
            f"CRITICAL CAUTION: The JSON Lists provided may contain merged or consolidated dictionaries where identical table-pairs generated multiple distinct chunks. You must evaluate each JSON element as a potentially valid, independent logical pathway and aggregate all valid lineage sources.\n\n"
            f"{progression}"
            f"{wiki_block}"
            "\nSynthesize the exact Source Table and Field arrays responsible for creating the Target."
        )
        
        try:
             structured_llm = self.llm.with_structured_output(MetadataExtractionOutput)
             response = structured_llm.invoke(prompt)
             return [d.model_dump() for d in response.lineages]
        except Exception as e:
             logger.error(f"LLM Metadata inference extraction failed: {e}")
             return []
