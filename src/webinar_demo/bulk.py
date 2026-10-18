"""Bounded-memory bulk fixture generation, resumable loading and embeddings."""
import argparse
import csv
import hashlib
import io
import json
import time
from pathlib import Path
from urllib.parse import quote

import oci
import oracledb

from webinar_demo.load_data import execute_block,guard
from webinar_demo.settings import ROOT,db_parameters,load_settings,oci_config

COLS=("dataset_id","part_no","row_no","model","body_text","content_hash")
FORMAT=dict(type="csv with embedded",delimiter=",",quote='"',skipheaders=1,
            characterset="AL32UTF8",rejectlimit=0,blankasnull=False)
MERGE="""MERGE INTO OJ41_BULK_DOCS t USING
(SELECT :1 dataset_id,:2 part_no,:3 row_no,:4 model,:5 body_text,:6 content_hash FROM dual) s
ON (t.dataset_id=s.dataset_id AND t.row_no=s.row_no)
WHEN MATCHED THEN UPDATE SET t.part_no=s.part_no,t.model=s.model,t.body_text=s.body_text,
 t.embedding=CASE WHEN t.content_hash=s.content_hash THEN t.embedding ELSE NULL END,
 t.embedding_model=CASE WHEN t.content_hash=s.content_hash THEN t.embedding_model ELSE NULL END,
 t.embed_state=CASE WHEN t.content_hash=s.content_hash THEN t.embed_state ELSE 'PENDING' END,
 t.embed_error=CASE WHEN t.content_hash=s.content_hash THEN t.embed_error ELSE NULL END,
 t.content_hash=s.content_hash
WHEN NOT MATCHED THEN INSERT(dataset_id,part_no,row_no,model,body_text,content_hash)
VALUES(s.dataset_id,s.part_no,s.row_no,s.model,s.body_text,s.content_hash)"""


def sha(data): return hashlib.sha256(data).hexdigest()


