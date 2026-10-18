-- Fictional manufacturer support registration numbers: DEV001 identifies one server.
-- Same DB connection throughout this workbook. Staff selects an accepted case.
-- Database Actions: run this whole file as ONE script; state does not persist between executions.
-- For one query, run open_case + that SELECT + clear_case together as ONE script.
BEGIN OJ41_CASE_CTX.open_case('SR001'); END;
/
SELECT s.case_id, c.customer_id, c.customer_name
FROM OJ41_SUPPORT_CASES s JOIN OJ41_CUSTOMERS c ON c.customer_id=s.customer_id
WHERE s.case_id=OJ41_CASE_CTX.current_case();

SELECT device_id, model, contract_id, status, is_active, onsite_eligible
FROM OJ41_VISIBLE_CONTRACTS
ORDER BY device_id;

-- A0: match the manufacturer's registration number within those contracts.
SELECT device_id, model, contract_id, status, is_active, onsite_eligible
FROM OJ41_VISIBLE_CONTRACTS
WHERE device_id = 'DEV001';

-- ORAJAM41USER. All search routes use the same scoped view and require an active case.
-- A1: synonym search, exact cosine distance (smaller is closer).
SELECT doc_id, title,
  VECTOR_DISTANCE(embedding,
    VECTOR_EMBEDDING(MULTILINGUAL_E5_LARGE USING 'query: 管理画面が固まって操作できない' AS data), COSINE) AS distance
FROM OJ41_VISIBLE_CHUNKS
WHERE model='AX-100' AND embedding IS NOT NULL
ORDER BY distance, doc_id
FETCH FIRST 3 ROWS ONLY;

-- A2: substring search cannot find a synonym absent from the text. Expected: 0 rows.
SELECT doc_id, title FROM OJ41_VISIBLE_CHUNKS
WHERE model='AX-100' AND INSTR(chunk_text, '固まって') > 0;

-- A3: compare E101 across models before adding the model filter.
SELECT doc_id, model, title,
  VECTOR_DISTANCE(embedding,
    VECTOR_EMBEDDING(MULTILINGUAL_E5_LARGE USING 'query: E101の対処は？' AS data), COSINE) AS distance
FROM OJ41_VISIBLE_CHUNKS
WHERE embedding IS NOT NULL
ORDER BY distance, doc_id
FETCH FIRST 3 ROWS ONLY;

BEGIN OJ41_CASE_CTX.clear_case; END;
/
