"""
test_separator_small.py — Small focused test with 3 nesting levels.

SQL structure:
  Level 0: PACKAGE BODY PKG_DEMO
  Level 1:   PROCEDURE LOAD_DATA
  Level 2:     INSERT INTO TARGET_TABLE SELECT FROM SOURCE_TABLE

Split into 2 chunks to test cross-chunk continuation.
"""

import os
import sys
from dotenv import load_dotenv
from langchain_google_genai import ChatGoogleGenerativeAI

# Fix Windows console encoding
sys.stdout.reconfigure(encoding="utf-8")

from src.separator.separator import CodeSeparator
from src.utils.chunker import SQLChunker, Chunk


SMALL_SQL = """\
CREATE OR REPLACE PACKAGE BODY PKG_DEMO AS

    g_counter NUMBER := 0;

    PROCEDURE LOAD_DATA IS
        v_cnt NUMBER;
    BEGIN
        g_counter := g_counter + 1;

        INSERT INTO TARGET_TABLE (id, name, value, load_date)
        SELECT
            src.id,
            UPPER(src.name),
            src.amount * 1.1,
            SYSDATE
        FROM SOURCE_TABLE src
        WHERE src.active_flag = 'Y';

        v_cnt := SQL%ROWCOUNT;

        SELECT COUNT(*) INTO v_cnt FROM TARGET_TABLE;

        COMMIT;
    END LOAD_DATA;

END PKG_DEMO;
/
"""


def print_tree(tree: list, indent: int = 0) -> None:
    """Pretty-print the entity tree."""
    for node in tree:
        prefix = "  " * indent + ("├── " if indent > 0 else "")
        op = f"/{node['operation_type']}" if node.get("operation_type") else ""
        resolved = "[OK]" if node.get("is_resolved") else "[..]"
        print(
            f"{prefix}{resolved} {node['entity_name']} "
            f"({node['entity_type']}{op}) "
            f"chunks={node['chunk_ids']} "
            f"code={node['code_length']} chars"
        )
        if node.get("children"):
            print_tree(node["children"], indent + 1)


def run_test():
    from loguru import logger as test_logger
    # Add a file sink for clean logs
    test_logger.add(
        "test_separator_run.log",
        format="{time:HH:mm:ss} | {level: <10} | {message}",
        level="DEBUG",
        encoding="utf-8",
        mode="w",
    )

    from src.agents.llm import get_llm
    llm = get_llm()

    # Window of 15 lines → forces 2-3 chunks
    chunker = SQLChunker(SMALL_SQL, window_size=15, overlap=3)
    chunks = list(chunker)
    print(f"SQL split into {len(chunks)} chunks (window=15, overlap=3)\n")
    for c in chunks:
        print(f"--- Chunk {c.chunk_id} ---")
        print(c.chunk_text)
        print()

    # Re-create chunker for the separator
    chunker = SQLChunker(SMALL_SQL, window_size=15, overlap=3)
    separator = CodeSeparator(llm, max_retries=3, skip_descriptions=True)
    registry = separator.process(chunker)

    # Results
    print("\n" + "=" * 60)
    print("ENTITY TREE")
    print("=" * 60 + "\n")
    tree = registry.get_tree()
    print_tree(tree)

    print("\n" + "=" * 60)
    print("ENTITY DETAILS")
    print("=" * 60)
    for entry in registry.get_all():
        print(f"\n[{entry.entity_id}] {entry.entity_name} ({entry.entity_type}"
              f"{'/' + entry.operation_type if entry.operation_type else ''})")
        print(f"  Parent: {entry.parent_id or '(root)'}")
        print(f"  Level: {entry.nesting_level}")
        print(f"  Chunks: {entry.chunk_ids}")
        print(f"  Resolved code ({len(entry.resolved_code)} chars):")
        for line in entry.resolved_code.splitlines():
            print(f"    | {line}")
        if entry.description:
            desc = entry.description[:200]
            if len(entry.description) > 200:
                desc += "..."
            print(f"  Description: {desc}")

    # Save
    registry.save_to_file("test_separator_output/small_registry.json")
    print(f"\nSaved to test_separator_output/small_registry.json")


if __name__ == "__main__":
    run_test()
