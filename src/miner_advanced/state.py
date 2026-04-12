"""
state.py — Advanced Miner State Tracker.

Manages Breadcrumb generation from Separator trees and maintains Scratchpad state
across multiple chunks of a single massive entity block.
"""

from typing import List, Dict, Any, Optional

class ScratchpadArea:
    """Stores intermediate results across chunk boundaries of a single massive entity."""
    def __init__(self, total_chunks: int):
        self.total_chunks = total_chunks
        self.current_chunk_idx = 0
        self.found_relationships: List[Dict[str, Any]] = []
        self.found_entities: List[Dict[str, Any]] = []
        self.found_flows: List[Dict[str, Any]] = []
        self.agent_notes: str = ""  # For the Langchain DeepAgent memory
        
        # Deep Level Context
        self.alias_registry: Dict[str, str] = {}
        self.variable_state: Dict[str, str] = {}

    def append_results(self, entities: List[dict], relationships: List[dict], flows: List[dict]):
        self.found_entities.extend(entities)
        self.found_relationships.extend(relationships)
        self.found_flows.extend(flows)
        self.current_chunk_idx += 1


class MinerStateContext:
    """Tracks position inside the Separator Tree and manages active chunking state."""
    def __init__(self, registry: Any):
        self.registry = registry
        self.breadcrumb_trail: List[str] = []
        self.active_scratchpad: Optional[ScratchpadArea] = None
        self.current_source_id: str = ""
        
    def push_breadcrumb(self, entity_id: str):
        """Append an entity's context to the hierarchical trail."""
        entry = self.registry.get(entity_id)
        if entry:
            desc = entry.description or ""
            one_liner = " ".join(desc.split())[:100]
            if len(desc) > 100:
                one_liner += "..."
            crumb = f"[{entry.entity_name} ({entry.entity_type}) - {one_liner}]"
            self.breadcrumb_trail.append(crumb)
    
    def pop_breadcrumb(self):
        """Remove the last breadcrumb when crawling back up the tree."""
        if self.breadcrumb_trail:
            self.breadcrumb_trail.pop()
            
    def get_context_string(self) -> str:
        """Returns the formatted hierarchical path."""
        if not self.breadcrumb_trail:
            return "Top Level Script"
        return " >\n".join(self.breadcrumb_trail)
        
    def init_scratchpad(self, total_chunks: int, source_id: str):
        """Initialize a new memory block when a large entity gets chunked."""
        self.current_source_id = source_id
        self.active_scratchpad = ScratchpadArea(total_chunks)
        
    def clear_scratchpad(self):
        """Clean memory tracking after the entity finishes."""
        self.active_scratchpad = None
        self.current_source_id = ""

    def get_chunk_context_string(self) -> str:
        """String format of previous learnings to prevent hallucinated duplicate extraction."""
        if not self.active_scratchpad:
            return "Processed as Single Block."
        
        s = self.active_scratchpad
        
        # Format variables cleanly
        aliases_str = "\n".join(f"  - {k} -> {v}" for k, v in s.alias_registry.items()) or "  - [None yet]"
        vars_str = "\n".join(f"  - {k}: {v}" for k, v in s.variable_state.items()) or "  - [None yet]"
        
        ctx = (
            f"Chunk Status: {s.current_chunk_idx} of {s.total_chunks} processed.\n"
            f"Entities Found Earlier: {len(s.found_entities)}\n"
            f"Relations Found Earlier: {len(s.found_relationships)}\n"
            f"Iterative Notes: {s.agent_notes}\n\n"
            f"== ALIAS REGISTRY ==\n{aliases_str}\n\n"
            f"== VARIABLE STATE ==\n{vars_str}"
        )
        return ctx
