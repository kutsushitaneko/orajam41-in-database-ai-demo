-- Dedicated bulk-test tables; no changes to the webinar's standard data.
DECLARE
  n NUMBER;
  PROCEDURE ensure_table(p_name VARCHAR2,p_sql VARCHAR2) IS
  BEGIN
    SELECT COUNT(*) INTO n FROM user_tables WHERE table_name=p_name;
    IF n=0 THEN EXECUTE IMMEDIATE p_sql; END IF;
  END;
BEGIN
  IF SYS_CONTEXT('USERENV','SESSION_USER')<>'ORAJAM41USER'
     OR SYS_CONTEXT('USERENV','CURRENT_SCHEMA')<>'ORAJAM41USER'
     OR NOT (LOWER(SYS_CONTEXT('USERENV','DB_NAME'))='arakawalab'
       OR LOWER(SYS_CONTEXT('USERENV','DB_NAME')) LIKE '%\_arakawalab' ESCAPE '\') THEN
    RAISE_APPLICATION_ERROR(-20041,'Unexpected database or schema');
  END IF;
  ensure_table('OJ41_BULK_STAGE',q'~CREATE TABLE OJ41_BULK_STAGE (
    dataset_id VARCHAR2(64) NOT NULL, part_no NUMBER NOT NULL,
    row_no NUMBER NOT NULL, model VARCHAR2(20) NOT NULL,
    body_text VARCHAR2(2400 CHAR) NOT NULL, content_hash VARCHAR2(64) NOT NULL)~');
  ensure_table('OJ41_BULK_DOCS',q'~CREATE TABLE OJ41_BULK_DOCS (
    dataset_id VARCHAR2(64) NOT NULL, part_no NUMBER NOT NULL,
    row_no NUMBER NOT NULL, model VARCHAR2(20) NOT NULL,
    body_text VARCHAR2(2400 CHAR) NOT NULL, content_hash VARCHAR2(64) NOT NULL,
    embedding VECTOR(1024,FLOAT32), embedding_model VARCHAR2(128),
    embed_state VARCHAR2(10) DEFAULT 'PENDING' NOT NULL
      CHECK (embed_state IN ('PENDING','DONE','FAILED')),
    embed_error VARCHAR2(40),
    PRIMARY KEY(dataset_id,row_no))~');
  ensure_table('OJ41_BULK_PARTS',q'~CREATE TABLE OJ41_BULK_PARTS (
    dataset_id VARCHAR2(64) NOT NULL, route VARCHAR2(10) NOT NULL,
    part_no NUMBER NOT NULL, file_hash VARCHAR2(64) NOT NULL,
    status VARCHAR2(10) NOT NULL CHECK (status IN ('DONE','FAILED')),
    loaded_rows NUMBER, operation_id NUMBER, error_code VARCHAR2(40),
    updated_at TIMESTAMP DEFAULT SYSTIMESTAMP NOT NULL,
    PRIMARY KEY(dataset_id,route,part_no))~');
END;
/
