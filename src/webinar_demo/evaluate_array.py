"""Measure array-call sizes without changing stored vectors (single worker)."""
import json
import time
from webinar_demo.bulk import ROOT, guard, load_settings, db_parameters, oracledb, read_manifest
from webinar_demo.array_embeddings import array_vectors


def main():
    path=ROOT/'local/array-evaluation.json'
    report={'counts':[], 'comparison':[], 'complete':False, 'timeout_ms':600000}
    m=read_manifest(ROOT/'data/generated/bulk')
    with oracledb.connect(**db_parameters(load_settings())) as conn:
        guard(conn);conn.call_timeout=600000
        report['db_version']=conn.version
        report['model']='MULTILINGUAL_E5_LARGE'
        report['provider']='database'
        with conn.cursor() as cur:
            cur.execute("select row_no,'passage: '||body_text from OJ41_BULK_DOCS where dataset_id=:d order by row_no fetch first 256 rows only",d=m['dataset_id'])
            rows=cur.fetchall();assert len(rows)==256
            report['input_chars']=[min(len(r[1]) for r in rows),max(len(r[1]) for r in rows)]
            report['input_utf8_bytes']=[min(len(r[1].encode()) for r in rows),max(len(r[1].encode()) for r in rows)]
            # Warm up both paths outside the measured comparison.
            array_vectors(cur,rows[:1])
            cur.execute('select vector_embedding(MULTILINGUAL_E5_LARGE using :t as data) from dual',t=rows[0][1]);cur.fetchone()
            for n in [1,8,32,64,128,256]:
                start=time.perf_counter()
                try:
                    vectors=array_vectors(cur,rows[:n])
                    item=dict(n=n,seconds=round(time.perf_counter()-start,3),outputs=len(vectors),status='success')
                except Exception as e:
                    item=dict(n=n,seconds=round(time.perf_counter()-start,3),status='failed',error=getattr(e.args[0],'full_code',type(e).__name__))
                report['counts'].append(item);path.write_text(json.dumps(report,indent=2),encoding='utf-8');print(item,flush=True)
                if item['status']!='success': break
            # Identical first 32 texts; alternate order to reduce ordering bias.
            for trial in range(3):
                results={};times={}
                for method in (['scalar','array'] if trial%2==0 else ['array','scalar']):
                    start=time.perf_counter()
                    if method=='array': results[method]=array_vectors(cur,rows[:32])
                    else:
                        cur.execute("select row_no,vector_embedding(MULTILINGUAL_E5_LARGE using 'passage: '||body_text as data) from OJ41_BULK_DOCS where dataset_id=:d and row_no<=32 order by row_no",d=m['dataset_id'])
                        results[method]=dict(cur.fetchall())
                    times[method]=round(time.perf_counter()-start,3)
                delta=max(abs(a-b) for k in results['scalar'] for a,b in zip(results['scalar'][k],results['array'][k]))
                assert delta<=1e-6
                item=dict(trial=trial+1,seconds=times,max_abs_difference=delta)
                report['comparison'].append(item);path.write_text(json.dumps(report,indent=2),encoding='utf-8');print(item,flush=True)
    report['complete']=True;path.write_text(json.dumps(report,indent=2),encoding='utf-8')

if __name__=='__main__': main()
