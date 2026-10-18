-- ADMIN: COPY_DATA log/bad-file directory permission (existing arakawalab).
DECLARE
  l_db VARCHAR2(128) := LOWER(SYS_CONTEXT('USERENV','DB_NAME'));
BEGIN
  IF SYS_CONTEXT('USERENV','SESSION_USER') <> 'ADMIN'
     OR NOT (l_db='arakawalab' OR l_db LIKE '%\_arakawalab' ESCAPE '\') THEN
    RAISE_APPLICATION_ERROR(-20001,'Connect to arakawalab as ADMIN.');
  END IF;
  EXECUTE IMMEDIATE 'GRANT READ, WRITE ON DIRECTORY DATA_PUMP_DIR TO orajam41user';
END;
/
