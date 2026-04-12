from loguru import logger
from typing import Dict, Any, List

class GraphRelationshipScout:
    """
    Examines the GraphEnricher outputs for relationships targeting the specific field.
    Restricts boundaries entirely to Graph JSON and entity descriptions,
    completely ignoring raw SQL chunk text rendering.
    """
    def __init__(self, enricher):
        self.enricher = enricher

    def run(self, table_name: str, field_name: str) -> Dict[str, Any]:
        logger.debug(f"GRAPH_SCOUT: Analyzing strict-JSON relationships for [{table_name}.{field_name}]")
        
        related = self.enricher.find_relationships_by_field(table_name, field_name)
        
        context = {
            "has_data": False,
            "target_table": table_name,
            "target_field": field_name,
            "relationships_json": [],
            "entity_descriptions": {}
        }
        
        if not related:
             logger.debug(f"GRAPH_SCOUT: No explicit Graph Edges bound to field {field_name}.")
             # We can't fall back to SQL scanning, so we check if the Table Entity description offers clues.
             entity_info = self.enricher.get_entity_info(table_name)
             if entity_info and entity_info.get("description"):
                  context["entity_descriptions"][table_name] = entity_info["description"]
                  context["has_data"] = True
             return context

        # Filter strictly for relations where we are the TARGET
        for rel in related:
            context["relationships_json"].append({
                "source": rel.get("source"),
                "target": rel.get("target"),
                "relationship_type": rel.get("relationship_type"),
                "confidence_score": rel.get("confidence_score"),
                "field_mappings": rel.get("field_mappings", []),
                "chunk_reference": rel.get("source_mapping_id")
            })
            
            # Stash contextual entity descriptions for LLM
            src = rel.get("source")
            if src and src not in context["entity_descriptions"]:
                 s_info = self.enricher.get_entity_info(src)
                 if s_info and s_info.get("description"):
                      context["entity_descriptions"][src] = s_info["description"]
                     
        if context["relationships_json"]:
             context["has_data"] = True
             
        return context
