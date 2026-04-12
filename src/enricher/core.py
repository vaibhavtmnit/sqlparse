"""
core.py - Miner Graph Enricher Engine

Aggregates structured JSON outputs into Pandas Dataframes, resolves bidirectional
relationships, and exposes a high-level API to instantly retrieve code chunks
from the AST based precisely on LLM constraints.
"""
import os
import pandas as pd
import json
from typing import List, Dict, Any, Optional

try:
    from rapidfuzz import process, fuzz
except ImportError:
    pass

def _dedup_list(items):
    """Deep flattens a list-like structure and heavily deduplicates it, preserving dict representations safely."""
    res = []
    if not isinstance(items, (list, tuple, set)):
        items = [items]
        
    for i in items:
        if isinstance(i, list):
             res.extend(_dedup_list(i))
        elif pd.notna(i) if not isinstance(i, (dict, list)) else True:
            # Drop null scalars, but keep empty dicts/lists if meaningful
            res.append(i)
            
    # Serialize dicts temporarily to string to guarantee uniqueness safely
    unique_res = []
    seen = set()
    for x in res:
        if isinstance(x, dict):
            sig = json.dumps(x, sort_keys=True)
            if sig not in seen:
                seen.add(sig)
                unique_res.append(x)
        else:
            if x not in seen:
                seen.add(x)
                unique_res.append(x)
                
    return unique_res

