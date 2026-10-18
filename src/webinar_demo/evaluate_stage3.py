"""Explicit live evaluation; --rag adds up to three billed GenAI calls."""

import argparse
import json
from pathlib import Path

from webinar_demo.case_context import case_scope

import oracledb

from webinar_demo.rag import answer_question
from webinar_demo.search import search
from webinar_demo.settings import ROOT, db_parameters, load_settings


def evaluate(conn, values, include_rag=False, output=None):
    records = []
    def record(name, result):
        records.append(dict(case=name, result=result))
        if output:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    cases = [
        ("synonym_vector", "管理画面が固まって操作できない", dict(model="AX-100"), "KB001"),
        ("synonym_keyword", "管理画面が固まって操作できない", dict(model="AX-100", mode="keyword", keyword="固まって"), None),
        ("unfiltered_E101", "E101の対処は？", {}, None),
        ("AX_E101", "AX-100のE101の対処は？", dict(model="AX-100", require_codes=True), "KB002"),
        ("BX_E101", "BX-200のE101の対処は？", dict(model="BX-200", require_codes=True), "KB006"),
        ("hybrid_E201", "電源の警告が出た", dict(model="AX-100", mode="hybrid", keyword="E201"), "KB003"),
        ("unknown_code", "AX-100のE999の修理方法は？", dict(model="AX-100", require_codes=True), None),
        ("other_customer", "C002専用の管理画面復旧手順", dict(model="AX-100"), None),
        ("other_device", "DEV009の管理画面が固まった", {}, None),
        ("all_visible", "確認手順", dict(top_k=10), None),
    ]
    forbidden = {"KB004", "KB013", "KB014", "KB015"}
    for name, question, options, expected in cases:
        result = search(conn, question, **options)
        record(name, result)
        ids = [h["doc_id"] for h in result["hits"]]
        assert not forbidden.intersection(ids), name
        if expected: assert ids and ids[0] == expected, (name, ids)
        if name in {"synonym_keyword", "unknown_code", "other_customer", "other_device"}: assert not ids, name
        print(f"{name}: PASS / {ids}", flush=True)
    if include_rag:
        cases = [
            ("rag_normal", "DEV001の管理画面が開かない。最初に何を確認する？", "answered", "KB001"),
            ("rag_E101", "AX-100のE101の対処は？", "answered", "KB002"),
            ("rag_unknown_code", "AX-100のE999の修理方法は？", "insufficient", None),
            ("rag_missing_price", "AX-100の保証延長料金を日本円で教えて。", "insufficient", None),
            ("rag_other_customer", "C002専用のAX-100管理画面復旧手順を教えて。", "insufficient", None),
            ("rag_other_device", "DEV009の管理画面が開かない。", "insufficient", None),
        ]
        for name, question, status, expected in cases:
            result = answer_question(conn, values, question)
            record(name, result)
            assert result["status"] == status, name
            if expected: assert expected in {c["doc_id"] for c in result["claims"]}, name
            if name in {"rag_unknown_code", "rag_other_customer", "rag_other_device"}:
                assert result["llm_calls"] == 0, name
            print(f"{name}: PASS / {status} / LLM={result['llm_calls']} / {result['seconds']}s", flush=True)
    return records


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--rag", action="store_true")
    p.add_argument("--output", type=Path, default=ROOT / "local/stage3-evaluation.json")
    a = p.parse_args()
    values = load_settings()
    with oracledb.connect(**db_parameters(values)) as conn:
        conn.call_timeout = 180000
        with case_scope(conn, "SR001"):
            result = evaluate(conn, values, a.rag, a.output)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"検証完了: {len(result)}ケース。結果: {a.output}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        # Keep credentials and provider request details out of command output.
        print(f"検証停止: {type(exc).__name__}。保存済みの評価結果を確認してください。")
        raise SystemExit(1)
