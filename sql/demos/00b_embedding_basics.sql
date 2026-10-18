-- Chapter 2: read-only model and vector demonstration on the prepared standard dataset.
-- Run as ORAJAM41USER. No import, data mutation, or case/session state is required.
-- Search all 16 tutorial documents, including other models and retired documents.
-- Business access-control and publication/model filters are introduced in demo A.
SELECT model_name, mining_function, algorithm, external_data, inmemory
FROM user_mining_models
WHERE model_name='MULTILINGUAL_E5_LARGE';

SELECT VECTOR_EMBEDDING(
  MULTILINGUAL_E5_LARGE
  USING 'query: 管理画面が固まって操作できない' AS data
) AS embedding FROM dual;

SELECT VECTOR_DIMENSION_COUNT(
  VECTOR_EMBEDDING(MULTILINGUAL_E5_LARGE
    USING 'query: 管理画面が固まって操作できない' AS data)
) AS dimensions FROM dual;

SELECT chunk_id, doc_id, SUBSTR(chunk_text, 1, 100) AS chunk_text_preview,
       VECTOR_DIMENSION_COUNT(embedding) AS dimensions
FROM OJ41_CHUNKS
ORDER BY doc_id;

SELECT doc_id, chunk_text,
  VECTOR_DISTANCE(embedding,
    VECTOR_EMBEDDING(MULTILINGUAL_E5_LARGE
      USING 'query: 管理画面が固まって操作できない' AS data),
    COSINE) AS distance
FROM OJ41_CHUNKS
ORDER BY distance, doc_id
FETCH FIRST 3 ROWS ONLY;
