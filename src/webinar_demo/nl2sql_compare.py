"""Compare identical owner-wide metadata scopes with comments off and on."""
import argparse
import json

from webinar_demo.case_context import case_scope, require_case

import oracledb

from webinar_demo.check_genai import attributes, text
from webinar_demo.load_data import guard
from webinar_demo.nl2sql import CASES, run_case
from webinar_demo.settings import ROOT, db_parameters, load_settings

BASELINE = "OJ41_NL2SQL_BASELINE"
TUNED = "OJ41_NL2SQL_TUNED"
COMMENTS = {
    "DEVICE_ID": "メーカー発行のサーバー保守登録番号。機器IDとも呼ぶ。",
    "ONSITE_ELIGIBLE": "基準日時点で現地保守の対象ならY、対象外ならN。現地保守対象の質問にはこの列がYの行を選ぶ。",
    "AS_OF_DATE": "この教材の現在を表す固定基準日。SYSDATEではない。",
    "IS_ACTIVE": "基準日時点で状態と期間を満たす有効契約ならY、それ以外はN。",
    "MODEL": "サーバーの機種。",
}


def setup(conn, values):
    guard(conn)
    comment_sql = ["COMMENT ON TABLE OJ41_VISIBLE_CONTRACTS IS '選択中の受付案件の顧客に属するサーバーの契約。案件と顧客の条件はビューで適用済み。追加の顧客条件や案件の表との結合は不要。1行が1台。'"]
    comment_sql += [f"COMMENT ON COLUMN OJ41_VISIBLE_CONTRACTS.{col} IS '{msg}'" for col, msg in COMMENTS.items()]
    base = attributes(values)
    base.pop("enforce_object_list")
    base.update(max_tokens=1600, object_list=[dict(owner="ORAJAM41USER")], comments=False)
    tuned = dict(base, comments=True)
    blocks = []
    with conn.cursor() as cur:
        for sql in comment_sql:
            cur.execute(sql)
        for name, attrs in ((BASELINE, base), (TUNED, tuned)):
            # These two dedicated comparison profiles are recreated to remove stale attributes.
            cur.execute("BEGIN DBMS_CLOUD_AI.DROP_PROFILE(:p,force=>TRUE); END;", p=name)
            cur.execute("BEGIN DBMS_CLOUD_AI.CREATE_PROFILE(profile_name=>:p,attributes=>:a); END;",
                        p=name, a=json.dumps(attrs))
            blocks.append("BEGIN DBMS_CLOUD_AI.CREATE_PROFILE(profile_name=>'" + name +
                          "',attributes=>'" + json.dumps(attrs).replace("'", "''") + "'); END;\n/")
    path = ROOT / "local/65_nl2sql_profiles.sql"
    path.parent.mkdir(exist_ok=True)
    path.write_text("-- Initial creation only; contains environment-specific values.\n" +
                    ";\n".join(comment_sql) + ";\n" + "\n".join(blocks) + "\n", encoding="utf-8")


def compare(conn):
    guard(conn)
    require_case(conn)
    question = CASES["onsite"][0]
    with conn.cursor() as cur:
        cur.execute("SELECT DBMS_CLOUD_AI.GENERATE(prompt=>:q,profile_name=>:p,action=>'showsql') FROM dual",
                    q=question, p=BASELINE)
        baseline = text(cur.fetchone()[0])
    # Display the comments-off response without executing it.
    return dict(question=question, baseline_response=baseline, tuned=run_case(conn, "onsite"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id", default="SR001")
    parser.add_argument("--setup", action="store_true")
    args = parser.parse_args()
    values = load_settings()
    with oracledb.connect(**db_parameters(values)) as conn:
        conn.call_timeout = 180000
        if args.setup:
            setup(conn, values)
            print("NL2SQL comparison profiles prepared")
        else:
            with case_scope(conn, args.case_id):
                result = compare(conn)
            (ROOT / "local/nl2sql-comparison.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
            print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"比較停止: {type(exc).__name__}（接続情報は非表示）")
        raise SystemExit(1)
