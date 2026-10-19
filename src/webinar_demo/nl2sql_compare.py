"""Compare annotations off/on within the same enforced, reviewed object scope."""
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
ANNOTATIONS = {
    "DEVICE_ID": "メーカーがサーバー1台ごとに発行する保守登録番号（機器ID）。値はDEVに3桁の数字を続けた形式（例: DEV001）。製造番号SERIAL_NO、機種MODELとは異なる。",
    "CONTRACT_ID": "サーバー1台ごとの保守契約の識別番号。機器IDと契約IDはこのビューのDEVICE_IDとCONTRACT_IDで照会できる。",
    "ONSITE_ELIGIBLE": "基準日時点で現地保守の対象ならY、対象外ならN。現地保守対象の質問にはこの列がYの行を選ぶ。",
    "AS_OF_DATE": "この教材の現在を表す固定基準日。SYSDATEではない。",
    "IS_ACTIVE": "基準日時点で状態と期間を満たす有効契約ならY、それ以外はN。",
    "MODEL": "サーバーの製品機種名。例: AX-100、BX-200、CX-300。個体の保守登録番号ではない。",
}
VIEW_DESCRIPTION = "選択中の受付案件の顧客に属するサーバーの契約。案件と顧客の条件はビューで適用済み。追加の顧客条件や案件の表との結合は不要。1行が1台。"
# Include every reviewed OJ41 table/view that cannot bypass customer/document scope.
# Bulk text copies include restricted knowledge, so they are excluded too.
REQUIRED_OBJECTS = {
    "OJ41_RUN", "OJ41_VISIBLE_CHUNKS", "OJ41_VISIBLE_CONTRACTS",
    "OJ41_VISIBLE_DEVICES", "OJ41_VISIBLE_KNOWLEDGE",
}
OPTIONAL_OBJECTS = {"OJ41_BULK_PARTS"}
RESTRICTED_OBJECTS = {
    "OJ41_CUSTOMERS", "OJ41_SUPPORT_CASES", "OJ41_DEVICES", "OJ41_CONTRACTS",
    "OJ41_KNOWLEDGE", "OJ41_CHUNKS", "OJ41_BULK_DOCS", "OJ41_BULK_STAGE",
}


def object_scope(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT object_name FROM user_objects WHERE object_name LIKE 'OJ41%' "
                    "AND object_type IN ('TABLE','VIEW') ORDER BY object_name")
        existing = {row[0] for row in cur.fetchall()}
    unknown = existing - REQUIRED_OBJECTS - OPTIONAL_OBJECTS - RESTRICTED_OBJECTS
    if unknown:
        raise ValueError("未分類のOJ41表・ビューを確認してください: " + ", ".join(sorted(unknown)))
    if not REQUIRED_OBJECTS <= existing:
        raise ValueError("NL2SQLの準備に必要な表・ビューがありません。")
    return [dict(owner="ORAJAM41USER", name=name)
            for name in sorted(existing & (REQUIRED_OBJECTS | OPTIONAL_OBJECTS))]


def annotation_statements():
    def literal(value):
        return "'" + value.replace("'", "''") + "'"
    return ["ALTER VIEW OJ41_VISIBLE_CONTRACTS ANNOTATIONS "
            "(ADD OR REPLACE description " + literal(VIEW_DESCRIPTION) + ")"] + [
        f"ALTER VIEW OJ41_VISIBLE_CONTRACTS MODIFY ({col} ANNOTATIONS "
        f"(ADD OR REPLACE description {literal(msg)}))" for col, msg in ANNOTATIONS.items()]


def setup(conn, values):
    guard(conn)
    scope = object_scope(conn)
    annotation_sql = annotation_statements()
    base = attributes(values)
    base.update(max_tokens=1600, object_list=scope, object_list_mode="all",
                enforce_object_list=True, comments=False, annotations=False)
    tuned = dict(base, annotations=True)
    blocks = []
    with conn.cursor() as cur:
        for sql in annotation_sql:
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
                    ";\n".join(annotation_sql) + ";\n" + "\n".join(blocks) + "\n", encoding="utf-8")


def compare(conn):
    guard(conn)
    require_case(conn)
    question = CASES["onsite"][0]
    with conn.cursor() as cur:
        cur.execute("SELECT DBMS_CLOUD_AI.GENERATE(prompt=>:q,profile_name=>:p,action=>'showsql') FROM dual",
                    q=question, p=BASELINE)
        baseline = text(cur.fetchone()[0])
    # Display the annotations-off response without executing it.
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
