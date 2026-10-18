-- ORAJAM41USER: stage only; replace values in a local copy.
-- Render with: python -m webinar_demo.bulk --render-sql
DECLARE
  l_dataset VARCHAR2(64) := '__DATASET__';
  l_uri VARCHAR2(4000) := '__URI__';
  l_op NUMBER;
  l_rows NUMBER;
  l_distinct NUMBER;
BEGIN
  IF SYS_CONTEXT('USERENV','SESSION_USER')<>'ORAJAM41USER'
     OR SYS_CONTEXT('USERENV','CURRENT_SCHEMA')<>'ORAJAM41USER'
     OR NOT (LOWER(SYS_CONTEXT('USERENV','DB_NAME'))='arakawalab'
       OR LOWER(SYS_CONTEXT('USERENV','DB_NAME')) LIKE '%\_arakawalab' ESCAPE '\') THEN
    RAISE_APPLICATION_ERROR(-20041,'Unexpected database or schema');
  END IF;
  IF l_dataset='__DATA' || 'SET__' OR l_uri='__U' || 'RI__' THEN
    RAISE_APPLICATION_ERROR(-20042,'Render local SQL first');
  END IF;
  DELETE FROM OJ41_BULK_STAGE WHERE dataset_id=l_dataset AND part_no=1;
  COMMIT;
  DBMS_CLOUD.COPY_DATA(
    table_name=>'OJ41_BULK_STAGE',
    credential_name=>'OCI$RESOURCE_PRINCIPAL',
    file_uri_list=>l_uri,
    format=>'__FORMAT__',
    operation_id=>l_op);
  SELECT COUNT(*),COUNT(DISTINCT row_no) INTO l_rows,l_distinct
    FROM OJ41_BULK_STAGE WHERE dataset_id=l_dataset AND part_no=1;
  IF l_rows<>__ROWS__ OR l_distinct<>__ROWS__ THEN
    RAISE_APPLICATION_ERROR(-20043,'Staging count mismatch');
  END IF;
  DBMS_OUTPUT.PUT_LINE('operation_id=' || l_op || ', rows=' || l_rows);
  -- No promotion here: bulk --route cloud validates every column before MERGE.
END;
/
