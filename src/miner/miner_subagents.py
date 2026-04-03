"""
miner_subagents.py

Defines structured SubAgentConfig classes for use with MinerDeepAgent.
Each subagent can be augmented with extra tools after construction, then
converted to a dict for use with create_deep_agent(subagents=[...]).
"""

from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional


class SubAgentConfig:
    """
    A lightweight wrapper around a deepagents SubAgent dict definition.

    Allows tools to be added after initial construction and supports
    conversion to the dict format expected by create_deep_agent().

    Usage::

        agent = SubAgentConfig(
            name="my-agent",
            description="Does something useful",
            system_prompt="You are a helpful assistant.",
        )
        agent.add_tool(my_tool)
        subagents = [agent.to_subagent_dict()]
    """

    def __init__(
        self,
        name: str,
        description: str,
        system_prompt: str,
        tools: Optional[List[Callable]] = None,
        model: Optional[str] = None,
    ):
        """
        Initialize a SubAgentConfig.

        Args:
            name: Unique name for the subagent (used in the task() tool call).
            description: Clear description of when and how to use this subagent.
            system_prompt: Detailed instructions for the subagent.
            tools: Initial list of callable tools.
            model: Optional model override (e.g. 'google_genai:gemini-2.5-flash').
                   If None, inherits from the main agent.
        """
        self.name = name
        self.description = description
        self.system_prompt = system_prompt
        self.tools: List[Callable] = list(tools or [])
        self.model = model

    def add_tool(self, tool: Callable) -> "SubAgentConfig":
        """
        Add a tool to this subagent's tool list.

        Args:
            tool: A callable (plain function or LangChain @tool) to add.

        Returns:
            self, for method chaining.
        """
        self.tools.append(tool)
        return self

    def add_tools(self, tools: List[Callable]) -> "SubAgentConfig":
        """
        Add multiple tools at once.

        Args:
            tools: List of callables to add.

        Returns:
            self, for method chaining.
        """
        self.tools.extend(tools)
        return self

    def to_subagent_dict(self) -> dict:
        """
        Convert this config to the dict format expected by create_deep_agent().

        Returns:
            A dict with keys: name, description, system_prompt, tools,
            and optionally model.
        """
        d: dict = {
            "name": self.name,
            "description": self.description,
            "system_prompt": self.system_prompt,
            "tools": self.tools,
        }
        if self.model is not None:
            d["model"] = self.model
        return d

    def __repr__(self) -> str:
        return (
            f"SubAgentConfig(name={self.name!r}, tools={[t.__name__ for t in self.tools]})"
        )


# =============================================================================
# Pre-built subagents for the SQL Miner
# =============================================================================


class ChunkContextSubAgent(SubAgentConfig):
    """
    Subagent that reads the current SQL chunk and the previous chunk details,
    then tells the MinerDeepAgent how the current chunk relates to previous ones.

    This agent does NOT write anything — it only analyzes and reports.
    Tools must be injected after creation via add_tool() / add_tools().
    Expected tools:
        - read_current_chunk()
        - get_recent_chunk_details(n)
    """

    _SYSTEM_PROMPT = """\
You are a SQL code context analyzer. Your job is to understand how the current
SQL code chunk relates to the previous processing context.

PROCESS:
1. Use the read_current_chunk tool to get the current SQL code.
2. Use the get_recent_chunk_details tool to get descriptions of the last 2 chunks
   (if they exist — if not, inform the main agent that no prior context is available).
3. Compare the current SQL code against the previous chunk descriptions.
4. Return a concise analysis covering:
   - What major constructs appear in the current chunk (packages, procedures, tables, etc.)
   - How this chunk continues from or diverges from the previous chunks.
   - Key entities that bridge between this chunk and previous chunks.
   - Whether the chunk appears to be a continuation, a new section, or standalone.

IMPORTANT:
- If prior chunk details do not exist, clearly say so and analyze only the current chunk.
- Keep your response under 400 words.
- Do NOT write anything to any files — only read and report.
"""

    def __init__(self, model: Optional[str] = None):
        super().__init__(
            name="chunk-context-analyzer",
            description=(
                "Analyzes the current SQL chunk and compares it against the previous "
                "chunk descriptions to determine continuity and context. Use this agent "
                "BEFORE mining entities/relationships to understand how the current chunk "
                "fits into the broader codebase flow."
            ),
            system_prompt=self._SYSTEM_PROMPT,
            tools=[],
            model=model,
        )


