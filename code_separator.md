# Build an AI agent to process oracle sql code chunks and create sgegregated chunks separated by natural code boundaries.

Background : Chunks would be received by AI agent which are created by splitting the sql script based on the size of the chunk.
The chunks contains following entities corresponding to which relevant sql code arre to be segregated. By code segregation we mean to create a new chunk which contains only the sql code related to the entity and not the sql code of other entities.

Entities are :

1. Packages - The package definition is the code to be etracted and segregated.
2. Procedures - same as package
3. Functions - same as package
4. Views, Tables and CTEs that are modified by other tables etc. i.e. views tables ctes that are inserted, created or appended with information from other table. - The entire code which shows the operation and captures the depdendency on other table as well as covers the entire modification operation is to be captured.

Chunk Contents: A chunk have have following contents

- A chunk may contain partial or full sql code for an entity. i.e. initial part could be coninuation of entity from immediate or one of the previous entity. The other part in the chunk may contain new entity which is partially defined and rest of the code for new is to be expected in net chunk onwards.

- A chunk may contain may contain code continuuation of previous chunk and the entire current chunk is continuation only.
- A chunk along with continuation of previous chunk may also contain code for one or more new entities which is partially defined and rest of the code for new is to be expected in net chunk onwards.

Thus the idea is as new chunks are received AI would analyse it split it to create boundry between entities and add the continuation part of the chunk and create new half entity.

Coninuuation registry and tracker:
a python class to hold entity and the full code for entities which have been fully resolved and a new enetity has been found. It should have attributes like entity_name, entity_type, entity_code, is_resolved, full code of entity (created by reapeatedly resolving entities). Description of code generated using aI at the last this description should be a detailed one.

A current entity tracker : this is for the entity which is partically resolved and its continuation code is expected next. It should have attributes like entity_name, entity_type, entity_code, is_resolved, full code of entity (created by reapeatedly resolving entities). Description of code generated using aI at the last this description should be a detailed one.

Capture Steps:

- Take a chunk analyse what to do with this code.
- Take action and maintain entity tracker
- once an entity's full code is resolved then register it.

- Remember single entity might appear multiple time e.g. same table getting modified in different tables operations all of those are separate and the registry should handle it.

- Registry should have use ful methods like get all entities, find entry for an entity etc.

- create deepagent harness if required which can recursively call itself to resolve entities and maintain state and checks whether objective is met or not regularly, just like langchain deepagent, feel free to use langchain's implementation as well.
