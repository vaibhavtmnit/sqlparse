"""
miner_tools.py

Contains the RegistryManager class for managing mining output files,
plus LangChain-compatible tool functions for reading/writing SQL chunks
and chunk details.
"""

import json
import os
from pathlib import Path
from typing import Any
from loguru import logger
from langchain.tools import tool
import sys
logger.remove()
logger.add(sys.stderr, colorize=True, format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>")

logger.level("Tool Execution",no=15,color="<light-magenta>",icon="🛠️")
logger.level("Registry Operation",no=18,color="<light-green>",icon="💾")

class RegistryManager:
    """
    Manages the mining output registry: JSON files for relationships,
    entities, and flows. NOT a LangChain-compatible class itself; instead,
    it exposes methods from which LangChain tools are built.

    Usage:
        registry = RegistryManager("/path/to/workspace")
        tool_fn = registry.add_relationship_tool()
    """

    def __init__(self, directory: str):
        """
        Initialize the RegistryManager.

        Args:
            directory: Root workspace directory. All paths derived from this.
        """
        self.root = directory
        self.relationships_path = directory + "/mining/output/relationships.json"
        self.entities_path = directory + "/mining/output/entities.json"
        self.flows_path = directory + "/mining/output/flows.json"
        self.current_chunk_path = directory + "/mining/state/current_chunk.sql"
        self.chunk_details_dir = directory + "/mining/output/chunk_details"
        self.chunks_dir = directory + "/mining/output/chunks"
        self.logs_dir = directory + "/mining/logs"

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    def _ensure_dir(self, file_path: str) -> None:
        """Create parent directories for file_path if they don't exist."""
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)

    def _append_to_file(self, path: str, data: dict) -> dict:
        """
        Read existing JSON list from path, auto-increment id, append data,
        and write back. Creates the file (and parent dirs) if it doesn't exist.

        Args:
            path: Absolute path to a JSON file that stores a list of dicts.
            data: The record to append (without id; id is auto-assigned).

        Returns:
            The record that was appended (with id set).
        """
        self._ensure_dir(path)

        # Load existing entries
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                try:
                    entries: list = json.load(f)
                    if not isinstance(entries, list):
                        entries = []
                except json.JSONDecodeError:
                    entries = []
        else:
            entries = []

        # Determine next id
        if entries:
            last_id = entries[-1].get("id", len(entries) - 1)
            new_id = last_id + 1
        else:
            new_id = 0

        record = {"id": new_id, **data}
        entries.append(record)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)

        return record

    def _read_last_n(self, path: str, n: int) -> list:
        """Return last n entries from a JSON list file."""
        if not os.path.exists(path):
            return []
        with open(path, "r", encoding="utf-8") as f:
            try:
                entries = json.load(f)
                if not isinstance(entries, list):
                    return []
            except json.JSONDecodeError:
                return []
        return entries[-n:] if n > 0 else entries

    # -------------------------------------------------------------------------
    # Chunk archive (raw SQL chunks store)
    # -------------------------------------------------------------------------

    def write_chunk_to_archive(self, chunk_text: str) -> str:
        """
        Write a raw SQL chunk to the numbered archive directory
        (mining/output/chunks). Files are named 0001.sql, 0002.sql, etc.
        The number is auto-incremented based on existing files.

        Args:
            chunk_text: The raw SQL code for this chunk.

        Returns:
            The path of the file written.
        """
        chunks_dir = Path(self.chunks_dir)
        chunks_dir.mkdir(parents=True, exist_ok=True)

        existing = sorted(chunks_dir.glob("*.sql"))
        if existing:
            last_num = int(existing[-1].stem)
            next_num = last_num + 1
        else:
            next_num = 1

        file_path = chunks_dir / f"{next_num:04d}.sql"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(chunk_text)

        logger.log("Registry Operation", f"Chunk archived to {file_path}")
        return str(file_path)

    #Tool
    def get_nth_chunk_tool(self):
        """
        Returns a LangChain tool that reads the Nth-last chunk from the archive.
        n=1 means the last (most recent) chunk, n=2 the second-last, etc.
        """
        registry = self

        @tool
        def get_nth_chunk(n: int) -> str:
            """
            Return the raw SQL code of the Nth-last archived chunk.

            Args:
                n: How far back to look. 1 = most recent chunk, 2 = second-most-recent, etc.

            Returns:
                The SQL code string, or an error message if not found.
            """
            chunks_dir = Path(registry.chunks_dir)
            if not chunks_dir.exists():
                return "No chunks archive directory found."

            files = sorted(chunks_dir.glob("*.sql"))
            if not files:
                return "No archived chunks found."

            if n < 1 or n > len(files):
                return f"Invalid n={n}. Only {len(files)} chunk(s) available."

            target = files[-n]
            with open(target, "r", encoding="utf-8") as f:
                content = f.read()

            logger.log("Tool Execution", f"Read archived chunk #{len(files) - n + 1} from {target}")
            return content

        return get_nth_chunk

    # -------------------------------------------------------------------------
    # Batch write helpers (plain methods — used by the miner run loop)
    # ------------------------------------------------------------------------
    # -------------------------------------------------------------------------
    # Append tools for the three output files (LangChain @tool wrappers)
    # -------------------------------------------------------------------------

    def write_relationships(self, relationships: list[dict]):
        """Append multiple relationship records to relationships.json."""
        for rel in relationships:
            self._append_to_file(self.relationships_path, rel)
            logger.log("Registry Operation", f"Added relationship: {rel.get('source')} -> {rel.get('target')} ({rel.get('relationship_tag')})")

    def write_entities(self, entities: list[dict]):
        """Append multiple entity records to entities.json."""
        for ent in entities:
            self._append_to_file(self.entities_path, ent)
            logger.log("Registry Operation", f"Added entity: {ent.get('entity_name')} ({ent.get('entity_type')})")

    def write_flows(self, flows: list[dict]):
        """Append multiple flow records to flows.json."""
        for flow in flows:
            self._append_to_file(self.flows_path, flow)
            logger.log("Registry Operation", f"Added flow step: {flow.get('flow_id')} ({flow.get('flow_entity_name')})")

    def clean_workspace_files(self):
        """
        Cleans the workspace by removing all files inside the output and state directories, 
        but keeps the directories themselves intact.
        """
        from pathlib import Path
        dirs_to_clean = [
            self.root + "/mining/output",
            self.root + "/mining/state"
        ]
        
        for d in dirs_to_clean:
            dir_path = Path(d)
            if dir_path.exists() and dir_path.is_dir():
                for file_path in dir_path.rglob('*'):
                    if file_path.is_file():
                        try:
                            file_path.unlink()
                        except:
                            pass
        logger.info("Workspace files cleaned (directories retained).")

    # -------------------------------------------------------------------------
    # Registry read tools
    # -------------------------------------------------------------------------

    #Tool
    def get_last_n_entries_tool(self):
        """
        Returns a LangChain agent tool that reads the last N entries from
        any of the three output JSON files by filename.
        """
        registry = self

        @tool
        def get_last_n_entries(filename: str, n: int) -> str:
            """
            Return the last N entries from a registry output file.

            Args:
                filename: One of 'relationships.json', 'entities.json',
                          or 'flows.json'. The root path is automatically
                          prepended.
                n: Number of trailing entries to return.

            Returns:
                JSON string of the last N entries, or an error message if
                the file does not exist.
            """
            full_path = os.path.join(registry.root, "mining", "output", filename)
            entries = registry._read_last_n(full_path, n)
            if not entries:
                return f"File '{filename}' does not exist or is empty."
            logger.log("Tool Execution",f"Retrieved last {n} entries from {filename}")
            return json.dumps(entries, indent=2)

        

        return get_last_n_entries

    #Tool
    def get_last_five_flows_tool(self):
        """Returns a LangChain tool that reads the last 5 entries from flows.json."""
        registry = self

        @tool
        def get_last_five_flows() -> str:
            """
            Return the last 5 flow steps from the flows registry.

            Returns:
                JSON string of up to 5 most recent flow records, or a message
                if the file does not exist.
            """
            entries = registry._read_last_n(registry.flows_path, 5)
            if not entries:
                return "flows.json does not exist or is empty."
            logger.log("Tool Execution",f"Retrieved last 5 flows from.")
            return json.dumps(entries, indent=2)

        return get_last_five_flows

    # -------------------------------------------------------------------------
    # Current chunk SQL tools
    # -------------------------------------------------------------------------

    #Tool
    # def get_write_current_chunk_tool(self):
    #     """Returns a LangChain tool to write the current SQL chunk to a file."""
    #     registry = self

    #     @tool
    #     def write_current_chunk(sql_code: str) -> str:
    #         """
    #         Write the current SQL chunk to the state file for processing.

    #         Args:
    #             sql_code: The SQL code string to write.

    #         Returns:
    #             Confirmation message with the path written.
    #         """
    #         registry._ensure_dir(registry.current_chunk_path)
    #         with open(registry.current_chunk_path, "w", encoding="utf-8") as f:
    #             f.write(sql_code)
    #         logger.log("Tool Execution",f"SQL chunk written to {registry.current_chunk_path}")
    #         return f"SQL chunk written to {registry.current_chunk_path}"

    #     return write_current_chunk

    #Tool
    def get_read_current_chunk_tool(self):
        """Returns a LangChain tool to read the current SQL chunk from file."""
        registry = self

        @tool
        def read_current_chunk() -> str:
            """
            Read the current SQL chunk from the state file.

            Returns:
                The SQL code string, or an error message if the file doesn't exist.
            """
            if not os.path.exists(registry.current_chunk_path):
                return "No current chunk file found. Please write a chunk first."
            with open(registry.current_chunk_path, "r", encoding="utf-8") as f:
                logger.log("Tool Execution",f"SQL chunk read from {registry.current_chunk_path}")
                return f.read()
            
        return read_current_chunk

    # -------------------------------------------------------------------------
    # Chunk detail tools
    # -------------------------------------------------------------------------

    #Tool
    def get_write_chunk_detail_tool(self):
        """
        Returns a LangChain tool to write a numbered chunk detail file.
        Files are numbered sequentially as 0001.txt, 0002.txt, etc.
        """
        registry = self

        @tool
        def write_chunk_detail(text: str) -> str:
            """
            Write a chunk description/detail to a numbered file in the
            chunk_details output directory.

            Args:
                text: The detail text to write (description of the chunk).

            Returns:
                The path of the file written.
            """
            details_dir = Path(registry.chunk_details_dir)
            details_dir.mkdir(parents=True, exist_ok=True)

            # Find next number
            existing = sorted(details_dir.glob("*.txt"))
            if existing:
                last_num = int(existing[-1].stem)
                next_num = last_num + 1
            else:
                next_num = 1

            file_path = details_dir / f"{next_num:04d}.txt"
            with open(file_path, "w", encoding="utf-8") as f:
                logger.log("Tool Execution",f"Chunk detail written to {file_path}")
                f.write(text)

            return f"Chunk detail written to {file_path}"

        return write_chunk_detail

    #Tool
    def get_recent_chunk_details_tool(self, default_n: int = 2):
        """
        Returns a LangChain tool to read the last N chunk detail files.

        Args:
            default_n: Default number of previous chunks to read if not specified.
        """
        registry = self

        @tool
        def get_recent_chunk_details(n: int = default_n) -> str:
            """
            Return the text of the last N chunk detail files, separated by a
            chunk boundary marker.

            The format is:
                <Last to last chunk detail text>
                ----- Chunk boundary -------
                <Last chunk detail text>

            Args:
                n: Number of previous chunk details to retrieve (default: 2).

            Returns:
                Combined text of the last N chunk details, or a message if
                no detail files are found.
            """
            details_dir = Path(registry.chunk_details_dir)
            if not details_dir.exists():
                return "No chunk detail files found. The chunk_details directory does not exist."

            files = sorted(details_dir.glob("*.txt"))
            if not files:
                return "No chunk detail files found."

            selected = files[-n:] if n > 0 else files
            texts = []
            for f in selected:
                with open(f, "r", encoding="utf-8") as fh:
                    texts.append(fh.read())

            separator = "\n----- Chunk boundary -------\n"
            logger.log("Tool Execution",f"Retrieved last {n} chunk details from {details_dir}")
            return separator.join(texts)

        return get_recent_chunk_details

    # -------------------------------------------------------------------------
    # Convenience: get all tools as a flat list
    # -------------------------------------------------------------------------

    def get_all_tools(self) -> list:
        """
        Return all LangChain tools as a flat list, ready to pass to an agent.
        """
        return [
            self.get_last_n_entries_tool(),
            self.get_last_five_flows_tool(),
            self.get_read_current_chunk_tool(),
            self.get_write_chunk_detail_tool(),
            self.get_recent_chunk_details_tool(),
            self.get_nth_chunk_tool(),
        ]
