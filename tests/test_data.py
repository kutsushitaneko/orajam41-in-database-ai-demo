import json

import pytest

from webinar_demo.generate_data import generate, write_data, literal, evaluation_cases
from webinar_demo.load_data import read_dataset


def test_byte_reproducibility_and_csv_roundtrip(tmp_path):
    left, right = tmp_path / "left", tmp_path / "right"
    write_data(left)
    write_data(right)
    for p in left.iterdir():
        assert p.read_bytes() == (right / p.name).read_bytes()
    _, loaded = read_dataset(left)
    assert loaded == generate()
    special = loaded["OJ41_KNOWLEDGE"][-1]["body"]
    assert "owner's_log" in special and "\n" in special and '"警告"' in special and "温度,電源" in special


def test_references_and_hashes():
    from webinar_demo.generate_data import digest
    data = generate()
    docs = {r["doc_id"]: r for r in data["OJ41_KNOWLEDGE"]}
    devices = {r["device_id"] for r in data["OJ41_DEVICES"]}
    assert len(docs) == 16 and len(devices) == 12
    assert len({r["contract_id"] for r in data["OJ41_CONTRACTS"]}) == 12
    assert all(r["device_id"] in devices for r in data["OJ41_CONTRACTS"])
    for chunk in data["OJ41_CHUNKS"]:
        assert chunk["doc_id"] in docs
        assert chunk["content_hash"] == digest(chunk["chunk_text"].encode())


@pytest.mark.parametrize("as_of", ["2026-10-15", "2028-02-29", "2027-01-01"])
def test_contract_boundary_expectations(as_of):
    data = generate(as_of)
    contracts = {r["device_id"]: r for r in data["OJ41_CONTRACTS"]}
    for case in evaluation_cases():
        if case["kind"] == "contract":
            c = contracts[case["device_id"]]
            eligible = c["status"] == "ACTIVE" and c["service_scope"] == "ONSITE" and c["start_date"] <= as_of <= c["end_date"]
            assert eligible == case["expected_onsite"], case["id"]


def test_seed_changes_serials_without_changing_business_cases():
    a, b = generate(seed=41), generate(seed=42)
    assert a["OJ41_DEVICES"] != b["OJ41_DEVICES"]
    assert a["OJ41_CONTRACTS"] == b["OJ41_CONTRACTS"]
    assert a["OJ41_KNOWLEDGE"] == b["OJ41_KNOWLEDGE"]


def test_modified_csv_is_rejected(tmp_path):
    write_data(tmp_path)
    with (tmp_path / "oj41_devices.csv").open("a", encoding="utf-8") as f:
        f.write("broken\n")
    with pytest.raises(ValueError, match="ハッシュ不一致"):
        read_dataset(tmp_path)


def test_sql_literal_preserves_special_characters():
    assert literal("owner's\nA&B", "body") == "'owner''s' || CHR(10) || 'A' || CHR(38) || 'B'"
    assert literal(None, "customer_id") == "NULL"
    assert literal("2026-10-15", "as_of_date") == "TO_DATE('2026-10-15', 'YYYY-MM-DD')"


def test_missing_manifest_files_rejected(tmp_path):
    write_data(tmp_path)
    path = tmp_path / "manifest.json"
    m = json.loads(path.read_text(encoding="utf-8"))
    del m["files"]["oj41_devices.csv"]
    path.write_text(json.dumps(m), encoding="utf-8")
    with pytest.raises(ValueError, match="一覧"):
        read_dataset(tmp_path)
