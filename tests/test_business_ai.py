import json

import pytest

from webinar_demo.nl2sql import validated_sql
from webinar_demo.business_ai import validate_trace, validate_history


def test_agent_setup_removes_stale_sql_profile_attributes(monkeypatch, tmp_path):
    from unittest.mock import MagicMock
    from webinar_demo import business_ai, nl2sql_compare
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchall.return_value = []
    cur.fetchone.return_value = (1,)
    monkeypatch.setattr(business_ai, "guard", lambda _: None)
    monkeypatch.setattr(business_ai, "execute_block", lambda *_: None)
    monkeypatch.setattr(business_ai, "ROOT", tmp_path)
    monkeypatch.setattr(nl2sql_compare, "setup", lambda *_: None)
    values = dict(OCI_GENAI_REGION="test-region", OCI_GENAI_MODEL_ID="test-model",
                  OCI_GENAI_COMPARTMENT_OCID="test-compartment")
    business_ai.setup(conn, values)
    calls = cur.execute.call_args_list
    drop = next(i for i,c in enumerate(calls) if 'DBMS_CLOUD_AI.DROP_PROFILE' in c.args[0])
    create = next(i for i,c in enumerate(calls) if 'DBMS_CLOUD_AI.CREATE_PROFILE' in c.args[0])
    assert drop < create
    attrs = json.loads(calls[create].kwargs['a'])
    assert set(attrs) == {'provider', 'credential_name', 'region', 'model',
                          'oci_compartment_id', 'temperature', 'max_tokens'}
    generated = (tmp_path / 'local/64_business_ai.sql').read_text(encoding='utf-8')
    assert 'object_list' not in generated


@pytest.mark.parametrize("sql", [
    "SELECT device_id FROM OJ41_VISIBLE_CONTRACTS WHERE onsite_eligible='Y' ORDER BY device_id",
    'SELECT "c"."MODEL", COUNT(*) FROM "ORAJAM41USER"."OJ41_VISIBLE_CONTRACTS" "c" WHERE UPPER("c"."IS_ACTIVE")=\'Y\' GROUP BY "c"."MODEL"',
])
def test_scoped_select_allowed(sql):
    assert "SELECT" in validated_sql(sql)


@pytest.mark.parametrize("sql", [
    "DELETE FROM OJ41_VISIBLE_CONTRACTS",
    "SELECT device_id FROM OJ41_VISIBLE_CONTRACTS; DROP TABLE OJ41_DEVICES",
    "SELECT device_id FROM OJ41_DEVICES",
    "SELECT device_id FROM ADMIN.OJ41_VISIBLE_CONTRACTS",
    "SELECT * FROM OJ41_VISIBLE_CONTRACTS",
    "SELECT password FROM OJ41_VISIBLE_CONTRACTS",
    "SELECT UTL_HTTP.REQUEST('https://example.com') FROM OJ41_VISIBLE_CONTRACTS",
    "SELECT OJ41_CONTRACT_TOOL('DEV001') FROM OJ41_VISIBLE_CONTRACTS",
    "SELECT device_id FROM OJ41_VISIBLE_CONTRACTS UNION SELECT device_id FROM OJ41_DEVICES",
    "SELECT device_id FROM OJ41_VISIBLE_CONTRACTS FOR UPDATE",
    "WITH x AS (SELECT * FROM OJ41_DEVICES) SELECT device_id FROM x",
    "SELECT a.device_id FROM OJ41_VISIBLE_CONTRACTS a JOIN OJ41_DEVICES b ON a.device_id=b.device_id",
])
def test_disallowed_sql_rejected(sql):
    with pytest.raises(ValueError): validated_sql(sql)


def trace(eligible="N"):
    return [dict(tool="contract",device_id="DEV001",result=dict(run_id="run-1",device_id="DEV001",onsite_eligible=eligible,status="ACTIVE")),
            dict(tool="knowledge",device_id="DEV001",result=dict(run_id="run-1",documents=[dict(doc_id="KB001",text="電源ランプとLANケーブルを確認します。")]))]


def test_contract_decision_is_not_taken_from_llm():
    raw=json.dumps(dict(status="answered",onsite_eligible="Y",approval_required=False,
                        claims=[dict(text="接続を確認します。",doc_id="KB001",quote="電源ランプとLANケーブルを確認します。")]))
    result=validate_trace(raw,trace())
    assert result["contract"]["onsite_eligible"]=="N"
    assert result["approval_required"] is True
    assert result["decision"]=="現地保守の対象として手配しない"


