"""Live checks for request scope, switching, cleanup, and cross-customer isolation."""
import json

import oracledb

from webinar_demo.business_ai import run_agent
from webinar_demo.case_context import case_scope, current_case
from webinar_demo.load_data import guard
from webinar_demo.search import search
from webinar_demo.settings import ROOT, db_parameters, load_settings


def evaluate(conn):
    guard(conn)
    result = {}
    with conn.cursor() as cur:
        def devices():
            cur.execute("SELECT device_id FROM OJ41_VISIBLE_DEVICES ORDER BY device_id")
            return [r[0] for r in cur]

        def empty():
            assert current_case(conn) == dict(case_id=None, customer_id=None)
            for view in ("OJ41_VISIBLE_DEVICES", "OJ41_VISIBLE_CONTRACTS", "OJ41_VISIBLE_KNOWLEDGE", "OJ41_VISIBLE_CHUNKS"):
                cur.execute(f"SELECT COUNT(*) FROM {view}")
                assert cur.fetchone()[0] == 0

        cur.execute("BEGIN OJ41_CASE_CTX.clear_case; END;")
        empty()
        result["no_case_all_views_empty"] = True
        with case_scope(conn, "SR001"):
            assert devices() == [f"DEV{i:03}" for i in range(1, 9)]
            assert search(conn, "DEV009の管理画面が開かない")["hits"] == []
            try:
                run_agent(conn, "DEV009", "管理画面が開かない")
                raise AssertionError("Foreign device should stop before RUN_TEAM")
            except ValueError as exc:
                assert "選択案件" in str(exc)
            try:
                cur.execute("BEGIN OJ41_AGENT_CTX.start_run('DEV009','管理画面','reject-test'); END;")
                raise AssertionError("SQL entry must reject a foreign device")
            except oracledb.Error as exc:
                assert exc.args[0].code == 20053
            result["sr001_rejects_dev009_before_llm"] = True
        empty()
        with case_scope(conn, "SR002"):
            assert devices() == [f"DEV{i:03}" for i in range(9, 13)]
            cur.execute("SELECT doc_id FROM OJ41_VISIBLE_KNOWLEDGE WHERE scope='CUSTOMER'")
            assert cur.fetchall() == [("KB013",)]
            assert search(conn, "DEV001の管理画面が開かない")["hits"] == []
            assert search(conn, "DEV009の管理画面が開かない")["hits"]
            result["sr002_dev009_visible_dev001_hidden"] = True
        empty()
        try:
            with case_scope(conn, "SR001"):
                raise RuntimeError("Injected application failure")
        except RuntimeError:
            pass
        empty()
        result["exception_clears_scope"] = True
        cur.execute("BEGIN OJ41_CASE_CTX.open_case('SR001'); END;")
        try:
            cur.execute("BEGIN OJ41_CASE_CTX.open_case('MISSING'); END;")
            raise AssertionError("Missing case must fail")
        except oracledb.Error as exc:
            assert exc.args[0].code == 20061
        empty()
        result["invalid_case_clears_previous_scope"] = True
        with case_scope(conn, "SR001"):
            cur.execute("BEGIN OJ41_AGENT_CTX.start_run('DEV001','管理画面','case-test'); OJ41_CASE_CTX.open_case('SR002'); END;")
            try:
                cur.execute("SELECT OJ41_CONTRACT_TOOL('DEV001') FROM dual")
                raise AssertionError("Stale agent run must fail")
            except oracledb.Error as exc:
                assert exc.args[0].code == 20062
            result["case_switch_invalidates_agent_run"] = True
        with case_scope(conn, "SR001"):
            cur.execute("BEGIN OJ41_AGENT_CTX.start_run('DEV001','管理画面','case-test'); OJ41_CASE_CTX.open_case('SR001'); END;")
            try:
                cur.execute("SELECT OJ41_CONTRACT_TOOL('DEV001') FROM dual")
                raise AssertionError("Reopened case must invalidate prior run")
            except oracledb.Error as exc:
                assert exc.args[0].code == 20062
            cur.execute("BEGIN OJ41_AGENT_CTX.clear_run; END;")
            result["reopen_invalidates_agent_run"] = True
        empty()
        with case_scope(conn, "SR001"):
            # A second physical connection has no implicit scope.
            with oracledb.connect(**db_parameters(load_settings())) as other:
                assert current_case(other) == dict(case_id=None, customer_id=None)
                with other.cursor() as c2:
                    c2.execute("SELECT COUNT(*) FROM OJ41_VISIBLE_CONTRACTS")
                    assert c2.fetchone()[0] == 0
            result["connections_do_not_share_scope"] = True
    return dict(checks=result, complete=True)


def main():
    with oracledb.connect(**db_parameters(load_settings())) as conn:
        conn.call_timeout = 180000
        report = evaluate(conn)
    (ROOT / "local/case-evaluation.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
