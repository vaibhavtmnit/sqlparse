import sys
from pathlib import Path
import json

sys.path.append(str(Path(__file__).parent.absolute()))

from src.enricher.core import GraphEnricher
from src.separator.registry import EntityRegistry # mock or load
from pydantic import BaseModel

class DummyEntry:
     def __init__(self, code):
          self.resolved_code = code
          self.chunk_ids = [0]

class DummyRegistry:
     def get(self, eid):
          if eid == "ent_1":
               return DummyEntry("SELECT * FROM TABLE_1;")
          return None

def test():
     entities = [
          {"entity_name": "T1", "description": "Desc 1"},
          {"entity_name": "T1", "description": "Desc 2"},
          {"entity_name": "T2", "description": "Table 2"}
     ]
     relations = [
          {"source": "T1", "target": "T2", "confidence_score": 0.8, "field_mappings": [{"target_field": "col_1"}]},
          {"source": "T2", "target": "T1", "confidence_score": 0.9, "field_mappings": [{"target_field": "col_2"}]}
     ]
     flows = []
     
     with open("tmp_ent.json", "w") as f: json.dump(entities, f)
     with open("tmp_rel.json", "w") as f: json.dump(relations, f)
     with open("tmp_flow.json", "w") as f: json.dump(flows, f)
     
     enricher = GraphEnricher(DummyRegistry(), "tmp_ent.json", "tmp_rel.json", "tmp_flow.json")
     
     print("Entities DF:")
     print(enricher.entities_df)
     print("\nRelations DF:")
     print(enricher.relationships_df)
     
     print("\nFind Entities 'T1':")
     print(enricher.find_entities("T1"))
     
     import os
     os.remove("tmp_ent.json")
     os.remove("tmp_rel.json")
     os.remove("tmp_flow.json")

if __name__ == "__main__":
     test()
