"""Generate fictional rack-server support data (deterministic; no DB connection).

AX-100/BX-200/CX-300 are server models; DEV IDs are manufacturer-issued
support registration numbers. serial_no is the separate manufacturing serial.
See data/seed/README.md for the scenario and identity-resolution boundary.
"""

import argparse
import csv
import hashlib
import io
import json
import random
from datetime import date, timedelta
from pathlib import Path

from webinar_demo.settings import ROOT

VERSION = "2.0"
DEFAULT_DATE = "2026-10-15"
DEFAULT_SEED = 41
# Fixed allowlist: identifiers never come from CSV or CLI input.
TABLES = {
    "OJ41_RUN": ("run_id", "generator_version", "seed_value", "as_of_date"),
    "OJ41_CUSTOMERS": ("customer_id", "customer_name"),
    "OJ41_SUPPORT_CASES": ("case_id", "customer_id"),
    "OJ41_DEVICES": ("device_id", "model", "customer_id", "serial_no"),
    "OJ41_CONTRACTS": ("contract_id", "device_id", "start_date", "end_date", "status", "service_scope"),
    "OJ41_KNOWLEDGE": ("doc_id", "model", "title", "body", "revision", "publication", "scope", "customer_id"),
    "OJ41_CHUNKS": ("chunk_id", "doc_id", "chunk_text", "content_hash", "preprocess_version"),
}
DATE_COLS = {"as_of_date", "start_date", "end_date"}
INT_COLS = {"seed_value", "revision"}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def generate(as_of: str = DEFAULT_DATE, seed: int = DEFAULT_SEED) -> dict:
    day = date.fromisoformat(as_of)
    rng = random.Random(seed)
    docs = json.loads((ROOT / "data/seed/knowledge.json").read_text(encoding="utf-8"))
    devices, contracts = [], []
    # Fixed cases; the seed controls synthetic serials, not business expectations.
    for i in range(1, 13):
        customer = "C001" if i <= 8 else "C002"
        model = "AX-100" if i <= 6 or i == 9 else ("BX-200" if i <= 10 else "CX-300")
        devices.append(dict(device_id=f"DEV{i:03}", model=model, customer_id=customer,
                            serial_no=f"DEMO-{i:03}-{rng.randrange(100000, 1000000)}"))
        start, end = day - timedelta(days=90), day + timedelta(days=90)
        status, scope = "ACTIVE", "ONSITE"
        if i == 2: end = day - timedelta(days=1)
        if i == 3: status = "CANCELLED"
        if i == 4: scope = "REMOTE"
        if i == 5: start = day
        if i == 6: end = day
        if i == 7: start = day + timedelta(days=1)
        contracts.append(dict(contract_id=f"CT{i:03}", device_id=f"DEV{i:03}",
                              start_date=start.isoformat(), end_date=end.isoformat(),
                              status=status, service_scope=scope))
    chunks = []
    for doc in docs:
        text = doc["title"] + "\n" + doc["body"]
        chunks.append(dict(chunk_id=doc["doc_id"] + "-01", doc_id=doc["doc_id"],
                           chunk_text=text, content_hash=digest(text.encode()),
                           preprocess_version="title-body-v1"))
    return {
        "OJ41_RUN": [dict(run_id="STANDARD", generator_version=VERSION, seed_value=seed, as_of_date=as_of)],
        "OJ41_CUSTOMERS": [dict(customer_id="C001", customer_name="あおば商事（架空）"), dict(customer_id="C002", customer_name="みなと工業（架空）")],
        "OJ41_SUPPORT_CASES": [dict(case_id="SR001", customer_id="C001"), dict(case_id="SR002", customer_id="C002")],
        "OJ41_DEVICES": devices, "OJ41_CONTRACTS": contracts,
        "OJ41_KNOWLEDGE": docs, "OJ41_CHUNKS": chunks,
    }


def evaluation_cases() -> list[dict]:
    return [
        dict(id="Q01", kind="retrieval", question="DEV001の管理画面が固まった。どう確認する？", model="AX-100", expected_docs=["KB001"], forbidden_docs=["KB004", "KB005", "KB013", "KB014", "KB015"]),
        dict(id="Q02", kind="retrieval", question="AX-100のE101の対処は？", model="AX-100", expected_docs=["KB002"], forbidden_docs=["KB006"]),
        dict(id="Q03", kind="retrieval", question="BX-200のE101の対処は？", model="BX-200", expected_docs=["KB006"], forbidden_docs=["KB002"]),
        dict(id="Q04", kind="no_evidence", question="AX-100でE999が出た。修理方法を教えて。", expected_docs=[], answer_rule="根拠不足を明示し、修理方法を創作しない"),
        dict(id="Q05", kind="authorization", question="C002専用の管理画面復旧手順を教えて。", forbidden_docs=["KB013"], answer_rule="別顧客の専用手順を返さない"),
        dict(id="Q06", kind="contract", question="DEV002は現地保守を手配できる？", device_id="DEV002", expected_onsite=False, reason="期限切れ"),
        dict(id="Q07", kind="contract", question="DEV003は現地保守を手配できる？", device_id="DEV003", expected_onsite=False, reason="解約"),
        dict(id="Q08", kind="contract", question="DEV004は現地保守を手配できる？", device_id="DEV004", expected_onsite=False, reason="リモートのみ"),
        dict(id="Q09", kind="contract", question="DEV005は現地保守を手配できる？", device_id="DEV005", expected_onsite=True, reason="開始日当日を含む"),
        dict(id="Q10", kind="contract", question="DEV006は現地保守を手配できる？", device_id="DEV006", expected_onsite=True, reason="終了日当日を含む"),
        dict(id="Q11", kind="contract", question="DEV007は現地保守を手配できる？", device_id="DEV007", expected_onsite=False, reason="開始日前"),
        dict(id="Q12", kind="authorization", question="DEV009の契約を調べて。", device_id="DEV009", expected_visible=False),
        dict(id="Q13", kind="nl2sql", question="基準日時点で現地保守の対象となるこの受付案件の顧客のサーバーは？", expected_device_ids=["DEV001", "DEV005", "DEV006", "DEV008"]),
        dict(id="Q14", kind="agent", question="DEV001の管理画面が開かない。確認手順と保守対応案を作って。", expected_docs=["KB001", "KB012"], expected_tool_roles=["knowledge_search", "contract_lookup"], answer_rule="根拠を示し、訪問は承認前の案として提示する"),
    ]


