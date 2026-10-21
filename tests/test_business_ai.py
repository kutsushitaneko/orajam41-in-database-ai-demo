import json

import pytest

from webinar_demo.nl2sql import validated_sql
from webinar_demo.business_ai import validate_trace


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
    return [dict(tool="contract",result=dict(onsite_eligible=eligible,status="ACTIVE")),
            dict(tool="knowledge",result=dict(documents=[dict(doc_id="KB001",text="電源ランプとLANケーブルを確認します。")]))]


def test_contract_decision_is_not_taken_from_llm():
    raw=json.dumps(dict(status="answered",onsite_eligible="Y",approval_required=False,
                        claims=[dict(text="接続を確認します。",doc_id="KB001",quote="電源ランプとLANケーブルを確認します。")]))
    result=validate_trace(raw,trace())
    assert result["contract"]["onsite_eligible"]=="N"
    assert result["approval_required"] is True
    assert result["decision"]=="現地保守の対象として手配しない"


def test_missing_tool_execution_rejected():
    with pytest.raises(ValueError): validate_trace('{"status":"insufficient","claims":[]}',trace()[:1])


def test_duplicate_tool_execution_rejected():
    with pytest.raises(ValueError): validate_trace('{"status":"insufficient","claims":[]}',trace()+trace()[:1])


def test_plain_answer_and_whitespace_normalization():
    events=trace()
    events[1]["result"]["documents"][0]["text"]="確認手順\n電源ランプとLANケーブルを確認します。"
    result=validate_trace('「確認手順 電源ランプとLANケーブルを確認します。」[KB001]',events)
    assert result["draft"]["citations"]==["KB001"]


@pytest.mark.parametrize("raw", [
    '「電源ランプとLANケーブルを確認します。」[KB013]',
    '「直ちに再起動してください。」[KB001]',
    '訪問確定。「電源ランプとLANケーブルを確認します。」[KB001]',
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
        with pytest.raises(ValueError,match="確約"):
            validate_trace(bad,events)
