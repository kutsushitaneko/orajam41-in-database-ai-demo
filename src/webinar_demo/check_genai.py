"""Small, reproducible GenAI connectivity and Select AI Agent checks."""

import argparse
import json

import oci
import oracledb
from oci.generative_ai_inference import models as gm

from webinar_demo.settings import ROOT, ConfigurationError, db_parameters, load_settings, oci_config, require

PROFILE = "ORAJAM41_GENAI_SMOKE"
PROMPT = "接続テストです。OKとのみ回答してください。"

VIEW_SQL = "CREATE OR REPLACE VIEW ORAJAM41_ENV_PROBE AS SELECT 41 AS PROBE_VALUE FROM dual"
FUNCTION_SQL = """CREATE OR REPLACE FUNCTION ORAJAM41_PROBE_STATUS(p_label IN VARCHAR2)
RETURN VARCHAR2 AUTHID CURRENT_USER IS
BEGIN
  DBMS_APPLICATION_INFO.SET_CLIENT_INFO('ORAJAM41_TOOL_CALLED');
  RETURN 'STATUS=READY; PROBE_VALUE=41; LABEL=' || SUBSTR(p_label,1,80);
END;"""


def attributes(values: dict[str, str]) -> dict:
    return {
        "provider": "oci", "credential_name": "OCI$RESOURCE_PRINCIPAL",
        "region": values["OCI_GENAI_REGION"], "model": values["OCI_GENAI_MODEL_ID"],
        "oci_compartment_id": values["OCI_GENAI_COMPARTMENT_OCID"],
        "temperature": 0, "max_tokens": 1024,
        "object_list": [{"owner": "ORAJAM41USER", "name": "ORAJAM41_ENV_PROBE"}],
        "enforce_object_list": True,
    }


def text(value) -> str:
    return value.read() if hasattr(value, "read") else str(value)


def connect(values):
    conn = oracledb.connect(**db_parameters(values))
    conn.call_timeout = 180000
    with conn.cursor() as cur:
        cur.execute("SELECT SYS_CONTEXT('USERENV','DB_NAME'), USER FROM dual")
        db, user = cur.fetchone()
        if user != "ORAJAM41USER" or not (db.lower() == "arakawalab" or db.lower().endswith("_arakawalab")):
            conn.close()
            raise ConfigurationError("実際の接続先DB／ユーザーが想定と異なります。")
    return conn


def python_chat(values):
    config = oci_config(values)
    config["region"] = values["OCI_GENAI_REGION"]
    options = {"timeout": (10, 120), "retry_strategy": oci.retry.NoneRetryStrategy()}
    if values.get("OCI_GENAI_ENDPOINT"):
        options["service_endpoint"] = values["OCI_GENAI_ENDPOINT"]
    client = oci.generative_ai_inference.GenerativeAiInferenceClient(config, **options)
    result = client.chat(gm.ChatDetails(
        compartment_id=values["OCI_GENAI_COMPARTMENT_OCID"],
        serving_mode=gm.OnDemandServingMode(model_id=values["OCI_GENAI_MODEL_ID"]),
        chat_request=gm.GenericChatRequest(
            messages=[gm.UserMessage(content=[gm.TextContent(text=PROMPT)])],
            max_tokens=256, temperature=0),
    ))
    answer = "".join(content.text for choice in result.data.chat_response.choices
                     for content in choice.message.content if getattr(content, "text", None))
    if not answer.strip():
        raise ConfigurationError("GenAIからテキスト応答がありません。")
    print(f"Python API署名キー: HTTP {result.status} / {answer[:200]}", flush=True)


