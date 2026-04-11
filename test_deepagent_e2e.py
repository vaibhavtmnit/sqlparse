"""
test_deepagent_e2e.py

End-to-end test of the deepagent miner pipeline with a real LLM call
on a substantial Oracle SQL code sample.
"""

import shutil
from pathlib import Path
from src.miner.miner import SQLMiner
from src.agents.llm import get_llm
from loguru import logger

SAMPLE_SQL = """\
-- ============================================================
-- ETL Package: PKG_CUSTOMER_ETL
-- Purpose: Load and transform customer data from staging to
--          production tables with full audit trail.
-- ============================================================

CREATE OR REPLACE PACKAGE BODY PKG_CUSTOMER_ETL AS

    -- ---------------------------------------------------------
    -- Procedure: LOAD_STAGING
    -- Reads from external source table and populates staging
    -- ---------------------------------------------------------
    PROCEDURE LOAD_STAGING IS
        v_batch_id   NUMBER;
        v_row_count  NUMBER := 0;
    BEGIN
        -- Get next batch identifier
        SELECT SEQ_BATCH_ID.NEXTVAL INTO v_batch_id FROM DUAL;

        -- Truncate staging before fresh load
        EXECUTE IMMEDIATE 'TRUNCATE TABLE STG_CUSTOMER_RAW';

        -- Load raw customer data from source
        INSERT INTO STG_CUSTOMER_RAW (
            BATCH_ID, CUSTOMER_ID, FIRST_NAME, LAST_NAME,
            EMAIL, PHONE, ADDRESS_LINE1, ADDRESS_LINE2,
            CITY, STATE, ZIP_CODE, COUNTRY,
            CREATED_DATE, MODIFIED_DATE
        )
        SELECT
            v_batch_id,
            src.CUST_ID,
            UPPER(TRIM(src.FNAME)),
            UPPER(TRIM(src.LNAME)),
            LOWER(TRIM(src.EMAIL_ADDR)),
            REGEXP_REPLACE(src.PHONE_NUM, '[^0-9]', ''),
            src.ADDR1,
            src.ADDR2,
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

        -- Log the load
        INSERT INTO AUDIT_LOG (
            LOG_ID, BATCH_ID, PROCEDURE_NAME,
            ROWS_PROCESSED, STATUS, LOG_TIMESTAMP
        )
        VALUES (
            SEQ_AUDIT_LOG.NEXTVAL, v_batch_id, 'LOAD_STAGING',
            v_row_count, 'SUCCESS', SYSTIMESTAMP
        );

        COMMIT;

        DBMS_OUTPUT.PUT_LINE('LOAD_STAGING: Loaded ' || v_row_count || ' rows.');
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
    -- Applies business rules and deduplication
    -- ---------------------------------------------------------
    PROCEDURE TRANSFORM_AND_VALIDATE IS
        v_batch_id   NUMBER;
        v_valid      NUMBER := 0;
        v_invalid    NUMBER := 0;
    BEGIN
        SELECT MAX(BATCH_ID) INTO v_batch_id FROM STG_CUSTOMER_RAW;

        -- Validate email format
        UPDATE STG_CUSTOMER_RAW
        SET VALIDATION_STATUS = 'INVALID_EMAIL'
        WHERE BATCH_ID = v_batch_id
          AND NOT REGEXP_LIKE(EMAIL, '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}$');

        -- Validate phone (must be 10+ digits)
        UPDATE STG_CUSTOMER_RAW
        SET VALIDATION_STATUS = NVL(VALIDATION_STATUS || ',', '') || 'INVALID_PHONE'
        WHERE BATCH_ID = v_batch_id
          AND LENGTH(PHONE) < 10
          AND VALIDATION_STATUS IS NULL;

        -- Mark remaining as valid
        UPDATE STG_CUSTOMER_RAW
        SET VALIDATION_STATUS = 'VALID'
        WHERE BATCH_ID = v_batch_id
          AND VALIDATION_STATUS IS NULL;

        -- Deduplicate: keep latest by MODIFIED_DATE per CUSTOMER_ID
        DELETE FROM STG_CUSTOMER_RAW a
        WHERE a.ROWID > (
            SELECT MIN(b.ROWID)
            FROM STG_CUSTOMER_RAW b
            WHERE b.CUSTOMER_ID = a.CUSTOMER_ID
              AND b.BATCH_ID = v_batch_id
              AND b.VALIDATION_STATUS = 'VALID'
        )
        AND a.BATCH_ID = v_batch_id;

        SELECT COUNT(*) INTO v_valid
        FROM STG_CUSTOMER_RAW
        WHERE BATCH_ID = v_batch_id AND VALIDATION_STATUS = 'VALID';

        SELECT COUNT(*) INTO v_invalid
        FROM STG_CUSTOMER_RAW
        WHERE BATCH_ID = v_batch_id AND VALIDATION_STATUS != 'VALID';

        -- Archive invalid records
        INSERT INTO CUSTOMER_REJECTS (
            REJECT_ID, BATCH_ID, CUSTOMER_ID,
            REJECT_REASON, ORIGINAL_DATA, REJECT_DATE
        )
        SELECT
            SEQ_REJECT_ID.NEXTVAL, BATCH_ID, CUSTOMER_ID,
            VALIDATION_STATUS,
            FIRST_NAME || '|' || LAST_NAME || '|' || EMAIL || '|' || PHONE,
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
            v_valid + v_invalid, 'SUCCESS', SYSTIMESTAMP
        );

        COMMIT;
    END TRANSFORM_AND_VALIDATE;

    -- ---------------------------------------------------------
    -- Procedure: MERGE_TO_PRODUCTION
    -- Upserts valid staging data into production customer table
    -- ---------------------------------------------------------
    PROCEDURE MERGE_TO_PRODUCTION IS
        v_batch_id    NUMBER;
        v_merged      NUMBER := 0;
        v_inserted    NUMBER := 0;
        v_updated     NUMBER := 0;
    BEGIN
        SELECT MAX(BATCH_ID) INTO v_batch_id FROM STG_CUSTOMER_RAW;

        -- Use CTE to prepare merge-ready data
        MERGE INTO CUSTOMER_MASTER tgt
        USING (
            WITH CTE_VALID_CUSTOMERS AS (
                SELECT
                    CUSTOMER_ID,
                    FIRST_NAME,
                    LAST_NAME,
                    EMAIL,
                    PHONE,
                    ADDRESS_LINE1,
                    ADDRESS_LINE2,
                    CITY,
                    STATE,
                    ZIP_CODE,
                    COUNTRY,
                    MODIFIED_DATE
                FROM STG_CUSTOMER_RAW
                WHERE BATCH_ID = v_batch_id
                  AND VALIDATION_STATUS = 'VALID'
            )
            SELECT * FROM CTE_VALID_CUSTOMERS
        ) src
        ON (tgt.CUSTOMER_ID = src.CUSTOMER_ID)
        WHEN MATCHED THEN
            UPDATE SET
                tgt.FIRST_NAME     = src.FIRST_NAME,
                tgt.LAST_NAME      = src.LAST_NAME,
                tgt.EMAIL           = src.EMAIL,
                tgt.PHONE           = src.PHONE,
                tgt.ADDRESS_LINE1   = src.ADDRESS_LINE1,
                tgt.ADDRESS_LINE2   = src.ADDRESS_LINE2,
                tgt.CITY            = src.CITY,
                tgt.STATE           = src.STATE,
                tgt.ZIP_CODE        = src.ZIP_CODE,
                tgt.COUNTRY         = src.COUNTRY,
                tgt.LAST_UPDATED    = SYSDATE,
                tgt.UPDATE_BATCH_ID = v_batch_id
        WHEN NOT MATCHED THEN
            INSERT (
                CUSTOMER_ID, FIRST_NAME, LAST_NAME, EMAIL, PHONE,
                ADDRESS_LINE1, ADDRESS_LINE2, CITY, STATE, ZIP_CODE,
                COUNTRY, CREATED_DATE, LAST_UPDATED, CREATE_BATCH_ID
            )
            VALUES (
                src.CUSTOMER_ID, src.FIRST_NAME, src.LAST_NAME,
                src.EMAIL, src.PHONE, src.ADDRESS_LINE1, src.ADDRESS_LINE2,
                src.CITY, src.STATE, src.ZIP_CODE, src.COUNTRY,
                SYSDATE, SYSDATE, v_batch_id
            );

        v_merged := SQL%ROWCOUNT;

        -- Update customer dimension for reporting
        INSERT INTO CUSTOMER_DIM_HISTORY (
            HISTORY_ID, CUSTOMER_ID, SNAPSHOT_DATE,
            FIRST_NAME, LAST_NAME, EMAIL, CITY, STATE, COUNTRY
        )
        SELECT
            SEQ_DIM_HISTORY.NEXTVAL,
            cm.CUSTOMER_ID, SYSDATE,
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
    -- Main orchestrator procedure
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
-- Fires after any DML on CUSTOMER_MASTER for change tracking
-- ============================================================
CREATE OR REPLACE TRIGGER TRG_CUSTOMER_AUDIT
AFTER INSERT OR UPDATE OR DELETE ON CUSTOMER_MASTER
FOR EACH ROW
DECLARE
    v_action VARCHAR2(10);
BEGIN
    IF INSERTING THEN
        v_action := 'INSERT';
    ELSIF UPDATING THEN
        v_action := 'UPDATE';
    ELSIF DELETING THEN
        v_action := 'DELETE';
    END IF;

    INSERT INTO CUSTOMER_CHANGE_LOG (
        CHANGE_ID, CUSTOMER_ID, ACTION_TYPE,
        OLD_EMAIL, NEW_EMAIL,
        OLD_PHONE, NEW_PHONE,
        CHANGE_DATE, CHANGED_BY
    )
    VALUES (
        SEQ_CHANGE_LOG.NEXTVAL,
        NVL(:NEW.CUSTOMER_ID, :OLD.CUSTOMER_ID),
        v_action,
        :OLD.EMAIL, :NEW.EMAIL,
        :OLD.PHONE, :NEW.PHONE,
        SYSTIMESTAMP, USER
    );
END TRG_CUSTOMER_AUDIT;
/

-- ============================================================
-- View: VW_CUSTOMER_SUMMARY
-- Consolidated customer view for reporting
-- ============================================================
CREATE OR REPLACE VIEW VW_CUSTOMER_SUMMARY AS
SELECT
    cm.CUSTOMER_ID,
    cm.FIRST_NAME || ' ' || cm.LAST_NAME AS FULL_NAME,
    cm.EMAIL,
    cm.PHONE,
    cm.CITY || ', ' || cm.STATE || ' ' || cm.ZIP_CODE AS FULL_ADDRESS,
    cm.COUNTRY,
    cm.CREATED_DATE,
    cm.LAST_UPDATED,
    (SELECT COUNT(*)
     FROM CUSTOMER_DIM_HISTORY dh
     WHERE dh.CUSTOMER_ID = cm.CUSTOMER_ID) AS HISTORY_COUNT
FROM CUSTOMER_MASTER cm
WHERE cm.CUSTOMER_ID IS NOT NULL;
/
"""


