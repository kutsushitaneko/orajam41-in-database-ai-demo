CREATE OR REPLACE PACKAGE BODY OJ41_CHECKED_AGENT AS
  FUNCTION run(p_case_id VARCHAR2,p_device VARCHAR2,p_question VARCHAR2) RETURN CLOB IS
    run_id VARCHAR2(40) := RAWTOHEX(SYS_GUID());
    raw_answer CLOB; checked CLOB;
    conversation_id VARCHAR2(4000);
  BEGIN
    OJ41_CASE_CTX.clear_case;
    IF TRIM(p_question) IS NULL OR LENGTH(p_question)>800 THEN
      RAISE_APPLICATION_ERROR(-20072,'Question must contain 1 to 800 characters');
    END IF;
    OJ41_CASE_CTX.open_case(p_case_id);
    OJ41_AGENT_CTX.start_run(p_device,p_question,run_id);
    conversation_id:=DBMS_CLOUD_AI.CREATE_CONVERSATION();
    raw_answer:=DBMS_CLOUD_AI_AGENT.RUN_TEAM(team_name=>'OJ41_SUPPORT_TEAM',
      user_prompt=>'Device ID: '||UPPER(p_device)||'. Question: '||p_question,
      params=>'{"conversation_id":"'||conversation_id||'"}');
    checked:=OJ41_ANSWER_GUARD.validate_agent(raw_answer,OJ41_AGENT_CTX.trace,run_id);
    OJ41_AGENT_CTX.clear_run; DBMS_CLOUD_AI.CLEAR_CONVERSATION_ID; OJ41_CASE_CTX.clear_case;
    RETURN checked;
  EXCEPTION WHEN OTHERS THEN
    OJ41_AGENT_CTX.clear_run; DBMS_CLOUD_AI.CLEAR_CONVERSATION_ID; OJ41_CASE_CTX.clear_case;
    RAISE;
  END;
END;
/
