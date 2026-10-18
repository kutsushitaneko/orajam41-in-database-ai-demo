-- ADMIN on arakawalab. Configure the target ADB dynamic group and IAM policies first.
DECLARE
  l_count PLS_INTEGER;
  l_db VARCHAR2(128) := LOWER(SYS_CONTEXT('USERENV','DB_NAME'));
BEGIN
  IF SYS_CONTEXT('USERENV','SESSION_USER') <> 'ADMIN'
     OR NOT (l_db = 'arakawalab' OR l_db LIKE '%\_arakawalab' ESCAPE '\') THEN
    RAISE_APPLICATION_ERROR(-20001, 'Connect to arakawalab as ADMIN.');
  END IF;
  SELECT COUNT(*) INTO l_count FROM dba_users WHERE username='ORAJAM41USER';
  IF l_count <> 1 THEN
    RAISE_APPLICATION_ERROR(-20002, 'Create ORAJAM41USER first.');
  END IF;
  SELECT COUNT(*) INTO l_count FROM dba_credentials
    WHERE owner='ADMIN' AND credential_name='OCI$RESOURCE_PRINCIPAL';
  IF l_count = 0 THEN
    DBMS_CLOUD_ADMIN.ENABLE_RESOURCE_PRINCIPAL();
  END IF;
  SELECT COUNT(*) INTO l_count FROM dba_tab_privs
    WHERE grantee='ORAJAM41USER' AND owner='ADMIN'
      AND table_name='OCI$RESOURCE_PRINCIPAL' AND privilege='EXECUTE';
  IF l_count = 0 THEN
    DBMS_CLOUD_ADMIN.ENABLE_RESOURCE_PRINCIPAL(
      username => 'ORAJAM41USER', grant_option => FALSE);
  END IF;
END;
/

SELECT grantee, owner, table_name, privilege FROM dba_tab_privs
WHERE grantee='ORAJAM41USER' AND table_name='OCI$RESOURCE_PRINCIPAL';
