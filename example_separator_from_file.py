"""
Example script demonstrating how to run the Code Separator on a SQL file.
It covers:
1. Reading SQL from a file path.
2. Initializing and running the CodeSeparator.
3. Saving the extracted EntityRegistry to a JSON file.
4. Reloading the EntityRegistry from the JSON file.
5. Exporting the tree to a NetworkX object with full metadata.
"""

import os
from pathlib import Path
from src.agents.llm import get_llm
from src.utils.chunker import SQLChunker
from src.separator.separator import CodeSeparator
from src.separator.registry import EntityRegistry

def process_sql_file(file_path: str, output_path: str):
    # ---------------------------------------------------------
    # 1. READ SQL FROM FILE
    # ---------------------------------------------------------
    print(f"Reading SQL file: {file_path}")
    with open(file_path, 'r', encoding='utf-8') as f:
        sql_content = f.read()

    # ---------------------------------------------------------
    # 2. RUN CODE SEPARATOR
    # ---------------------------------------------------------
    print("Initializing LLM and CodeSeparator...")
    llm = get_llm()
    # skip_descriptions=True speeds up testing by avoiding the description generation phase.
    # deduplicate_overlap=True enables line-based deduplication where consecutive overlapping chunks are merged.
    separator = CodeSeparator(llm=llm, skip_descriptions=True, deduplicate_overlap=True)
    
    # Initialize chunker (using small window sizes to ensure multiple chunks for testing)
    chunker = SQLChunker(sql_text=sql_content, window_size=100, overlap=0)
    
    print("Processing chunks...")
    # run process() to get the filled registry
    registry = separator.process(chunker)
    
    # ---------------------------------------------------------
    # 3. SAVE REGISTRY TO FILE
    # ---------------------------------------------------------
    print(f"Saving registry to: {output_path}")
    # This serializes the entire resolved tree structure and all code snippets into JSON.
    registry.save_to_file(output_path)
    
    # ---------------------------------------------------------
    # 4. RELOAD REGISTRY FROM FILE
    # ---------------------------------------------------------
    print(f"Reloading registry from: {output_path}")
    reloaded_registry = EntityRegistry.load_from_file(output_path)
    print(f"Reloaded {reloaded_registry.count} entities.")
    
    # You can print the tree using the new utility method added recently
    print("\n------- RELOADED ENTITY TREE -------")
    reloaded_registry.print_tree()

    # ---------------------------------------------------------
    # 5. CONVERT TO NETWORKX OBJECT
    # ---------------------------------------------------------
    print("\nConverting to NetworkX object...")
    graph = reloaded_registry.to_networkx()
    
    print(f"Graph created with {graph.number_of_nodes()} nodes and {graph.number_of_edges()} edges.")
    
    # Demonstrate accessing the nodes and their metadata
    print("\n------- NETWORKX METADATA PREVIEW -------")
    for node_id, data in graph.nodes(data=True):
        print(f"Node: {node_id}")
        print(f"  Name:           {data.get('entity_name')}")
        print(f"  Type:           {data.get('entity_type')}")
        print(f"  Operation Type: {data.get('operation_type')}")
        print(f"  Nesting Level:  {data.get('nesting_level')}")
        print(f"  Code Length:    {data.get('code_length')} characters")
        print(f"  Extracted from chunks: {data.get('chunk_ids')}\n")

if __name__ == "__main__":
    # Create a dummy SQL file for this example to work out-of-the-box
    dummy_sql_path = "example_dummy.sql"
    dummy_json_path = "example_registry_output.json"
    
    with open(dummy_sql_path, "w", encoding="utf-8") as f:
        f.write("CREATE PROCEDURE p_dummy AS BEGIN DBMS_OUTPUT.PUT_LINE('Hello'); END;\n/\n")
    
    try:
        process_sql_file(dummy_sql_path, dummy_json_path)
    finally:
        # Cleanup dummy files if they exist
        if os.path.exists(dummy_sql_path):
            os.remove(dummy_sql_path)
        # Uncomment below to also cleanup the output json file
        # if os.path.exists(dummy_json_path):
        #     os.remove(dummy_json_path)
