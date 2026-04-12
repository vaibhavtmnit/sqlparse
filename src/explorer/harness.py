import os
import json
from loguru import logger
from collections import deque
from pydantic import BaseModel
from typing import List, Dict, Any, Optional

from src.enricher.core import GraphEnricher

class QueueItem(BaseModel):
    table_name: str
    field_name: str
    trace_path: str = "" 

class ExplorerHarness:
    """
    Manages the long-running exploration flow using native Python queues.
    Implements exact structural extraction alongside the continuous LLM LineageWiki.
    """
    def __init__(self, enricher: GraphEnricher, llm: Any = None):
        if enricher is None:
            raise ValueError("GraphEnricher is required for Explorer operations.")
            
        self.enricher = enricher
        self.llm = llm
        
        self.queue = deque()
        self.visited = set()
        
        self.lineage_tree = {}
        # Structured memory for the AI (The LLM Wiki)
        self.lineage_wiki = {}
        
    def enqueue(self, table_name: str, field_name: str, trace_path: str = ""):
        # Standardize matching signature to prevent Infinite Loops / Cycle Recursion
        sig = f"{str(table_name).lower()}.{str(field_name).lower()}"
        if sig in self.visited:
            logger.debug(f"CYCLE PREVENTED: {sig} is already visited across this exploration.")
            return
            
        # Avoid requeuing elements currently active in the queue as well
        if any(f"{q.table_name}.{q.field_name}".lower() == sig for q in self.queue):
             return
             
        self.queue.append(QueueItem(table_name=table_name, field_name=field_name, trace_path=trace_path))
        logger.info(f"QUEUED: {sig}")
        
    def load_wiki(self) -> str:
        """Renders the entire running lineage wiki sequentially stringified."""
        wiki_text = ""
        for k, v in self.lineage_wiki.items():
            wiki_text += f"\n- **{k}**: {v}"
        return wiki_text
        
    def run(self, initial_table: str, initial_field: str):
        self.enqueue(initial_table, initial_field, trace_path=f"[{initial_table}.{initial_field}]")
        
        while self.queue:
            item = self.queue.popleft()
            sig = f"{item.table_name}.{item.field_name}".lower()
            self.visited.add(sig)
            
            logger.info(f"EXPLORING: {sig} (Queue Remaining: {len(self.queue)})")
            
            # Lazy import subagents to prevent circular dependencies
            try:
                from src.explorer.agents.scout import ContextScoutAgent
                from src.explorer.agents.alias_lineage import AliasAndLineageAgent
                from src.explorer.agents.summarizer import TransformationSummarizerAgent
            except ImportError as e:
                logger.error(f"Agent Import Failure: {e}. Check directory structure!")
                return None
                
            # STEP 1: SCOUT DB FOR CONTEXT BOUNDARIES
            scout = ContextScoutAgent(self.enricher)
            context = scout.run(item.table_name, item.field_name)
            
            if not context or not context.get("has_data"):
                logger.debug(f"DEAD END (No further AST code connections found for {sig})")
                self.lineage_wiki[sig] = "Leaf node or external system dependency. No further structural transformation found inside extracted code."
                continue
                
            # STEP 2: LINEAGE TRACE
            alias_agent = AliasAndLineageAgent(self.llm, self.enricher)
            wiki_context = self.load_wiki()
            lineage_results = alias_agent.run(item.table_name, item.field_name, context, wiki_context)
            
            # Safe structural binding
            if not lineage_results:
                 self.lineage_wiki[sig] = "Complex transformation logic exists but no further upstream target tables/fields were safely extracted."
                 continue
                 
            self.lineage_tree[sig] = {
                "sources": lineage_results,
                "trace": item.trace_path
            }
            
            # STEP 3: NARRATIVE
            summarizer = TransformationSummarizerAgent(self.llm)
            wiki_summary = summarizer.run(item.table_name, item.field_name, lineage_results, context)
            
            self.lineage_wiki[sig] = wiki_summary
            
            # Push new frontiers
            for source in lineage_results:
                src_tbl = source.get("source_table", "")
                src_fld = source.get("source_field", "")
                if src_tbl and src_fld:
                     new_trace = f"{item.trace_path} -> [{src_tbl}.{src_fld}]"
                     self.enqueue(src_tbl, src_fld, new_trace)
                
        logger.info(f"EXPLORATION COMPLETE. Mapped {len(self.visited)} unique logic layers.")
        return {
            "tree": self.lineage_tree,
            "wiki": self.lineage_wiki
        }
