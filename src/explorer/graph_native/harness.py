import os
from loguru import logger
from collections import deque
from pydantic import BaseModel
from typing import Any

from src.enricher.core import GraphEnricher

class GraphQueueItem(BaseModel):
    table_name: str
    field_name: str
    trace_path: str = "" 

class GraphNativeHarness:
    """
    Manages long-running exploration solely based on pre-mined JSON Edges and nodes.
    Tightly integrated with NetworkX to deterministically solve paths bypassing LLMs.
    """
    def __init__(self, enricher: GraphEnricher, llm: Any = None):
        if enricher is None:
            raise ValueError("GraphEnricher is required for Graph-Native operations.")
            
        self.enricher = enricher
        self.llm = llm
        
        self.queue = deque()
        self.visited = set()
        
        self.lineage_tree = {}
        self.lineage_wiki = {}
        
        # Instantiate NetworkX Programmatic Engine
        from src.explorer.graph_native.agents.network_analyzer import NetworkXAnalyzer
        self.network = NetworkXAnalyzer(self.enricher)
        
    def enqueue(self, table_name: str, field_name: str, trace_path: str = ""):
        sig = f"{str(table_name).lower()}.{str(field_name).lower()}"
        if sig in self.visited:
            logger.debug(f"CYCLE PREVENTED: {sig}")
            return
            
        if any(f"{q.table_name}.{q.field_name}".lower() == sig for q in self.queue):
             return
             
        self.queue.append(GraphQueueItem(table_name=table_name, field_name=field_name, trace_path=trace_path))
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
            
            logger.info(f"EXPLORING [GRAPH NATIVE]: {sig} (Queue: {len(self.queue)})")
            
            # STEP 1: Fast NetworkX Programmatic Bypass
            lineage_results = self.network.get_upstream_sources(item.table_name, item.field_name)
            
            from src.explorer.graph_native.agents.scout_graph import GraphRelationshipScout
            from src.explorer.graph_native.agents.metadata_inference import MetadataInferenceAgent
            from src.explorer.graph_native.agents.synthesizer import WikiSynthesizerAgent
            
            scout = GraphRelationshipScout(self.enricher)
            context = scout.run(item.table_name, item.field_name)
            
            if not lineage_results:
                # Fallback to LLM AI parsing of JSON dictionaries
                logger.info("NetworkX edge missing, falling back to JSON Metadata Inference AI.")
                
                if not context.get("has_data"):
                    logger.debug(f"DEAD END (No further Edges or Code blocks for {sig})")
                    self.lineage_wiki[sig] = "Leaf node or external data."
                    continue
                    
                inference = MetadataInferenceAgent(self.llm)
                lineage_results = inference.run(item.table_name, item.field_name, context, self.load_wiki())
            
            if not lineage_results:
                 self.lineage_wiki[sig] = "Failed to extract logical source targets from Edges."
                 continue
                 
            self.lineage_tree[sig] = {
                "sources": lineage_results,
                "trace": item.trace_path
            }
            
            # STEP 2: SYNTHESIZE WIKI
            # The AI just reads the JSON to build the English logic strings
            synthesizer = WikiSynthesizerAgent(self.llm)
            wiki_summary = synthesizer.run(item.table_name, item.field_name, lineage_results, context)
            
            # Programmatic logic injection from graph if we natively solved it
            if self.network.graph and "Deterministically" in wiki_summary:
                 for r in lineage_results:
                      st, sf = r.get("source_table"), r.get("source_field")
                      if st and sf:
                           trans = self.network.get_transformation_logic(item.table_name, item.field_name, st, sf)
                           wiki_summary += f" ({trans})"

            self.lineage_wiki[sig] = wiki_summary
            
            # STEP 3: QUEUE DESCENDANTS
            for source in lineage_results:
                src_tbl = source.get("source_table", "")
                src_fld = source.get("source_field", "")
                if src_tbl and src_fld:
                     new_trace = f"{item.trace_path} -> [{src_tbl}.{src_fld}]"
                     self.enqueue(src_tbl, src_fld, new_trace)
                
        logger.info(f"GRAPH-NATIVE COMPLETE. Handled {len(self.visited)} paths.")
        return {
            "tree": self.lineage_tree,
            "wiki": self.lineage_wiki
        }
