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
          AND NOT REGEXP_LIKE(EMAIL, '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$');

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