def run_test():
    workspace = Path("./test_workspace_deepagent")
    if workspace.exists():
        shutil.rmtree(workspace)

    logger.info("Initialising SQLMiner with pipeline='deepagent', output_mode='pydantic'...")
    llm = get_llm()
    miner = SQLMiner(
        llm=llm,
        workspace=str(workspace),
        window_size=120,
        overlap=15,
        pipeline="deepagent",
        output_mode="pydantic",
    )

    logger.info("Running deepagent miner on sample SQL...")
    miner.run(SAMPLE_SQL)

    # Print results
    import json
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)

    for name in ("entities", "relationships", "flows"):
        path = workspace / "mining" / "output" / f"{name}.json"
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            print(f"\n--- {name.upper()} ({len(data)} records) ---")
            for item in data:
                if name == "entities":
                    print(f"  [{item.get('id')}] {item.get('entity_name')} ({item.get('entity_type')}) chunk={item.get('chunk_id')} flow={item.get('flow_id')}")
                elif name == "relationships":
                    print(f"  [{item.get('id')}] {item.get('source')} --{item.get('relationship_tag')}--> {item.get('target')} chunk={item.get('chunk_id')}")
                elif name == "flows":
                    print(f"  [{item.get('id')}] {item.get('flow_id')}: {item.get('flow_entity_name')} ({item.get('flow_entity_role')}) parent={item.get('parent_flow_id')} chunk={item.get('flow_entity_chunk_id')}")
        else:
            print(f"\n--- {name.upper()}: file not found ---")

    # Check chunk details
    details_dir = workspace / "mining" / "output" / "chunk_details"
    if details_dir.exists():
        details = sorted(details_dir.glob("*.txt"))
        print(f"\n--- CHUNK DETAILS ({len(details)} files) ---")
        for d in details:
            text = d.read_text(encoding="utf-8")
            print(f"  {d.name}: {len(text)} chars — {text[:80]}...")


if __name__ == "__main__":
    run_test()
