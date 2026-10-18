import json

import pytest

from webinar_demo.nl2sql import validated_sql
from webinar_demo.business_ai import validate_trace


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
