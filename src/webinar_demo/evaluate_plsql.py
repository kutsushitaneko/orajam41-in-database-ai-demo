"""Verify PL/SQL RAG, output guards, and checked Agent on the prepared demo DB."""
import argparse
import json,time
from pathlib import Path
import oracledb
from webinar_demo.check_genai import connect,text
from webinar_demo.settings import load_settings
from webinar_demo.load_data import execute_block

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument("--setup",action="store_true",help="Install only SQL packages 65-68 and 80-81 before checking")
args=parser.parse_args()
results=[]
with connect(load_settings()) as conn,conn.cursor() as cur:
    for name in ('65_answer_guard.sql','66_answer_guard_body.sql','67_rag.sql','68_rag_body.sql','80_checked_agent.sql','81_checked_agent_body.sql'):
        if args.setup: execute_block(conn,Path('sql/setup')/name)
    cur.execute("SELECT name,line,text FROM user_errors WHERE name IN ('OJ41_ANSWER_GUARD','OJ41_RAG','OJ41_CHECKED_AGENT') ORDER BY name,sequence")
    errors=cur.fetchall()
    if errors: print(errors); raise SystemExit(1)
    def run(name,block,params,expected,error=False):
        start=time.perf_counter(); out=cur.var(oracledb.DB_TYPE_CLOB)
        try:
            cur.execute(block,out=out,**params)
            value=json.loads(text(out.getvalue()))
            passed=not error and expected(value)
            row=dict(name=name,passed=passed,result=value)
        except oracledb.Error as exc:
            row=dict(name=name,passed=error and exc.args[0].full_code in ('ORA-20071','ORA-20072','ORA-40441','ORA-20053'),error=exc.args[0].full_code)
        cur.execute('SELECT OJ41_CASE_CTX.current_case() FROM dual')
        row['cleared']=cur.fetchone()[0] is None
        row['seconds']=round(time.perf_counter()-start,2);results.append(row)
        print(json.dumps({k:v for k,v in row.items() if k!='result'},ensure_ascii=False),flush=True)
        Path('local/plsql-demo-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    for repeat in range(2):
        for name,question,status,calls in (
            ('normal','DEV001の管理画面が開かない。最初に何を確認する？','answered',1),
            ('unknown-code','AX-100のE999の修理方法は？','insufficient',0),
            ('price','AX-100の保証延長料金を日本円で教えて。','insufficient',1),
            ('other-customer','DEV009の管理画面が開かない。','insufficient',0),
            ('two-codes','AX-100のE101とE999を教えて。','insufficient',0),
            ('customer-id','C002のAX-100の確認手順','insufficient',0),
        ):
            run(f'rag-{name}-{repeat}',"BEGIN :out:=OJ41_RAG.answer_question('SR001',:q); END;",dict(q=question),lambda r:r['status']==status and r['llm_calls']==calls)
    for q in ('DEV001とDEV002を確認','DEV001 BX-200の確認',' ','x'*801):
        run('rag-invalid-input',"BEGIN :out:=OJ41_RAG.answer_question('SR001',:q); END;",dict(q=q),None,True)
    docs=json.dumps([dict(doc_id='KB001',text='電源ランプとLANケーブルを確認します。')],ensure_ascii=False)
    for answer in ('not json','{"status":"answered","claims":[]}',json.dumps(dict(status='answered',claims=[dict(text='再起動',doc_id='KB013',quote='直ちに装置を再起動してください。')]),ensure_ascii=False)):
        run('guard-reject',"BEGIN :out:=OJ41_ANSWER_GUARD.validate_json(:a,:d); END;",dict(a=answer,d=docs),None,True)
    for device,case,question,eligible in (
        ('DEV001','SR001','管理画面が開かない。確認手順と現地保守の対応案を示して。','Y'),
        ('DEV002','SR001','管理画面が開かない。現地保守を利用できる？','N'),
        ('DEV004','SR001','管理画面が開かない。現地保守を利用できる？','N'),
        ('DEV009','SR002','管理画面が開かない。現地保守を利用できる？','Y'),
        ('DEV001','SR001','AX-100のE999の修理方法は？','Y'),
    ):
        run('agent-'+device+'-'+question,"BEGIN :out:=OJ41_CHECKED_AGENT.run(:c,:d,:q); END;",dict(c=case,d=device,q=question),lambda r:r['contract']['onsite_eligible']==eligible and r['approval_required'])
assert all(r['passed'] and r['cleared'] for r in results)
