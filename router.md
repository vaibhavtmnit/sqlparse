create an agentic router whwhich manages the subagents a long term memory based in latest and best indsutry guidelines and best practices(refer reserach papers if required). The design and definition is given next.

- the orcehstrator would remain same ecept the part of mining entities, relationship and flows would be using the router. also a new functionalitty to prcess output sould be required but some of the functionality would bbe from the existing design.

- router has a supervsior agents to control subagents and deepagents. and it manages agent state etc.
- The plan of the router is to gather all the information relevant for the processing and let deepagent do the processing and return the output.
- the output can be two kinds either json for which the current code cane be uused or collection of pydantic base model classes e.g. collection of entities, collection of relationships and collection of flows. Create entities basemodel class, relationships basemodel class, flows basemodel class. collections are respectively list of these classes to be returned.
- a functionality to take the output from router either json or collections of pydantic model and call the relevant tools to write. Ensure to use the eisting processing steps and tools, e.g. creating flow ids, linking entities to flows, writing entities, writing relationships, writing flows.

- The router needs to be desgined as below:

- Takes trigger and loads sql chunk and save it to agent agent for easy referecen.
- loads the last five flows, details of last 3 chunk description details and saves them individual to agentstate.
- runs a subagent to uunderstand this chunk in relation with previous chunk to understand flow and create a description highlighting how the
  new chunk is related to the previous chunks. Bring in important information from previous chunks as a sort of summary only highlighting the connection. and store this information into agent state and write it using tools to relavent file(refer current design).

- Now a deepagent is required which takes the sql chunk to mine entities, relationships and flows, either as json of pydantic class. Make it uuser setting. give the class defintion as structured_ouutpuut argument for the deepagent.
- The deepagent should be allowed to interact with agent state, i.e. all the information whcih has been accumulated which is needs to mine the entities, relationships and flows. During mining it should have options to keep temporary notes or other relevant tools to mine entities, relationships and flows efficiently. Also give it a tool to refer last n entities and relationship in case it wants to create relationship between entities found in this chuunk with entities in previous chuunk. In fact this must be part of its processing step.
