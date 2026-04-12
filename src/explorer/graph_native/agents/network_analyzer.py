from loguru import logger
from typing import List, Dict, Any

class NetworkXAnalyzer:
    """
    Constructs a strict Graph Theory NetworkX Directed Graph out of the 
    AI-mined JSON Relationships. Enables deterministic field-to-field tracking
    without forcing constant LLM parsing tokens!
    """
    def __init__(self, enricher):
        self.enricher = enricher
        self.graph = None
        self._build_graph()
        
    def _build_graph(self):
        try:
            import networkx as nx
            # MultiDiGraph allows multiple distinct transformation edges between same fields 
            # if they exist across different conditions/chunks.
            self.graph = nx.MultiDiGraph()
            
            if not hasattr(self.enricher, 'relationships_df') or self.enricher.relationships_df.empty:
                logger.warning("NETWORKX: No Graph Enriched relationships available. Graph empty.")
                return
                
            for _, row in self.enricher.relationships_df.iterrows():
                src_tbl = str(row.get('source')).lower()
                tgt_tbl = str(row.get('target')).lower()
                
                fm_list = row.get('field_mappings', [])
                if not isinstance(fm_list, list):
                     continue
                     
                for fm in fm_list:
                     if not isinstance(fm, dict): continue
                     sf = fm.get('source_field')
                     tf = fm.get('target_field')
                     trans = fm.get('transformation_logic', 'Mapped upstream deterministically.')
                     
                     # Check if sf is a list (e.g. multiple source fields map to one target)
                     sources = sf if isinstance(sf, list) else [sf]
                     
                     for s in sources:
                          if s and tf:
                              s = str(s).lower()
                              t = str(tf).lower()
                              src_node = f"{src_tbl}.{s}"
                              tgt_node = f"{tgt_tbl}.{t}"
                              
                              self.graph.add_edge(
                                   src_node, 
                                   tgt_node,
                                   transformation=trans,
                                   source_table=src_tbl,
                                   source_field=s
                              )
            
            logger.info(f"NETWORKX Engine Ready: Instantiated Directed Graph with {self.graph.number_of_nodes()} nodes and {self.graph.number_of_edges()} deterministic mapped operations.")
        except ImportError:
            logger.error("NETWORKX module not installed!")
            
    def get_upstream_sources(self, table_name: str, field_name: str) -> List[Dict[str, str]]:
        if not self.graph:
            return []
            
        target_node = f"{str(table_name).lower()}.{str(field_name).lower()}"
        
        if not self.graph.has_node(target_node):
             logger.debug(f"NETWORKX: Target {target_node} not explicitly mapped in mathematical graph.")
             return []
             
        predecessors = list(self.graph.predecessors(target_node))
        
        results = []
        for p in predecessors:
             parts = p.split('.')
             if len(parts) >= 2:
                  results.append({"source_table": parts[0], "source_field": parts[1]})
                  
        if results:
             logger.info(f"NETWORKX: Programmatically extracted Lineage for {target_node} -> {results}")
             
        return results
        
    def get_transformation_logic(self, table_name: str, field_name: str, src_table: str, src_field: str) -> str:
        """Retrieves the explicit text written during mapping between the fields."""
        if not self.graph: return ""
        
        tn = f"{str(table_name).lower()}.{str(field_name).lower()}"
        sn = f"{str(src_table).lower()}.{str(src_field).lower()}"
        
        if self.graph.has_edge(sn, tn):
             # Just pull the first mapping edge between them
             edge_data = self.graph.get_edge_data(sn, tn)
             if edge_data and 0 in edge_data:
                  return str(edge_data[0].get('transformation', 'Computed from source.'))
        return "Mapped internally from relations."
