---
skill_name: Oracle Deep Lineage Trace
description: Core guidelines on how to accurately extract Oracle SQL lineage dependencies.
---

# Oracle SQL Lineage Extraction Skill

You are tracing lineage across an Oracle SQL block. Use the following explicit guidelines to extract target paths:

### 1. Merges vs Inserts
In Oracle `MERGE` statements, carefully evaluate the `WHEN MATCHED THEN UPDATE SET` vs `WHEN NOT MATCHED THEN INSERT` blocks. If the target field exists in the target table, read the `SET tgt.field = src.field` clause to find the true source. Do not confuse boolean matching criteria (`ON tgt.id = src.id`) with actual data transformation mappings.

### 2. Aliasing
Look out for table prefixes. `SELECT a.amount AS gross_amount FROM financials a.` The target field `gross_amount` originates from `financials.amount`.

### 3. Procedure Output Parameters
If the block is a `PROCEDURE`, data may leave the procedure through `OUT` parameters instead of `INSERT/UPDATE`. Be aware of assignments like `p_total_salary OUT NUMBER` where `p_total_salary := v_calc + 10;`.

### 4. Mathematical Conversions
If the target is mathematically synthesized (e.g., `TARGET_VAL = VAL_A * (1 - VAL_B)`), you MUST extract BOTH `VAL_A` and `VAL_B` as separate source dependencies!

### 5. Ignoring Constants
If a field is populated entirely by a scalar, constant, or environmental function (`SYSDATE`, `100`, `'Y'`), do not return any lineage. There is no upstream DB table responsible for it.
