"""
orchestrator.py — Advanced Miner Orchestrator.

Walks the Separator Tree and pipes code into the multi-agent downstream
system. Handles >600 line Semantic Chunking automatically.
"""

import os
import json
from pathlib import Path
from datetime import datetime
from typing import Any, List, Optional
from loguru import logger

from src.utils.chunker import SQLChunker
from src.miner_advanced.state import MinerStateContext
from src.miner_advanced.models import AdvancedMiningResult

from src.miner_advanced.agents.dual_director import DualModeMiningDirector
from src.miner_advanced.tools import _set_global_registry

class MinerAdvancedOrchestrator:
    """
    Drives the Separator AST traversal, creates execution workspaces,
    and handles intelligent chunking for massive >600 line entities.
    """
    
    def __init__(
        self, 
        registry: Any, 
        llm: Any, 
        chunk_threshold: int = 600, 
        overlap: int = 20,
        chunking_mode: str = "lines",       # 'lines' or 'tokens'
        execution_mode: str = "deepagent",  # 'router' or 'deepagent'
        workspace_dir: Optional[str] = None
    ):
        self.registry = registry
        self.chunk_threshold = chunk_threshold
        self.overlap = overlap
        self.chunking_mode = chunking_mode
        self.execution_mode = execution_mode
        
        # Bind registry to global tools
        _set_global_registry(registry)
        
        self.state = MinerStateContext(registry)
        
        # Create output workspace
        if workspace_dir:
            self.workspace_dir = Path(workspace_dir)
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.workspace_dir = Path(f"miner_advanced_workspace_{timestamp}")
        
        self.workspace_dir.mkdir(parents=True, exist_ok=True)

        # Inject Multi-Agent Pipeline
        self.director = DualModeMiningDirector(
            llm=llm, 
            execution_mode=execution_mode, 
            registry=registry,
            workspace_dir=str(self.workspace_dir)
        )
        
        # Add a specific log file for this run
        log_file = self.workspace_dir / "miner_run.log"
        logger.add(
            log_file, 
            format="{time:HH:mm:ss} | {level: <10} | {message}", 
            level="DEBUG"
        )
        logger.info(f"Initialized MinerAdvancedOrchestrator workspace at {self.workspace_dir}")

    @classmethod
    def from_registry_file(
        cls, 
        registry_path: str, 
        llm: Any, 
        **kwargs
    ) -> "MinerAdvancedOrchestrator":
        """Factory method to initialize from a saved Separator Registry JSON."""
        from src.separator.registry import EntityRegistry
        registry = EntityRegistry.load_from_file(registry_path)
        logger.info(f"Loaded registry from {registry_path} ({registry.count} entities)")
        return cls(registry=registry, llm=llm, **kwargs)

    def run(self) -> dict:
        """Entrypoint for processing all parsed entities from top to bottom."""
        roots = self.registry.get_roots()
        
        results_aggregator = {
            "entities": [],
            "relationships": [],
            "flows": []
        }
        
        for root in roots:
            self._traverse_and_mine(root.entity_id, results_aggregator)
            
        # Final persistence of all findings
        output_file_entities = self.workspace_dir / "entities.json"
        with open(output_file_entities, 'w', encoding='utf-8') as f:
            json.dump(results_aggregator.get("entities", []), f, indent=2)
            
        output_file_rels = self.workspace_dir / "relationships.json"
        with open(output_file_rels, 'w', encoding='utf-8') as f:
            json.dump(results_aggregator.get("relationships", []), f, indent=2)
            
        output_file_flows = self.workspace_dir / "flows.json"
        with open(output_file_flows, 'w', encoding='utf-8') as f:
            json.dump(results_aggregator.get("flows", []), f, indent=2)
            
        logger.info(f"Mining fully complete. Output explicitly split and saved to {self.workspace_dir}")
        return results_aggregator

    def _traverse_and_mine(self, entity_id: str, aggregator: dict):
        """Recursively walks the tree, pushing breadcrumbs, and mining code."""
        entry = self.registry.get(entity_id)
        if not entry:
            return
            
        self.state.push_breadcrumb(entity_id)
        
        # Mine this entity based on its code length
        code_lines = entry.resolved_code.strip().splitlines()
        total_lines = len(code_lines)
        
        logger.info(f"Processing Array: {entry.entity_name} ({total_lines} lines)")
        
        if total_lines > self.chunk_threshold:
            self._process_in_chunks(entry, aggregator)
        elif total_lines > 0:
            self._process_single(entry, aggregator)
            
        # Recurse into children
        children = self.registry.get_children(entity_id)
        for child in children:
            self._traverse_and_mine(child.entity_id, aggregator)
            
        self.state.pop_breadcrumb()

    def _process_single(self, entry: Any, aggregator: dict):
        """Passes the entire block of code to the miner."""
        source_mapping_id = entry.entity_id
        
        logger.debug(f"Direct process: {source_mapping_id}")
        
        if self.director:
            result: AdvancedMiningResult = self.director.mine(
                code_text=entry.resolved_code,
                context_str=self.state.get_context_string(),
                chunk_context="",
                source_mapping_id=source_mapping_id,
                raw_chunk_ids=entry.chunk_ids
            )
            self._merge_results(result, aggregator)

    def _process_in_chunks(self, entry: Any, aggregator: dict):
        """Intelligently chunks code using strict token limits or naive lines."""
        code_str = entry.resolved_code
        
        if self.chunking_mode == "tokens":
            chunks = self._chunk_by_tokens(code_str)
        else:
            chunker = SQLChunker(code_str, window_size=int(self.chunk_threshold / 2), overlap=self.overlap)
            chunks = list(chunker)
            
        logger.info(f"Entity {entry.entity_name} split into {len(chunks)} chunks [{self.chunking_mode} mode].")
        
        base_mapping_id = entry.entity_id
        self.state.init_scratchpad(total_chunks=len(chunks), source_id=base_mapping_id)
        
        for c in chunks:
            chk_mapping_id = f"{base_mapping_id}#chk_{c.chunk_id}"
            logger.debug(f"Chunk process: {chk_mapping_id}")
            
            if self.director:
                result: AdvancedMiningResult = self.director.mine(
                    code_text=c.chunk_text,
                    context_str=self.state.get_context_string(),
                    chunk_context=self.state.get_chunk_context_string(),
                    source_mapping_id=chk_mapping_id,
                    raw_chunk_ids=entry.chunk_ids
                )
                
                # Update scratchpad so the next chunk knows what happened
                if self.state.active_scratchpad:
                    self.state.active_scratchpad.append_results(
                        entities=[e.model_dump() for e in result.entities],
                        relationships=[r.model_dump() for r in result.relationships],
                        flows=[f.model_dump() for f in result.flows]
                    )
                
                self._merge_results(result, aggregator)
                
        self.state.clear_scratchpad()

    def _chunk_by_tokens(self, code_str: str) -> list:
        """Splits code greedily preserving line boundaries up to a token limit."""
        import tiktoken
        from src.utils.chunker import Chunk

        enc = tiktoken.get_encoding("cl100k_base")
        lines = code_str.splitlines()
        chunks = []
        
        current_chunk_lines = []
        current_tokens = 0
        chunk_id = 0
        
        # Determine actual token limit (use chunk_threshold as surrogate if >0)
        # e.g., if chunk_threshold = 3000, we split at 3000 tokens
        limit = self.chunk_threshold if self.chunk_threshold > 1000 else 3000 
        
        for line in lines:
            # Approx tokens for line
            toks = len(enc.encode(line))
            if current_tokens + toks > limit and current_chunk_lines:
                chunks.append(Chunk(chunk_id=chunk_id, chunk_text="\\n".join(current_chunk_lines)))
                chunk_id += 1
                # Overlap logic: keep last 'overlap' lines from previous
                if self.overlap > 0 and len(current_chunk_lines) > self.overlap:
                    current_chunk_lines = current_chunk_lines[-self.overlap:]
                    current_tokens = sum(len(enc.encode(l)) for l in current_chunk_lines)
                else:
                    current_chunk_lines = []
                    current_tokens = 0
                    
            current_chunk_lines.append(line)
            current_tokens += toks
            
        if current_chunk_lines:
             chunks.append(Chunk(chunk_id=chunk_id, chunk_text="\\n".join(current_chunk_lines)))
             
        return chunks

    def _merge_results(self, result: AdvancedMiningResult, aggregator: dict):
        d = result.to_dict()
        aggregator["entities"].extend(d.get("entities", []))
        aggregator["relationships"].extend(d.get("relationships", []))
        aggregator["flows"].extend(d.get("flows", []))
