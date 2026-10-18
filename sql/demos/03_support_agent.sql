-- ORAJAM41USER. Enable DBMS Output. Execute the entire block in a fresh session.
DECLARE
  r CLOB;
BEGIN
  OJ41_CASE_CTX.open_case('SR001');
  OJ41_AGENT_CTX.start_run('DEV001','管理画面が開かない。確認手順と対応案を示して。',RAWTOHEX(SYS_GUID()));
  DBMS_CLOUD_AI_AGENT.SET_TEAM('OJ41_SUPPORT_TEAM');
  r := DBMS_CLOUD_AI_AGENT.RUN_TEAM(
    team_name=>'OJ41_SUPPORT_TEAM',
    user_prompt=>'Device ID: DEV001. 管理画面が開かない。両ツールで確認し、根拠文書IDと原文引用を含む日本語の手順を返してください。');
  DBMS_OUTPUT.PUT_LINE(DBMS_LOB.SUBSTR(r,16000,1));
  r := OJ41_AGENT_CTX.trace;
  DBMS_OUTPUT.PUT_LINE(DBMS_LOB.SUBSTR(r,16000,1));
  OJ41_AGENT_CTX.clear_run;
  DBMS_CLOUD_AI_AGENT.CLEAR_TEAM;
  OJ41_CASE_CTX.clear_case;
EXCEPTION WHEN OTHERS THEN
  OJ41_AGENT_CTX.clear_run;
  DBMS_CLOUD_AI_AGENT.CLEAR_TEAM;
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
