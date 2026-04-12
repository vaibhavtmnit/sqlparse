import os
from loguru import logger
from collections import deque
from pydantic import BaseModel
from typing import Any

from src.separator.registry import EntityRegistry

class TreeQueueItem(BaseModel):
    table_name: str
    field_name: str
    trace_path: str = "" 

class TreeNativeHarness:
    """
    Manages the long-running exploration flow exclusively utilizing
    the raw AST EntityRegistry from CodeSeparator.
    """
    def __init__(self, registry: EntityRegistry, llm: Any = None):
        if registry is None:
            raise ValueError("EntityRegistry is required for Pure-Tree operations.")
            
        self.registry = registry
        self.llm = llm
        
        self.queue = deque()
        self.visited = set()
        
        self.lineage_tree = {}
        self.lineage_wiki = {}
        
    def enqueue(self, table_name: str, field_name: str, trace_path: str = ""):
        sig = f"{str(table_name).lower()}.{str(field_name).lower()}"
        if sig in self.visited:
            logger.debug(f"CYCLE PREVENTED: {sig} is already visited.")
            return
            
        if any(f"{q.table_name}.{q.field_name}".lower() == sig for q in self.queue):
             return
             
        self.queue.append(TreeQueueItem(table_name=table_name, field_name=field_name, trace_path=trace_path))
        logger.info(f"QUEUED: {sig}")
        
    def load_wiki(self) -> str:
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
            
            from src.explorer.tree_native.agents.navigator import TreeNodeNavigator
            from src.explorer.tree_native.agents.deep_scanner import DeepScannerAgent
            from src.explorer.tree_native.agents.synthesizer import WikiSynthesizerAgent
                
            # STEP 1: NAVIGATE AST
            navigator = TreeNodeNavigator(self.registry)
            nodes = navigator.find_relevant_nodes(item.table_name, item.field_name)
            
            if not nodes:
                logger.debug(f"DEAD END (No further AST structures reference {sig})")
                self.lineage_wiki[sig] = "Leaf node or external system dependency. Code trace vanished."
                continue
                
            # STEP 2: DEEP SCAN
            scanner = DeepScannerAgent(self.llm)
            wiki_context = self.load_wiki()
            lineage_results = scanner.run(item.table_name, item.field_name, nodes, wiki_context)
            
            if not lineage_results:
                 self.lineage_wiki[sig] = "Code structurally referenced target, but Scanner extracted no further upstream explicit pipelines (likely scalar)."
                 continue
                 
            self.lineage_tree[sig] = {
                "sources": lineage_results,
                "trace": item.trace_path
            }
            
            # STEP 3: SYNTHESIZE WIKI
            synthesizer = WikiSynthesizerAgent(self.llm)
            wiki_summary = synthesizer.run(item.table_name, item.field_name, lineage_results, nodes)
            self.lineage_wiki[sig] = wiki_summary
            
            # PUSH
            for source in lineage_results:
                src_tbl = source.get("source_table", "")
                src_fld = source.get("source_field", "")
                if src_tbl and src_fld:
                     new_trace = f"{item.trace_path} -> [{src_tbl}.{src_fld}]"
                     self.enqueue(src_tbl, src_fld, new_trace)
                
        logger.info(f"PURE-TREE EXPLORATION COMPLETE. Mapped {len(self.visited)} unique logic layers.")
        return {
            "tree": self.lineage_tree,
            "wiki": self.lineage_wiki
        }
