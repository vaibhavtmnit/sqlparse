"""
director.py — DeepAgent Mining Director

Coordinates the multi-agent execution pipeline. It delegates initial extraction
to the base miner, then pipes relationships requiring field-level lineage analysis
to the specialized Field Lineage worker.
"""

import re
import time
from typing import List, Any
from loguru import logger
from pydantic import BaseModel
from langchain_core.prompts import ChatPromptTemplate

from src.miner_advanced.models import (
    AdvancedMiningResult, 
    AdvancedRelationshipRecord
)
from src.miner_advanced.tools import extract_field_candidates

class FieldLineageUpdate(BaseModel):
    """Temporary model to enforce structured output from the Lineage Agent."""
    updated_relationships: List[AdvancedRelationshipRecord]


class MiningDirector:
    """
    Directs the DeepAgent pipeline.
    
    Workflow:
    1. Base Miner: Extracts Entities, Relationships, Flows natively.
    2. Field Lineage Miner: Uses python execution outputs and code review to map columns.
    """
    
    def __init__(self, llm: Any, max_retries: int = 10):
        self.llm = llm
        self.max_retries = max_retries
        
        # Agents configured with their respective structured outputs
        self.base_miner_agent = self.llm.with_structured_output(AdvancedMiningResult)
        self.field_lineage_agent = self.llm.with_structured_output(FieldLineageUpdate)
        
        # Lightweight Scout Agent (Agentic Fallback for programmatic failures)
        scout_prompt = ChatPromptTemplate.from_messages([
            ("system", 
             "You are a specialized SQL Field Extraction Scout.\n"
             "Your goal is to extract ALL uniquely named column/field accesses from the SQL code.\n"
             "Return ONLY a comma-separated list of the fields you find. No explanation."
            ),
            ("user", "SQL Code:\n```sql\n{code_text}\n```")
        ])
        self.field_scout_agent = scout_prompt | self.llm
        
    def mine(
        self, 
        code_text: str, 
        context_str: str, 
        chunk_context: str, 
        source_mapping_id: str, 
        raw_chunk_ids: list[int]
    ) -> AdvancedMiningResult:
        """Entrypoint for the orchestrator to process a block of code."""
        
        logger.info(f"Director dispatched Agent Pipeline for block: {source_mapping_id}")
        
        # ---------------------------------------------------------
        # PHASE 1: Base Mining (Entities, Relationships, Flows)
        # ---------------------------------------------------------
        base_prompt = ChatPromptTemplate.from_messages([
            ("system", 
             "You are an expert Oracle SQL Miner. Your goal is to extract Entities, "
             "Relationships, and Code Flows from the provided SQL code.\n\n"
             "Breadcrumb Context (Where you are in the codebase):\n{context_str}\n\n"
             "Chunk Progression Info (Avoid duplicating prior outputs):\n{chunk_context}\n\n"
             "Rules:\n"
             "- Ensure Relationship direction is EXACT: Target (modified) <- Source (read).\n"
             "- Extract flow processes sequentially.\n"
             "- You are capturing high-level relationships here, do not worry about field-level yet.\n"
             "IMPORTANT: Assign the exactly provided `source_mapping_id` to every record you extract."
            ),
            ("user", "source_mapping_id to use: {mapping_id}\n\nSQL Code:\n```sql\n{code_text}\n```")
        ])
        
        for attempt in range(1, self.max_retries + 1):
            if attempt > 1:
                logger.log("RETRY", f"🔄 Retry {attempt}/{self.max_retries} for base mining: {source_mapping_id}")

            try:
                result: AdvancedMiningResult = (base_prompt | self.base_miner_agent).invoke({
                    "context_str": context_str,
                    "chunk_context": chunk_context,
                    "mapping_id": source_mapping_id,
                    "code_text": code_text
                })
                
                # Defensive programming: ensure tags aren't missed by the LLM
                if result:
                    for e in result.entities:
                        e.source_mapping_id = source_mapping_id
                        e.raw_chunk_ids = raw_chunk_ids
                    for r in result.relationships:
                        r.source_mapping_id = source_mapping_id
                    for f in result.flows:
                        f.source_mapping_id = source_mapping_id
                else:
                    result = AdvancedMiningResult()
                
                # If we got here, it succeeded
                break 
                    
            except Exception as e:
                exc_str = str(e)
                logger.error(f"  ❌ Base Miner Agent failed: {exc_str}")
                
                # Handle Rate Limiting (429 / RESOURCE_EXHAUSTED)
                if "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str:
                    wait_match = re.search(r"retry in (\d+\.?\d*)s", exc_str)
                    wait_time = float(wait_match.group(1)) if wait_match else 10.0
                    wait_time = min(wait_time, 60.0)
                    logger.warning(f"  ⏳ Rate limited. Sleeping for {wait_time}s before retry...")
                    time.sleep(wait_time)
                
                if attempt == self.max_retries:
                    return AdvancedMiningResult()
            
        # ---------------------------------------------------------
        # PHASE 2: Field Lineage Worker
        # ---------------------------------------------------------
        if result.relationships:
            logger.info(f"  -> Sending {len(result.relationships)} relations to Field Lineage Agent.")
            result = self._extract_field_lineage(result, code_text, source_mapping_id)
            
        return result
        
    def _extract_field_lineage(
        self, 
        result: AdvancedMiningResult, 
        code_text: str,
        source_mapping_id: str
    ) -> AdvancedMiningResult:
        """Runs the hybrid Python + LLM Field Lineage deep analysis."""
        
        # Hybrid Tooling: Have python parse fields natively to save LLM reasoning tokens
        field_hints = extract_field_candidates.invoke({"sql_text": code_text})
        
        # AGENTIC FALLBACK: If programmatic extraction failed or was flagged as needing fallback
        if "PROGRAMMATIC_PARSER_FAILED" in field_hints or "NEEDS_AGENTIC_FALLBACK" in field_hints:
            logger.info(f"  🔄 Programmatic parser hit complex syntax. Launching Agentic Field Scout for {source_mapping_id}...")
            try:
                scout_response = self.field_scout_agent.invoke({"code_text": code_text})
                # Handle both AIMessage and raw string (depending on LC version/config)
                scout_text = getattr(scout_response, 'content', str(scout_response))
                field_hints = f"AGENTIC SCOUT RESULTS (Text-based extraction):\n{scout_text}\n\n(Original Parser Error: {field_hints})"
            except Exception as e:
                logger.warning(f"  ⚠ Field Scout Agent failed too: {e}")
        
        lineage_prompt = ChatPromptTemplate.from_messages([
            ("system", 
             "You are a specialized Field-Level Data Lineage Agent.\n"
             "Review the given SQL block and enrich the provided Relationships with "
             "strict `field_mappings` (target_field <- source_fields).\n"
             "Rules:\n"
             "- Include Aliases if present.\n"
             "- Deduce logical mappings like CASE WHEN or SUM() in `transformation_logic`.\n"
             "- Preserve ALL other properties of the input relationships verbatim.\n\n"
             "Hints extracted from programmatic tools:\n{field_hints}"
            ),
            ("user", 
             "SQL Code:\n```sql\n{code_text}\n```\n\n"
             "Current Relationships to Enrich:\n{relationships}"
            )
        ])
        
        for attempt in range(1, self.max_retries + 1):
            if attempt > 1:
                logger.log("RETRY", f"🔄 Retry {attempt}/{self.max_retries} for field lineage: {source_mapping_id}")

            try:
                # Serialize relations for the prompt
                rels_dump = [r.model_dump() for r in result.relationships]
                
                update: FieldLineageUpdate = (lineage_prompt | self.field_lineage_agent).invoke({
                    "field_hints": field_hints,
                    "code_text": code_text,
                    "relationships": str(rels_dump)
                })
                
                if update and update.updated_relationships:
                    # Re-apply mapping ids just in case LLM lost them during reconstruction
                    for r in update.updated_relationships:
                        r.source_mapping_id = source_mapping_id
                    result.relationships = update.updated_relationships
                    logger.info(f"  ✓ Field lineage mapping complete.")
                
                # Succeed
                break

            except Exception as e:
                exc_str = str(e)
                logger.warning(f"  ⚠ Field Lineage Agent failed: {exc_str}")
                
                 # Handle Rate Limiting (429 / RESOURCE_EXHAUSTED)
                if "429" in exc_str or "RESOURCE_EXHAUSTED" in exc_str:
                    wait_match = re.search(r"retry in (\d+\.?\d*)s", exc_str)
                    wait_time = float(wait_match.group(1)) if wait_match else 10.0
                    wait_time = min(wait_time, 60.0)
                    logger.warning(f"  ⏳ Rate limited. Sleeping for {wait_time}s before retry...")
                    time.sleep(wait_time)

                if attempt == self.max_retries:
                    logger.warning(f"  ❌ Max retries reached for field lineage. Keeping base results.")
            
        return result
