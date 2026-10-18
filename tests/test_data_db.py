"""Opt-in tests: ORAJAM41_DB_TEST=1. Uses only the stage-2 standard tables.

The insert-path test replaces verified standard rows within one transaction.
Run before stage 3: existing embeddings cause that test to stop, not erase them.
"""

import array
import copy
import os

import oracledb
import pytest

from webinar_demo.generate_data import TABLES, merge_sql
from webinar_demo.load_data import execute_block, guard, load_python, read_dataset, verify
from webinar_demo.settings import ROOT, db_parameters, load_settings

pytestmark = pytest.mark.skipif(os.environ.get("ORAJAM41_DB_TEST") != "1", reason="Explicit DB test opt-in required")


@pytest.fixture
def db():
    with oracledb.connect(**db_parameters(load_settings())) as conn:
        conn.call_timeout = 120000
        guard(conn)
        try:
            yield conn
        finally:
            conn.rollback()


@pytest.fixture
def data():
    return read_dataset(ROOT / "data/generated/standard")[1]


def test_both_routes_insert_update_and_repeat(db, data):
    verify(db, data)  # Refuse to replace nonstandard data.
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM OJ41_CHUNKS WHERE embedding IS NOT NULL")
        assert cur.fetchone()[0] == 0, "Run only before embedding generation"
        for table in reversed(TABLES):
            cur.execute(f"DELETE FROM {table}")
    # SQL inserts into emptied tables and commits only after all statements succeed.
    execute_block(db, ROOT / "data/generated/standard/40_load_data.sql")
    sql_insert = verify(db, data)
    execute_block(db, ROOT / "data/generated/standard/40_load_data.sql")
    assert verify(db, data) == sql_insert
    with db.cursor() as cur:
        for table in reversed(TABLES):
            cur.execute(f"DELETE FROM {table}")
    assert load_python(db, data) == sql_insert
    assert load_python(db, data) == sql_insert


def test_failed_load_rolls_back_prior_updates(db, data):
    bad = copy.deepcopy(data)
    bad["OJ41_DEVICES"][0]["serial_no"] = "ROLLBACK_TEST"
    bad["OJ41_CONTRACTS"][0]["device_id"] = "DOES_NOT_EXIST"
    with pytest.raises(oracledb.IntegrityError):
        load_python(db, bad)
    verify(db, data)


def test_no_case_sees_no_rows(db):
    with db.cursor() as cur:
        cur.execute("BEGIN OJ41_CASE_CTX.clear_case; END;")
        for view in ("OJ41_VISIBLE_KNOWLEDGE", "OJ41_VISIBLE_CHUNKS", "OJ41_VISIBLE_DEVICES", "OJ41_VISIBLE_CONTRACTS"):
            cur.execute(f"SELECT COUNT(*) FROM {view}")
            assert cur.fetchone()[0] == 0
    # No customer identity is bound to the database user.


def test_duplicate_primary_key_is_rejected(db):
    with db.cursor() as cur:
        with pytest.raises(oracledb.IntegrityError):
            cur.execute("INSERT INTO OJ41_DEVICES SELECT * FROM OJ41_DEVICES WHERE device_id='DEV001'")


def test_embedding_retained_then_invalidated_on_text_change(db, data):
    cols = TABLES["OJ41_CHUNKS"]
    row = dict(data["OJ41_CHUNKS"][0])
    sql = merge_sql("OJ41_CHUNKS", [f":{i+1}" for i in range(len(cols))])
    with db.cursor() as cur:
        # Synthetic vector is transaction-local and never committed.
        cur.execute("UPDATE OJ41_CHUNKS SET embedding=:v, embedding_model='TEST_ONLY' WHERE chunk_id=:id",
                    v=array.array("f", [0.1] * 1024), id=row["chunk_id"])
        cur.execute(sql, [row[c] for c in cols])
        cur.execute("SELECT embedding_model FROM OJ41_CHUNKS WHERE chunk_id=:id", id=row["chunk_id"])
        assert cur.fetchone()[0] == "TEST_ONLY"
        row["content_hash"] = "0" * 64
        row["chunk_text"] = "変更された本文"
        cur.execute(sql, [row[c] for c in cols])
        cur.execute("SELECT embedding_model, embedding FROM OJ41_CHUNKS WHERE chunk_id=:id", id=row["chunk_id"])
        assert cur.fetchone() == (None, None)
