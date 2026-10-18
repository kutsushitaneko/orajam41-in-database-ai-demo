"""Select AI SQL generation with a deliberately narrow execution allowlist."""
import argparse
import json
import time

from webinar_demo.case_context import case_scope, require_case

import oracledb
import sqlglot
from sqlglot import exp

from webinar_demo.check_genai import text
from webinar_demo.load_data import guard
from webinar_demo.settings import db_parameters, load_settings

PROFILE = "OJ41_BUSINESS_AI"
VIEW = "OJ41_VISIBLE_CONTRACTS"
COLUMNS = {"CONTRACT_ID", "DEVICE_ID", "START_DATE", "END_DATE", "STATUS", "SERVICE_SCOPE",
           "CUSTOMER_ID", "MODEL", "AS_OF_DATE", "IS_ACTIVE", "ONSITE_ELIGIBLE"}
ALLOWED = {exp.Select, exp.Column, exp.Identifier, exp.Table, exp.From, exp.Where,
           exp.And, exp.Or, exp.EQ, exp.NEQ, exp.Literal, exp.Order, exp.Ordered,
           exp.Group, exp.Count, exp.Star, exp.Alias, exp.TableAlias, exp.Paren,
           exp.Distinct, exp.In, exp.Not, exp.Boolean, exp.Upper, exp.Lower}
CASES = {
    "onsite": ("この受付案件の顧客について、基準日時点で現地保守の対象となるサーバーの保守登録番号を昇順で教えてください。",
               "SELECT device_id FROM OJ41_VISIBLE_CONTRACTS WHERE onsite_eligible='Y' ORDER BY device_id"),
    "counts": ("基準日時点で現地保守対象のサーバー数を機種別に集計してください。機種と件数を返し、機種順に並べてください。",
               "SELECT model, COUNT(*) FROM OJ41_VISIBLE_CONTRACTS WHERE onsite_eligible='Y' GROUP BY model ORDER BY model"),
    "other": ("DEV009の機器IDと契約IDを取得してください。",
              "SELECT device_id, contract_id FROM OJ41_VISIBLE_CONTRACTS WHERE device_id='DEV009'"),
    "expired": ("現在有効ではない契約の機器IDだけを昇順で返してください。",
                "SELECT device_id FROM OJ41_VISIBLE_CONTRACTS WHERE is_active='N' ORDER BY device_id"),
}
CONDITION_COLUMNS = {
    "onsite": {"ONSITE_ELIGIBLE", "IS_ACTIVE"},
    "counts": {"ONSITE_ELIGIBLE", "IS_ACTIVE"},
    "other": {"DEVICE_ID"},
    "expired": {"IS_ACTIVE"},
}


def validated_sql(raw: str) -> str:
    if len(raw) > 8000: raise ValueError("SQLが長すぎます。")
    trees = sqlglot.parse(raw, read="oracle")
    if len(trees) != 1 or not isinstance(trees[0], exp.Select):
        raise ValueError("単一SELECTだけを実行できます。")
    tree = trees[0]
    for node in tree.walk():
        if type(node) not in ALLOWED: raise ValueError(f"許可していないSQL構造: {type(node).__name__}")
        if isinstance(node, exp.Column) and node.name.upper() not in COLUMNS:
            raise ValueError("許可していない列です。")
        if isinstance(node, exp.Star) and not isinstance(node.parent, exp.Count):
            raise ValueError("SELECT *は許可しません。")
    tables = list(tree.find_all(exp.Table))
    if len(tables) != 1 or tables[0].name.upper() != VIEW or tables[0].catalog:
        raise ValueError("閲覧用ビュー1つだけを参照してください。")
    if tables[0].db and tables[0].db.upper() != "ORAJAM41USER":
        raise ValueError("他スキーマは参照できません。")
    # Execute the parsed and regenerated AST, never the raw model output.
    return tree.sql(dialect="oracle", comments=False)


def run_case(conn, name):
    guard(conn)
    require_case(conn)
    question, reference = CASES[name]
    start = time.perf_counter()
    with conn.cursor() as cur:
        cur.execute("SELECT DBMS_CLOUD_AI.GENERATE(prompt=>:q, profile_name=>:p, action=>'showsql') FROM dual", q=question, p="OJ41_NL2SQL_TUNED")
        raw = text(cur.fetchone()[0])
        sql = validated_sql(raw)
        where=sqlglot.parse_one(sql,read="oracle").args.get("where")
        if where and not {c.name.upper() for c in where.find_all(exp.Column)} <= CONDITION_COLUMNS[name]:
            raise ValueError("質問にない絞り込み条件が追加されています。")
        cur.execute(sql)
        actual = cur.fetchmany(101)
        if len(actual) > 100: raise ValueError("結果件数が上限を超えました。")
        cur.execute(reference)
        expected = cur.fetchall()
        if actual != expected: raise ValueError(f"正解SQLとの結果不一致: {name}")
    return dict(case=name, question=question, generated_sql=sql, reference_sql=reference,
                rows=actual, matches_reference=True, seconds=round(time.perf_counter()-start,3))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case-id", default="SR001")
    p.add_argument("--case", choices=CASES, default="onsite")
    a=p.parse_args()
    with oracledb.connect(**db_parameters(load_settings())) as conn:
        conn.call_timeout=180000
        with case_scope(conn, a.case_id):
            print(json.dumps(run_case(conn,a.case),ensure_ascii=False,indent=2))


if __name__ == "__main__":
    try: main()
    except Exception as e:
        print(f"照会停止: {type(e).__name__}（詳細な接続情報は非表示）")
        raise SystemExit(1)
