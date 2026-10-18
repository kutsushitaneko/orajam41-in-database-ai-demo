-- ORAJAM41USER on arakawalab, after check_genai --setup.
-- Enable the SQL client's DBMS Output panel for the final block.
SELECT DBMS_CLOUD_AI.GENERATE(
  prompt => '接続テストです。OKとのみ回答してください。',
  profile_name => 'ORAJAM41_GENAI_SMOKE', action => 'chat') AS response
FROM dual;

SELECT DBMS_CLOUD_AI.GENERATE(
  prompt => 'ORAJAM41_ENV_PROBEビューのPROBE_VALUE列を取得するSQLを示してください。',
  profile_name => 'ORAJAM41_GENAI_SMOKE', action => 'showsql') AS generated_sql
FROM dual;

SELECT probe_value FROM orajam41_env_probe;

-- Keep SET_TEAM and RUN_TEAM in the same session/block.
DECLARE
  l_result CLOB;
BEGIN
  DBMS_CLOUD_AI_AGENT.SET_TEAM('ORAJAM41_SMOKE_TEAM');
  DBMS_APPLICATION_INFO.SET_CLIENT_INFO(NULL);
  l_result := DBMS_CLOUD_AI_AGENT.RUN_TEAM(
    team_name => 'ORAJAM41_SMOKE_TEAM',
    user_prompt => 'Read the status with label ORAJAM41.');
  IF NVL(SYS_CONTEXT('USERENV','CLIENT_INFO'), 'NOT_CALLED') <> 'ORAJAM41_TOOL_CALLED' THEN
    RAISE_APPLICATION_ERROR(-20001, 'PL/SQL tool invocation was not confirmed.');
  END IF;
  DBMS_OUTPUT.PUT_LINE(DBMS_LOB.SUBSTR(l_result, 4000, 1));
END;
/

SELECT tool_name, start_date, end_date FROM user_ai_agent_tool_history
WHERE tool_name='ORAJAM41_SMOKE_TOOL'
ORDER BY start_date DESC FETCH FIRST 5 ROWS ONLY;
