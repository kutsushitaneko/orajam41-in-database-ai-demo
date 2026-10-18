from unittest.mock import MagicMock

from webinar_demo import nl2sql_compare as demo


def test_baseline_response_is_never_executed(monkeypatch):
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchone.return_value = ("DELETE FROM OJ41_DEVICES",)
    monkeypatch.setattr(demo, "guard", lambda _: None)
    monkeypatch.setattr(demo, "require_case", lambda _: {"case_id": "SR001"})
    tuned = MagicMock(return_value={"matches_reference": True})
    monkeypatch.setattr(demo, "run_case", tuned)
    result = demo.compare(conn)
    cur.execute.assert_called_once()
    statement = cur.execute.call_args.args[0]
    assert "action=>'showsql'" in statement
    assert cur.execute.call_args.kwargs["q"] == demo.CASES["onsite"][0]
    assert cur.execute.call_args.kwargs["p"] == demo.BASELINE
    assert result["baseline_response"] == "DELETE FROM OJ41_DEVICES"
    tuned.assert_called_once_with(conn, "onsite")


def test_profiles_differ_only_in_comments(monkeypatch, tmp_path):
    import json
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    monkeypatch.setattr(demo, "guard", lambda _: None)
    monkeypatch.setattr(demo, "ROOT", tmp_path)
    monkeypatch.setattr(demo, "attributes", lambda _: {"object_list": [], "enforce_object_list": True})
    demo.setup(conn, {})
    attrs = [json.loads(c.kwargs["a"]) for c in cur.execute.call_args_list if "a" in c.kwargs]
    baseline, tuned = attrs
    assert baseline["object_list"] == [{"owner": "ORAJAM41USER"}]
    assert "object_list_mode" not in baseline
    assert "enforce_object_list" not in baseline
    assert baseline["comments"] is False
    assert tuned == dict(baseline, comments=True)
