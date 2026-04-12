# this module processed miner output and makes it reads for inference.

- it loads entities into pandas data frame and groups them by entity name such that all other columns are turned into list of items, e.g. code information, descriptions etc.
- in case of relationships it first lookks for cases where source and target are changed thus they are same relations but shown twice only. e.g. T1 -> T2 and T2 -> T1.
  combine such cases by keeping the relationship flow which has higher sum of confidence. while combining combine their column values in a list.
- then combine the relationships in same way as entities by goruping them by souurce and targget columns.

- keep a class which takes the updated entities, relations and flows and also loads the tree registry created by separator.

- this class will have methods to return matching entity names, use regexx pattern and eact or substring entity name but dont retuurn too many if exact name if present return it otherwise subbstring based or fuzzy match.

- other method is to get relationships for a given entity name, return all relationships where entity is either source or target.

- create methods to get entity informations, relationship infomration and when they hold chunk number then from separator tree get those chunks and also methods to get code for those chunks.

- think of other useful methods which may be required to interact with this information.
