from loguru import logger
from typing import Dict, Any, List

class ContextScoutAgent:
    """
    Acts as the eyes for the Explorer. Traverses the GraphEnricher AST
    to construct safe, bounded text chunks mapping directly to the target node.
    """
    def __init__(self, enricher):
        self.enricher = enricher

    def run(self, table_name: str, field_name: str) -> Dict[str, Any]:
        """
        Gathers raw context using the deterministic Field mapping layer.
        Falls back to exact AST retrieval.
        """
        logger.debug(f"SCOUT: Scanning for field relationships involving {table_name}.{field_name}")
        
        related = self.enricher.find_relationships_by_field(table_name, field_name)
        
        context = {
            "has_data": False,
            "target_table": table_name,
            "target_field": field_name,
            "explicit_mappings": [],
            "raw_code_blocks": []
        }
        
        # Pull code related to any matched mappings
        mapping_ids = []
        for r in related:
            # Check if this relationship inherently maps source to target explicitly
            # Miner Advanced creates robust field_mappings JSON arrays.
            if "source_mapping_id" in r:
                mapping_ids.append(r["source_mapping_id"])
                
            fields_lists = r.get("field_mappings", [])
            for fm in fields_lists:
                 if isinstance(fm, dict):
                      # If we are the EXACT TARGET FIELD, we can just grab the exact Source Fields blindly
                      # This bypasses the need for the deep LLM alias resolution entirely!
                      if str(fm.get("target_field")).lower() == field_name.lower():
                           context["explicit_mappings"].append(fm)
                           
        # Fetch bounded raw SQL for the mappings
        if mapping_ids:
             code_map = self.enricher.get_code_for_source_mappings(mapping_ids)
             context["raw_code_blocks"] = list(code_map.values())
             context["has_data"] = True
             
        # Fallback: If nothing was explicitly bound to field_mappings, pull the entire raw definition of the TABLE
        if not context["has_data"]:
             logger.debug(f"SCOUT: No granular mappings for {field_name}. Fallback pulling entire Table AST definition.")
             entity_info = self.enricher.get_entity_info(table_name)
             if entity_info:
                 maps = entity_info.get("source_mapping_id", [])
                 if isinstance(maps, list):
                     code_map = self.enricher.get_code_for_source_mappings(maps)
                     context["raw_code_blocks"] = list(code_map.values())
                     
                 # Pull description out of entity logic 
                 desc = entity_info.get("description", [])
                 if desc:
                     context["description_resolved"] = "\\n".join(desc) if isinstance(desc, list) else desc
                     
                 if context["raw_code_blocks"] or context.get("description_resolved"):
                       context["has_data"] = True
                       
        return context
