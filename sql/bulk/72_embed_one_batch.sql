-- ORAJAM41USER: one batch, at most 8 rows among the first 32.
DECLARE
  l_dataset VARCHAR2(64) := '__DATASET__';
  TYPE t_ids IS TABLE OF NUMBER;
  l_ids t_ids;
  l_error VARCHAR2(40);
BEGIN
  IF SYS_CONTEXT('USERENV','SESSION_USER')<>'ORAJAM41USER'
     OR SYS_CONTEXT('USERENV','CURRENT_SCHEMA')<>'ORAJAM41USER'
     OR NOT (LOWER(SYS_CONTEXT('USERENV','DB_NAME'))='arakawalab'
       OR LOWER(SYS_CONTEXT('USERENV','DB_NAME')) LIKE '%\_arakawalab' ESCAPE '\') THEN
    RAISE_APPLICATION_ERROR(-20041,'Unexpected database or schema');
  END IF;
  IF l_dataset='__DATA' || 'SET__' THEN
    RAISE_APPLICATION_ERROR(-20042,'Render local SQL first');
  END IF;
  SELECT row_no BULK COLLECT INTO l_ids FROM OJ41_BULK_DOCS
    WHERE dataset_id=l_dataset AND row_no<=32
      AND (embed_state<>'DONE' OR embedding IS NULL OR embedding_model IS NULL
        OR embedding_model<>'MULTILINGUAL_E5_LARGE')
    ORDER BY row_no FETCH FIRST 8 ROWS ONLY;
  BEGIN
    FOR i IN 1..l_ids.COUNT LOOP
      UPDATE OJ41_BULK_DOCS SET
        embedding=VECTOR_EMBEDDING(MULTILINGUAL_E5_LARGE USING 'passage: ' || body_text AS data),
        embedding_model='MULTILINGUAL_E5_LARGE',embed_state='DONE',embed_error=NULL
        WHERE dataset_id=l_dataset AND row_no=l_ids(i);
    END LOOP;
    COMMIT;
  EXCEPTION WHEN OTHERS THEN
    l_error:=TO_CHAR(SQLCODE);
    ROLLBACK;
    FOR i IN 1..l_ids.COUNT LOOP
      UPDATE OJ41_BULK_DOCS SET embed_state='FAILED',embed_error=l_error
        WHERE dataset_id=l_dataset AND row_no=l_ids(i);
    END LOOP;
    COMMIT;
    RAISE;
  END;
  DBMS_OUTPUT.PUT_LINE('Embedded rows=' || l_ids.COUNT);
END;
/
