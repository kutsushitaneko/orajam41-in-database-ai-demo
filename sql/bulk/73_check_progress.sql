-- ORAJAM41USER; read-only. Filter dataset_id when comparing runs.
SELECT dataset_id,route,part_no,status,loaded_rows,operation_id,error_code
FROM OJ41_BULK_PARTS ORDER BY dataset_id,route,part_no;

SELECT dataset_id,embed_state,COUNT(*) AS row_count,
  SUM(CASE WHEN embedding IS NOT NULL THEN 1 ELSE 0 END) AS vectors
FROM OJ41_BULK_DOCS GROUP BY dataset_id,embed_state ORDER BY dataset_id,embed_state;

SELECT id,status,rows_loaded,logfile_table,badfile_table
FROM user_load_operations WHERE table_name='OJ41_BULK_STAGE' ORDER BY id DESC;
-- Inspect the LOGFILE_TABLE/BADFILE_TABLE returned for the failed operation.
-- SELECT * FROM COPY$nn_LOG; -- replace nn with the actual returned name
