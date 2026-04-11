"""
test_separator_e2e.py — End-to-end test of the Code Separator pipeline.

Uses a realistic Oracle SQL script with packages, procedures, functions,
table operations, triggers, views, dynamic SQL, and anonymous blocks.
"""

import json
from src.separator.separator import CodeSeparator
from src.utils.chunker import SQLChunker
from src.agents.llm import get_llm


SAMPLE_SQL = """\
-- ============================================================
-- ETL Package: PKG_CUSTOMER_ETL
-- Purpose: Load and transform customer data from staging to
--          production tables with full audit trail.
-- ============================================================

CREATE OR REPLACE PACKAGE PKG_CUSTOMER_ETL AS
    PROCEDURE LOAD_STAGING;
    PROCEDURE TRANSFORM_AND_VALIDATE;
    PROCEDURE MERGE_TO_PRODUCTION;
    PROCEDURE RUN_ETL;
END PKG_CUSTOMER_ETL;
/

CREATE OR REPLACE PACKAGE BODY PKG_CUSTOMER_ETL AS

    g_batch_id NUMBER;

    -- ---------------------------------------------------------
    -- Procedure: LOAD_STAGING
    -- Reads from external source table and populates staging
    -- ---------------------------------------------------------
    PROCEDURE LOAD_STAGING IS
        v_batch_id   NUMBER;
        v_row_count  NUMBER := 0;
    BEGIN
        SELECT SEQ_BATCH_ID.NEXTVAL INTO v_batch_id FROM DUAL;

        EXECUTE IMMEDIATE 'TRUNCATE TABLE STG_CUSTOMER_RAW';

        INSERT INTO STG_CUSTOMER_RAW (
            BATCH_ID, CUSTOMER_ID, FIRST_NAME, LAST_NAME,
            EMAIL, PHONE, CITY, STATE, ZIP_CODE, COUNTRY,
            CREATED_DATE, MODIFIED_DATE
        )
        SELECT
            v_batch_id,
            src.CUST_ID,
            UPPER(TRIM(src.FNAME)),
            UPPER(TRIM(src.LNAME)),
            LOWER(TRIM(src.EMAIL_ADDR)),
            REGEXP_REPLACE(src.PHONE_NUM, '[^0-9]', ''),
            src.CITY,
            src.STATE_CD,
            src.ZIP,
            NVL(src.COUNTRY_CD, 'US'),
            SYSDATE,
            SYSDATE
        FROM EXTERNAL_CUSTOMER_SOURCE src
        WHERE src.ACTIVE_FLAG = 'Y'
          AND src.CUST_ID IS NOT NULL;

        v_row_count := SQL%ROWCOUNT;

        INSERT INTO AUDIT_LOG (
            LOG_ID, BATCH_ID, PROCEDURE_NAME,
            ROWS_PROCESSED, STATUS, LOG_TIMESTAMP
        )
        VALUES (
            SEQ_AUDIT_LOG.NEXTVAL, v_batch_id, 'LOAD_STAGING',
            v_row_count, 'SUCCESS', SYSTIMESTAMP
        );

        COMMIT;
    EXCEPTION
        WHEN OTHERS THEN
            ROLLBACK;
            INSERT INTO AUDIT_LOG (
                LOG_ID, BATCH_ID, PROCEDURE_NAME,
                ROWS_PROCESSED, STATUS, ERROR_MESSAGE, LOG_TIMESTAMP
            )
            VALUES (
                SEQ_AUDIT_LOG.NEXTVAL, v_batch_id, 'LOAD_STAGING',
                0, 'FAILED', SQLERRM, SYSTIMESTAMP
            );
            COMMIT;
            RAISE;
    END LOAD_STAGING;

    -- ---------------------------------------------------------
    -- Procedure: TRANSFORM_AND_VALIDATE
    -- ---------------------------------------------------------
    PROCEDURE TRANSFORM_AND_VALIDATE IS
        v_batch_id   NUMBER;
    BEGIN
        SELECT MAX(BATCH_ID) INTO v_batch_id FROM STG_CUSTOMER_RAW;

        UPDATE STG_CUSTOMER_RAW
        SET VALIDATION_STATUS = 'INVALID_EMAIL'
        WHERE BATCH_ID = v_batch_id
          AND NOT REGEXP_LIKE(EMAIL, '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\\\.[A-Za-z]{2,}$');

        UPDATE STG_CUSTOMER_RAW
        SET VALIDATION_STATUS = 'VALID'
        WHERE BATCH_ID = v_batch_id
          AND VALIDATION_STATUS IS NULL;

        DELETE FROM STG_CUSTOMER_RAW a
        WHERE a.ROWID > (
            SELECT MIN(b.ROWID)
            FROM STG_CUSTOMER_RAW b
            WHERE b.CUSTOMER_ID = a.CUSTOMER_ID
              AND b.BATCH_ID = v_batch_id
              AND b.VALIDATION_STATUS = 'VALID'
        )
        AND a.BATCH_ID = v_batch_id;

        INSERT INTO CUSTOMER_REJECTS (
            REJECT_ID, BATCH_ID, CUSTOMER_ID,
            REJECT_REASON, ORIGINAL_DATA, REJECT_DATE
        )
        SELECT
            SEQ_REJECT_ID.NEXTVAL, BATCH_ID, CUSTOMER_ID,
            VALIDATION_STATUS,
            FIRST_NAME || '|' || LAST_NAME || '|' || EMAIL,
            SYSDATE
        FROM STG_CUSTOMER_RAW
        WHERE BATCH_ID = v_batch_id
          AND VALIDATION_STATUS != 'VALID';

        INSERT INTO AUDIT_LOG (
            LOG_ID, BATCH_ID, PROCEDURE_NAME,
            ROWS_PROCESSED, STATUS, LOG_TIMESTAMP
        )
        VALUES (
            SEQ_AUDIT_LOG.NEXTVAL, v_batch_id, 'TRANSFORM_AND_VALIDATE',
            0, 'SUCCESS', SYSTIMESTAMP
        );

        COMMIT;
    END TRANSFORM_AND_VALIDATE;

    -- ---------------------------------------------------------
    -- Procedure: MERGE_TO_PRODUCTION
    -- ---------------------------------------------------------
    PROCEDURE MERGE_TO_PRODUCTION IS
        v_batch_id    NUMBER;
        v_merged      NUMBER := 0;
    BEGIN
        SELECT MAX(BATCH_ID) INTO v_batch_id FROM STG_CUSTOMER_RAW;

        MERGE INTO CUSTOMER_MASTER tgt
        USING (
            WITH CTE_VALID_CUSTOMERS AS (
                SELECT CUSTOMER_ID, FIRST_NAME, LAST_NAME, EMAIL, PHONE,
                       CITY, STATE, ZIP_CODE, COUNTRY, MODIFIED_DATE
                FROM STG_CUSTOMER_RAW
                WHERE BATCH_ID = v_batch_id AND VALIDATION_STATUS = 'VALID'
            )
            SELECT * FROM CTE_VALID_CUSTOMERS
        ) src
        ON (tgt.CUSTOMER_ID = src.CUSTOMER_ID)
        WHEN MATCHED THEN
            UPDATE SET
                tgt.FIRST_NAME = src.FIRST_NAME,
                tgt.LAST_NAME  = src.LAST_NAME,
                tgt.EMAIL      = src.EMAIL,
                tgt.PHONE      = src.PHONE,
                tgt.CITY       = src.CITY,
                tgt.STATE      = src.STATE,
                tgt.ZIP_CODE   = src.ZIP_CODE,
                tgt.COUNTRY    = src.COUNTRY,
                tgt.LAST_UPDATED = SYSDATE,
                tgt.UPDATE_BATCH_ID = v_batch_id
        WHEN NOT MATCHED THEN
            INSERT (CUSTOMER_ID, FIRST_NAME, LAST_NAME, EMAIL, PHONE,
                    CITY, STATE, ZIP_CODE, COUNTRY, CREATED_DATE,
                    LAST_UPDATED, CREATE_BATCH_ID)
            VALUES (src.CUSTOMER_ID, src.FIRST_NAME, src.LAST_NAME,
                    src.EMAIL, src.PHONE, src.CITY, src.STATE,
                    src.ZIP_CODE, src.COUNTRY, SYSDATE, SYSDATE,
                    v_batch_id);

        v_merged := SQL%ROWCOUNT;

        INSERT INTO CUSTOMER_DIM_HISTORY (
            HISTORY_ID, CUSTOMER_ID, SNAPSHOT_DATE,
            FIRST_NAME, LAST_NAME, EMAIL, CITY, STATE, COUNTRY
        )
        SELECT
            SEQ_DIM_HISTORY.NEXTVAL, cm.CUSTOMER_ID, SYSDATE,
            cm.FIRST_NAME, cm.LAST_NAME, cm.EMAIL,
            cm.CITY, cm.STATE, cm.COUNTRY
        FROM CUSTOMER_MASTER cm
        WHERE cm.LAST_UPDATED >= TRUNC(SYSDATE);

        INSERT INTO AUDIT_LOG (
            LOG_ID, BATCH_ID, PROCEDURE_NAME,
            ROWS_PROCESSED, STATUS, LOG_TIMESTAMP
        )
        VALUES (
            SEQ_AUDIT_LOG.NEXTVAL, v_batch_id, 'MERGE_TO_PRODUCTION',
            v_merged, 'SUCCESS', SYSTIMESTAMP
        );

        COMMIT;
    END MERGE_TO_PRODUCTION;

    -- ---------------------------------------------------------
    -- Main orchestrator
    -- ---------------------------------------------------------
    PROCEDURE RUN_ETL IS
    BEGIN
        DBMS_OUTPUT.PUT_LINE('=== Starting Customer ETL ===');
        LOAD_STAGING;
        TRANSFORM_AND_VALIDATE;
        MERGE_TO_PRODUCTION;
        DBMS_OUTPUT.PUT_LINE('=== Customer ETL Complete ===');
    EXCEPTION
        WHEN OTHERS THEN
            DBMS_OUTPUT.PUT_LINE('ETL FAILED: ' || SQLERRM);
            RAISE;
    END RUN_ETL;

END PKG_CUSTOMER_ETL;
/

-- ============================================================
-- Trigger: TRG_CUSTOMER_AUDIT
-- ============================================================
CREATE OR REPLACE TRIGGER TRG_CUSTOMER_AUDIT
AFTER INSERT OR UPDATE OR DELETE ON CUSTOMER_MASTER
FOR EACH ROW
DECLARE
    v_action VARCHAR2(10);
BEGIN
    IF INSERTING THEN v_action := 'INSERT';
    ELSIF UPDATING THEN v_action := 'UPDATE';
    ELSIF DELETING THEN v_action := 'DELETE';
    END IF;

    INSERT INTO CUSTOMER_CHANGE_LOG (
        CHANGE_ID, CUSTOMER_ID, ACTION_TYPE,
        OLD_EMAIL, NEW_EMAIL, CHANGE_DATE, CHANGED_BY
    )
    VALUES (
        SEQ_CHANGE_LOG.NEXTVAL,
        NVL(:NEW.CUSTOMER_ID, :OLD.CUSTOMER_ID),
        v_action, :OLD.EMAIL, :NEW.EMAIL,
        SYSTIMESTAMP, USER
    );
END TRG_CUSTOMER_AUDIT;
/

-- ============================================================
-- View: VW_CUSTOMER_SUMMARY
-- ============================================================
CREATE OR REPLACE VIEW VW_CUSTOMER_SUMMARY AS
SELECT
    cm.CUSTOMER_ID,
    cm.FIRST_NAME || ' ' || cm.LAST_NAME AS FULL_NAME,
    cm.EMAIL, cm.PHONE,
    cm.CITY || ', ' || cm.STATE || ' ' || cm.ZIP_CODE AS FULL_ADDRESS,
    cm.COUNTRY, cm.CREATED_DATE, cm.LAST_UPDATED,
    (SELECT COUNT(*) FROM CUSTOMER_DIM_HISTORY dh
     WHERE dh.CUSTOMER_ID = cm.CUSTOMER_ID) AS HISTORY_COUNT
FROM CUSTOMER_MASTER cm
WHERE cm.CUSTOMER_ID IS NOT NULL;
/
"""


