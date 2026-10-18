-- Execute the complete block as ORAJAM41USER. DDL commits implicitly.
-- For a new tutorial schema. Existing tables with the same definition are kept.
-- Schema migration from other versions is not supported.
DECLARE
  n NUMBER;
  PROCEDURE ensure_table(p_name VARCHAR2, p_ddl VARCHAR2) IS
  BEGIN
    SELECT COUNT(*) INTO n FROM user_tables WHERE table_name = p_name;
    IF n = 0 THEN EXECUTE IMMEDIATE p_ddl; END IF;
  END;
BEGIN
  IF SYS_CONTEXT('USERENV','SESSION_USER') <> 'ORAJAM41USER'
     OR SYS_CONTEXT('USERENV','CURRENT_SCHEMA') <> 'ORAJAM41USER'
     OR NOT (LOWER(SYS_CONTEXT('USERENV','DB_NAME')) = 'arakawalab'
             OR LOWER(SYS_CONTEXT('USERENV','DB_NAME')) LIKE '%\_arakawalab' ESCAPE '\') THEN
    RAISE_APPLICATION_ERROR(-20041, 'Unexpected database or user');
  END IF;
  ensure_table('OJ41_RUN', q'~CREATE TABLE OJ41_RUN (
    run_id VARCHAR2(20) PRIMARY KEY CHECK (run_id='STANDARD'),
    generator_version VARCHAR2(20) NOT NULL, seed_value NUMBER(10) NOT NULL,
    as_of_date DATE NOT NULL)~');
  ensure_table('OJ41_CUSTOMERS', q'~CREATE TABLE OJ41_CUSTOMERS (
    customer_id VARCHAR2(10) PRIMARY KEY, customer_name VARCHAR2(100 CHAR) NOT NULL)~');
  ensure_table('OJ41_SUPPORT_CASES', q'~CREATE TABLE OJ41_SUPPORT_CASES (
    case_id VARCHAR2(20) PRIMARY KEY,
    customer_id VARCHAR2(10) NOT NULL REFERENCES OJ41_CUSTOMERS(customer_id))~');
  ensure_table('OJ41_DEVICES', q'~CREATE TABLE OJ41_DEVICES (
    device_id VARCHAR2(20) PRIMARY KEY, model VARCHAR2(20) NOT NULL,
    customer_id VARCHAR2(10) NOT NULL REFERENCES OJ41_CUSTOMERS(customer_id), serial_no VARCHAR2(40) NOT NULL UNIQUE)~');
  ensure_table('OJ41_CONTRACTS', q'~CREATE TABLE OJ41_CONTRACTS (
    contract_id VARCHAR2(20) PRIMARY KEY,
    device_id VARCHAR2(20) NOT NULL UNIQUE REFERENCES OJ41_DEVICES(device_id),
    start_date DATE NOT NULL, end_date DATE NOT NULL,
    status VARCHAR2(20) NOT NULL CHECK (status IN ('ACTIVE','CANCELLED')),
    service_scope VARCHAR2(20) NOT NULL CHECK (service_scope IN ('ONSITE','REMOTE')),
    CHECK (start_date <= end_date))~');
  ensure_table('OJ41_KNOWLEDGE', q'~CREATE TABLE OJ41_KNOWLEDGE (
    doc_id VARCHAR2(20) PRIMARY KEY, model VARCHAR2(20) NOT NULL,
    title VARCHAR2(200 CHAR) NOT NULL, body VARCHAR2(2000 CHAR) NOT NULL,
    revision NUMBER(5) NOT NULL CHECK (revision > 0),
    publication VARCHAR2(20) NOT NULL CHECK (publication IN ('PUBLISHED','DRAFT','RETIRED')),
    scope VARCHAR2(20) NOT NULL CHECK (scope IN ('PUBLIC','CUSTOMER','INTERNAL')),
    customer_id VARCHAR2(10) REFERENCES OJ41_CUSTOMERS(customer_id),
    CHECK ((scope='CUSTOMER' AND customer_id IS NOT NULL) OR (scope IN ('PUBLIC','INTERNAL') AND customer_id IS NULL)))~');
  ensure_table('OJ41_CHUNKS', q'~CREATE TABLE OJ41_CHUNKS (
    chunk_id VARCHAR2(24) PRIMARY KEY, doc_id VARCHAR2(20) NOT NULL REFERENCES OJ41_KNOWLEDGE(doc_id),
    chunk_text VARCHAR2(2400 CHAR) NOT NULL, content_hash VARCHAR2(64) NOT NULL,
    preprocess_version VARCHAR2(40) NOT NULL,
    embedding_model VARCHAR2(128), embedding VECTOR(1024,FLOAT32))~');
  -- Private package state belongs to a request/connection, not to a customer login.
  EXECUTE IMMEDIATE q'~CREATE OR REPLACE PACKAGE OJ41_CASE_CTX AUTHID DEFINER AS
    PROCEDURE open_case(p_case_id VARCHAR2);
    PROCEDURE clear_case;
    FUNCTION current_case RETURN VARCHAR2;
    FUNCTION customer_id RETURN VARCHAR2;
    FUNCTION generation RETURN NUMBER;
  END;~';
  EXECUTE IMMEDIATE q'~CREATE OR REPLACE PACKAGE BODY OJ41_CASE_CTX AS
    g_case VARCHAR2(20);
    g_customer VARCHAR2(10);
    g_generation NUMBER := 0;
    PROCEDURE clear_case IS
    BEGIN
      g_case := NULL; g_customer := NULL; g_generation := g_generation + 1;
    END;
    PROCEDURE open_case(p_case_id VARCHAR2) IS
    BEGIN
      clear_case;
      SELECT case_id, customer_id INTO g_case, g_customer
      FROM OJ41_SUPPORT_CASES WHERE case_id=UPPER(p_case_id);
    EXCEPTION WHEN NO_DATA_FOUND THEN
      clear_case;
      RAISE_APPLICATION_ERROR(-20061, 'Support case not found');
    END;
    FUNCTION current_case RETURN VARCHAR2 IS BEGIN RETURN g_case; END;
    FUNCTION customer_id RETURN VARCHAR2 IS BEGIN RETURN g_customer; END;
    FUNCTION generation RETURN NUMBER IS BEGIN RETURN g_generation; END;
  END;~';
  EXECUTE IMMEDIATE q'~CREATE OR REPLACE VIEW OJ41_VISIBLE_DEVICES AS
    SELECT d.* FROM OJ41_DEVICES d
    WHERE d.customer_id=OJ41_CASE_CTX.customer_id()~';
  EXECUTE IMMEDIATE q'~CREATE OR REPLACE VIEW OJ41_VISIBLE_KNOWLEDGE AS
    SELECT k.* FROM OJ41_KNOWLEDGE k
    WHERE k.publication='PUBLISHED' AND OJ41_CASE_CTX.current_case() IS NOT NULL
      AND (k.scope='PUBLIC' OR (k.scope='CUSTOMER' AND k.customer_id=OJ41_CASE_CTX.customer_id()))~';
  EXECUTE IMMEDIATE q'~CREATE OR REPLACE VIEW OJ41_VISIBLE_CHUNKS AS
    SELECT c.*, k.model, k.title FROM OJ41_CHUNKS c
    JOIN OJ41_VISIBLE_KNOWLEDGE k ON k.doc_id=c.doc_id~';
  EXECUTE IMMEDIATE q'~CREATE OR REPLACE VIEW OJ41_VISIBLE_CONTRACTS AS
    SELECT c.*, d.customer_id, d.model, r.as_of_date,
      CASE WHEN c.status='ACTIVE' AND r.as_of_date BETWEEN c.start_date AND c.end_date
        THEN 'Y' ELSE 'N' END AS is_active,
      CASE WHEN c.status='ACTIVE' AND r.as_of_date BETWEEN c.start_date AND c.end_date
        AND c.service_scope='ONSITE' THEN 'Y' ELSE 'N' END AS onsite_eligible
    FROM OJ41_CONTRACTS c JOIN OJ41_VISIBLE_DEVICES d ON d.device_id=c.device_id
    CROSS JOIN OJ41_RUN r WHERE r.run_id='STANDARD'~';
END;
/
