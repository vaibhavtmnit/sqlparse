# Last piece of the puzzle is explorer.

- some of the resources to refer:
  https://www.anthropic.com/engineering/harness-design-long-running-apps
  https://blog.langchain.com/the-anatomy-of-an-agent-harness/
  https://www.anthropic.com/engineering/building-effective-agents
  https://www.humanlayer.dev/blog/skill-issue-harness-engineering-for-coding-agents
  https://claude.com/blog/building-agents-with-the-claude-agent-sdk
  https://www.anthropic.com/engineering/multi-agent-research-system
  https://github.com/walkinglabs/awesome-harness-engineering#context-memory--working-state

- It will be a multi hierarchy agent. Your call on how to design it but use core explorer sugagents as deep harness or deepagents.

-Understand the enricher on what it would provide you.

The explorer role and responsibilities are:

- take a field name as input, other optional input is table name. This field and table name would corresponding to a oracle sql code such that the table is either created or modified and the field is one of the field of the table.
  The explorer main objective is to build a lineage of the field as it passes on from one to table to another table, so if the table name is given refer that table name and understand what could be the name of the field(s) and table(s) the input combination has come from. It is important to note that an input field may be dervided from multiple fields of multiple tables and its important to track all of them.
  In the next step the dependencies found would become input and the same process is to be repeated until no more dependencies are found.
  Explorer should try to maintain a tree like structure to capture entire dependency chain. and at the same time maintain a description summary explaining how the original field is derived from other field e.g. F1 is created by suumming F2 and F3, F2 is created from F4 by umltiplying it by 100 etc. So the entire transformation logic needs to be tracked.

Resurces to be used by explorer

- The explorer has to refer enricher object ie entities, relationships, tree registry created by separator for its exploration. USe eisting tools and create new tools to perform the operation.
  It can refer the resolved code created by separator corresonding to an entity and it the resolved code is too big for AI agent then chunk it and process it for easy reference but the goal now is to find the dependencies and transformation logic. You could also refer the description of resolved code quickkly understand what this is about.

Exploration technical specification:

- use python classes and functions wherver required.
- there could be situation when one field is derived from multiple fields of multiple tables. so expand the both and explore them both and recursively keep expanding.
- keep the objective in in mind especially deepagent should know the objective is to keep on epanding until nothing else is to expand.
- do not expand wrongly
- consider aliases e.g. the given input might be an alias of some other field name. so dont be confuused and find the field and table linked to the field of which lias has been given to explorer.
- built hierarchy that the explorer can refer entity, relationships for detail in case of confusion can look resolved code description and even the raw code chunks. Build these functionalitities in enricher if not available.
- context engineer by creating many subagents for specific tasks and do not burden single subagemtn with many tasks.
- I imagine it to be a long-running exploration so use the right practice it is like a combination of research and deep investigation so use memory hanress accordingly.
- Do not be overwhelmed if an entity has too many relations, understand those relations and filter out the irrelevant ones bbased on description or code and keep the ones where fields are connected.

Use loguru: log each and every action sbeing perfomred either by agent or explorer . I wan to see in logs how the lineage finding is progressing.
skills : use Agentic skills to guide agents to perform the task. create multiple if required.
