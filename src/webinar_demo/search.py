"""Exact cosine search over session-scoped views; no LLM call."""

import argparse
import json
import re
import time

from webinar_demo.case_context import case_scope

import oracledb

from webinar_demo.load_data import execute_block, guard
from webinar_demo.settings import ROOT, ConfigurationError, db_parameters, load_settings

MODEL = "MULTILINGUAL_E5_LARGE"


def embed_documents(conn) -> dict:
    guard(conn)
    start = time.perf_counter()
    execute_block(conn, ROOT / "sql/setup/50_embed_documents.sql")
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*), MIN(VECTOR_DIMENSION_COUNT(embedding)), MAX(VECTOR_DIMENSION_COUNT(embedding)) FROM OJ41_CHUNKS WHERE embedding IS NOT NULL")
        count, low, high = cur.fetchone()
        cur.execute("SELECT COUNT(*) FROM OJ41_CHUNKS")
        if count != cur.fetchone()[0] or low != 1024 or high != 1024:
            raise ValueError("ベクトルの件数／次元が不一致です。")
    return dict(count=count, dimensions=1024, seconds=round(time.perf_counter() - start, 3))


def search(conn, question: str, model: str | None = None, device: str | None = None,
           mode: str = "vector", keyword: str | None = None, top_k: int = 3,
           require_codes: bool = False) -> dict:
    guard(conn)
    if not question.strip() or len(question) > 800 or not 1 <= top_k <= 10:
        raise ValueError("質問は1〜800文字、top-kは1〜10で指定してください。")
    if mode not in {"vector", "keyword", "hybrid"}:
        raise ValueError("未知の検索方式です。")
    if mode != "vector" and (not keyword or not keyword.strip()):
        raise ValueError("keyword／hybridには--keywordが必要です。")
    if keyword and len(keyword) > 100:
        raise ValueError("keywordは100文字以下です。")
    start = time.perf_counter()
    result = dict(question=question, mode=mode, model=model, hits=[], reason=None)
    with conn.cursor() as cur:
        cur.execute("SELECT OJ41_CASE_CTX.customer_id() FROM dual")
        identity = cur.fetchone()
        if not identity or identity[0] is None:
            result["reason"] = "no_selected_case"
            result["seconds"] = round(time.perf_counter() - start, 3)
            return result
        requested_customers = re.findall(r"\bC\d{3}\b", question, flags=re.ASCII | re.IGNORECASE)
        if any(c.upper() != identity[0] for c in requested_customers):
            result["reason"] = "outside_authorized_scope"
            result["seconds"] = round(time.perf_counter() - start, 3)
            return result
        # Device identity is resolved against the scoped DB view, never trusted from a prompt.
        devices = {v.upper() for v in re.findall(r"DEV\d{3}", question, re.IGNORECASE)}
        if device: devices.add(device.upper())
        if len(devices) > 1: raise ValueError("このデモでは機器を1台ずつ指定してください。")
        if devices:
            cur.execute("SELECT model FROM OJ41_VISIBLE_DEVICES WHERE device_id=:d", d=devices.pop())
            row = cur.fetchone()
            if not row:
                result["reason"] = "device_not_visible_or_missing"
                result["seconds"] = round(time.perf_counter() - start, 3)
                return result
            if model and model != row[0]: raise ValueError("指定機種が機器と一致しません。")
            model = row[0]
        mentioned_models = set(re.findall(r"[A-Z]{2}-\d{3}", question.upper()))
        if model and any(m != model for m in mentioned_models):
            raise ValueError("質問内の機種と指定機種が一致しません。")
        result["model"] = model
        if mode != "keyword":
            cur.execute("SELECT COUNT(*) FROM OJ41_VISIBLE_CHUNKS WHERE embedding IS NULL OR embedding_model IS NULL OR embedding_model<>:m", m=MODEL)
            if cur.fetchone()[0]:
                raise ValueError("未生成またはモデルが異なるベクトルがあります。--prepareを実行してください。")
        filters = ["embedding IS NOT NULL"]
        params = dict(k=top_k)
        if model:
            filters.append("model=:model")
            params["model"] = model
        codes = sorted(set(re.findall(r"\bE\d{3}\b", question.upper(), re.ASCII))) if require_codes else []
        # Error codes are hard constraints for RAG, not fuzzy similarity targets.
        for i, code in enumerate(codes):
            filters.append(f"INSTR(UPPER(chunk_text), :code{i}) > 0")
            params[f"code{i}"] = code
        lexical = "0"
        if keyword:
            lexical = "CASE WHEN INSTR(UPPER(chunk_text), UPPER(:keyword)) > 0 THEN 1 ELSE 0 END"
            params["keyword"] = keyword
        if mode == "keyword":
            filters.append("INSTR(UPPER(chunk_text), UPPER(:keyword)) > 0")
            distance, order = "CAST(NULL AS NUMBER)", "doc_id, chunk_id"
        else:
            cur.execute("SELECT VECTOR_EMBEDDING(MULTILINGUAL_E5_LARGE USING :q AS data) FROM dual", q="query: " + question)
            params["qvec"] = cur.fetchone()[0]
            distance = "VECTOR_DISTANCE(embedding, :qvec, COSINE)"
            order = "lexical_hit DESC, distance, doc_id, chunk_id" if mode == "hybrid" else "distance, doc_id, chunk_id"
        cur.execute(f"SELECT chunk_id, doc_id, title, chunk_text, {distance} AS distance, {lexical} AS lexical_hit "
                    f"FROM OJ41_VISIBLE_CHUNKS WHERE {' AND '.join(filters)} ORDER BY {order} FETCH FIRST :k ROWS ONLY", params)
        keys = ("chunk_id", "doc_id", "title", "text", "distance", "lexical_hit")
        result["hits"] = [dict(zip(keys, row, strict=True)) for row in cur]
        result["reason"] = None if result["hits"] else "no_matching_evidence"
    result["seconds"] = round(time.perf_counter() - start, 3)
    return result


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case-id", default="SR001")
    p.add_argument("--prepare", action="store_true")
    p.add_argument("--question")
    p.add_argument("--model")
    p.add_argument("--device")
    p.add_argument("--mode", choices=("vector", "keyword", "hybrid"), default="vector")
    p.add_argument("--keyword")
    p.add_argument("--top-k", type=int, default=3)
    a = p.parse_args()
    if not (a.prepare or a.question): p.error("--prepare または --question を指定してください。")
    try:
        with oracledb.connect(**db_parameters(load_settings())) as conn:
            conn.call_timeout = 600000
            if a.prepare: print(json.dumps(embed_documents(conn), ensure_ascii=False))
            if a.question:
                with case_scope(conn, a.case_id):
                    print(json.dumps(search(conn, a.question, a.model, a.device, a.mode, a.keyword, a.top_k), ensure_ascii=False, indent=2))
        return 0
    except oracledb.Error as exc:
        print("検索失敗: " + exc.args[0].full_code)
    except (ValueError, ConfigurationError) as exc:
        print(str(exc))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