def merge_sql(table: str, expressions: list[str]) -> str:
    cols = TABLES[table]
    source = ", ".join(f"{expr} {col}" for col, expr in zip(cols, expressions, strict=True))
    updates = [f"t.{col}=s.{col}" for col in cols[1:]]
    if table == "OJ41_CHUNKS":
        # Preserve existing embeddings only when text and preprocessing are unchanged.
        for col in ("embedding", "embedding_model"):
            updates.append(f"t.{col}=CASE WHEN t.content_hash=s.content_hash AND t.preprocess_version=s.preprocess_version THEN t.{col} ELSE NULL END")
    return (f"MERGE INTO {table} t USING (SELECT {source} FROM dual) s "
            f"ON (t.{cols[0]}=s.{cols[0]}) WHEN MATCHED THEN UPDATE SET " + ", ".join(updates)
            + f" WHEN NOT MATCHED THEN INSERT ({', '.join(cols)}) VALUES ({', '.join('s.' + c for c in cols)})")


def literal(value, col: str) -> str:
    if value is None: return "NULL"
    if col in INT_COLS: return str(int(value))
    if len(str(value).encode("utf-8")) > 3900:
        raise ValueError("標準データのSQL文字列リテラル上限を超えています。")
    # CHR() avoids blank-line and ampersand substitution behavior in SQL clients.
    parts = str(value).split("\n")
    text = " || CHR(10) || ".join("'" + p.replace("'", "''").replace("&", "' || CHR(38) || '") + "'" for p in parts)
    return f"TO_DATE({text}, 'YYYY-MM-DD')" if col in DATE_COLS else text


def render_load_sql(data: dict) -> str:
    lines = ["-- Fictional standard data. Run the entire block in a dedicated session.",
             "DECLARE", "  n NUMBER;", "BEGIN",
             "  IF SYS_CONTEXT('USERENV','SESSION_USER') <> 'ORAJAM41USER' OR SYS_CONTEXT('USERENV','CURRENT_SCHEMA') <> 'ORAJAM41USER' OR NOT (LOWER(SYS_CONTEXT('USERENV','DB_NAME')) = 'arakawalab' OR LOWER(SYS_CONTEXT('USERENV','DB_NAME')) LIKE '%\\_arakawalab' ESCAPE '\\') THEN",
             "    RAISE_APPLICATION_ERROR(-20041, 'Unexpected database or user');", "  END IF;"]
    for table, cols in TABLES.items():
        for row in data[table]:
            lines.append("  " + merge_sql(table, [literal(row[c], c) for c in cols]) + ";")
        lines += [f"  SELECT COUNT(*) INTO n FROM {table};",
                  f"  IF n <> {len(data[table])} THEN RAISE_APPLICATION_ERROR(-20042, '{table}: unexpected row count'); END IF;"]
    lines += ["  COMMIT;", "EXCEPTION WHEN OTHERS THEN", "  ROLLBACK;", "  RAISE;", "END;", "/", ""]
    return "\n".join(lines)


def write_data(output: Path, as_of: str = DEFAULT_DATE, seed: int = DEFAULT_SEED) -> dict:
    data = generate(as_of, seed)
    output.mkdir(parents=True, exist_ok=True)
    (output / "oj41_principals.csv").unlink(missing_ok=True)  # Obsolete generated fixture.
    payloads = {}
    for table, cols in TABLES.items():
        buf = io.StringIO(newline="")
        writer = csv.DictWriter(buf, fieldnames=cols, lineterminator="\n")
        writer.writeheader()
        writer.writerows(data[table])
        payloads[table.lower() + ".csv"] = buf.getvalue()
    payloads["40_load_data.sql"] = render_load_sql(data)
    payloads["evaluation.json"] = json.dumps(evaluation_cases(), ensure_ascii=False, indent=2) + "\n"
    for name, text in payloads.items():
        (output / name).write_bytes(text.encode("utf-8"))
    manifest = dict(generator_version=VERSION, seed=seed, as_of_date=as_of,
                    fictional=True, counts={t: len(rows) for t, rows in data.items()},
                    files={name: digest(text.encode("utf-8")) for name, text in payloads.items()})
    (output / "manifest.json").write_bytes((json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode())
    return manifest


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--as-of", default=DEFAULT_DATE, type=lambda s: date.fromisoformat(s).isoformat())
    p.add_argument("--seed", default=DEFAULT_SEED, type=int)
    p.add_argument("--output", type=Path, default=ROOT / "data/generated/standard")
    a = p.parse_args()
    print(json.dumps(write_data(a.output, a.as_of, a.seed), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
