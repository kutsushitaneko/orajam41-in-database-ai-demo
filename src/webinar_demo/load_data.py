"""Load and validate the standard dataset in the designated demo schema."""

import argparse
import csv
import json
from datetime import date, datetime
from pathlib import Path

from webinar_demo.case_context import case_scope

import oracledb

from webinar_demo.generate_data import TABLES, DATE_COLS, INT_COLS, digest, generate, merge_sql
from webinar_demo.settings import ROOT, ConfigurationError, db_parameters, load_settings


def guard(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT SYS_CONTEXT('USERENV','DB_NAME'), SYS_CONTEXT('USERENV','SESSION_USER'), SYS_CONTEXT('USERENV','CURRENT_SCHEMA') FROM dual")
        db, user, schema = cur.fetchone()
        if not (db.lower() == "arakawalab" or db.lower().endswith("_arakawalab")) or user != "ORAJAM41USER" or schema != user:
            raise ConfigurationError("実際の接続先DB／ユーザー／スキーマが想定と異なります。")


def read_dataset(folder: Path) -> tuple[dict, dict]:
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    expected = generate(manifest["as_of_date"], manifest["seed"])
    required = {t.lower() + ".csv" for t in TABLES} | {"40_load_data.sql", "evaluation.json"}
    if set(manifest["files"]) != required:
        raise ValueError("生成ファイル一覧が標準データと一致しません。")
    for filename in required:
        if digest((folder / filename).read_bytes()) != manifest["files"][filename]:
            raise ValueError(f"生成ファイルのハッシュ不一致: {filename}")
    data = {}
    for table, cols in TABLES.items():
        with (folder / (table.lower() + ".csv")).open(encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f)
            if reader.fieldnames != list(cols):
                raise ValueError(f"CSV列の不一致: {table}")
            rows = []
            for row in reader:
                for col in cols:
                    row[col] = None if row[col] == "" else int(row[col]) if col in INT_COLS else row[col]
                rows.append(row)
            data[table] = rows
    if data != expected or manifest["counts"] != {t: len(v) for t, v in data.items()}:
        raise ValueError("CSVの内容が現在の生成器と一致しません。再生成してください。")
    return manifest, data


def execute_block(conn, path: Path) -> None:
    # These files contain exactly one anonymous PL/SQL block, no SQL splitter.
    text = path.read_text(encoding="utf-8").strip()
    if not text.endswith("\n/"):
        raise ValueError("単一PL/SQLブロック形式ではありません。")
    with conn.cursor() as cur:
        cur.execute(text[:-1].rstrip())


def canonical(value):
    if isinstance(value, (datetime, date)): return value.date().isoformat() if isinstance(value, datetime) else value.isoformat()
    return value


def verify(conn, data: dict) -> dict:
    result = {}
    with conn.cursor() as cur:
        for table, cols in TABLES.items():
            cur.execute(f"SELECT {', '.join(cols)} FROM {table} ORDER BY {cols[0]}")
            actual = [dict(zip(cols, (canonical(v) for v in row), strict=True)) for row in cur]
            expected = sorted(data[table], key=lambda r: r[cols[0]])
            if actual != expected:
                raise ValueError(f"DBの全列比較が不一致: {table}")
            result[table] = len(actual)
        checks = {
            "visible_documents": ("SELECT doc_id FROM OJ41_VISIBLE_KNOWLEDGE ORDER BY doc_id", [f"KB{i:03}" for i in range(1, 17) if i not in (4, 13, 14, 15)]),
            "visible_chunks": ("SELECT chunk_id FROM OJ41_VISIBLE_CHUNKS ORDER BY chunk_id", [f"KB{i:03}-01" for i in range(1, 17) if i not in (4, 13, 14, 15)]),
            "visible_devices": ("SELECT device_id FROM OJ41_VISIBLE_DEVICES ORDER BY device_id", [f"DEV{i:03}" for i in range(1, 9)]),
            "onsite_devices": ("SELECT device_id FROM OJ41_VISIBLE_CONTRACTS WHERE onsite_eligible='Y' ORDER BY device_id", ["DEV001", "DEV005", "DEV006", "DEV008"]),
            "invalid_objects": ("SELECT object_name FROM user_objects WHERE object_name LIKE 'OJ41\\_%' ESCAPE '\\' AND status <> 'VALID'", []),
        }
        with case_scope(conn, "SR001"):
            for name, (sql, expected) in checks.items():
                cur.execute(sql)
                actual = [r[0] for r in cur]
                if actual != expected: raise ValueError(f"ビュー／定義の検証失敗: {name}")
                result[name] = actual
    return result


def load_python(conn, data: dict) -> dict:
    guard(conn)
    try:
        with conn.cursor() as cur:
            for table, cols in TABLES.items():
                sql = merge_sql(table, [f":{i+1}" for i in range(len(cols))])
                rows = [tuple(date.fromisoformat(row[c]) if c in DATE_COLS else row[c] for c in cols) for row in data[table]]
                # Small standard dataset: one transaction, no partial commit.
                cur.executemany(sql, rows)
        result = verify(conn, data)
        conn.commit()
        return result
    except Exception:
        conn.rollback()
        raise


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--input", type=Path, default=ROOT / "data/generated/standard")
    p.add_argument("--setup", action="store_true", help="Create missing tables and refresh dedicated views")
    p.add_argument("--route", choices=("python", "sql"), default="python")
    p.add_argument("--verify-only", action="store_true")
    p.add_argument("--report", type=Path, help="Write a non-secret JSON verification report")
    a = p.parse_args()
    if a.setup and a.verify_only:
        p.error("--setup と --verify-only は併用できません。")
    try:
        manifest, data = read_dataset(a.input)
        with oracledb.connect(**db_parameters(load_settings())) as conn:
            conn.call_timeout = 120000
            guard(conn)
            if a.setup:
                execute_block(conn, ROOT / "sql/setup/35_create_demo_tables.sql")
            if a.verify_only:
                result = verify(conn, data)
            elif a.route == "python":
                result = load_python(conn, data)
            else:
                execute_block(conn, a.input / "40_load_data.sql")
                result = verify(conn, data)
            report = dict(action="verify" if a.verify_only else a.route,
                          as_of_date=manifest["as_of_date"], seed=manifest["seed"], results=result)
            if a.report:
                a.report.parent.mkdir(parents=True, exist_ok=True)
                a.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except oracledb.Error as exc:
        print("データ準備失敗: " + exc.args[0].full_code + "（接続情報を含む詳細は非表示）")
    except (ConfigurationError, ValueError, OSError) as exc:
        print(f"データ準備失敗: {exc}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
