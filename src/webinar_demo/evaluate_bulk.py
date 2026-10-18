"""Live stage-5 checks; only dedicated bulk fixtures are changed."""
import csv
import json
import time

from webinar_demo.bulk import (
    ROOT, db_parameters, embed, execute_block, generate, guard, load,
    load_settings, oracledb, read_manifest, upload, upload_file,
)


def count(cur, dataset, clause="1=1"):
    cur.execute("SELECT COUNT(*) FROM OJ41_BULK_DOCS WHERE dataset_id=:d AND "+clause,d=dataset)
    return cur.fetchone()[0]


def main():
    v=load_settings(); folder=ROOT/"data/generated/bulk"
    m=generate(folder); report={"rows":m["rows"],"csv_bytes":sum(p["bytes"] for p in m["parts"])}
    with oracledb.connect(**db_parameters(v)) as conn:
        guard(conn); conn.call_timeout=600000
        execute_block(conn,ROOT/"sql/bulk/70_create_bulk_tables.sql")
        report["python_first"]=load(conn,folder,stop_after=1)
        report["python_resume"]=load(conn,folder)
        report["python_rerun"]=load(conn,folder)
        assert all(p["status"]=="skipped" for p in report["python_rerun"]["parts"])
        t=time.perf_counter(); uris=upload(v,folder)
        report["upload_or_head_seconds"]=round(time.perf_counter()-t,3)
        report["cloud_first"]=load(conn,folder,"cloud",uris,stop_after=1)
        report["cloud_resume"]=load(conn,folder,"cloud",uris)
        report["cloud_rerun"]=load(conn,folder,"cloud",uris)
        assert all(p["status"]=="skipped" for p in report["cloud_rerun"]["parts"])
        with conn.cursor() as cur:
            assert count(cur,m["dataset_id"])==1000
        # Fresh isolated fixture: no earlier target rows may hide a rejected load.
        badfolder=ROOT/"data/generated/bulk-reject"
        fm=generate(badfolder,17,17)
        with (badfolder/fm["parts"][0]["file"]).open(encoding="utf-8",newline="") as f:
            rows=list(csv.reader(f))
        rows[1][2]="not-a-number"
        bad=badfolder/"invalid-row.csv"
        with bad.open("w",encoding="utf-8",newline="") as f:
            csv.writer(f,lineterminator="\n").writerows(rows)
        baduri=upload_file(v,fm,bad)
        # Reset only this deterministic 17-row failure fixture for repeatable checks.
        with conn.cursor() as cur:
            for table in ("OJ41_BULK_DOCS","OJ41_BULK_PARTS","OJ41_BULK_STAGE"):
                cur.execute(f"DELETE FROM {table} WHERE dataset_id=:d",d=fm["dataset_id"])
            conn.commit()
        try:
            load(conn,badfolder,"cloud",{1:baduri})
            raise AssertionError("Invalid numeric data unexpectedly loaded")
        except oracledb.DatabaseError as exc:
            assert exc.args[0].full_code=="ORA-20003"
            report["rejected_load_code"]=exc.args[0].full_code
        with conn.cursor() as cur:
            assert count(cur,fm["dataset_id"])==0
            cur.execute("SELECT status FROM OJ41_BULK_PARTS WHERE dataset_id=:d",d=fm["dataset_id"])
            assert cur.fetchone()==("FAILED",)
            cur.execute("SELECT id,status,rows_loaded,logfile_table,badfile_table FROM user_load_operations WHERE table_name='OJ41_BULK_STAGE' ORDER BY id DESC FETCH FIRST 1 ROW ONLY")
            report["rejected_operation"]=list(cur.fetchone())
        report["corrected_load"]=load(conn,badfolder,"cloud",upload(v,badfolder))
        with conn.cursor() as cur:
            assert count(cur,fm["dataset_id"])==17
            # The embedding test intentionally resets only the first 32 bulk rows.
            cur.execute("UPDATE OJ41_BULK_DOCS SET embedding=NULL,embedding_model=NULL,embed_state='PENDING',embed_error=NULL WHERE dataset_id=:d AND row_no<=32",d=m["dataset_id"])
            conn.commit()
        try:
            embed(conn,m["dataset_id"],inject_failure=True)
            raise AssertionError("Injected error was not raised")
        except oracledb.DatabaseError as exc:
            assert exc.args[0].full_code=="ORA-01476"
        with conn.cursor() as cur:
            assert count(cur,m["dataset_id"],"embed_state='FAILED' AND embedding IS NULL")==8
            assert count(cur,m["dataset_id"],"embedding IS NOT NULL")==0
        report["embed_first"]=embed(conn,m["dataset_id"],stop_after=1)
        report["embed_resume"]=embed(conn,m["dataset_id"])
        report["embed_rerun"]=embed(conn,m["dataset_id"])
        assert report["embed_rerun"]["batches"]==[]
        with conn.cursor() as cur:
            assert count(cur,m["dataset_id"],"embed_state='DONE' AND embedding IS NOT NULL AND VECTOR_DIMENSION_COUNT(embedding)=1024")==32
            assert count(cur,m["dataset_id"],"embed_state='PENDING'")==968
        report["complete"]=True
    path=ROOT/"local/stage5-evaluation.json";path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2))


if __name__=="__main__":
    main()
