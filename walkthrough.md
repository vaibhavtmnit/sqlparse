# SQL Miner Execution Flow

This document details the exact sequence of events, tool calls, and subagent invocations when `SQLMiner.run()` is executed. It illustrates how the system breaks down codebase context and orchestrates the LangChain `MinerDeepAgent`.

## System Execution Flow Diagram

```mermaid
sequenceDiagram
    participant Miner as SQLMiner Loop
    participant Reg as RegistryManager
    participant Agent as MinerDeepAgent (LLM)
    participant SubContext as Context Subagent
    participant SubDesc as Description Subagent
    participant SubEntity as Entity Subagent
    participant SubRel as Relationship Subagent
    participant SubFlow as Flow Subagent
    participant Linker as LLM (Linkage Pass)

    Miner->>Reg: clean_workspace_files()
    Miner->>Miner: Chunker breaks SQL into chunks
    loop For Each Chunk
        Miner->>Reg: write_chunk_to_archive()
        Miner->>Reg: save current_chunk.sql
        Miner->>Agent: _run_core_mining(chunk_index)

        note over Agent: STEP 1: Understand continuity
        Agent->>Reg: Tool: read_current_chunk()
        Agent-->>SubContext: task("chunk-context-analyzer")
        SubContext->>Reg: Tool: get_recent_chunk_details()
        SubContext-->>Agent: Returns continuity analysis text

        note over Agent: STEP 2: Document Context
        Agent-->>SubDesc: task("chunk-description-writer")
        SubDesc->>Reg: Tool: write_chunk_detail()
        SubDesc-->>Agent: Returns "SUCCESS"

        note over Agent: STEP 3 (Mental): Track Parent Container

        note over Agent: STEP 4: Entities
        Agent-->>SubEntity: task("entity-miner")
        SubEntity->>SubEntity: Parses Chunk
        SubEntity-->>Agent: Returns clean JSON Array

        note over Agent: STEP 5: Relationships
        Agent-->>SubRel: task("relationship-miner")
        SubRel->>Reg: Tool: get_last_n_entries("entities.json")
        SubRel-->>Agent: Returns clean JSON Array

        note over Agent: STEP 6: Flows
        Agent-->>SubFlow: task("flow-miner")
        SubFlow->>Reg: Tool: get_last_five_flows()
        SubFlow-->>Agent: Returns clean JSON Array

        note over Agent: STEP 7: Final Assemble
        Agent-->>Miner: Emits final message containing JSON markdown blocks

        note over Miner: Phase 4: Persistence
        Miner->>Miner: _parse_agent_result() extracts JSON
        Miner->>Reg: write_flows() (stamps chunk_id)
        Miner->>Linker: _link_entities_to_flows()
        Linker-->>Miner: Returns {Entity: Flow_ID} mapping
        Miner->>Reg: write_entities() (stamps flow_id & chunk_id)
        Miner->>Reg: write_relationships()
    end
```

## Step-by-Step Breakdown

### Phase 1: Setup & Pre-processing

When you initiate the routine using `miner.run(sql_code)`:

1. **Workspace Clear**: `RegistryManager` clears out existing data safely from the `mining/output` and `mining/state` directories using `clean_workspace_files()`.
2. **Chunking Engine**: The `SQLChunker` divides the long code string into overlapping functional fragments defined by your `window_size` and `overlap`.

### Phase 2: Starting the Loop (`_run_core_mining`)

For each individual code block (`chunk_index`), the loop:

1. Archives the code permanently to `output/chunks/<id>.sql`.
2. Temporarily registers it to `state/current_chunk.sql`.
3. Injects 5 mapped `LangChain` subagents alongside the standard local file-reading registry tools into the primary `MinerDeepAgent`.

### Phase 3: The Orchestrator's Deep Agent Processing

Driven by the `miner_prompt.md` instructions, the overarching LLM instance now manages the work queue for the chunk:

1. **Context Initialization**: The agent calls `read_current_chunk` for itself and triggers the **`chunk-context-analyzer`** via the subagent `task` framework. The subagent compares the active file with `get_recent_chunk_details()` to tell the orchestrator where we are in the script's lifespan.
2. **Documentation**: It passes control to **`chunk-description-writer`**, a dedicated subagent allowed to invoke `write_chunk_detail` so later modules have fresh memory context saved into the registry.
3. **Entity Extraction**: Invokes **`entity-miner`**. The miner scopes through the codebase explicitly grabbing packages, triggers, queries, etc., bypassing variables, and returns a JSON array back strictly to the delegating agent.
4. **Relationship Linking**: Invokes **`relationship-miner`**. Since previous objects might overlap with the current chunk, this sub-bot uses `get_last_n_entries` reading `entities.json` dynamically to maintain relational continuity. Returns a JSON array.
5. **Architectural Hierarchy**: Invokes **`flow-miner`**. Queries previous flows via `get_last_five_flows` so nested execution identifiers run uninterrupted. Returns a sequential JSON array.
6. **Data Compilation**: The master `MinerDeepAgent` gathers the subagent arrays and responds back to the python script directly with defined `**Entities**`, `**Relationships**`, and `**Flows**` regex boundaries.

### Phase 4: Parsing and Final File Writing (`_persist_result`)

The agent's text stream exits out back to your standard Python loop:

1. `_parse_agent_result` strips out the surrounding Markdown output via regex matching and extracts the exact python arrays.
2. **Flows** immediately get annotated with the current `chunk_id` and are saved to `flows.json` via the registry manager.
3. An explicit LLM-powered AI mapping pass occurs (`_link_entities_to_flows`). Using just the JSON payloads, it figures out specifically what flow ID context every entity belongs to inside this exact chunk.
4. Finally, **Entities** (now augmented with `chunk_id` and `flow_id`) and **Relationships** are committed to their output tables via the `RegistryManager` batch writers (`write_entities`, `write_relationships`).

## Explanation

Viewed miner_subagents.py:1-250
Viewed miner_subagents.py:240-500
Viewed miner_subagents.py:500-566

After thoroughly reviewing `miner_subagents.py` and the tool injection factory, I can confirm that the subagents and their injected tools **perfectly align** with the pure stateless-handoff philosophy we established for DeepAgent.

Here is exactly why the architecture aligns with deep agent best practices:

### 1. Zero Mutation Side-Effects for Extractors

The primary philosophy of a stable LLM data pipeline is: **"Extractors should extract, orchestrators should orchestrate, and code should persist."**

- If we look at `EntityMinerSubAgent`, `RelationshipMinerSubAgent`, and `FlowMinerSubAgent`, they have been stripped of all tools that manipulate data on disc.
- They are only injected with read-only tools: `read_current_chunk`, `get_recent_chunk_details`, `get_last_n_entries`, and `get_last_five_flows`.
- **Why this matters:** The LLM cannot accidentally overwrite previous files, corrupt JSON tables, or run into race conditions. It behaves as a pure function: `(SQL Code, Context Tools) -> JSON Array String`.

### 2. Controlled Mutation for Meta-State

The only subagent allowed to break the "no-write" rule is the `chunk-description-writer`.

- It explicitly receives the `write_chunk_detail` tool.
- **Why this matters:** A deep agent system needs a form of "short-term memory", otherwise the context window explodes. By giving this single, rigidly scoped subagent the job of writing a textual summary to disk, the later chunk windows have a simple text file they can query for "What happened previously?" without needing to parse heavy JSON files or raw prior code. It's an elegant ledger system.

### 3. Prompt Constraints Force "Chain of Thought"

Deep agents often fail when they try to jump the gun. We avoid this by utilizing strict prompt schemas:

- In the `FlowMinerSubAgent` prompt, the LLM is explicitly mandated to perform a **"PLANNING PASS (do this in your reasoning before producing output)"**. It forces the LLM to call `get_last_five_flows`, assign sequential IDs top-down in its mental draft, and only _then_ map out the JSON Array. This mitigates "forward-reference" bugs (a common LLM JSON error where it assigns a child to a parent ID it hasn't generated yet).
- The `RelationshipMinerSubAgent` doesn't just guess relationships based on the chunk layout; it is forced to use `get_last_n_entries("entities.json")` to look up the canonical names of previously found entities before linking them.

### 4. Tool Precision (The Injection Factory)

In the `build_default_subagents` function, tools are injected strictly on a "need-to-know" basis.

- The `entity-miner` does not get the `get_last_five_flows` tool.
- The `flow-miner` does not get the `get_last_n_entries` tool.
- The main orchestrator (`MinerDeepAgent`) doesn't get _any_ of the writing tools, meaning it is impossible for the orchestrator to accidentally write raw text to a JSON table.

**Conclusion:** The subagent configuration provides the flexibility of multiple LLM brains (LangChain Agents) but boxes them into strict data pipelines safely regulated by the Python orchestration loop. This acts exactly as a production-level DeepAgent system should flow.