class ChunkDescriptionWriterSubAgent(SubAgentConfig):
    """
    Subagent that reads the current SQL chunk and previous chunk details,
    writes a rich description for the current chunk, and notifies the main
    agent upon success.

    Tools must be injected after creation via add_tool() / add_tools().
    Expected tools:
        - read_current_chunk()
        - get_recent_chunk_details(n)
        - write_chunk_detail(text)
    """

    _SYSTEM_PROMPT = """\
You are a SQL chunk documentation specialist. Your job is to write a clear,
comprehensive description of the current SQL code chunk.

PROCESS:
1. Use read_current_chunk to get the current SQL code.
2. Use get_recent_chunk_details to get the descriptions of the last 2 chunks
   for context (if they do not exist, note that and proceed with only the
   current chunk). Inform the main agent if no prior context is available.
3. Write a description for the current chunk. The description MUST cover:
   - MAJOR OPERATIONS: What major operation(s) are being performed
     (INSERT, UPDATE, CREATE, CALL, etc.)?
   - KEY ACTORS: What packages, procedures, functions, or triggers are
     executing these operations?
   - KEY OBJECTS: What tables, views, CTEs, sequences, or synonyms are
     being acted upon?
   - OVERALL PURPOSE: What is the business/technical purpose of this chunk?
   - CONTINUITY: Based on the previous chunk descriptions, how does this
     chunk connect to what came before? Is it a continuation, a new phase,
     or a standalone unit?
4. Use write_chunk_detail to save the description.
5. Return a SUCCESS confirmation with the gist of the description written.

STYLE GUIDELINES:
- Write in clear, concise prose (not bullet points).
- Length: 200–350 words.
- Refer to previous chunks naturally (e.g., "Continuing from the previous chunk
  which set up the staging tables, this chunk...").
- Do NOT include raw SQL code in the description.
"""

    def __init__(self, model: Optional[str] = None):
        super().__init__(
            name="chunk-description-writer",
            description=(
                "Reads the current SQL chunk and the descriptions of the previous 2 chunks, "
                "then writes a rich contextual description for the current chunk. The description "
                "covers operations performed, key actors, key objects, overall purpose, and "
                "continuity with previous chunks. Use this agent to document each chunk BEFORE "
                "mining entities and relationships."
            ),
            system_prompt=self._SYSTEM_PROMPT,
            tools=[],
            model=model,
        )


# =============================================================================
# Specialized mining subagents (Section 4 of instruction.md)
# =============================================================================


