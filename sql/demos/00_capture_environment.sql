-- ORAJAM41USER, arakawalab. Read-only queries for screenshot S01.
-- Hide connection strings, credentials and unrelated tabs before capturing.
SELECT SYS_CONTEXT('USERENV','SESSION_USER') AS session_user,
       SYS_CONTEXT('USERENV','CURRENT_SCHEMA') AS current_schema
FROM dual;

SELECT model_name, mining_function, algorithm, external_data, inmemory
FROM user_mining_models
WHERE model_name='MULTILINGUAL_E5_LARGE';

SELECT VECTOR_DIMENSION_COUNT(
  VECTOR_EMBEDDING(MULTILINGUAL_E5_LARGE
    USING 'query: 管理画面が応答しない' AS data)) AS dimensions
FROM dual;

SELECT COUNT(*) AS document_count,
       SUM(CASE WHEN embedding IS NOT NULL THEN 1 ELSE 0 END) AS embedded_count
FROM OJ41_CHUNKS;
