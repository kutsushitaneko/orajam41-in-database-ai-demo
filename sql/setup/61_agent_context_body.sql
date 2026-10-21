CREATE OR REPLACE PACKAGE BODY OJ41_AGENT_CTX AS
  g_generation NUMBER;
  g_device VARCHAR2(20);
  g_model VARCHAR2(20);
  g_question VARCHAR2(800);
  g_calls PLS_INTEGER := 0;
  g_run_id VARCHAR2(40);
  g_events JSON_ARRAY_T := JSON_ARRAY_T();

  PROCEDURE clear_run IS
  BEGIN
    g_generation := NULL; g_device := NULL; g_model := NULL;
    g_question := NULL; g_run_id := NULL; g_calls := 0;
    g_events := JSON_ARRAY_T();
  END;

  PROCEDURE start_run(p_device VARCHAR2, p_question VARCHAR2, p_run_id VARCHAR2) IS
    l_customer VARCHAR2(10);
    l_requested VARCHAR2(10);
  BEGIN
    clear_run;
    g_generation := OJ41_CASE_CTX.generation();
    IF OJ41_CASE_CTX.current_case() IS NULL THEN
      RAISE_APPLICATION_ERROR(-20062, 'No support case selected');
    END IF;
    g_device := UPPER(p_device); g_model := NULL; g_question := p_question;
    g_calls := 0; g_events := JSON_ARRAY_T();
    g_run_id := p_run_id;
    SELECT model, customer_id INTO g_model,l_customer FROM OJ41_VISIBLE_DEVICES WHERE device_id=g_device;
    l_requested := REGEXP_SUBSTR(UPPER(p_question),'C[0-9]{3}');
    IF l_requested IS NOT NULL AND l_requested <> l_customer THEN
      RAISE_APPLICATION_ERROR(-20053, 'Request outside selected support case');
    END IF;
  EXCEPTION WHEN NO_DATA_FOUND THEN
    clear_run;
    RAISE_APPLICATION_ERROR(-20053, 'Device outside selected support case');
  WHEN OTHERS THEN
    clear_run;
    RAISE;
  END;

  PROCEDURE check_call(p_device VARCHAR2) IS
  BEGIN
    IF OJ41_CASE_CTX.current_case() IS NULL OR g_generation IS NULL
       OR g_generation <> OJ41_CASE_CTX.generation() THEN
      RAISE_APPLICATION_ERROR(-20062, 'Support case changed or cleared');
    END IF;
    g_calls := g_calls + 1;
    IF g_calls > 4 THEN RAISE_APPLICATION_ERROR(-20051,'Tool call limit exceeded'); END IF;
    IF g_device IS NULL OR UPPER(p_device) <> g_device OR p_device IS NULL THEN
      RAISE_APPLICATION_ERROR(-20052,'Device does not match trusted request');
    END IF;
  END;

  FUNCTION record_result(p_tool VARCHAR2,p_result CLOB) RETURN CLOB IS
    e JSON_OBJECT_T := JSON_OBJECT_T();
    r JSON_OBJECT_T := JSON_OBJECT_T.parse(p_result);
  BEGIN
    r.put('run_id',g_run_id);
    e.put('tool',p_tool); e.put('device_id',g_device);
    e.put('result',r);
    g_events.append(e);
    RETURN r.to_clob();
  END;

  FUNCTION contract_info(p_device VARCHAR2) RETURN CLOB IS
    r CLOB;
  BEGIN
    check_call(p_device);
    IF g_model IS NULL THEN RETURN record_result('contract','{"status":"not_visible_or_missing"}'); END IF;
    SELECT JSON_OBJECT('device_id' VALUE device_id,'model' VALUE model,
      'as_of_date' VALUE TO_CHAR(as_of_date,'YYYY-MM-DD'),
      'start_date' VALUE TO_CHAR(start_date,'YYYY-MM-DD'),'end_date' VALUE TO_CHAR(end_date,'YYYY-MM-DD'),
      'is_active' VALUE is_active,'onsite_eligible' VALUE onsite_eligible,
      'eligibility_reason' VALUE CASE WHEN status='CANCELLED' THEN 'CANCELLED'
        WHEN as_of_date<start_date THEN 'NOT_STARTED' WHEN as_of_date>end_date THEN 'EXPIRED'
        WHEN service_scope='REMOTE' THEN 'REMOTE_ONLY' ELSE 'ELIGIBLE' END,
      'status' VALUE status,'service_scope' VALUE service_scope,
      'approval_required' VALUE 'true' FORMAT JSON RETURNING CLOB)
    INTO r FROM OJ41_VISIBLE_CONTRACTS WHERE device_id=g_device;
    RETURN record_result('contract',r);
  EXCEPTION WHEN NO_DATA_FOUND THEN
    RETURN record_result('contract','{"status":"not_visible_or_missing"}');
  END;

  FUNCTION knowledge_search(p_device VARCHAR2,p_query VARCHAR2) RETURN CLOB IS
    v VECTOR(1024,FLOAT32);
    r CLOB;
    l_code VARCHAR2(10);
  BEGIN
    check_call(p_device);
    IF g_model IS NULL THEN RETURN record_result('knowledge','{"documents":[]}'); END IF;
    IF TRIM(p_query) IS NULL OR LENGTH(p_query)>800 THEN
      RAISE_APPLICATION_ERROR(-20073,'Search query must contain 1 to 800 characters');
    END IF;
    SELECT VECTOR_EMBEDDING(MULTILINGUAL_E5_LARGE USING 'query: ' || TRIM(p_query) AS data) INTO v FROM dual;
    l_code := REGEXP_SUBSTR(UPPER(g_question),'E[0-9]{3}');
    SELECT JSON_OBJECT('documents' VALUE COALESCE(
      JSON_ARRAYAGG(JSON_OBJECT('doc_id' VALUE doc_id,'text' VALUE chunk_text RETURNING CLOB)
        ORDER BY distance,doc_id RETURNING CLOB),TO_CLOB('[]')) FORMAT JSON RETURNING CLOB)
    INTO r FROM (
      SELECT doc_id,chunk_text,distance FROM (
        SELECT c.doc_id,c.chunk_text,VECTOR_DISTANCE(c.embedding,v,COSINE) distance,
          ROW_NUMBER() OVER (PARTITION BY k.scope ORDER BY VECTOR_DISTANCE(c.embedding,v,COSINE),c.doc_id) rn
        FROM OJ41_VISIBLE_CHUNKS c JOIN OJ41_VISIBLE_KNOWLEDGE k ON k.doc_id=c.doc_id
        WHERE c.model=g_model AND c.embedding IS NOT NULL
          AND (l_code IS NULL OR INSTR(UPPER(c.chunk_text),l_code)>0))
      WHERE rn=1 ORDER BY distance,doc_id);
    RETURN record_result('knowledge',r);
  END;

  FUNCTION trace RETURN CLOB IS
  BEGIN RETURN g_events.to_clob(); END;
END;
/
