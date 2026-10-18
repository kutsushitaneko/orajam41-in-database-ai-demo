-- Run as ORAJAM41USER on arakawalab. Replace the URI in a local copy.
-- DBMS_VECTOR also reads the External Initializer files from the same prefix.
DECLARE
  l_uri VARCHAR2(4000) := 'REPLACE_WITH_ONNX_URI';
  l_count PLS_INTEGER;
  l_db VARCHAR2(128) := LOWER(SYS_CONTEXT('USERENV','DB_NAME'));
BEGIN
  IF SYS_CONTEXT('USERENV','SESSION_USER') <> 'ORAJAM41USER'
     OR NOT (l_db='arakawalab' OR l_db LIKE '%\_arakawalab' ESCAPE '\') THEN
    RAISE_APPLICATION_ERROR(-20001, 'Connect to arakawalab as ORAJAM41USER.');
  END IF;
  IF l_uri = 'REPLACE_WITH_ONNX_URI' THEN
    RAISE_APPLICATION_ERROR(-20002, 'Set the ONNX URI in a local copy.');
  END IF;
  SELECT COUNT(*) INTO l_count FROM user_mining_models
  WHERE model_name='MULTILINGUAL_E5_LARGE';
  IF l_count = 0 THEN
    DBMS_VECTOR.LOAD_ONNX_MODEL_CLOUD(
      model_name => 'MULTILINGUAL_E5_LARGE',
      credential => 'OCI$RESOURCE_PRINCIPAL',
      uri => l_uri,
      metadata => JSON('{"function":"embedding","embeddingOutput":"embedding","input":{"input":["DATA"]}}'));
  END IF;
  -- Import resets INMEMORY to NO. Share external initializers across sessions.
  DBMS_VECTOR.INMEMORY_ONNX_MODEL(
    model_name => 'MULTILINGUAL_E5_LARGE', enable => TRUE);
END;
/

SELECT model_name, mining_function, algorithm, external_data, inmemory FROM user_mining_models
WHERE model_name='MULTILINGUAL_E5_LARGE';

SELECT VECTOR_DIMENSION_COUNT(
  VECTOR_EMBEDDING(MULTILINGUAL_E5_LARGE USING 'query: サーバーが応答しない' AS data)
) AS dimensions FROM dual;