class EntityMinerSubAgent(SubAgentConfig):
    """
    Subagent responsible for extracting ALL entities from the current SQL chunk.

    Entities are Oracle SQL named objects (excluding column/field names):
    packages, procedures, functions, triggers, views, tables, sequences,
    synonyms, CTEs, types, etc.

    Tools must be injected after creation via add_tool() / add_tools().
    Expected tools:
        - read_current_chunk()
        - get_recent_chunk_details(n)     [for context only]
    """

    _SYSTEM_PROMPT = """\
You are a specialist Oracle SQL Entity Extractor. Your job is to find every
named Oracle SQL object in the current SQL chunk and return them as a JSON array.

WHAT IS AN ENTITY:
Any named SQL object EXCEPT column/field names. This includes:
  - PACKAGE, PACKAGE BODY
  - PROCEDURE, FUNCTION
  - TRIGGER
  - VIEW
  - TABLE
  - SEQUENCE, SYNONYM
  - CTE (Common Table Expression / WITH clause)
  - TYPE, TYPE BODY

PROCESS:
1. Use read_current_chunk to load the SQL code.
2. Use get_recent_chunk_details (n=2) to read the last two chunk descriptions
   for context. If they don't exist, note it and continue without them.
3. Scan the SQL code carefully and identify EVERY entity. Do not skip any.
4. For each entity, construct a record with these fields:
   - entity_name: Exact name from the SQL (e.g., PKG_ETL_LOADER, STAG_TABLE).
   - entity_type: Uppercase type (TABLE, PROCEDURE, PACKAGE, VIEW, CTE, etc.).
   - entity_description: 150-250 words covering:
       * What type of object is it and what is its declared purpose?
       * What operations are performed on or by this entity?
       * What other entities does it interact with in this chunk?
       * What data does it handle or produce?
       * If context from previous chunks is relevant, mention the continuity.
5. Return ALL entity records as a single JSON array. Example:
   [
     {
       "entity_name": "PKG_ETL_LOADER",
       "entity_type": "PACKAGE",
       "entity_description": "..."
     },
     ...
   ]

IMPORTANT RULES:
- Column names, variable names, and parameter names are NOT entities.
- Extract from the CURRENT CHUNK CODE only. Previous chunk details are context.
- Do NOT miss any entity — completeness is critical.
- The parent package or procedure of each entity should be noted in entity_description.
- Do NOT include chunk_id or flow_id — these are assigned externally by the run loop.
"""

    def __init__(self, model: Optional[str] = None):
        super().__init__(
            name="entity-miner",
            description=(
                "Extracts all Oracle SQL entities from the current chunk: packages, procedures, "
                "functions, triggers, views, tables, sequences, synonyms, CTEs, and types. "
                "Records each entity with a detailed description, returning a JSON array. "
                "Use this AFTER chunk-description-writer has documented the chunk."
            ),
            system_prompt=self._SYSTEM_PROMPT,
            tools=[],
            model=model,
        )


class RelationshipMinerSubAgent(SubAgentConfig):
    """
    Subagent responsible for extracting ALL relationships between entities
    in the current SQL chunk.

    A relationship captures how one Oracle SQL entity acts on or relates to another:
    calling, modifying, reading, joining, depending on, etc.

    Tools must be injected after creation via add_tool() / add_tools().
    Expected tools:
        - read_current_chunk()
        - get_recent_chunk_details(n)     [for cross-chunk relationship context]
        - get_last_n_entries(filename, n) [to check already-mined entities]
    """

    _SYSTEM_PROMPT = """\
You are a specialist Oracle SQL Relationship Extractor. Your job is to identify and
record all relationships between entities in the current SQL chunk.

RELATIONSHIP TAGS (use uppercase, pick the most specific):
  - INSERTS_INTO, UPDATES, DELETES_FROM, READS_FROM, MERGES_INTO
  - CALLS, EXECUTES, INVOKES
  - CREATES, DROPS, ALTERS, TRUNCATES
  - JOINS_WITH, REFERENCES, DEPENDS_ON
  - CONTAINS, DEFINES, OVERRIDES
  - TRIGGERS_ON (for triggers)
  - QUERIES (for views/CTEs querying tables)
  - POPULATES (when a procedure populates a table via a CTE/view)

PROCESS:
1. Use read_current_chunk to get the current SQL code.
2. Use get_recent_chunk_details (n=2) to understand the previous context.
   This is important because entities in the current chunk may relate to
   entities mentioned in previous chunks (e.g., a procedure started in the
   previous chunk is still the active parent here).
3. Use get_last_n_entries("entities.json", 20) to see what entities have
   already been recorded, to ensure relationship sources/targets are consistent.
4. Identify EVERY relationship in the code. For each:
   - source: The entity initiating the action (e.g., the procedure doing the insert).
   - target: The entity being acted upon (e.g., the table receiving the insert).
   - relationship_tag: A short uppercase tag (see list above).
   - confidence_score: 0.0 to 1.0 reflecting certainty from code evidence.
   - relationship_description: Under 200 words explaining what the relationship
     means in the context of this chunk and the broader script.
5. Return ALL relationship records as a single JSON array. Example:
   [
     {
       "source": "PROC_LOAD",
       "target": "STAG_TABLE",
       "relationship_tag": "INSERTS_INTO",
       "confidence_score": 1.0,
       "relationship_description": "..."
     },
     ...
   ]

HIERARCHY RULE:
The active PACKAGE or PROCEDURE is the parent/executor. Tables and views modified
within it have a relationship with it (e.g., PROC_A INSERTS_INTO TABLE_B).
Always capture the package/procedure → table relationships.

CROSS-CHUNK RELATIONSHIPS:
If the current chunk references an entity from a previous chunk (e.g., a package
declared previously), still create the relationship — use the previous chunk details
to confirm the entity name.

IMPORTANT:
- Do NOT skip any relationship — completeness is critical.
- Extract from the CURRENT CHUNK CODE only; prior chunk details are context.
- Each relationship must have a clear source and target (named SQL objects).
"""

    def __init__(self, model: Optional[str] = None):
        super().__init__(
            name="relationship-miner",
            description=(
                "Extracts all relationships between Oracle SQL entities in the current chunk: "
                "inserts, updates, calls, reads, joins, dependencies, triggers, etc. "
                "Also captures cross-chunk relationships where entities from previous chunks "
                "are referenced. Returns relationships as a JSON array. "
                "Use this AFTER entity-miner has recorded the entities."
            ),
            system_prompt=self._SYSTEM_PROMPT,
            tools=[],
            model=model,
        )


