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
        sources = metadata.get("sources", [])
        for src in sources:
            src_tbl = src.get("source_table", "UNKNOWN")
            src_fld = src.get("source_field", "UNKNOWN")
            src_node = f"{src_tbl}.{src_fld}".upper()
            
            # Extract relationship logic
            relationship_logic = src.get("logic", "Direct Map")
            
            # Lineage flows from Source -> Target
            G.add_edge(src_node, target_node.upper(), 
                       relationship=relationship_logic,
                       confidence=src.get("confidence", 1.0))

    if G.number_of_nodes() == 0:
        print("The lineage tree is empty. No nodes to plot.")
        return

    print(f"Generated network object with {G.number_of_nodes()} nodes and {G.number_of_edges()} edges.")

    # --- PLOTTING ---
    plt.figure(figsize=(16, 12))
    
    # Use a more spread-out layout to accommodate edge labels
    pos = nx.spring_layout(G, k=0.8, iterations=100, seed=42)
    
    # Draw Nodes
    nx.draw_networkx_nodes(G, pos, 
                           node_size=3000, 
                           node_color="#4361ee", 
                           alpha=0.9,
                           edgecolors="white",
                           linewidths=1)
    
    # Draw Edges
    nx.draw_networkx_edges(G, pos, 
                           width=2, 
                           edge_color="#3f37c9", 
                           alpha=0.4, 
                           arrows=True, 
                           arrowsize=30, 
                           connectionstyle="arc3,rad=0.1")
    
    # Draw Node Labels
    nx.draw_networkx_labels(G, pos, 
                            font_size=9, 
                            font_family="sans-serif", 
                            font_weight="bold", 
                            font_color="white")

    # Draw Edge Labels (Relationships)
    edge_labels = nx.get_edge_attributes(G, 'relationship')
    # Filter out long strings to keep plot clean
    formatted_labels = {k: (v[:30] + '...') if len(str(v)) > 30 else v for k, v in edge_labels.items()}
    
    nx.draw_networkx_edge_labels(G, pos, 
                                 edge_labels=formatted_labels,
                                 font_size=7,
                                 font_color="#333333",
                                 label_pos=0.5,
                                 alpha=0.9,
                                 rotate=True,
                                 bbox=dict(facecolor='white', edgecolor='none', alpha=0.7, boxstyle='round,pad=0.2'))

    plt.title("SQL Lineage Map with Data Relationships", fontsize=18, fontweight="bold", pad=30)
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
