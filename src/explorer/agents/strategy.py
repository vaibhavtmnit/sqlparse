from loguru import logger

class OracleStrategyAgent:
    """
    Implements deterministic domain logic for how the Harness manages
    navigational priorities without hitting an LLM unnecessarily.
    """
    
    @staticmethod
    def get_navigation_directive(table_type: str, operation_hint: str) -> dict:
        table_type = str(table_type).lower()
        hint = str(operation_hint).lower()
        
        directive = {
            "search_priority": "standard",
            "avoid_synonyms": True,
            "look_for": []
        }
        
        if "view" in table_type:
             directive["search_priority"] = "schema"
             directive["look_for"] = ["CREATE VIEW", "CREATE OR REPLACE VIEW"]
             logger.debug(f"STRATEGY: Detected VIEW. Modifying search to locate root View creation logic.")
             
        if "merge" in hint:
             directive["look_for"] = ["WHEN MATCHED THEN UPDATE", "WHEN NOT MATCHED THEN INSERT"]
             logger.debug(f"STRATEGY: Detected MERGE logic. Modifying field mappings to carefully check update vs insert logic splits.")
             
        if "package" in table_type:
             directive["search_priority"] = "body"
             logger.debug(f"STRATEGY: Detected Package Object. Forcing sub-agents to ignore Spec and target Package Body logic.")
             
        return directive
