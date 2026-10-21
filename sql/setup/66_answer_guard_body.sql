CREATE OR REPLACE PACKAGE BODY OJ41_ANSWER_GUARD AS
  PROCEDURE fail(p_message VARCHAR2) IS
  BEGIN RAISE_APPLICATION_ERROR(-20071,p_message); END;

  FUNCTION required_string(p_obj JSON_OBJECT_T,p_key VARCHAR2) RETURN VARCHAR2 IS
    e JSON_ELEMENT_T;
    s VARCHAR2(32767);
  BEGIN
    IF p_obj IS NULL THEN fail('Expected object'); END IF;
    e := p_obj.get(p_key);
    IF e IS NULL OR NOT e.is_string() THEN fail('Expected string: '||p_key); END IF;
    s := p_obj.get_string(p_key);
    IF TRIM(s) IS NULL THEN fail('Empty string: '||p_key); END IF;
    RETURN s;
  END;

  FUNCTION validate_json(p_answer CLOB, p_documents CLOB) RETURN CLOB IS
    a JSON_OBJECT_T := JSON_OBJECT_T.parse(p_answer);
    docs JSON_ARRAY_T := JSON_ARRAY_T.parse(p_documents);
    claims JSON_ARRAY_T;
    c JSON_OBJECT_T; d JSON_OBJECT_T; e JSON_ELEMENT_T;
    status VARCHAR2(30); body VARCHAR2(32767); id VARCHAR2(32767); quote VARCHAR2(32767);
    found BOOLEAN;
  BEGIN
    status := required_string(a,'status');
    IF status NOT IN ('answered','insufficient') THEN fail('Invalid status'); END IF;
    e := a.get('claims');
    IF e IS NULL OR NOT e.is_array() THEN fail('Expected claims array'); END IF;
    claims := a.get_array('claims');
    IF status='insufficient' THEN
      IF claims.get_size()<>0 THEN fail('Unexpected claims'); END IF;
    ELSE
      IF claims.get_size() NOT BETWEEN 1 AND 5 THEN fail('Claim count'); END IF;
      FOR i IN 0..claims.get_size()-1 LOOP
        c := TREAT(claims.get(i) AS JSON_OBJECT_T);
        body := required_string(c,'text'); id := required_string(c,'doc_id'); quote := required_string(c,'quote');
        IF LENGTH(body)>1000 OR LENGTH(quote)<8 THEN fail('Claim length'); END IF;
        found := FALSE;
        FOR j IN 0..docs.get_size()-1 LOOP
          d := TREAT(docs.get(j) AS JSON_OBJECT_T);
          IF d.get_string('doc_id')=id AND DBMS_LOB.INSTR(d.get_clob('text'),quote)>0 THEN found := TRUE; END IF;
        END LOOP;
        IF NOT found THEN fail('Citation does not match retrieved text'); END IF;
      END LOOP;
    END IF;
    RETURN a.to_clob();
  END;

  FUNCTION validate_agent(p_answer CLOB, p_trace CLOB, p_run_id VARCHAR2) RETURN CLOB IS
    events JSON_ARRAY_T := JSON_ARRAY_T.parse(p_trace);
    event JSON_OBJECT_T; r JSON_OBJECT_T; contract JSON_OBJECT_T; knowledge JSON_OBJECT_T;
    docs JSON_ARRAY_T := JSON_ARRAY_T(); batch_docs JSON_ARRAY_T; doc JSON_OBJECT_T;
    outer_obj JSON_OBJECT_T; e JSON_ELEMENT_T;
    answer CLOB := p_answer;
    commitment_text CLOB;
    warnings JSON_ARRAY_T := JSON_ARRAY_T();
    history_obj JSON_OBJECT_T; history_args JSON_OBJECT_T; history_result JSON_OBJECT_T;
    expected_json CLOB; actual_json CLOB; previous_json CLOB;
    device VARCHAR2(20); tool_name VARCHAR2(128); team_id VARCHAR2(128);
    matched BOOLEAN;
    TYPE seen_type IS TABLE OF BOOLEAN INDEX BY VARCHAR2(128);
    used_invocations seen_type;
    checked CLOB;
    result JSON_OBJECT_T := JSON_OBJECT_T();
    id VARCHAR2(30); quote VARCHAR2(32767);
    n PLS_INTEGER; nc PLS_INTEGER := 0; nk PLS_INTEGER := 0;
    found BOOLEAN; quote_found BOOLEAN := FALSE;
  BEGIN
    IF p_run_id IS NULL OR events.get_size() NOT BETWEEN 1 AND 4 THEN fail('Missing evidence or call budget exceeded'); END IF;
    FOR i IN 0..events.get_size()-1 LOOP
      event := TREAT(events.get(i) AS JSON_OBJECT_T); r := event.get_object('result');
      IF required_string(r,'run_id')<>p_run_id THEN fail('Wrong execution ID'); END IF;
      IF device IS NULL THEN device:=required_string(event,'device_id'); END IF;
      IF required_string(event,'device_id')<>device THEN fail('Wrong evidence device'); END IF;
      IF event.get_string('tool')='contract' THEN
        IF contract IS NOT NULL THEN
          previous_json:=contract.to_clob(); actual_json:=r.to_clob();
          SELECT CASE WHEN JSON_EQUAL(previous_json,actual_json) THEN 1 ELSE 0 END INTO n FROM dual;
          IF n<>1 THEN fail('Conflicting contract evidence'); END IF;
        END IF;
        contract:=r; nc:=nc+1; tool_name:='OJ41_LOOKUP_CONTRACT';
        IF required_string(r,'status')<>'not_visible_or_missing' THEN
          IF required_string(r,'device_id')<>device THEN fail('Wrong contract device'); END IF;
          IF required_string(r,'onsite_eligible') NOT IN ('Y','N') THEN fail('Missing eligibility decision'); END IF;
        END IF;
      ELSIF event.get_string('tool')='knowledge' THEN
        knowledge:=r; nk:=nk+1; tool_name:='OJ41_SEARCH_KNOWLEDGE';
        e:=r.get('documents');
        IF e IS NULL OR NOT e.is_array() THEN fail('Missing document search result'); END IF;
        batch_docs:=r.get_array('documents');
        FOR j IN 0..batch_docs.get_size()-1 LOOP
          docs.append(batch_docs.get(j));
        END LOOP;
      ELSE fail('Unexpected evidence type'); END IF;
      -- Match each evidence result to a distinct successful framework invocation.
      matched:=FALSE; expected_json:=r.to_clob();
      FOR h IN (SELECT invocation_id,team_exec_id,input,output
                FROM USER_AI_AGENT_TOOL_HISTORY
                WHERE task_name='OJ41_SUPPORT_TASK' AND tool_name=validate_agent.tool_name
                  AND INSTR(output,p_run_id)>0 ORDER BY start_date) LOOP
        IF NOT used_invocations.EXISTS(TO_CHAR(h.invocation_id)) THEN
          history_obj:=JSON_OBJECT_T.parse(h.output);
          history_args:=JSON_OBJECT_T.parse(h.input);
          IF required_string(history_obj,'status')='success' AND
             UPPER(required_string(history_args,'P_DEVICE'))=device THEN
            e:=history_obj.get('result');
            IF e.is_string() THEN history_result:=JSON_OBJECT_T.parse(history_obj.get_clob('result'));
            ELSE history_result:=TREAT(e AS JSON_OBJECT_T); END IF;
            actual_json:=history_result.to_clob();
            SELECT CASE WHEN JSON_EQUAL(expected_json,actual_json) THEN 1 ELSE 0 END INTO n FROM dual;
            IF n=1 THEN
              IF team_id IS NULL THEN team_id:=h.team_exec_id; END IF;
              IF team_id<>h.team_exec_id THEN fail('Mixed team executions'); END IF;
              used_invocations(TO_CHAR(h.invocation_id)):=TRUE;
              matched:=TRUE; EXIT;
            END IF;
          END IF;
        END IF;
      END LOOP;
      IF NOT matched THEN fail('Evidence does not match successful tool history'); END IF;
    END LOOP;
    -- This support workflow requires both evidence kinds, not a fixed call count.
    IF nc=0 OR nk=0 THEN fail('Missing required contract or document evidence'); END IF;
    SELECT COUNT(*) INTO n FROM USER_AI_AGENT_TOOL_HISTORY
      WHERE task_name='OJ41_SUPPORT_TASK' AND INSTR(output,p_run_id)>0;
    IF n<>events.get_size() THEN fail('Unmatched framework history'); END IF;
    BEGIN outer_obj := JSON_OBJECT_T.parse(answer);
    EXCEPTION WHEN OTHERS THEN outer_obj := NULL; END;
    IF outer_obj IS NOT NULL AND outer_obj.has('result') THEN
      IF required_string(outer_obj,'status')<>'success' THEN fail('Agent execution failed'); END IF;
      e := outer_obj.get('result');
      IF e.is_string() THEN answer:=outer_obj.get_clob('result'); ELSE answer:=e.to_clob(); END IF;
    ELSIF outer_obj IS NOT NULL AND outer_obj.get_string('status') IN ('error','failed','failure') THEN
      fail('Agent execution failed');
    END IF;
    BEGIN outer_obj := JSON_OBJECT_T.parse(answer);
    EXCEPTION WHEN OTHERS THEN outer_obj := NULL; END;
    -- Exclude only quotes that match a returned, cited document.
    commitment_text:=answer;
    FOR i IN 1..REGEXP_COUNT(answer,'「[^「」]+」') LOOP
      quote:=REGEXP_SUBSTR(answer,'「([^「」]+)」',1,i,NULL,1);
      IF LENGTH(quote)>=8 THEN
        FOR j IN 0..docs.get_size()-1 LOOP
          doc:=TREAT(docs.get(j) AS JSON_OBJECT_T);
          IF INSTR(answer,doc.get_string('doc_id'))>0 AND
             DBMS_LOB.INSTR(REGEXP_REPLACE(doc.get_clob('text'),'[[:space:]]+',' '),REGEXP_REPLACE(quote,'[[:space:]]+',' '))>0 THEN
            commitment_text:=REPLACE(commitment_text,'「'||quote||'」','');
          END IF;
        END LOOP;
      END IF;
    END LOOP;
    -- This exact approval requirement is not a commitment.
    commitment_text:=REGEXP_REPLACE(commitment_text,'訪問確定には(担当者の|担当者)?承認が必要です。','');
    IF REGEXP_LIKE(commitment_text,'訪問確定|予約済|手配済') THEN
      warnings.append('確約に見える表現があります。実際の処理結果と照合してください。');
    END IF;
    IF outer_obj IS NOT NULL AND outer_obj.has('claims') THEN
      checked := validate_json(answer,docs.to_clob());
      result.put('draft',JSON_OBJECT_T.parse(checked));
    ELSIF docs.get_size()=0 THEN
      -- Do not display an unchecked answer when there is no evidence.
      result.put('draft',JSON_OBJECT_T('{"status":"insufficient","claims":[]}'));
    ELSE
      n := REGEXP_COUNT(answer,'KB[0-9]{3}');
      IF n=0 THEN fail('Missing document IDs'); END IF;
      FOR i IN 1..n LOOP
        id:=REGEXP_SUBSTR(answer,'KB[0-9]{3}',1,i); found:=FALSE;
        FOR j IN 0..docs.get_size()-1 LOOP
          doc:=TREAT(docs.get(j) AS JSON_OBJECT_T);
          IF doc.get_string('doc_id')=id THEN found:=TRUE; END IF;
        END LOOP;
        IF NOT found THEN fail('Unknown document ID'); END IF;
      END LOOP;
      FOR i IN 1..REGEXP_COUNT(answer,'「[^「」]+」') LOOP
        quote:=REGEXP_SUBSTR(answer,'「([^「」]+)」',1,i,NULL,1);
        IF LENGTH(quote)>=8 THEN
          FOR j IN 0..docs.get_size()-1 LOOP
            doc:=TREAT(docs.get(j) AS JSON_OBJECT_T);
            IF INSTR(answer,doc.get_string('doc_id'))>0 AND
               DBMS_LOB.INSTR(REGEXP_REPLACE(doc.get_clob('text'),'[[:space:]]+',' '),REGEXP_REPLACE(quote,'[[:space:]]+',' '))>0 THEN
              quote_found:=TRUE;
            END IF;
          END LOOP;
        END IF;
      END LOOP;
      IF NOT quote_found THEN fail('Missing source quote'); END IF;
      result.put('draft',answer);
    END IF;
    result.put('contract',contract);
    IF contract.get_string('status')='not_visible_or_missing' THEN
      result.put('decision','閲覧可能な機器・契約を確認できない');
    ELSIF contract.get_string('onsite_eligible')='Y' THEN
      result.put('decision','承認後に現地保守の手配を検討');
    ELSE result.put('decision','現地保守の対象として手配しない'); END IF;
    result.put('approval_required',TRUE); result.put('run_id',p_run_id);
    result.put('validation_scope','evidence_only'); result.put('review_required',TRUE);
    result.put('action_status','not_executed'); result.put('review_warnings',warnings);
    RETURN result.to_clob();
  END;

  PROCEDURE print_clob(p_text CLOB) IS
    pos PLS_INTEGER := 1; piece VARCHAR2(32767);
  BEGIN
    -- Small character chunks also fit DBMS_OUTPUT's byte limit with UTF-8.
    WHILE pos<=DBMS_LOB.getlength(p_text) LOOP
      piece:=DBMS_LOB.SUBSTR(p_text,4000,pos);
      DBMS_OUTPUT.PUT_LINE(piece); pos:=pos+LENGTH(piece);
    END LOOP;
  END;
END;
/
