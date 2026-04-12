import json
from loguru import logger
from typing import List, Dict, Any

from src.enricher.core import GraphEnricher
from src.explorer.harness import ExplorerHarness
from src.explorer.tree_native.harness import TreeNativeHarness
from src.explorer.graph_native.harness import GraphNativeHarness
from src.pipeline.link_inference import LinkageInferenceAgent

class DaisyChainOrchestrator:
    """
    Given an ordered sequential list of script structures (Stage 1 -> Stage 2),
    it dynamically bounces backward passing downstream dependencies flawlessly
    up to the next AI Explorer interface.
    """
    def __init__(self, llm: Any):
        self.llm = llm
        
    def execute(self, target_table: str, target_field: str, ordered_enrichers: List[GraphEnricher], explorer_type: str = "hybrid"):
        logger.info(f"DAISY_CHAIN: Initiating Multi-Hop Sequence backward from target [{target_table}.{target_field}]")
        
        current_targets = [{"source_table": target_table, "source_field": target_field}]
        global_trace = {}
        
        # We evaluate backwards to follow dependency logic properly.
        # e.g., if array is [Staging, Core, DM], we evaluate DM first.
        reversed_enrichers = list(reversed(ordered_enrichers))
        
        for idx, enc in enumerate(reversed_enrichers):
             logger.info(f"\n=========================================\nDAISY SEQUENCE HOP: STAGE {len(reversed_enrichers)-idx} (Hop {idx+1}/{len(reversed_enrichers)})\n=========================================")
             
             if not current_targets:
                  logger.warning(f"DAISY_CHAIN: Extraction completely halted at Stage {idx}. No deeper mappings sent backwards.")
                  break
                  
             # Step 1: Infer boundary mapping aliases (skip on first iteration since User provided accurate target)
             if idx > 0:
                  inference = LinkageInferenceAgent(self.llm)
                  current_targets = inference.run(current_targets, enc)
                  logger.info(f"DAISY_CHAIN Context Bridged -> {current_targets}")
                  
             # Step 2: Determine appropriate Execution Harness
             harness = None
             if explorer_type == "tree_native":
                  if not hasattr(enc, "registry"):
                       raise ValueError("Tree-Native requires Enricher to cache pure Registry objects.")
                  harness = TreeNativeHarness(enc.registry, self.llm)
             elif explorer_type == "graph_native":
                  harness = GraphNativeHarness(enc, self.llm)
             else:
                  harness = ExplorerHarness(enc, self.llm)
                  
             # Step 3: Harvest
             stage_sources = []
             for tgt in current_targets:
                  st = tgt.get("source_table")
                  sf = tgt.get("source_field")
                  if not st or not sf:
                       continue
                       
                  # Execute the core engine internally on THIS exact script chunk graph!
                  results = harness.run(st, sf)
                  
                  # Append all trace contexts
                  for k, mapping in results.get("tree", {}).items():
                       global_trace[f"ScriptBoundary_{len(reversed_enrichers)-idx}::" + k] = mapping
                       
                       # We collect the bottom layer dependencies of THIS stage 
                       # to pass into the NEXT stage!
                       stage_sources.extend(mapping.get("sources", []))
                       
             # Step 4: De-duplicate sources before next hop
             dedup = []
             seen = set()
             for src in stage_sources:
                  sig = f"{str(src.get('source_table'))}.{str(src.get('source_field'))}"
                  if sig not in seen and src.get('source_table'):
                       dedup.append(src)
                       seen.add(sig)
             current_targets = dedup
             
        logger.info(f"DAISY CHAINING COMPLETED! Traced up {len(ordered_enrichers)} scripts!")
        return global_trace
