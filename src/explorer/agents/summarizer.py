from loguru import logger
from typing import Dict, Any, List

class TransformationSummarizerAgent:
    """
    Looks at the source mappings and raw code and renders a 1-2 sentence description
    of EXACTLY what logic was used to get from A to B (e.g. SUM(), multiply, concatenation).
    This feeds into the LLM Wiki to prevent redundant analysis later.
    """
    def __init__(self, llm):
        self.llm = llm

    def run(self, table_name: str, field_name: str, lineage_results: List[Dict[str, str]], context: Dict[str, Any]) -> str:
        if not lineage_results:
             return "No upstream inputs extracted. Value may be scalar, mocked, or derived outside context bounds."
             
        sources_str = ", ".join([f"[{s['source_table']}.{s['source_field']}]" for s in lineage_results])
        
        snippets = ""
        # Provide small bits of code
        for idx, block in enumerate(context.get("raw_code_blocks", [])[:1]): 
            # First block is usually enough for the transformation
            snippets += f"```sql\n{block}\n```\n"
            
        desc = context.get("description_resolved", "")
        
        prompt = (
            f"You are writing a short Encyclopedia Wiki entry for a data lineage tracking system.\n"
            f"Write exactly 1 to 3 concise sentences explaining the transformation logic for `{table_name}.{field_name}`.\n\n"
            f"We ALREADY KNOW it is derived from these upstream fields: {sources_str}.\n"
            f"Your ONLY job is to explain the math, aggregation, or logical transformation applied (e.g. 'Summed over group', 'Multiplied by 100', 'Passed directly as string').\n"
            f"Do NOT write any introduction or conclusion. Start directly with the explanation.\n\n"
            f"Reference Code:\n{snippets}\n\n"
            f"Reference Description:\n{desc}"
        )
        
        try:
             response = self.llm.invoke(prompt)
             content = response.content if hasattr(response, "content") else str(response)
             return content.strip()
        except Exception as e:
             logger.error(f"Failed to generate transformation summary: {e}")
             return f"Derived mechanically from {sources_str}."
