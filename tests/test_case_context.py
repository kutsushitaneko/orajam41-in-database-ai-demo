from unittest.mock import MagicMock

import pytest

from webinar_demo.case_context import case_scope


def test_request_failure_still_clears_scope():
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchone.return_value = ("SR001", "C001")
    with pytest.raises(RuntimeError):
        with case_scope(conn, "SR001"):
            raise RuntimeError("request failed")
    assert "clear_case" in cur.execute.call_args.args[0]


def test_failed_open_also_clears_scope():
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.execute.side_effect = [ValueError("bad case"), None]
    with pytest.raises(ValueError):
        with case_scope(conn, "MISSING"):
            pytest.fail("must not yield")
    assert "clear_case" in cur.execute.call_args.args[0]
