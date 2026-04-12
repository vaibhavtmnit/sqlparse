from loguru import logger
from typing import List, Optional
from src.separator.registry import EntityRegistry
from src.separator.models import EntityEntry

class TreeNodeNavigator:
    """
    Simulates navigating the AST tree directly. Bypasses explicitly mapped
    relationship links by actively evaluating the code properties inside the Tree.
    """
    def __init__(self, registry: EntityRegistry):
        self.registry = registry

    def find_relevant_nodes(self, table_name: str, field_name: str) -> List[EntityEntry]:
        logger.debug(f"NAVIGATOR: Hunting AST for [{table_name}.{field_name}] occurrences...")
        matches = []
        
        target_tb = str(table_name).lower()
        target_fd = str(field_name).lower()
        
        for entry in self.registry.get_all():
            code = entry.resolved_code.lower() if entry.resolved_code else ""
            desc = (entry.description or "").lower()
            
            # Direct Structural Hit
            if target_tb in code and target_fd in code:
                matches.append(entry)
            # LLM-described Hit (Often captures aliasing naturally)
            elif target_tb in desc and target_fd in desc:
                matches.append(entry)
                
        if not matches:
             # Fallback check just the table if field is deeply aliased
             for entry in self.registry.get_all():
                  code = entry.resolved_code.lower() if entry.resolved_code else ""
                  if target_tb in code:
                       matches.append(entry)
             if not matches:
                  return []
             
        # Prefer the deepest nodes (nesting_level).
        # Reason: A PACKAGE_BODY will contain all child text, but we want the specific PROCEDURE.
        matches_sorted = sorted(matches, key=lambda x: x.nesting_level, reverse=True)
        
        # Eliminate parents if their child is already explicitly matched here.
        # This keeps the context window tight.
        distinct_nodes = []
        bound_ids = set()
        for node in matches_sorted:
             if node.parent_id in bound_ids:
                 continue
             distinct_nodes.append(node)
             bound_ids.add(node.entity_id)
        
        # Return top most specific node blocks
        best = distinct_nodes[:2]
        logger.info(f"NAVIGATOR: Found {len(best)} highly specific Tree Nodes for analysis.")
        return best