def print_tree(tree: list, indent: int = 0) -> None:
    """Pretty-print the entity tree."""
    for node in tree:
        prefix = "  " * indent + ("├── " if indent > 0 else "")
        op = f"/{node['operation_type']}" if node.get("operation_type") else ""
        print(
            f"{prefix}{node['entity_name']} ({node['entity_type']}{op}) "
            f"[id={node['entity_id']}, chunks={node['chunk_ids']}, "
            f"code={node['code_length']} chars]"
        )
        if node.get("children"):
            print_tree(node["children"], indent + 1)


def run_test():
    llm = get_llm()

    # Use small window to force multi-chunk processing
    chunker = SQLChunker(SAMPLE_SQL, window_size=40, overlap=5)
    chunks = list(chunker)
    print(f"SQL split into {len(chunks)} chunks (window=40, overlap=5)")
    print()

    # Run the separator
    separator = CodeSeparator(llm, max_retries=3)
    registry = separator.process(chunker)

    # Print results
    print("\n" + "=" * 70)
    print("ENTITY REGISTRY")
    print("=" * 70)
    print(f"\n{registry.summary()}\n")

    # Print tree
    print("\n--- TREE ---\n")
    tree = registry.get_tree()
    print_tree(tree)

    # Print details for each entity
    print("\n\n--- ENTITY DETAILS ---\n")
    for entry in registry.get_all():
        print(f"[{entry.entity_id}] {entry.entity_name} ({entry.entity_type}"
              f"{'/' + entry.operation_type if entry.operation_type else ''})")
        print(f"  Parent: {entry.parent_id or '(root)'}")
        print(f"  Level: {entry.nesting_level}")
        print(f"  Chunks: {entry.chunk_ids}")
        print(f"  Resolved: {entry.is_resolved}")
        print(f"  Code length: {len(entry.resolved_code)} chars")
        if entry.trigger_target:
            print(f"  Trigger target: {entry.trigger_target}")
        # Show first 3 lines of code
        code_lines = entry.resolved_code.strip().splitlines()
        preview = "\n    ".join(code_lines[:3])
        if len(code_lines) > 3:
            preview += f"\n    ... ({len(code_lines) - 3} more lines)"
        print(f"  Code preview:\n    {preview}")
        if entry.description:
            desc_preview = entry.description[:200]
            if len(entry.description) > 200:
                desc_preview += "..."
            print(f"  Description: {desc_preview}")
        print()

    # Save registry
    registry.save_to_file("test_separator_output/entity_registry.json")
    print("Registry saved to test_separator_output/entity_registry.json")


if __name__ == "__main__":
    run_test()
