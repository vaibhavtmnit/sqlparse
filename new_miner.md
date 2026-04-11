# Understand separator and leverage existing miner functionalities to crete an advanced miner.

Separator once separates a code into ints natural boundry it should be easier to miner to process such that it can find information abount entities and their relationships. More or less the mining process would remain same but now few change in design are required.
Do not change the miner code but build a bridge between current classes and functions and wherver required built totally new mining classes and functions.
Build the code in a new folder for easy reference.
I want miner for both router agent design and deep agent design both.
The mining process should leverage the natural structure of the code provided by separator. The strategy is:

- start from top level and take the code. If code is more then 250 lines split it into chunks of 250 lines with user defined setting of overlapping window. use existing chunker.
- If single code then process it entirely in one go to mine all the entities and relationships, use the metadata information from separator eg. description etc to first understand what the code is about.
- the structural relations found out seprator are also to be used to find right relationships e.g. if there are nested entities found by separator then there is naturally a relationship between parent and child from the separator tree.

- The type of entities and relationships to be tracked would be same but ensure that relationship direction is always same e.g. from table getting modified(inserted, created etc.) to the table involved in the operation.

- A new feature to be added is tracking of field between relations, e.g. if a code shows that fields F1 in table T1 are created using F2 from T2 and F3 from T3 then when mining relationship between T1 and T2 also extract. and the relationship between T1 and T2 would also have part of F1 which are dependent on F2 with T1 and F2 with T2. Ensure there is separate agent for this step so that context is preserved and isolated from rest of the processing. This separate agent should look at each relationship and code and extract field level information. Use python tools to make it easy and cost efficient.

- The miner should be able to look into the resolved code multiple times if required to look for information is needs for processing. Thus it is exactly like how a human behaves.

- Keep specific logs for all the actions taken by agent and orchestrator and pront them, use loguru.
- during minning the new miner should extensively use the tree structure to keep track of state as where is it , what it has processed and so on this would help it get great insights about the code. e.g. which package, procedure it is working on etc.

- In the entire build follow context engineering principles to get high accuuracy.
