-- Case selection is connection-local.
BEGIN OJ41_CASE_CTX.open_case('SR001'); END;
/
-- Read-only checks. Expected results refer to the standard dataset.
SELECT 'KNOWLEDGE' AS dataset, COUNT(*) AS actual_count, 16 AS expected_count FROM OJ41_KNOWLEDGE
UNION ALL SELECT 'CUSTOMERS', COUNT(*), 2 FROM OJ41_CUSTOMERS
UNION ALL SELECT 'SUPPORT_CASES', COUNT(*), 2 FROM OJ41_SUPPORT_CASES
UNION ALL SELECT 'CHUNKS', COUNT(*), 16 FROM OJ41_CHUNKS
UNION ALL SELECT 'DEVICES', COUNT(*), 12 FROM OJ41_DEVICES
UNION ALL SELECT 'CONTRACTS', COUNT(*), 12 FROM OJ41_CONTRACTS;

SELECT * FROM OJ41_RUN;

-- C001: 12 visible documents. KB004/013/014/015 must be absent.
SELECT doc_id, model, title FROM OJ41_VISIBLE_KNOWLEDGE ORDER BY doc_id;

-- Zero rows: foreign-key orphans.
SELECT c.chunk_id FROM OJ41_CHUNKS c
LEFT JOIN OJ41_KNOWLEDGE k ON k.doc_id=c.doc_id WHERE k.doc_id IS NULL;
SELECT c.contract_id FROM OJ41_CONTRACTS c
LEFT JOIN OJ41_DEVICES d ON d.device_id=c.device_id WHERE d.device_id IS NULL;

-- Expected: DEV001, DEV005, DEV006, DEV008 (date endpoints are inclusive).
SELECT device_id, start_date, end_date, status, service_scope, onsite_eligible
FROM OJ41_VISIBLE_CONTRACTS ORDER BY device_id;
SELECT device_id FROM OJ41_VISIBLE_CONTRACTS
WHERE onsite_eligible='Y' ORDER BY device_id;

-- Zero rows: duplicate keys (also prevented by primary keys).
SELECT doc_id, COUNT(*) FROM OJ41_KNOWLEDGE GROUP BY doc_id HAVING COUNT(*) > 1;

-- Stage 2: 16 rows, 0 embeddings. Embeddings are generated in stage 3.
SELECT COUNT(*) AS chunks,
       SUM(CASE WHEN embedding IS NOT NULL THEN 1 ELSE 0 END) AS embedded_chunks
FROM OJ41_CHUNKS;

BEGIN OJ41_CASE_CTX.clear_case; END;
/