def setup(cur, values):
    cur.execute(VIEW_SQL)
    cur.execute(FUNCTION_SQL)
    attrs = attributes(values)
    cur.execute("SELECT COUNT(*) FROM user_cloud_ai_profiles WHERE profile_name=:p", p=PROFILE)
    if cur.fetchone()[0] == 0:
        cur.execute("BEGIN DBMS_CLOUD_AI.CREATE_PROFILE(profile_name=>:p,attributes=>:a); END;", p=PROFILE, a=json.dumps(attrs))
    else:
        # This is our dedicated smoke-test profile, not an existing application profile.
        for name, value in attrs.items():
            encoded = json.dumps(value) if isinstance(value, (list, dict, bool)) else str(value)
            cur.execute("BEGIN DBMS_CLOUD_AI.SET_ATTRIBUTE(profile_name=>:p,attribute_name=>:n,attribute_value=>:v); END;", p=PROFILE, n=name, v=encoded)
    definitions = [
        ("TOOL", "ORAJAM41_SMOKE_TOOL", {"instruction": "Read the environment status. Call this once with p_label set to the requested label.", "function": "ORAJAM41_PROBE_STATUS"}),
        ("AGENT", "ORAJAM41_SMOKE_AGENT", {"profile_name": PROFILE, "role": "You verify database connectivity by calling the provided status tool once and reporting its result.", "enable_human_tool": False}),
        ("TASK", "ORAJAM41_SMOKE_TASK", {"instruction": "Call ORAJAM41_SMOKE_TOOL exactly once for this request: {query}. Report the tool result without guessing.", "tools": ["ORAJAM41_SMOKE_TOOL"]}),
        ("TEAM", "ORAJAM41_SMOKE_TEAM", {"agents": [{"name": "ORAJAM41_SMOKE_AGENT", "task": "ORAJAM41_SMOKE_TASK"}], "process": "sequential"}),
    ]
    for kind, name, config in definitions:
        # Fixed identifiers from this module; no user input is interpolated into SQL.
        views = {"TOOL": "USER_AI_AGENT_TOOLS", "AGENT": "USER_AI_AGENTS", "TASK": "USER_AI_AGENT_TASKS", "TEAM": "USER_AI_AGENT_TEAMS"}
        column = "AGENT_TEAM_NAME" if kind == "TEAM" else kind + "_NAME"
        cur.execute(f"SELECT COUNT(*) FROM {views[kind]} WHERE {column}=:n", n=name)
        if cur.fetchone()[0] == 0:
            cur.execute(f"BEGIN DBMS_CLOUD_AI_AGENT.CREATE_{kind}({kind.lower()}_name=>:n,attributes=>:a); END;", n=name, a=json.dumps(config))
    print("最小動作確認用ビュー・関数・プロファイル・エージェント定義: 準備完了", flush=True)
    # Export reproducible, environment-specific SQL for the supported SQL clients.
    profile_sql = "BEGIN DBMS_CLOUD_AI.CREATE_PROFILE(profile_name=>'" + PROFILE + "',attributes=>'" + json.dumps(attrs).replace("'", "''") + "'); END;"
    statements = [VIEW_SQL + ";", FUNCTION_SQL + "\n/", profile_sql + "\n/"]
    for kind, name, config in definitions:
        statements.append(f"BEGIN DBMS_CLOUD_AI_AGENT.CREATE_{kind}({kind.lower()}_name=>'{name}',attributes=>'" + json.dumps(config).replace("'", "''") + "'); END;\n/")
    out = ROOT / "local/20_genai_smoke_setup.sql"
    out.parent.mkdir(exist_ok=True)
    out.write_text("-- ORAJAM41USER on arakawalab. Initial setup only; named AI objects must not already exist.\n" + "\n\n".join(statements) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", action="store_true")
    parser.add_argument("--setup", action="store_true")
    parser.add_argument("--db", action="store_true")
    parser.add_argument("--nl2sql", action="store_true")
    parser.add_argument("--agent", action="store_true")
    args = parser.parse_args()
    if not any(vars(args).values()):
        parser.print_help()
        return 0
    try:
        values = load_settings()
        require(values, "OCI_GENAI_REGION", "OCI_GENAI_MODEL_ID", "OCI_GENAI_COMPARTMENT_OCID")
        if args.python:
            python_chat(values)
        if any((args.setup, args.db, args.nl2sql, args.agent)):
            with connect(values) as conn, conn.cursor() as cur:
                if args.setup:
                    setup(cur, values)
                if args.db:
                    cur.execute("SELECT DBMS_CLOUD_AI.GENERATE(prompt=>:q,profile_name=>:p,action=>'chat') FROM dual", q=PROMPT, p=PROFILE)
                    print("DBリソースプリンシパル: " + text(cur.fetchone()[0])[:200], flush=True)
                if args.nl2sql:
                    cur.execute("SELECT DBMS_CLOUD_AI.GENERATE(prompt=>:q,profile_name=>:p,action=>'showsql') FROM dual", q="ORAJAM41_ENV_PROBEビューのPROBE_VALUE列を取得するSQLを示してください。", p=PROFILE)
                    print("NL2SQL生成結果（自動実行しません）: " + text(cur.fetchone()[0])[:1200], flush=True)
                    cur.execute("SELECT PROBE_VALUE FROM ORAJAM41_ENV_PROBE")
                    print("正解SQLの結果: " + str(cur.fetchone()[0]), flush=True)
                if args.agent:
                    cur.execute("BEGIN DBMS_CLOUD_AI_AGENT.SET_TEAM('ORAJAM41_SMOKE_TEAM'); END;")
                    cur.execute("BEGIN DBMS_APPLICATION_INFO.SET_CLIENT_INFO(NULL); END;")
                    cur.execute("SELECT DBMS_CLOUD_AI_AGENT.RUN_TEAM(team_name=>'ORAJAM41_SMOKE_TEAM',user_prompt=>'Read the status with label ORAJAM41.') FROM dual")
                    answer = text(cur.fetchone()[0])
                    cur.execute("SELECT SYS_CONTEXT('USERENV','CLIENT_INFO') FROM dual")
                    if cur.fetchone()[0] != "ORAJAM41_TOOL_CALLED":
                        raise ConfigurationError("PL/SQLツールの実行を確認できませんでした。")
                    print("エージェントのPL/SQLツール呼び出し: 確認済み", flush=True)
                    print("エージェント応答: " + answer[:1500], flush=True)
        return 0
    except ConfigurationError as exc:
        print(str(exc))
    except oci.exceptions.ServiceError as exc:
        print(f"OCIエラー: status={exc.status}, code={exc.code}")
    except oracledb.Error as exc:
        print("DBエラー: " + exc.args[0].full_code)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
