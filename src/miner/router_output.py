"""
router_output.py

Output processor for the MiningRouter. Takes the mining result (either
Pydantic MiningResult or plain dict) and persists it using the existing
RegistryManager write methods and the entity-flow LLM linkage logic.

This module reuses the existing persistence pipeline from miner.py:
  1. Stamp chunk_id on all flow steps → write_flows()
  2. Link entities to flows via LLM → _link_entities_to_flows()
  3. Stamp chunk_id on entities → write_entities()
  4. Write relationships → write_relationships()
"""

import json
import sys
from typing import Any, Union

from loguru import logger

from src.miner.models import MiningResult
from src.miner.miner_tools import RegistryManager

logger.remove()
logger.add(
    sys.stderr,
    colorize=True,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
)


def process_mining_output(
    result: Union[MiningResult, dict],
    chunk_id: str,
    registry: RegistryManager,
    llm: Any,
) -> None:
    """
    Take the router's mining output and persist all records.

    Handles both output formats:
      - ``MiningResult`` (Pydantic mode) — converted to dict via .to_dict()
      - ``dict`` (JSON mode) — used directly

    Args:
        result: The mining output, either a MiningResult or a dict with keys
                ``entities``, ``relationships``, ``flows``.
        chunk_id: String identifier for the current chunk (e.g. "0", "1").
        registry: The RegistryManager instance for file I/O.
        llm: The LLM instance for entity-flow linkage.
    """
    # ── Normalise to dict ─────────────────────────────────────────────
    if isinstance(result, MiningResult):
        data = result.to_dict()
        logger.debug(f"Output processor: converted MiningResult to dict")
    elif isinstance(result, dict):
        data = result
    else:
        logger.error(f"Output processor: unexpected result type {type(result)}")
        return

    entities = data.get("entities", [])
    relationships = data.get("relationships", [])
    flows = data.get("flows", [])

    logger.info(
        f"Output processor: chunk {chunk_id} — "
        f"{len(entities)} entities, "
        f"{len(relationships)} relationships, "
        f"{len(flows)} flows"
    )

    # ── Step 1: Stamp chunk_id on flows and persist ───────────────────
    for flow in flows:
        flow["flow_entity_chunk_id"] = chunk_id

    if flows:
        registry.write_flows(flows)
        logger.debug(f"Chunk {chunk_id}: persisted {len(flows)} flow step(s)")

    # ── Step 2: Link entities to flows via LLM ────────────────────────
    if entities:
        entities = _link_entities_to_flows(entities, flows, chunk_id, llm)

    # ── Step 3: Stamp chunk_id on entities and persist ────────────────
    for entity in entities:
        entity["chunk_id"] = chunk_id

    if entities:
        registry.write_entities(entities)
        assigned = sum(
            1 for e in entities if e.get("flow_id", "unassigned") != "unassigned"
        )
        logger.debug(
            f"Chunk {chunk_id}: persisted {len(entities)} entity/entities "
            f"({assigned} linked to a flow, {len(entities) - assigned} unassigned)"
        )

    # ── Step 4: Persist relationships ─────────────────────────────────
    if relationships:
        registry.write_relationships(relationships)
        logger.debug(f"Chunk {chunk_id}: persisted {len(relationships)} relationship(s)")


def _link_entities_to_flows(
    entities: list, flows: list, chunk_id: str, llm: Any
) -> list:
    """
    Use a direct LLM call to assign the correct flow_id to each entity.

    The LLM receives the compact flow hierarchy and entity names/types,
    and returns a JSON mapping of entity_name → flow_id.

    Falls back gracefully (all "unassigned") if the LLM call fails.

    Args:
        entities: List of entity dicts.
        flows: List of flow step dicts for this chunk.
        chunk_id: Used only for logging.
        llm: The LLM instance.

    Returns:
        The entities list with flow_id set on every record.
    """
    if not flows:
        for entity in entities:
            entity["flow_id"] = "unassigned"
        return entities

    # Build compact representations
    entities_payload = json.dumps(
        [{"entity_name": e["entity_name"], "entity_type": e["entity_type"]}
         for e in entities],
        indent=2,
    )
    flows_payload = json.dumps(
        [{
            "flow_id": f["flow_id"],
            "flow_entity_name": f["flow_entity_name"],
            "flow_entity_type": f["flow_entity_type"],
            "flow_entity_role": f["flow_entity_role"],
            "parent_flow_id": f.get("parent_flow_id"),
            "flow_description": f["flow_description"],
        } for f in flows],
        indent=2,
    )

    prompt = (
        "You are a SQL code analysis assistant.\n\n"
        "You are given two lists extracted from the same SQL code chunk:\n"
        "  1. ENTITIES  — named SQL objects found in the chunk.\n"
        "  2. FLOW STEPS — a hierarchical tree describing code structure.\n\n"
        "Task: For each entity return the flow_id of the flow step it most logically "
        "belongs to.\n\n"
        "Rules:\n"
        "- If an entity IS the flow_entity_name of a flow step (exact match, "
        "case-insensitive), assign that flow step's flow_id.\n"
        "- If an entity participates in a flow step as a TARGET, DEPENDENCY, or "
        "INTERMEDIARY (even if it is not the flow_entity_name of that step), assign "
        "the flow_id of the most specific (deepest) flow step it is part of.\n"
        "- If no confident match exists, use \"unassigned\".\n\n"
        "Return ONLY a flat JSON object — no markdown, no explanation:\n"
        "{\n"
        '  "ENTITY_NAME": "flow_id",\n'
        "  ...\n"
        "}\n\n"
        f"ENTITIES:\n{entities_payload}\n\n"
        f"FLOW STEPS:\n{flows_payload}"
    )

    try:
        response = llm.invoke(prompt)
        content = response.content if hasattr(response, "content") else str(response)
        content = content.strip()

        # Strip markdown fences if present
        if content.startswith("```"):
            lines = content.splitlines()
            content = "\n".join(
                line for line in lines if not line.strip().startswith("```")
            ).strip()

        mapping: dict = json.loads(content)

        # Normalise keys to uppercase for case-insensitive matching
        mapping_upper = {k.strip().upper(): v for k, v in mapping.items()}

        for entity in entities:
            key = entity["entity_name"].strip().upper()
            entity["flow_id"] = mapping_upper.get(key, "unassigned")

        logger.debug(
            f"Chunk {chunk_id}: LLM linked "
            f"{sum(1 for e in entities if e['flow_id'] != 'unassigned')}/"
            f"{len(entities)} entities to flows"
        )

    except Exception as exc:
        logger.warning(
            f"Chunk {chunk_id}: entity-flow LLM linkage failed ({exc}). "
            f"Falling back to 'unassigned' for all entities."
        )
        for entity in entities:
            entity["flow_id"] = "unassigned"

    return entities
