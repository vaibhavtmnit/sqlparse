"""
dual_director.py — Dual-Mode Execution Framework

Provides a single interface to execute Advanced Mining through either a 
Classic Supervisor Router architecture or an autonomous Multi-Agent DeepAgent.
"""

import os
import re
import time
from pathlib import Path
from typing import Any

from src.miner_advanced.models import AdvancedMiningResult
from src.miner_advanced.agents.director import MiningDirector # The classic LCEL fallback
from src.miner_advanced.tools import extract_field_candidates, fetch_entity_code
from src.miner.miner_tools import RegistryManager
from src.miner.miner_subagents import build_default_subagents

try:
    from src.miner.miner_deepagent import MinerDeepAgent
except ImportError:
    MinerDeepAgent = None

class DualModeMiningDirector:
    """
    Executes mining instructions based on the requested Engine Mode.
    
    Modes:
      - 'deepagent': Loads the legacy framework's robust LangGraph system, 
                     injecting our extended structured schemas.
      - 'router': Uses exactly defined Router-Supervisor routines.
    """
    
    def __init__(self, llm: Any, execution_mode: str, registry: Any, workspace_dir: str = "."):
        self.llm = llm
        self.execution_mode = execution_mode
        self.registry = registry
        
        # LCEL simple director acts as basis for Router mode
        self.lcel_router = MiningDirector(llm=self.llm)
        
        if execution_mode == "deepagent":
            if not MinerDeepAgent:
                logger.error("MinerDeepAgent not found. Falling back to router mode.")
                self.execution_mode = "router"
            else:
                # Initialize Storage Registry (legacy format) for DeepAgent tools
                self.reg_manager = RegistryManager(workspace_dir)
                
                # Combine all tools
                legacy_tools = self.reg_manager.get_all_tools()
                advanced_tools = [extract_field_candidates, fetch_entity_code]
                all_tools = legacy_tools + advanced_tools
                
                # Build subagents with the tool map
                tool_map = {t.name: t for t in all_tools}
                subagents = build_default_subagents(tool_map)
                
                self.deep_agent = MinerDeepAgent(
                    model=llm,
                    output_mode="pydantic",
                    tools=all_tools,
                    subagents=subagents,
                    log_dir=str(Path(self.reg_manager.root) / "mining" / "logs")
                )

    def mine(
        self, 
        code_text: str, 
        context_str: str, 
        chunk_context: str, 
        source_mapping_id: str, 
        raw_chunk_ids: list[int]
    ) -> AdvancedMiningResult:
        """Executes the proper engine."""
        
        if self.execution_mode == "deepagent":
            return self._run_deepagent(code_text, context_str, chunk_context, source_mapping_id, raw_chunk_ids)
        else:
            return self._run_router(code_text, context_str, chunk_context, source_mapping_id, raw_chunk_ids)

    def _run_router(
        self, 
        code_text: str, 
        context_str: str, 
        chunk_context: str, 
        source_mapping_id: str, 
        raw_chunk_ids: list[int]
    ) -> AdvancedMiningResult:
        """
        Mode A: Supervisor Router approach. 
        Context agent sets the scene implicitly via LCEL sequential piping.
        """
        logger.info("[MODE: ROUTER] Delegating via strictly ordered Supervisor")
        return self.lcel_router.mine(code_text, context_str, chunk_context, source_mapping_id, raw_chunk_ids)

    def _run_deepagent(
        self, 
        code_text: str, 
        context_str: str, 
        chunk_context: str, 
        source_mapping_id: str, 
        raw_chunk_ids: list[int]
    ) -> AdvancedMiningResult:
        """
        Mode B: DeepAgent autonomous routing logic.
        """
        logger.info("[MODE: DEEPAGENT] Delegating via LangGraph Autonomous Tools")
        
        # Persist chunk to state file so tools can read it
        if hasattr(self, "reg_manager"):
            os.makedirs(os.path.dirname(self.reg_manager.current_chunk_path), exist_ok=True)
            with open(self.reg_manager.current_chunk_path, "w", encoding="utf-8") as f:
                f.write(code_text)
        
        user_query = (
            f"You are inside a code block mapped to {source_mapping_id}.\n"
            f"Context Path: {context_str}\n"
            f"State Info:\n{chunk_context}\n\n"
            f"Please extract all entities, structured relationships with field-lineage mappings, "
            f"and sequential flows explicitly from this code:\n\n"
            f"```sql\n{code_text}\n```"
        )
        
        result = None
        for attempt in range(1, 4):
            try:
                result = self.deep_agent.invoke(user_query)
                break
            except Exception as e:
                exc_str = str(e)
                logger.error(f"[DEEPAGENT] Attempt {attempt} failed: {exc_str}")
                if "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str:
                    wait_match = re.search(r"retry in (\d+\.?\d*)s", exc_str)
                    wait_time = float(wait_match.group(1)) if wait_match else 15.0
                    wait_time = min(wait_time, 60.0) 
                    logger.warning(f"  ⏳ [DEEPAGENT] Rate limited. Sleeping {wait_time}s...")
                    time.sleep(wait_time)
                
                if attempt == 3:
                     logger.error("[DEEPAGENT] Final attempt failed. Returning empty results.")
                     return AdvancedMiningResult()

        try:
            # The result from DeepAgent (pydantic mode) should be MiningResult (legacy)
            # We need to convert it to AdvancedMiningResult and inject source_mapping_id
            from src.miner_advanced.models import AdvancedEntityRecord, AdvancedRelationshipRecord, AdvancedFlowRecord
            
            adv_result = AdvancedMiningResult()
            
            # If the agent returned a structured response
            structured = getattr(result, "structured_response", None) or (
                result.get("structured_response") if isinstance(result, dict) else None
            )
            
            if structured:
                # entities
                for ent in getattr(structured, "entities", []):
                    adv_result.entities.append(AdvancedEntityRecord(
                        entity_name=ent.entity_name,
                        entity_type=ent.entity_type,
                        entity_description=ent.entity_description,
                        source_mapping_id=source_mapping_id,
                        raw_chunk_ids=raw_chunk_ids
                    ))
                # relationships
                for rel in getattr(structured, "relationships", []):
                    adv_result.relationships.append(AdvancedRelationshipRecord(
                        target=rel.target,
                        source=rel.source,
                        relationship_tag=rel.relationship_tag,
                        relationship_description=rel.relationship_description,
                        confidence_score=rel.confidence_score,
                        source_mapping_id=source_mapping_id
                    ))
                # flows
                for flo in getattr(structured, "flows", []):
                    adv_result.flows.append(AdvancedFlowRecord(
                        flow_id=flo.flow_id,
                        flow_description=flo.flow_description,
                        parent_flow_id=flo.parent_flow_id,
                        flow_entity_name=flo.flow_entity_name,
                        flow_entity_type=flo.flow_entity_type,
                        flow_entity_description=flo.flow_entity_description,
                        flow_entity_role=flo.flow_entity_role,
                        flow_entity_parent_relation=flo.flow_entity_parent_relation,
                        source_mapping_id=source_mapping_id
                    ))
            
            return adv_result
            
        except Exception as e:
            logger.error(f"DeepAgent results parsing failed: {e}")
            return AdvancedMiningResult()
