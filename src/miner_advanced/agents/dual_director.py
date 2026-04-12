"""
dual_director.py — Dual-Mode Execution Framework

Provides a single interface to execute Advanced Mining through either a 
Classic Supervisor Router architecture or an autonomous Multi-Agent DeepAgent.
"""

from typing import Any
from loguru import logger
from langchain_core.prompts import ChatPromptTemplate

from src.miner_advanced.models import AdvancedMiningResult
from src.miner_advanced.agents.director import MiningDirector # The classic LCEL fallback
from src.miner_advanced.tools import extract_field_candidates

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
    
    def __init__(self, llm: Any, execution_mode: str, registry: Any):
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
                self.deep_agent = MinerDeepAgent(
                    model=llm,
                    output_mode="pydantic",
                    # We inject our structured output using Custom tools if necessary
                    tools=[extract_field_candidates] 
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
        
        # Construct message payload explicitly referencing the context
        query = (
            f"You are inside a code block mapped to {source_mapping_id}.\n"
            f"Context Path: {context_str}\n"
            f"State Info:\n{chunk_context}\n\n"
            f"Please extract all entities, structured relationships with field-lineage mappings, "
            f"and sequential flows explicitly from this code:\n\n"
            f"```sql\n{code_text}\n```"
        )
        
        try:
            result = self.deep_agent.invoke(query)
            # The deep agent output mode 'pydantic' was hooked into MiningResult initially.
            # However, since we injected our prompt logic, if it returns dict we convert it to AdvancedMiningResult.
            
            # Defensive conversion parsing
            if hasattr(result, "structured_response") and result["structured_response"]:
                if isinstance(result["structured_response"], dict):
                     return AdvancedMiningResult.from_dict(result["structured_response"])
                
            return AdvancedMiningResult() # Base fallback
            
        except Exception as e:
            logger.error(f"DeepAgent pipeline failed: {e}")
            return AdvancedMiningResult()
