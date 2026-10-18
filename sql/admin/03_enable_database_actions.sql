-- Optional: ADMIN on arakawalab, when using Database Actions with ORAJAM41USER.
-- No application tables are enabled for AutoREST by this script.
DECLARE
  l_db VARCHAR2(128) := LOWER(SYS_CONTEXT('USERENV','DB_NAME'));
BEGIN
  IF SYS_CONTEXT('USERENV','SESSION_USER') <> 'ADMIN'
     OR NOT (l_db = 'arakawalab' OR l_db LIKE '%\_arakawalab' ESCAPE '\') THEN
    RAISE_APPLICATION_ERROR(-20001, 'Connect to arakawalab as ADMIN.');
  END IF;
  ORDS.ENABLE_SCHEMA(
    p_enabled => TRUE,
    p_schema => 'ORAJAM41USER',
    p_url_mapping_type => 'BASE_PATH',
    p_url_mapping_pattern => 'orajam41user',
    p_auto_rest_auth => TRUE);
  COMMIT;
END;
/
