"""Execute the repository's SQL demo files via the driver (not GUI validation)."""
import argparse
import json
import re

import oracledb

from webinar_demo.business_ai import validate_trace
from webinar_demo.case_context import current_case
from webinar_demo.check_genai import text
from webinar_demo.load_data import guard
from webinar_demo.nl2sql import validated_sql
from webinar_demo.settings import ROOT, db_parameters, load_settings


def statements(source):
    """Minimal splitter for these fixed files; no general SQL-script support."""
    buf = []
    block = False
    for line in source.splitlines():
        if line.lstrip().startswith("--") or not line.strip():
            continue
        if not buf:
            block = bool(re.match(r"\s*(BEGIN|DECLARE)\b", line, re.I))
        if block and line.strip() == "/":
            yield "\n".join(buf)
            buf = []
        else:
            buf.append(line)
            if not block and line.rstrip().endswith(";"):
                yield "\n".join(buf).rstrip()[:-1]
                buf = []
    if buf:
        raise ValueError("Unterminated statement in tutorial SQL file")


def run_file(conn, relative):
    results = []
    with conn.cursor() as cur:
        for statement in statements((ROOT / relative).read_text(encoding="utf-8")):
            cur.execute(statement)
            if cur.description:
                results.append(dict(columns=[c[0] for c in cur.description],
                                    rows=[[text(v) if isinstance(v, oracledb.LOB) else v for v in row] for row in cur.fetchall()]))
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", action="store_true")
    args = parser.parse_args()
    report = {}
    with oracledb.connect(**db_parameters(load_settings())) as conn:
        guard(conn)
        conn.call_timeout = 180000
        report["environment"] = run_file(conn, "sql/demos/00_capture_environment.sql")
        assert report["environment"][2]["rows"] == [[1024]]
        assert report["environment"][3]["rows"] == [[16, 16]]
        report["data"] = run_file(conn, "sql/setup/45_check_demo_data.sql")
        assert all(actual == expected for _, actual, expected in report["data"][0]["rows"])
        report["A"] = run_file(conn, "sql/demos/01_vector_search.sql")
        assert report["A"][0]["rows"][0][:2] == ["SR001", "C001"]
        assert [r[0] for r in report["A"][3]["rows"]] == ["KB001", "KB008", "KB002"]
        assert report["A"][4]["rows"] == []
        assert [r[0] for r in report["A"][5]["rows"]] == ["KB002", "KB006", "KB003"]
        assert current_case(conn)["case_id"] is None
        report["C"] = run_file(conn, "sql/demos/02_nl2sql.sql")
        assert current_case(conn)["case_id"] is None
        # Validate and execute only the tuned response, within the same explicit case.
        from webinar_demo.case_context import case_scope
        with case_scope(conn, "SR001"), conn.cursor() as cur:
            cur.execute(validated_sql(report["C"][1]["rows"][0][0]))
            assert [list(r) for r in cur.fetchall()] == report["C"][2]["rows"]
        if args.agent:
            with conn.cursor() as cur:
                cur.callproc("DBMS_OUTPUT.ENABLE", [1000000])
            report["D_history"] = run_file(conn, "sql/demos/03_support_agent.sql")
            lines = []
            with conn.cursor() as cur:
                line, status = cur.var(str, size=32767), cur.var(int)
                while True:
                    cur.callproc("DBMS_OUTPUT.GET_LINE", [line, status])
                    if status.getvalue() != 0:
                        break
                    lines.append(line.getvalue())
            assert len(lines) == 2
            report["D_output"] = lines
            report["D_validated"] = validate_trace(lines[0], json.loads(lines[1]))
            assert current_case(conn)["case_id"] is None
            assert report["D_validated"]["contract"]["onsite_eligible"] == "Y"
        report["complete"] = True
    (ROOT / "local/sql-demo-check.json").write_text(json.dumps(report, ensure_ascii=False, default=str, indent=2), encoding="utf-8")
    print("SQL files: PASS (driver execution; GUI operation remains a separate check)")


if __name__ == "__main__":
    main()
