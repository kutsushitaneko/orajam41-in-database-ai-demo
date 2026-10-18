"""Live stage-4 checks. --agents additionally runs five support-agent requests."""
import argparse
import json
from pathlib import Path

from webinar_demo.case_context import case_scope

import oracledb

from webinar_demo.business_ai import run_agent
from webinar_demo.check_genai import text
from webinar_demo.load_data import guard
from webinar_demo.nl2sql import CASES,run_case
from webinar_demo.settings import ROOT,db_parameters,load_settings


def tool_checks(conn):
    guard(conn)
    results=[]
    with conn.cursor() as cur:
        for i in range(1,10):
            device=f"DEV{i:03}"
            if i==9:
                try:
                    cur.execute("BEGIN OJ41_AGENT_CTX.start_run(:d,'管理画面が開かない','direct-test'); END;",d=device)
                    raise AssertionError("Foreign device should be rejected at entry")
                except oracledb.Error as exc:
                    assert exc.args[0].code == 20053
                results.append(dict(device=device, rejected_before_agent=True))
                continue
            cur.execute("BEGIN OJ41_AGENT_CTX.start_run(:d,'管理画面が開かない','direct-test'); END;",d=device)
            cur.execute("SELECT OJ41_CONTRACT_TOOL(:d) FROM dual",d=device)
            result=json.loads(text(cur.fetchone()[0]))
            assert result["onsite_eligible"]==("Y" if i in (1,5,6,8) else "N")
            results.append(dict(device=device,contract=result))
        cur.execute("BEGIN OJ41_AGENT_CTX.start_run('DEV001','画面が停止','limit-test'); END;")
        try:
            cur.execute("SELECT OJ41_CONTRACT_TOOL('DEV009') FROM dual")
            raise AssertionError("Device substitution was not rejected")
        except oracledb.Error as exc: assert exc.args[0].code==20052
        cur.execute("BEGIN OJ41_AGENT_CTX.start_run('DEV001','画面が停止','limit-test'); END;")
        for _ in range(4):
            cur.execute("SELECT OJ41_CONTRACT_TOOL('DEV001') FROM dual")
            cur.fetchone()
        try:
            cur.execute("SELECT OJ41_CONTRACT_TOOL('DEV001') FROM dual")
            raise AssertionError("Call limit was not enforced")
        except oracledb.Error as exc: assert exc.args[0].code==20051
    return dict(contracts=results,substitution_rejected=True,call_limit_enforced=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--agents",action="store_true")
    p.add_argument("--agents-only",action="store_true",help="Recheck tools and agents without repeating Select AI calls")
    p.add_argument("--output",type=Path,default=ROOT/"local/stage4-evaluation.json")
    a=p.parse_args()
    values=load_settings()
    report=dict(nl2sql=[],agents=[])
    if a.agents_only and a.output.exists():
        report["nl2sql"]=json.loads(a.output.read_text(encoding="utf-8")).get("nl2sql",[])
    def save():
        a.output.parent.mkdir(exist_ok=True,parents=True)
        a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    with oracledb.connect(**db_parameters(values)) as conn:
        conn.call_timeout=180000
        with case_scope(conn, "SR001"):
            report["tools"]=tool_checks(conn); save()
        print("Direct tools: 9 contract cases, device binding, call limit PASS",flush=True)
        for case in (() if a.agents_only else CASES):
            with case_scope(conn, "SR001"):
                result=run_case(conn,case)
            report["nl2sql"].append(result); save()
            print(f"NL2SQL {case}: PASS {result['rows']}",flush=True)
    if a.agents or a.agents_only:
        for device,question,status,onsite in [
            ("DEV001","管理画面が開かない。確認手順と現地保守の対応案を示して。","answered","Y"),
            ("DEV002","管理画面が開かない。現地保守を利用できる？","answered","N"),
            ("DEV004","管理画面が開かない。現地保守を利用できる？","answered","N"),
            ("DEV009","管理画面が開かない。現地保守を利用できる？","answered","Y"),
            ("DEV001","E999の修理方法と現地保守の対応案を教えて。","insufficient","Y"),
        ]:
            # Fresh DB sessions keep the agent conversation independent for each case.
            with oracledb.connect(**db_parameters(values)) as conn:
                with case_scope(conn, "SR002" if device=="DEV009" else "SR001"):
                    result=run_agent(conn,device,question)
            report["agents"].append(result); save()
            assert result["draft"]["status"]==status,(device,result["draft"])
            assert result["contract"].get("onsite_eligible")==onsite
            assert result["approval_required"] is True
            ids={c["doc_id"] for c in result["draft"]["claims"]}
            assert not ids.intersection({"KB004","KB012" if device=="DEV009" else "KB013","KB014","KB015"})
            evidence={d["doc_id"] for e in result["trace"] if e["tool"]=="knowledge" for d in e["result"]["documents"]}
            if status=="answered": assert {"KB001","KB013" if device=="DEV009" else "KB012"} <= evidence
            print(f"Agent {device}: PASS {status} onsite={onsite} {result['seconds']}s",flush=True)
    report["complete"]=True; save()


if __name__=="__main__":
    try: main()
    except Exception as exc:
        code = getattr(exc.args[0], 'full_code', type(exc).__name__) if exc.args else type(exc).__name__
        print(f"工程4検証停止: {code}。localの実行記録を確認してください。")
        raise SystemExit(1)