class GraphEnricher:
    """
    Connects aggregated Pandas dataframes to the Code AST.
    """
    def __init__(self, registry: Any, entities_json: str, relationships_json: str, flows_json: str):
        self.registry = registry
        
        self.entities_df = self._aggregate_entities(entities_json)
        self.relationships_df = self._aggregate_relationships(relationships_json)
        self.flows_df = self._aggregate_flows(flows_json)
        
    def _aggregate_entities(self, path: str) -> pd.DataFrame:
        if not os.path.exists(path):
            return pd.DataFrame()
        try:
            df = pd.read_json(path)
        except Exception:
            return pd.DataFrame()
            
        if df.empty:
            return df
            
        return df.groupby('entity_name', as_index=False).agg(lambda x: _dedup_list(x.tolist()))

    def _aggregate_relationships(self, path: str) -> pd.DataFrame:
        if not os.path.exists(path):
             return pd.DataFrame()
        try:
            df = pd.read_json(path)
        except Exception:
            return pd.DataFrame()
            
        if df.empty:
            return df
            
        def get_edge_sig(row):
            s, t = str(row.get('source', '')), str(row.get('target', ''))
            return f"{s}::{t}" if s < t else f"{t}::{s}"
            
        df['edge_sig'] = df.apply(get_edge_sig, axis=1)
        
        # We also need confidence scoring
        if 'confidence_score' not in df.columns:
             df['confidence_score'] = 1.0
             
        grouped_edges = []
        for sig, group in df.groupby('edge_sig'):
            # Determine direction
            direction_conf = group.groupby(['source', 'target'])['confidence_score'].sum().reset_index()
            # Sort highest confidence to the top
            direction_conf = direction_conf.sort_values(by='confidence_score', ascending=False)
            
            best_source = direction_conf.iloc[0]['source']
            best_target = direction_conf.iloc[0]['target']
            
            agg_row = {
                'source': best_source,
                'target': best_target
            }
            # Agg properties
            for col in group.columns:
                if col not in ['source', 'target', 'edge_sig']:
                    agg_row[col] = _dedup_list(group[col].tolist())
                    
            grouped_edges.append(agg_row)
            
        return pd.DataFrame(grouped_edges)

    def _aggregate_flows(self, path: str) -> pd.DataFrame:
        if not os.path.exists(path):
             return pd.DataFrame()
        try:
            df = pd.read_json(path)
        except Exception:
            return pd.DataFrame()
            
        if df.empty:
            return df
            
        # Optional: flow_entity_name is sometimes present instead of flow_id
        group_key = 'flow_id' if 'flow_id' in df.columns else 'flow_entity_name'
        if group_key not in df.columns:
             return df
             
        return df.groupby(group_key, as_index=False).agg(lambda x: _dedup_list(x.tolist()))
        
    # --- QUERY INTERFACE ---
    
    def find_entities(self, pattern: str) -> List[dict]:
        """
        Locates an entity by exact match, substring, or RapidFuzz limiting to Top 2 constraints.
        Returns a list of matching Entity Dictionary rows.
        """
        if self.entities_df.empty or 'entity_name' not in self.entities_df.columns:
            return []
            
        names = self.entities_df['entity_name'].tolist()
        
        # 1. Exact Match
        if pattern in names:
            return self.entities_df[self.entities_df['entity_name'] == pattern].to_dict('records')
            
        # 2. Substring Match
        substring_matches = [n for n in names if pattern.lower() in str(n).lower()]
        if substring_matches:
            # We enforce Top 2 boundary
            return self.entities_df[self.entities_df['entity_name'].isin(substring_matches[:2])].to_dict('records')
            
        # 3. Fuzzy Match via rapidfuzz
        try:
            from rapidfuzz import process, fuzz
            matches = process.extract(pattern, names, scorer=fuzz.WRatio, limit=2)
            # Match returns list of (choice, score, index)
            # If the score gap is massive or lowest score is really bad, assume No Match.
            valid_names = []
            for choice, score, idx in matches:
                if score >= 60.0:  # Threshold constraint: If poor match, ignore
                    valid_names.append(choice)
                    
            if valid_names:
                 return self.entities_df[self.entities_df['entity_name'].isin(valid_names)].to_dict('records')
        except ImportError:
             pass
             
        # No matches found matching safety criteria
        return []

    def get_relationships(self, entity_name: str) -> List[dict]:
        """Returns all aggregated relationships where entity is either source or target."""
        if self.relationships_df.empty or 'source' not in self.relationships_df.columns:
            return []
            
        mask = (self.relationships_df['source'] == entity_name) | (self.relationships_df['target'] == entity_name)
        return self.relationships_df[mask].to_dict('records')
        
    def find_relationships_by_field(self, entity_name: str, field_name: str) -> List[dict]:
        """
        Locates a relationship heavily involving specific data lineage targeting a field column.
        We inspect `field_mappings` dictionaries: e.g. [{"target_field": "net_salary"}] 
        combined recursively from all chunks!
        """
        relations = self.get_relationships(entity_name)
        matched = []
        
        field_lower = field_name.lower()
        
        for r in relations:
            fields_list = r.get("field_mappings", [])
            is_match = False
            # Flatten because fields_list might actually be deeply nested from the agg
            flat_fields = _dedup_list(fields_list)
            for fm in flat_fields:
                if not isinstance(fm, dict):
                    # We accept comma separated raw string hints if field mapping broke
                    if isinstance(fm, str) and field_lower in fm.lower():
                        is_match = True
                        break
                    continue
                    
                target = str(fm.get("target_field", "")).lower()
                source_f = [str(x).lower() for x in fm.get("source_fields", [])]
                
                if field_lower in target or any(field_lower in s for s in source_f):
                    is_match = True
                    break
                    
            if is_match:
                matched.append(r)
                
        return matched

    def get_entity_info(self, entity_name: str) -> dict:
        """Returns aggregated info for the entity explicitly."""
        records = self.entities_df[self.entities_df['entity_name'] == entity_name].to_dict('records')
        return records[0] if records else {}

    def get_code_for_source_mappings(self, mapping_ids: list) -> Dict[str, str]:
        """
        The critical logic converting Abstract Lineage IDs (e.g. ent_123#chk_1) into Raw SQL Code blocks!
        Requires the class initialized `registry`.
        """
        if not self.registry:
            return {"error": "No AST Registry bound."}
            
        flat_maps = _dedup_list(mapping_ids)
        result_code = {}
        
        for m_id in flat_maps:
            if not isinstance(m_id, str):
                continue
                
            parts = m_id.split("#chk_")
            entity_id = parts[0]
            
            entry = self.registry.get(entity_id)
            if not entry:
                result_code[m_id] = "-- ENTITY NOT FOUND IN AST --"
                continue
                
            if len(parts) == 1:
                # Direct Entity (No chunks) - Just give its entire code
                result_code[m_id] = entry.resolved_code
            else:
                # Exact chunk retrieval via the saved chunk_ids
                try:
                    target_chunk_id = int(parts[1])
                    if target_chunk_id in entry.chunk_ids:
                        from src.utils.chunker import SQLChunker
                        # Note: We must mimic the threshold orchestration config
                        # We use 300 since threshold default 600 / 2 = 300.
                        # For robustness, just grab everything for now.
                        chunker = SQLChunker(entry.resolved_code, window_size=300, overlap=20)
                        for c in chunker:
                            if c.chunk_id == target_chunk_id:
                                result_code[m_id] = c.chunk_text
                                break
                    if m_id not in result_code:
                         result_code[m_id] = "-- CHUNK METADATA MISSING --"
                except Exception as e:
                     result_code[m_id] = f"-- PARSER ERROR: {e} --"
                     
        return result_code
