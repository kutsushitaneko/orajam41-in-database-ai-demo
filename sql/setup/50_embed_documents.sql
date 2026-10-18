-- Run once before the webinar. Existing embeddings for this model are retained.
BEGIN
  IF SYS_CONTEXT('USERENV','SESSION_USER') <> 'ORAJAM41USER'
     OR SYS_CONTEXT('USERENV','CURRENT_SCHEMA') <> 'ORAJAM41USER'
     OR NOT (LOWER(SYS_CONTEXT('USERENV','DB_NAME')) = 'arakawalab'
       OR LOWER(SYS_CONTEXT('USERENV','DB_NAME')) LIKE '%\_arakawalab' ESCAPE '\') THEN
    RAISE_APPLICATION_ERROR(-20041, 'Unexpected database or user');
  END IF;
  UPDATE OJ41_CHUNKS
  SET embedding=VECTOR_EMBEDDING(MULTILINGUAL_E5_LARGE USING 'passage: ' || chunk_text AS data),
      embedding_model='MULTILINGUAL_E5_LARGE'
  WHERE embedding IS NULL OR embedding_model IS NULL OR embedding_model <> 'MULTILINGUAL_E5_LARGE';
  COMMIT;
EXCEPTION WHEN OTHERS THEN
  ROLLBACK;
  RAISE;
END;
/
