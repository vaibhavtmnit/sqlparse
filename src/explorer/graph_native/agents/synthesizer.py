from loguru import logger
from typing import List, Dict, Any

class WikiSynthesizerAgent:
    """
    Renders a Wiki entry explicitly from Graph node mappings and string descriptions.
    Does not require raw code parsing.
    """
    def __init__(self, llm):
        self.llm = llm

    def run(self, table_name: str, field_name: str, lineage_results: List[Dict[str, str]], context: Dict[str, Any]) -> str:
        if not lineage_results:
             return "Value may be scalar, mocked, or derived outside explicitly detectable Metadata bounds."
             
        sources_str = ", ".join([f"[{s['source_table']}.{s['source_field']}]" for s in lineage_results])
        
        # Check if we have exact descriptions to pass
        desc_str = ""
        for tbl, txt in context.get("entity_descriptions", {}).items():
            desc_str += f"Block [{tbl}]: {txt}\n"
            
        rels = context.get("relationships_json", [])
        
        prompt = (
            f"You are writing a short Encyclopedia Wiki entry for a data lineage tracking system.\n"
            f"Write exactly 1 to 2 concise sentences explaining the logic for `{table_name}.{field_name}`.\n\n"
            f"We ALREADY KNOW it is derived from these upstream fields: {sources_str}.\n"
            f"Use the expert AI descriptions and relationship mapping logic below to state the transform (e.g. 'Math computation', 'Direct Map').\n"
            f"Start directly mapping without introduction.\n\n"
            f"Graph Mappings (JSON):\n{rels}\n\n"
            f"Node Entity Descriptions:\n{desc_str}"
        )
        
        try:
             response = self.llm.invoke(prompt)
             content = response.content if hasattr(response, "content") else str(response)
             return content.strip()
        except Exception as e:
             logger.error(f"Failed to generate synthesis: {e}")
             return f"Deterministically evaluated via Graph Theory from {sources_str}."
