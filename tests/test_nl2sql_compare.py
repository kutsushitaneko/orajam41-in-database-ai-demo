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


def test_profiles_differ_only_in_annotations(monkeypatch, tmp_path):
    import json
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    monkeypatch.setattr(demo, "guard", lambda _: None)
    monkeypatch.setattr(demo, "ROOT", tmp_path)
    monkeypatch.setattr(demo, "attributes", lambda _: {"object_list": [], "enforce_object_list": True})
    cur.fetchall.return_value = [(n,) for n in demo.REQUIRED_OBJECTS | demo.OPTIONAL_OBJECTS | demo.RESTRICTED_OBJECTS]
    demo.setup(conn, {})
    attrs = [json.loads(c.kwargs["a"]) for c in cur.execute.call_args_list if "a" in c.kwargs]
    baseline, tuned = attrs
    assert {o['name'] for o in baseline['object_list']} == demo.REQUIRED_OBJECTS | demo.OPTIONAL_OBJECTS
    assert baseline["object_list_mode"] == "all"
    assert baseline["enforce_object_list"] is True
    assert baseline["comments"] is False
    assert baseline["annotations"] is False
    assert tuned == dict(baseline, annotations=True)
    assert not any(c.args[0].startswith('COMMENT ON') for c in cur.execute.call_args_list)


def test_scope_rejects_unreviewed_objects_and_allows_missing_bulk_tables():
    import pytest
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchall.return_value = [(n,) for n in demo.REQUIRED_OBJECTS | demo.RESTRICTED_OBJECTS]
    assert {x['name'] for x in demo.object_scope(conn)} == demo.REQUIRED_OBJECTS
    cur.fetchall.return_value += [('OJ41_NEW_CUSTOMER_DATA',)]
    with pytest.raises(ValueError, match='未分類'):
        demo.object_scope(conn)
