from loguru import logger
from typing import List, Dict, Any
from src.separator.models import EntityEntry

class WikiSynthesizerAgent:
    """
    Renders a Wiki entry by observing the Code blocks and explaining transformations.
    """
    def __init__(self, llm):
        self.llm = llm

    def run(self, table_name: str, field_name: str, lineage_results: List[Dict[str, str]], nodes: List[EntityEntry]) -> str:
        if not lineage_results:
             return "Value may be scalar, mocked, or derived outside explicitly detectable Code bounds."
             
        sources_str = ", ".join([f"[{s['source_table']}.{s['source_field']}]" for s in lineage_results])
        
        snippets = ""
        # Only provide the FIRST most critical node to save context space
        if nodes:
            best_node = nodes[0]
            snippets = f"```sql\n{best_node.resolved_code}\n```"
        
        prompt = (
            f"You are writing a short Encyclopedia Wiki entry for a data lineage tracking system.\n"
            f"Write exactly 1 to 3 concise sentences explaining the transformation logic for `{table_name}.{field_name}`.\n\n"
            f"We ALREADY KNOW it is derived from these upstream fields: {sources_str}.\n"
            f"Your ONLY job is to explain the math, aggregation, or logical transformation applied.\n"
            f"Do NOT write any introduction or conclusion. Start directly with the explanation.\n\n"
            f"Reference Code:\n{snippets}"
        )
        
        try:
             response = self.llm.invoke(prompt)
             content = response.content if hasattr(response, "content") else str(response)
             return content.strip()
        except Exception as e:
             logger.error(f"Failed to generate transformation summary: {e}")
             return f"Derived mechanically from {sources_str}."
