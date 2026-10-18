-- ORAJAM41USER: one UTL_TO_EMBEDDINGS call for at most 8 inputs.
DECLARE
  l_dataset VARCHAR2(64) := '__DATASET__';
  TYPE t_ids IS TABLE OF NUMBER;
  l_ids t_ids;
  l_error VARCHAR2(40);
  l_inputs VECTOR_ARRAY_T := VECTOR_ARRAY_T();
  l_outputs VECTOR_ARRAY_T;
  TYPE t_texts IS TABLE OF VARCHAR2(4000) INDEX BY PLS_INTEGER;
  TYPE t_seen IS TABLE OF BOOLEAN INDEX BY PLS_INTEGER;
  l_texts t_texts;
  l_seen t_seen;
  l_obj JSON_OBJECT_T;
  l_id PLS_INTEGER;
  l_vec VECTOR;
  l_vector_text CLOB;
  l_text VARCHAR2(4000);
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
    IF l_ids.COUNT>0 THEN
      l_inputs.extend(l_ids.COUNT);
      FOR i IN 1..l_ids.COUNT LOOP
        SELECT 'passage: '||body_text INTO l_text FROM OJ41_BULK_DOCS
          WHERE dataset_id=l_dataset AND row_no=l_ids(i);
        l_texts(l_ids(i)):=l_text;
        SELECT JSON_OBJECT('chunk_id' VALUE l_ids(i),'chunk_offset' VALUE 1,
          'chunk_length' VALUE LENGTH(l_text),'chunk_data' VALUE l_text RETURNING CLOB)
          INTO l_inputs(i) FROM dual;
      END LOOP;
      l_outputs:=DBMS_VECTOR.UTL_TO_EMBEDDINGS(l_inputs,
        JSON('{"provider":"database","model":"MULTILINGUAL_E5_LARGE"}'));
      IF l_outputs.COUNT<>l_ids.COUNT THEN
        RAISE_APPLICATION_ERROR(-20044,'Output count mismatch');
      END IF;
      FOR i IN 1..l_outputs.COUNT LOOP
        l_obj:=JSON_OBJECT_T.parse(l_outputs(i));
        l_id:=l_obj.get_number('embed_id');
        IF NOT l_texts.exists(l_id) OR l_seen.exists(l_id) THEN
          RAISE_APPLICATION_ERROR(-20045,'Output ID mismatch');
        END IF;
        IF l_obj.get_string('embed_data') IS NULL OR l_obj.get_string('embed_data')<>l_texts(l_id) THEN
          RAISE_APPLICATION_ERROR(-20046,'Output text mismatch');
        END IF;
        l_seen(l_id):=TRUE;
        l_vector_text:=l_obj.get_clob('embed_vector');
        SELECT TO_VECTOR(l_vector_text,1024,FLOAT32) INTO l_vec FROM dual;
        IF l_vec IS NULL THEN
          RAISE_APPLICATION_ERROR(-20047,'Missing output vector');
        END IF;
        UPDATE OJ41_BULK_DOCS SET embedding=l_vec,
          embedding_model='MULTILINGUAL_E5_LARGE',embed_state='DONE',embed_error=NULL
          WHERE dataset_id=l_dataset AND row_no=l_id;
      END LOOP;
    END IF;
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