class FlowMinerSubAgent(SubAgentConfig):
    """
    Subagent responsible for building the structural code flow graph
    for the current SQL chunk.

    Flows capture how the code is organised (not necessarily execution order),
    from top-level containers (packages/procedures) down to the tables and
    objects they operate on.

    Tools must be injected after creation via add_tool() / add_tools().
    Expected tools:
        - read_current_chunk()
        - get_recent_chunk_details(n)     [for context]
        - get_last_five_flows()           [to check previous flow steps and continue]
    """

    _SYSTEM_PROMPT = """\
You are a specialist Oracle SQL Code Flow Builder. Your job is to construct a
structural flow graph that captures how the SQL code in the current chunk is organised
and return it as a JSON array.

WHAT IS A FLOW:
Flows represent code organisation and dependency — how the code is structured from
top-level containers down to the objects they act upon. Think of it as a tree:

  PACKAGE PKG_ETL (CONTAINER)
    └── PROCEDURE PROC_LOAD (EXECUTOR)
          └── CTE_STAGING (DEPENDENCY / INTERMEDIARY)
          └── TABLE_TARGET (TARGET — gets inserted into)
          └── TABLE_LOOKUP (DEPENDENCY — queried for lookups)

FLOW ENTITY ROLES:
  - CONTAINER: A package that contains procedures/functions.
  - EXECUTOR: A procedure or function that performs operations.
  - TARGET: A table/view that is the primary object being modified.
  - DEPENDENCY: A table/view/CTE/sequence queried or used to support the operation.
  - INTERMEDIARY: A CTE or temp structure used between executor and target.

FLOW ID NAMING:
Use sequential IDs continuing from the last flow. Call get_last_five_flows first to
determine the last used flow_id, then continue from there
(e.g., if the last was flow_042, new IDs start at flow_043, flow_044, …).
If no prior flows exist, start at flow_001.

PROCESS — PLAN FIRST, THEN EMIT:
Do NOT write any JSON until you have completed a full planning pass.

PLANNING PASS (do this in your reasoning before producing output):
  1. Call read_current_chunk to get the SQL code.
  2. Call get_recent_chunk_details (n=2) for continuity context.
  3. Call get_last_five_flows to find the last committed flow_id; determine your
     starting ID for this batch.
  4. Read the chunk top-to-bottom and list every entity that will become a flow step,
     in the order they appear.
  5. Assign a flow_id to each, top-down (parents always assigned before their children).
  6. For each entity, identify its parent in the hierarchy and note the parent's
     already-assigned flow_id as parent_flow_id.
     - Root-level entities (package body, top-level procedure) have parent_flow_id = null,
       unless a parent was established in a previous chunk (use get_last_five_flows).

EMIT PASS (only after planning is complete):
  Return ALL flow steps as a single JSON array, ordered parent-before-child.
  Because you assigned IDs top-down in the planning pass, every parent_flow_id
  you reference will already appear earlier in the same array — no forward references.

JSON FORMAT (do not include flow_entity_chunk_id — it is added externally):
  [
    {
      "flow_id": "flow_003",
      "flow_description": "Top-level ETL package container",
      "parent_flow_id": null,
      "flow_entity_name": "PKG_ETL",
      "flow_entity_type": "PACKAGE",
      "flow_entity_description": "...",
      "flow_entity_role": "CONTAINER",
      "flow_entity_parent_relation": null
    },
    {
      "flow_id": "flow_004",
      "flow_description": "Procedure that loads staging data",
      "parent_flow_id": "flow_003",
      "flow_entity_name": "PROC_LOAD",
      "flow_entity_type": "PROCEDURE",
      "flow_entity_description": "...",
      "flow_entity_role": "EXECUTOR",
      "flow_entity_parent_relation": "CONTAINED_BY"
    },
    ...
  ]

IMPORTANT:
- Capture ALL important entities in the flow — especially every table being modified.
- Maintain the hierarchy: package → procedure → tables/CTEs.
- If the chunk is a continuation of a procedure from the previous chunk, use the
  existing procedure's flow_id (from get_last_five_flows) as the parent_flow_id.
- Do NOT skip the active package/procedure context.
- Do NOT include flow_entity_chunk_id — it is stamped externally by the run loop.
"""

    def __init__(self, model: Optional[str] = None):
        super().__init__(
            name="flow-miner",
            description=(
                "Builds the structural code flow graph for the current SQL chunk. "
                "Creates flow steps from top-level packages/procedures down to the tables, "
                "CTEs, and views they operate on. Maintains hierarchy (CONTAINER → EXECUTOR → TARGET). "
                "Continues from previous flow steps to ensure cross-chunk flow continuity. "
                "Use this AFTER entity-miner and relationship-miner have run."
            ),
            system_prompt=self._SYSTEM_PROMPT,
            tools=[],
            model=model,
        )


