import json
import os
import networkx as nx
import matplotlib.pyplot as plt
from pathlib import Path

def visualize_discovery(json_path: str = "discovery_results.json"):
    """
    Loads the discovery results from the explorer and plots them as a 
    Directed Graph (Lineage Flow).
    """
    # Handle both plural and singular names common in user requests
    if not os.path.exists(json_path):
        alt_path = "discovery_result.json"
        if os.path.exists(alt_path):
            json_path = alt_path
        else:
            print(f"Error: Could not find {json_path} or {alt_path}")
            return

    # Load JSON data
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Extract the 'tree' component which contains the field-level mappings
    tree = data.get("tree", {})
    if not tree:
        print("No 'tree' structure found in the JSON result.")
        return

    # Create a Directed Graph (DiGraph)
    G = nx.DiGraph()

    # Build edges from source fields to target fields
    for target_node, metadata in tree.items():
        # target_node is usually 'TABLE_NAME.FIELD_NAME'
        sources = metadata.get("sources", [])
        for src in sources:
            src_tbl = src.get("source_table", "UNKNOWN")
            src_fld = src.get("source_field", "UNKNOWN")
            src_node = f"{src_tbl}.{src_fld}".upper()
            
            # Lineage flows from Source -> Target
            G.add_edge(src_node, target_node.upper(), 
                       logic=src.get("logic", "N/A"),
                       confidence=src.get("confidence", 1.0))

    if G.number_of_nodes() == 0:
        print("The lineage tree is empty. No nodes to plot.")
        return

    print(f"Generated network object with {G.number_of_nodes()} nodes and {G.number_of_edges()} edges.")

    # --- PLOTTING ---
    plt.figure(figsize=(14, 10))
    
    # Use spring layout for a balanced look
    pos = nx.spring_layout(G, k=0.6, iterations=50)
    
    # Draw Nodes
    nx.draw_networkx_nodes(G, pos, 
                           node_size=2500, 
                           node_color="#4361ee", 
                           alpha=0.8)
    
    # Draw Edges
    nx.draw_networkx_edges(G, pos, 
                           width=2, 
                           edge_color="#3f37c9", 
                           alpha=0.5, 
                           arrows=True, 
                           arrowsize=25, 
                           connectionstyle="arc3,rad=0.1")
    
    # Draw Labels
    nx.draw_networkx_labels(G, pos, 
                            font_size=9, 
                            font_family="sans-serif", 
                            font_weight="bold", 
                            font_color="white")

    plt.title("SQL Lineage Discovery - Field Level Map", fontsize=16, fontweight="bold", pad=20)
    plt.axis("off")
    
    output_img = "lineage_discovery_plot.png"
    plt.savefig(output_img, dpi=300, bbox_inches="tight")
    print(f"Plot saved successfully to: {output_img}")
    
    # Try to show if in interactive environment
    try:
        plt.show()
    except Exception:
        pass

    return G

if __name__ == "__main__":
    # You can change the path here if your file has a different name
    visualize_discovery("discovery_results.json")
