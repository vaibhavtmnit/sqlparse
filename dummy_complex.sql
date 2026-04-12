CREATE OR REPLACE PACKAGE hr_management_pkg AS
    TYPE employee_record IS RECORD (
        emp_id NUMBER,
        emp_name VARCHAR2(100),
        salary NUMBER
    );
    
    TYPE employee_table IS TABLE OF employee_record;

    PROCEDURE process_payroll(p_dept_id NUMBER);
    FUNCTION get_top_performers(p_limit NUMBER) RETURN employee_table;
END hr_management_pkg;
/

CREATE OR REPLACE PACKAGE BODY hr_management_pkg AS

    PROCEDURE process_payroll(p_dept_id NUMBER) IS
        l_emps employee_table;
    BEGIN
        -- Nested Table Operation: Bulk collect into nested table
        SELECT emp_id, emp_name, salary 
        BULK COLLECT INTO l_emps
        FROM employees
        WHERE department_id = p_dept_id;

        FOR i IN 1..l_emps.COUNT LOOP
            IF l_emps(i).salary < 5000 THEN
                UPDATE employees 
                SET salary = salary * 1.1 
                WHERE emp_id = l_emps(i).emp_id;
            END IF;
        END LOOP;
        
        COMMIT;
    END process_payroll;

    FUNCTION get_top_performers(p_limit NUMBER) RETURN employee_table IS
        l_result employee_table := employee_table();
    BEGIN
        -- Nested Table Operation: Initialize and extend
        FOR r IN (SELECT emp_id, emp_name, salary 
                  FROM employees 
                  ORDER BY salary DESC) 
        LOOP
            IF l_result.COUNT < p_limit THEN
                l_result.EXTEND;
                l_result(l_result.COUNT) := employee_record(r.emp_id, r.emp_name, r.salary);
            ELSE
                EXIT;
            END IF;
        END LOOP;
        
        RETURN l_result;
    END get_top_performers;

END hr_management_pkg;
/

-- Additional complex structure Example: Table with nested table column
CREATE TYPE phone_number_t AS TABLE OF VARCHAR2(20);
/

CREATE TABLE contact_info (
    contact_id NUMBER,
    contact_name VARCHAR2(100),
    phones phone_number_t
) NESTED TABLE phones STORE AS phones_tab;
/

-- Operation on Nested Table Column
INSERT INTO contact_info VALUES (1, 'John Doe', phone_number_t('123-456', '789-012'));
/

UPDATE TABLE(SELECT phones FROM contact_info WHERE contact_id = 1) p
SET COLUMN_VALUE = '555-555'
WHERE COLUMN_VALUE = '123-456';
/

-- Query with nested table operator
SELECT contact_name, p.COLUMN_VALUE 
FROM contact_info c, TABLE(c.phones) p;
/