def test_missing_tool_execution_rejected():
    with pytest.raises(ValueError): validate_trace('{"status":"insufficient","claims":[]}',trace()[:1])


def test_repeated_consistent_read_is_allowed():
    result=validate_trace('「電源ランプとLANケーブルを確認します。」[KB001]',trace()+trace()[:1])
    assert result["validation_scope"]=="evidence_only"
    assert result["review_required"] is True
    assert result["action_status"]=="not_executed"


def test_plain_answer_and_whitespace_normalization():
    events=trace()
    events[1]["result"]["documents"][0]["text"]="確認手順\n電源ランプとLANケーブルを確認します。"
    result=validate_trace('「確認手順 電源ランプとLANケーブルを確認します。」[KB001]',events)
    assert result["draft"]["citations"]==["KB001"]


@pytest.mark.parametrize("raw", [
    '「電源ランプとLANケーブルを確認します。」[KB013]',
    '「直ちに再起動してください。」[KB001]',
    '{"status":"error","result":"failed"}',
])
def test_invalid_plain_answer_rejected(raw):
    with pytest.raises(ValueError): validate_trace(raw,trace())


def test_source_quote_about_visit_approval_is_not_a_commitment():
    events=trace("Y")
    events[1]["result"]["documents"].append(dict(doc_id="KB012",text="訪問確定には担当者の承認が必要です。"))
    raw='「訪問確定には担当者の承認が必要です。」[KB012]'
    assert validate_trace(raw,events)["draft"]["status"]=="answered"
    for bad in (raw+' 訪問確定しました。',raw+' 「訪問は予約済です。」'):
        assert validate_trace(bad,events)["review_warnings"]


@pytest.mark.parametrize("approval", ["承認", "担当者承認", "担当者の承認"])
def test_approval_requirement_outside_quote_is_not_a_commitment(approval):
    raw=f'訪問確定には{approval}が必要です。「電源ランプとLANケーブルを確認します。」[KB001]'
    assert validate_trace(raw,trace("Y"))["draft"]["status"]=="answered"
    for assertion in ["訪問確定しました。", "予約済です。", "手配済です。"]:
        assert validate_trace(raw+assertion,trace("Y"))["review_warnings"]


def history(events):
    names={"contract":"OJ41_LOOKUP_CONTRACT","knowledge":"OJ41_SEARCH_KNOWLEDGE"}
    return [dict(invocation_id=str(i),team_exec_id="team-1",tool_name=names[e["tool"]],
                 input=json.dumps({"P_DEVICE":"DEV001"}),
                 output=json.dumps({"status":"success","result":json.dumps(e["result"])}))
            for i,e in enumerate(events)]


def test_history_allows_reordering_and_consistent_repeated_read():
    events=trace()+trace()[:1]
    validate_history(events,list(reversed(history(events))),"run-1","DEV001")


@pytest.mark.parametrize("mutation",["missing","duplicate_id","wrong_device","wrong_run","failed","wrong_result","mixed_team"])
def test_history_rejects_unverified_evidence(mutation):
    rows=history(trace())
    if mutation=="missing": rows.pop()
    elif mutation=="duplicate_id": rows[1]["invocation_id"]=rows[0]["invocation_id"]
    elif mutation=="wrong_device": rows[0]["input"]='{"P_DEVICE":"DEV009"}'
    elif mutation=="mixed_team": rows[1]["team_exec_id"]="team-2"
    else:
        obj=json.loads(rows[0]["output"])
        value=json.loads(obj["result"])
        if mutation=="wrong_run": value["run_id"]="old-run"
        elif mutation=="wrong_result": value["onsite_eligible"]="Y"
        else: obj["status"]="error"
        obj["result"]=json.dumps(value);rows[0]["output"]=json.dumps(obj)
    with pytest.raises(ValueError): validate_history(trace(),rows,"run-1","DEV001")


@pytest.mark.parametrize("mutation",["mixed_run","mixed_device","conflict","budget"])
def test_evidence_conflicts_rejected(mutation):
    events=trace()
    if mutation=="mixed_run": events[1]["result"]["run_id"]="old-run"
    elif mutation=="mixed_device": events[1]["device_id"]="DEV009"
    elif mutation=="budget": events=events*3
    else: events+=trace("Y")[:1]
    with pytest.raises(ValueError): validate_trace('「電源ランプとLANケーブルを確認します。」[KB001]',events)