# =============================================================================
# Convenience factory
# =============================================================================


def build_default_subagents(registry_tools: dict) -> list:
    """
    Build the complete set of subagents with their required tools injected.

    Five subagents are created:
      1. chunk-context-analyzer  — understands chunk continuity
      2. chunk-description-writer — writes chunk description
      3. entity-miner             — extracts all entities
      4. relationship-miner       — extracts all relationships
      5. flow-miner               — builds the structural flow graph

    Args:
        registry_tools: A dict mapping tool names to tool callables. Expected keys:
            "read_current_chunk", "get_recent_chunk_details", "write_chunk_detail",
            "get_last_n_entries", "get_last_five_flows"

    Returns:
        A list of five subagent dicts ready for use with create_deep_agent().

    Example::

        from src.miner.miner_tools import RegistryManager
        from src.miner.miner_subagents import build_default_subagents

        registry = RegistryManager("/my/workspace")
        tool_map = {t.name: t for t in registry.get_all_tools()}
        subagents = build_default_subagents(tool_map)
    """
    context_agent = ChunkContextSubAgent()
    context_agent.add_tool(registry_tools["read_current_chunk"])
    context_agent.add_tool(registry_tools["get_recent_chunk_details"])

    description_agent = ChunkDescriptionWriterSubAgent()
    description_agent.add_tool(registry_tools["read_current_chunk"])
    description_agent.add_tool(registry_tools["get_recent_chunk_details"])
    description_agent.add_tool(registry_tools["write_chunk_detail"])

    entity_agent = EntityMinerSubAgent()
    entity_agent.add_tool(registry_tools["read_current_chunk"])
    entity_agent.add_tool(registry_tools["get_recent_chunk_details"])

    relationship_agent = RelationshipMinerSubAgent()
    relationship_agent.add_tool(registry_tools["read_current_chunk"])
    relationship_agent.add_tool(registry_tools["get_recent_chunk_details"])
    relationship_agent.add_tool(registry_tools["get_last_n_entries"])

    flow_agent = FlowMinerSubAgent()
    flow_agent.add_tool(registry_tools["read_current_chunk"])
    flow_agent.add_tool(registry_tools["get_recent_chunk_details"])
    flow_agent.add_tool(registry_tools["get_last_five_flows"])

    return [
        context_agent.to_subagent_dict(),
        description_agent.to_subagent_dict(),
        entity_agent.to_subagent_dict(),
        relationship_agent.to_subagent_dict(),
        flow_agent.to_subagent_dict(),
    ]
