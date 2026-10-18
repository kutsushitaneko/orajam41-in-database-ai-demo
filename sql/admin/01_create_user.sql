-- Connect as ADMIN to the existing arakawalab database.
-- Replace the password locally. Do not save a real password in this tracked file.
-- Initial quota: 10 GiB, including the large embedding model; adjust after measurement.
DECLARE
  l_password VARCHAR2(128) := 'REPLACE_WITH_LOCAL_PASSWORD';
  l_count PLS_INTEGER;
  l_db VARCHAR2(128) := LOWER(SYS_CONTEXT('USERENV', 'DB_NAME'));
BEGIN
  IF SYS_CONTEXT('USERENV','SESSION_USER') <> 'ADMIN'
     OR NOT (l_db = 'arakawalab' OR l_db LIKE '%\_arakawalab' ESCAPE '\') THEN
    RAISE_APPLICATION_ERROR(-20001, 'Connect to arakawalab as ADMIN.');
  END IF;
  IF l_password = 'REPLACE_WITH_LOCAL_PASSWORD' THEN
    RAISE_APPLICATION_ERROR(-20002, 'Set a local password before running this block.');
  END IF;
  SELECT COUNT(*) INTO l_count FROM dba_users WHERE username = 'ORAJAM41USER';
  IF l_count <> 0 THEN
    RAISE_APPLICATION_ERROR(-20003, 'ORAJAM41USER already exists. Inspect it; do not recreate or reset it.');
  END IF;
  EXECUTE IMMEDIATE 'CREATE USER orajam41user IDENTIFIED BY '
    || DBMS_ASSERT.ENQUOTE_NAME(l_password, FALSE)
    || ' DEFAULT TABLESPACE DATA QUOTA 10G ON DATA';
  EXECUTE IMMEDIATE 'GRANT CREATE SESSION, CREATE TABLE, CREATE VIEW, CREATE PROCEDURE, CREATE SEQUENCE, CREATE MINING MODEL TO orajam41user';
  EXECUTE IMMEDIATE 'GRANT EXECUTE ON DBMS_CLOUD TO orajam41user';
  EXECUTE IMMEDIATE 'GRANT EXECUTE ON DBMS_VECTOR TO orajam41user';
  EXECUTE IMMEDIATE 'GRANT EXECUTE ON DBMS_CLOUD_AI TO orajam41user';
  EXECUTE IMMEDIATE 'GRANT EXECUTE ON DBMS_CLOUD_AI_AGENT TO orajam41user';
END;
/

-- DDL commits independently. If a grant fails, inspect these results;
-- do not drop/recreate the user or rerun password changes.
SELECT username, account_status, default_tablespace FROM dba_users WHERE username='ORAJAM41USER';
SELECT privilege FROM dba_sys_privs WHERE grantee='ORAJAM41USER' ORDER BY privilege;
SELECT owner, table_name, privilege FROM dba_tab_privs WHERE grantee='ORAJAM41USER' ORDER BY table_name;
