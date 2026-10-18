-- Run as ORAJAM41USER. Read-only; no LLM calls or model loading.
SELECT SYS_CONTEXT('USERENV','DB_NAME') AS db_name,
       SYS_CONTEXT('USERENV','SESSION_USER') AS session_user,
       SYS_CONTEXT('USERENV','CURRENT_SCHEMA') AS current_schema
FROM dual;

SELECT privilege FROM session_privs ORDER BY privilege;
SELECT table_name, privilege FROM all_tab_privs
WHERE grantee='ORAJAM41USER'
  AND table_name IN ('DBMS_CLOUD','DBMS_VECTOR','DBMS_CLOUD_AI','DBMS_CLOUD_AI_AGENT','OCI$RESOURCE_PRINCIPAL')
ORDER BY table_name;

SELECT model_name, mining_function, algorithm
FROM user_mining_models WHERE model_name='MULTILINGUAL_E5_LARGE';

SELECT tablespace_name, bytes, max_bytes FROM user_ts_quotas;

-- Run only after MULTILINGUAL_E5_LARGE exists in this schema:
-- SELECT VECTOR_DIMENSION_COUNT(
--   VECTOR_EMBEDDING(MULTILINGUAL_E5_LARGE USING 'query: サーバーが応答しない' AS data)
-- ) AS dimensions FROM dual;