def generate(folder:Path,rows=1000,part_size=250):
    if rows<1 or part_size<1 or part_size>10000: raise ValueError("rows>0、part-sizeは1〜10000です。")
    seed_bytes=(ROOT/"data/seed/knowledge.json").read_bytes()
    docs=json.loads(seed_bytes)
    # Byte-independent seed hash allows LF/CRLF checkout differences in the source JSON.
    seed_hash=sha(json.dumps(docs,ensure_ascii=False,sort_keys=True).encode())
    dataset=sha(f"bulk-v1:{rows}:{part_size}:{seed_hash}".encode())[:24]
    folder.mkdir(parents=True,exist_ok=True)
    manifest=dict(version="bulk-v1",dataset_id=dataset,rows=rows,part_size=part_size,parts=[],fictional=True)
    for first in range(1,rows+1,part_size):
        part=(first-1)//part_size+1
        buf=io.StringIO(newline="")
        writer=csv.writer(buf,lineterminator="\n")
        writer.writerow(COLS)
        last=min(rows,first+part_size-1)
        for i in range(first,last+1):
            d=docs[(i-1)%len(docs)]
            body=f"架空のロード試験 {i:08}\n{d['title']}\n{d['body']}"
            writer.writerow((dataset,part,i,d['model'],body,sha(body.encode())))
        name=f"part-{part:05}.csv"
        content=buf.getvalue().encode()
        (folder/name).write_bytes(content)
        manifest["parts"].append(dict(number=part,file=name,first=first,last=last,rows=last-first+1,sha256=sha(content),bytes=len(content)))
    (folder/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    return manifest


def read_manifest(folder):
    m=json.loads((folder/"manifest.json").read_text(encoding="utf-8"))
    if m["version"]!="bulk-v1" or m["rows"]<1 or not m["parts"]:
        raise ValueError("manifestの形式が不正です。")
    expected_first=1
    for number,p in enumerate(m["parts"],1):
        if p["number"]!=number or p["first"]!=expected_first or p["file"]!=f"part-{number:05}.csv" or p["rows"]!=p["last"]-p["first"]+1 or not 1<=p["rows"]<=10000:
            raise ValueError("分割ファイルの定義が不正です。")
        content=(folder/p["file"]).read_bytes()
        if sha(content)!=p["sha256"]: raise ValueError("ファイルハッシュ不一致です。")
        expected_first=p["last"]+1
    if expected_first-1!=m["rows"]: raise ValueError("manifest件数不一致です。")
    return m


def read_part(folder,m,p):
    with (folder/p["file"]).open(encoding="utf-8",newline="") as f:
        reader=csv.DictReader(f)
        if reader.fieldnames!=list(COLS): raise ValueError("CSV列が不一致です。")
        rows=[]
        for r in reader:
            values=(r["dataset_id"],int(r["part_no"]),int(r["row_no"]),r["model"],r["body_text"],r["content_hash"])
            if values[0]!=m["dataset_id"] or values[1]!=p["number"] or sha(values[4].encode())!=values[5]:
                raise ValueError("CSVの識別子または本文ハッシュ不一致です。")
            rows.append(values)
    if [r[2] for r in rows]!=list(range(p["first"],p["last"]+1)): raise ValueError("行番号が不一致です。")
    return rows


def mark(cur,m,p,route,status,count=0,op=None,error=None):
    cur.execute("""MERGE INTO OJ41_BULK_PARTS t USING
      (SELECT :d dataset_id,:r route,:p part_no FROM dual) s
      ON (t.dataset_id=s.dataset_id AND t.route=s.route AND t.part_no=s.part_no)
      WHEN MATCHED THEN UPDATE SET file_hash=:h,status=:st,loaded_rows=:n,operation_id=:op,error_code=:e,updated_at=SYSTIMESTAMP
      WHEN NOT MATCHED THEN INSERT(dataset_id,route,part_no,file_hash,status,loaded_rows,operation_id,error_code)
      VALUES(:d,:r,:p,:h,:st,:n,:op,:e)""",d=m["dataset_id"],r=route,p=p["number"],h=p["sha256"],st=status,n=count,op=op,e=error)


def compare(cur,table,m,p,expected):
    if table not in {"OJ41_BULK_DOCS","OJ41_BULK_STAGE"}: raise ValueError("Unknown table")
    cur.execute(f"SELECT {','.join(COLS)} FROM {table} WHERE dataset_id=:d AND part_no=:p ORDER BY row_no",d=m["dataset_id"],p=p["number"])
    if cur.fetchall()!=expected: raise ValueError(f"投入内容が不一致: {table} part {p['number']}")


def load(conn,folder,route="python",uris=None,stop_after=None):
    guard(conn)
    m=read_manifest(folder)
    records=[]
    start=time.perf_counter()
    with conn.cursor() as cur:
        for p in m["parts"]:
            rows=read_part(folder,m,p)
            cur.execute("SELECT file_hash,status FROM OJ41_BULK_PARTS WHERE dataset_id=:d AND route=:r AND part_no=:p",d=m["dataset_id"],r=route,p=p["number"])
            done=cur.fetchone()
            if done and done[0]!=p["sha256"]: raise ValueError("完了記録とファイルハッシュが異なります。")
            if done and done[1]=="DONE":
                compare(cur,"OJ41_BULK_DOCS",m,p,rows)
                records.append(dict(part=p["number"],status="skipped")); continue
            op=None
            t=time.perf_counter()
            try:
                if route=="cloud":
                    cur.execute("DELETE FROM OJ41_BULK_STAGE WHERE dataset_id=:d AND part_no=:p",d=m["dataset_id"],p=p["number"])
                    conn.commit()  # COPY_DATA is an independent load; staging is disposable.
                    operation=cur.var(oracledb.DB_TYPE_NUMBER)
                    cur.execute("BEGIN DBMS_CLOUD.COPY_DATA(table_name=>'OJ41_BULK_STAGE',credential_name=>'OCI$RESOURCE_PRINCIPAL',file_uri_list=>:u,format=>:f,operation_id=>:op); END;",u=uris[p["number"]],f=json.dumps(FORMAT),op=operation)
                    op=int(operation.getvalue())
                    compare(cur,"OJ41_BULK_STAGE",m,p,rows)
                elif route!="python": raise ValueError("Unknown load route")
                # Both routes promote only validated rows, in one shard transaction.
                if route=="cloud":
                    source="SELECT "+",".join(COLS)+" FROM OJ41_BULK_STAGE WHERE dataset_id=:d AND part_no=:p"
                    select=MERGE[MERGE.index("SELECT"):MERGE.index(") s")]
                    cur.execute(MERGE.replace(select,source),d=m["dataset_id"],p=p["number"])
                else:
                    cur.executemany(MERGE,rows)
                compare(cur,"OJ41_BULK_DOCS",m,p,rows)
                mark(cur,m,p,route,"DONE",len(rows),op)
                conn.commit()
                records.append(dict(part=p["number"],status="loaded",rows=len(rows),operation_id=op,seconds=round(time.perf_counter()-t,3)))
            except Exception as exc:
                conn.rollback()
                code=getattr(exc.args[0],"full_code",type(exc).__name__) if exc.args else type(exc).__name__
                mark(cur,m,p,route,"FAILED",op=op,error=code)
                conn.commit()
                raise
            if stop_after and sum(r["status"]=="loaded" for r in records)>=stop_after: break
    return dict(route=route,parts=records,seconds=round(time.perf_counter()-start,3))


def storage(values):
    region=values.get("OCI_BULK_REGION") or values["OCI_MODEL_REGION"]
    bucket=values.get("OCI_BULK_BUCKET") or values["OCI_MODEL_BUCKET"]
    config=oci_config(values); config["region"]=region
    return oci.object_storage.ObjectStorageClient(config),values["OCI_OBJECT_STORAGE_NAMESPACE"],bucket,region


def upload_file(values,m,path):
    client,namespace,bucket,region=storage(values)
    payload=path.read_bytes(); digest=sha(payload)
    # Hash-addressed names plus conditional creation prevent overwriting existing objects.
    name=f"orajam41-bulk/{m['dataset_id']}/{digest}/{path.name}"
    try:
        head=client.head_object(namespace,bucket,name)
        if head.headers.get("opc-meta-sha256")!=digest: raise ValueError("既存Objectのハッシュが一致しません。")
    except oci.exceptions.ServiceError as exc:
        if exc.status!=404: raise
        client.put_object(namespace,bucket,name,payload,if_none_match="*",opc_meta={"sha256":digest},content_type="text/csv; charset=utf-8")
    return f"https://objectstorage.{region}.oraclecloud.com/n/{namespace}/b/{bucket}/o/{quote(name,safe='/')}"


def upload(values,folder):
    m=read_manifest(folder)
    return {p["number"]:upload_file(values,m,folder/p["file"]) for p in m["parts"]}


def render_sql(folder,uris):
    m=read_manifest(folder)
    sql=(ROOT/"sql/bulk/71_copy_one_part.sql").read_text(encoding="utf-8")
    for key,value in {"__DATASET__":m["dataset_id"],"__URI__":uris[1],
                      "__FORMAT__":json.dumps(FORMAT),"__ROWS__":str(m["parts"][0]["rows"])}.items():
        sql=sql.replace(key,value.replace("'","''"))
    path=ROOT/"local/71_copy_one_part.sql"; path.parent.mkdir(exist_ok=True)
    path.write_text(sql,encoding="utf-8")
    embed_sql=(ROOT/"sql/bulk/72_embed_one_batch.sql").read_text(encoding="utf-8")
    (ROOT/"local/72_embed_one_batch.sql").write_text(embed_sql.replace("__DATASET__",m["dataset_id"].replace("'","''")),encoding="utf-8")
    array_sql=(ROOT/"sql/bulk/75_embed_array_batch.sql").read_text(encoding="utf-8")
    (ROOT/"local/75_embed_array_batch.sql").write_text(array_sql.replace("__DATASET__",m["dataset_id"].replace("'","''")),encoding="utf-8")
    return path


def embed(conn,dataset,limit=32,batch_size=8,stop_after=None,inject_failure=False,method="scalar"):
    guard(conn)
    if limit<1 or not 1<=batch_size<=256: raise ValueError("limit>0、batch-sizeは1〜256です。")
    if method not in {"scalar","array"}: raise ValueError("Unknown embedding method")
    started=time.perf_counter(); records=[]
    with conn.cursor() as cur:
        while True:
            cur.execute("SELECT row_no FROM OJ41_BULK_DOCS WHERE dataset_id=:d AND row_no<=:lim AND (embed_state<>'DONE' OR embedding IS NULL OR embedding_model IS NULL OR embedding_model<>'MULTILINGUAL_E5_LARGE') ORDER BY row_no FETCH FIRST :b ROWS ONLY",d=dataset,lim=limit,b=batch_size)
            ids=[r[0] for r in cur]
            if not ids: break
            binds={f"i{i}":n for i,n in enumerate(ids)}
            predicate="dataset_id=:d AND row_no IN ("+",".join(":"+k for k in binds)+")"
            binds["d"]=dataset
            t=time.perf_counter()
            try:
                if method=="array":
                    from webinar_demo.array_embeddings import array_vectors
                    cur.execute("SELECT row_no,'passage: '||body_text FROM OJ41_BULK_DOCS WHERE "+predicate+" ORDER BY row_no",binds)
                    rows=cur.fetchall()
                    vectors=array_vectors(cur,rows)
                    cur.executemany("UPDATE OJ41_BULK_DOCS SET embedding=:v,embedding_model='MULTILINGUAL_E5_LARGE',embed_state='DONE',embed_error=NULL WHERE dataset_id=:d AND row_no=:i",
                                    [dict(v=vectors[i],d=dataset,i=i) for i in ids])
                else:
                    cur.execute("UPDATE OJ41_BULK_DOCS SET embedding=VECTOR_EMBEDDING(MULTILINGUAL_E5_LARGE USING 'passage: ' || body_text AS data),embedding_model='MULTILINGUAL_E5_LARGE',embed_state='DONE',embed_error=NULL WHERE "+predicate,binds)
                if inject_failure: cur.execute("SELECT 1/0 FROM dual"); cur.fetchone()
                conn.commit()
            except (oracledb.Error,ValueError) as exc:
                conn.rollback()
                cur.execute("UPDATE OJ41_BULK_DOCS SET embed_state='FAILED',embed_error=:err WHERE "+predicate,dict(binds,err=getattr(exc.args[0],"full_code",type(exc).__name__)))
                conn.commit()
                raise
            records.append(dict(first=ids[0],last=ids[-1],rows=len(ids),seconds=round(time.perf_counter()-t,3)))
            if stop_after and len(records)>=stop_after: break
    return dict(method=method,batches=records,seconds=round(time.perf_counter()-started,3))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--folder",type=Path,default=ROOT/"data/generated/bulk")
    p.add_argument("--generate",action="store_true")
    p.add_argument("--rows",type=int,default=1000)
    p.add_argument("--part-size",type=int,default=250)
    p.add_argument("--setup",action="store_true")
    p.add_argument("--render-sql",action="store_true")
    p.add_argument("--route",choices=("python","cloud"))
    p.add_argument("--embed",action="store_true")
    p.add_argument("--embedding-method",choices=("scalar","array"),default="scalar")
    p.add_argument("--limit",type=int,default=32)
    p.add_argument("--batch-size",type=int,default=8)
    p.add_argument("--stop-after",type=int)
    a=p.parse_args()
    if a.generate:
        m=generate(a.folder,a.rows,a.part_size)
        print(f"生成: {m['rows']} rows / {len(m['parts'])} files")
    if not (a.setup or a.route or a.embed or a.render_sql): return
    v=load_settings(); m=read_manifest(a.folder)
    uris=upload(v,a.folder) if a.route=="cloud" or a.render_sql else None
    if a.render_sql:
        render_sql(a.folder,uris)
        print("SQL: local/71_copy_one_part.sql, local/72_embed_one_batch.sql, local/75_embed_array_batch.sql")
    if not (a.setup or a.route or a.embed): return
    with oracledb.connect(**db_parameters(v)) as conn:
        guard(conn); conn.call_timeout=600000
        if a.setup: execute_block(conn,ROOT/"sql/bulk/70_create_bulk_tables.sql")
        if a.route: print(json.dumps(load(conn,a.folder,a.route,uris,a.stop_after),indent=2))
        if a.embed: print(json.dumps(embed(conn,m["dataset_id"],a.limit,a.batch_size,a.stop_after,method=a.embedding_method),indent=2))


if __name__=="__main__":
    try: main()
    except Exception as exc:
        code=getattr(exc.args[0],"full_code",None) if exc.args else None
        print(f"Bulk処理停止: {code or type(exc).__name__}（接続情報は非表示）")
        raise SystemExit(1)
