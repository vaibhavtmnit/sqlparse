import json
from loguru import logger
from typing import Dict, Any, List
from pydantic import BaseModel, Field

from src.enricher.core import GraphEnricher

class RemappedLink(BaseModel):
    original_target: str = Field(description="The upstream table/field string required by the downstream stage.")
    inferred_table: str = Field(description="The exact table name it corresponds to within the current execution stage.")
    inferred_field: str = Field(description="The exact field name it corresponds to within the current execution stage.")

class LinkageInferenceOutput(BaseModel):
    remapped_links: List[RemappedLink] = Field(description="Strict inferred re-mappings to bridge the script boundary.")

class LinkageInferenceAgent:
    """
    Leaps the namespace boundaries between distinct multi-file extraction stages.
    """
    def __init__(self, llm):
        self.llm = llm

    def run(self, required_sources: List[Dict[str, str]], stage_enricher: GraphEnricher) -> List[Dict[str, str]]:
        if not required_sources:
             return []
             
        logger.info(f"LINK_INFERENCE: Attempting to map {len(required_sources)} floating elements across sequence boundaries.")
        
        # Pull global knowledge from this stage
        all_tables = list(stage_enricher.entities_df["entity_name"].unique()) if not stage_enricher.entities_df.empty else []
        
        # Build prompt payload
        req_str = json.dumps(required_sources, indent=2)
        
        # We also need to feed the AI descriptions of the tables inside this stage so it can infer
        desc_block = ""
        for t in all_tables:
             info = stage_enricher.get_entity_info(t)
             if info and info.get("description"):
                  desc_block += f"[{t}]: {info['description']}\n"
                  
        prompt = (
            f"You are the Apex Naming Linkage Inference Agent.\n"
            f"A downstream dependency script explicitly requires the following upstream sources:\n"
            f"{req_str}\n\n"
            f"However, we have jumped codebases. The current codebase only contains the following exact table names:\n"
            f"{json.dumps(all_tables)}\n\n"
            f"=== METADATA DESCRIPTIONS FOR CURRENT STAGE ===\n"
            f"{desc_block}\n\n"
            f"Your objective: Map each of the 'required upstream sources' to the actual EXACT Table and Field names present in THIS current stage.\n"
            f"If the table name exactly matches something in the current list, map it perfectly. If it is an alias (e.g. STG_EMP -> LOAD_RAW_EMP), use the descriptions to infer the connection."
        )
        
        try:
             structured_llm = self.llm.with_structured_output(LinkageInferenceOutput)
             response = structured_llm.invoke(prompt)
             
             results = []
             for link in response.remapped_links:
                  results.append({
                       "source_table": link.inferred_table,
                       "source_field": link.inferred_field
                  })
             return results
        except Exception as e:
             logger.error(f"LINK_INFERENCE: Inference logic failure: {e}")
             return required_sources # Fallback: return originals hoping downstream explorers can native-fault catch it!
