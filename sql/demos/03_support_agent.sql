-- ORAJAM41USER. Enable DBMS Output. Execute the entire block in a fresh session.
DECLARE
  r CLOB;
  l_conversation_id VARCHAR2(4000);
BEGIN
  OJ41_CASE_CTX.open_case('SR001');
  OJ41_AGENT_CTX.start_run('DEV001','管理画面が開かない。確認手順と対応案を示して。',RAWTOHEX(SYS_GUID()));
  l_conversation_id := DBMS_CLOUD_AI.CREATE_CONVERSATION();
  r := DBMS_CLOUD_AI_AGENT.RUN_TEAM(
    team_name=>'OJ41_SUPPORT_TEAM',
    user_prompt=>'Device ID: DEV001. 管理画面が開かない。最初に何を確認し、誰へ連絡すればよいですか。現地保守を頼めますか。両ツールの結果を組み合わせ、契約上の可否と承認の要否も回答してください。根拠文書IDと原文引用を含めてください。',
    params=>'{"conversation_id":"'||l_conversation_id||'"}');
  DBMS_OUTPUT.PUT_LINE(DBMS_LOB.SUBSTR(r,16000,1));
  r := OJ41_AGENT_CTX.trace;
  DBMS_OUTPUT.PUT_LINE(DBMS_LOB.SUBSTR(r,16000,1));
  OJ41_AGENT_CTX.clear_run;
  DBMS_CLOUD_AI.CLEAR_CONVERSATION_ID;
  OJ41_CASE_CTX.clear_case;
EXCEPTION WHEN OTHERS THEN
  OJ41_AGENT_CTX.clear_run;
  DBMS_CLOUD_AI.CLEAR_CONVERSATION_ID;
  OJ41_CASE_CTX.clear_case;
  RAISE;
END;
/

-- Actual tool calls, inputs and outputs. Match run_id in output with the trace above.
SELECT invocation_id,team_exec_id,tool_name,start_date,input,output
FROM USER_AI_AGENT_TOOL_HISTORY
WHERE task_name='OJ41_SUPPORT_TASK'
ORDER BY start_date DESC
FETCH FIRST 10 ROWS ONLY;
