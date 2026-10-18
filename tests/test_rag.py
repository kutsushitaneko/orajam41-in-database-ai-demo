import json

import pytest

from webinar_demo.rag import validate_answer, answer_question

HITS = [dict(doc_id="KB001", text="電源ランプとLANケーブルを確認します。")]


def payload(**changes):
    claim = dict(text="電源ランプとLANケーブルを確認します。", doc_id="KB001", quote="電源ランプとLANケーブルを確認します。")
    claim.update(changes)
    return json.dumps(dict(status="answered", claims=[claim]), ensure_ascii=False)


def test_valid_citation():
    assert validate_answer(payload(), HITS)["claims"][0]["doc_id"] == "KB001"


@pytest.mark.parametrize("changes", [dict(doc_id="KB013"), dict(quote="装置を直ちに再起動してください。"), dict(quote="電源"), dict(text="")])
def test_bad_citation_or_missing_claim_rejected(changes):
    with pytest.raises(ValueError): validate_answer(payload(**changes), HITS)


@pytest.mark.parametrize("raw", ['not json', '{"status":"insufficient","claims":[{}]}', '{"status":"answered","claims":[]}'])
def test_invalid_structure_rejected(raw):
    with pytest.raises(ValueError): validate_answer(raw, HITS)


def test_no_evidence_skips_llm(monkeypatch):
    monkeypatch.setattr("webinar_demo.rag.search", lambda *a, **kw: dict(hits=[], reason="no_matching_evidence"))
    def fail(*args): raise AssertionError("LLM must not be called")
    result = answer_question(None, {}, "AX-100のE999", llm=fail)
    assert result["status"] == "insufficient" and result["llm_calls"] == 0


def test_db_resolved_model_reaches_llm(monkeypatch):
    monkeypatch.setattr("webinar_demo.rag.search", lambda *a, **kw: dict(hits=HITS, model="AX-100"))
    def fake(values, question, hits, target_model):
        assert target_model == "AX-100"
        assert question.startswith("DEV001")
        return payload()
    result = answer_question(None, {}, "DEV001の画面が開かない", llm=fake)
    assert result["status"] == "answered" and result["llm_calls"] == 1


def test_unvalidated_answer_not_returned(monkeypatch):
    monkeypatch.setattr("webinar_demo.rag.search", lambda *a, **kw: dict(hits=HITS, model="AX-100"))
    with pytest.raises(ValueError):
        answer_question(None, {}, "AX-100の画面が開かない", llm=lambda *a, **kw: payload(doc_id="KB013"))
