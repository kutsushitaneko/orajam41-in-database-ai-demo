"""Live rollback/resume and SQL-client block checks for the array route."""
import json
from webinar_demo.bulk import *


def main():
    folder=ROOT/'data/generated/bulk-reject';m=generate(folder,17,17)
    report={}
    with oracledb.connect(**db_parameters(load_settings())) as conn:
        guard(conn);conn.call_timeout=600000;load(conn,folder)
        with conn.cursor() as cur:
            cur.execute("UPDATE OJ41_BULK_DOCS SET embedding=NULL,embedding_model=NULL,embed_state='PENDING',embed_error=NULL WHERE dataset_id=:d AND row_no<=16",d=m['dataset_id']);conn.commit()
        try:
            embed(conn,m['dataset_id'],limit=16,method='array',inject_failure=True)
            raise AssertionError('Expected failure')
        except oracledb.DatabaseError as e:
            assert e.args[0].full_code=='ORA-01476'
        with conn.cursor() as cur:
            cur.execute("select count(*) from OJ41_BULK_DOCS where dataset_id=:d and embed_state='FAILED' and embedding is null",d=m['dataset_id'])
            assert cur.fetchone()[0]==8
        report['first']=embed(conn,m['dataset_id'],limit=16,method='array',stop_after=1)
        report['resume']=embed(conn,m['dataset_id'],limit=16,method='array')
        report['rerun']=embed(conn,m['dataset_id'],limit=16,method='array')
        assert report['rerun']['batches']==[]
        with conn.cursor() as cur:
            cur.execute("select row_no,embedding from OJ41_BULK_DOCS where dataset_id=:d and row_no<=8 order by row_no",d=m['dataset_id']);expected=dict(cur.fetchall())
            cur.execute("UPDATE OJ41_BULK_DOCS SET embedding=NULL,embedding_model=NULL,embed_state='PENDING' WHERE dataset_id=:d AND row_no<=8",d=m['dataset_id']);conn.commit()
        sql=(ROOT/'sql/bulk/75_embed_array_batch.sql').read_text(encoding='utf-8').replace('__DATASET__',m['dataset_id'])
        path=ROOT/'local/75_array_validation.sql';path.write_text(sql,encoding='utf-8');execute_block(conn,path)
        with conn.cursor() as cur:
            cur.execute("select row_no,embedding from OJ41_BULK_DOCS where dataset_id=:d and row_no<=8 order by row_no",d=m['dataset_id']);actual=dict(cur.fetchall())
            delta=max(abs(a-b) for k in expected for a,b in zip(expected[k],actual[k]));assert delta<=1e-6
        report['sql_max_abs_difference']=delta;report['complete']=True
    (ROOT/'local/array-resume.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))

if __name__=='__main__': main()
