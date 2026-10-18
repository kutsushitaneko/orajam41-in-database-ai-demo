"""Archive then reset only the named tutorial assets; the DB user is retained."""
import argparse
import array
from datetime import date, datetime, timezone
import json
import time

import oracledb

from webinar_demo.load_data import guard
from webinar_demo.settings import ROOT, db_parameters, load_settings

TABLES = ('OJ41_BULK_STAGE', 'OJ41_BULK_DOCS', 'OJ41_BULK_PARTS',
          'OJ41_CHUNKS', 'OJ41_CONTRACTS', 'OJ41_DEVICES', 'OJ41_KNOWLEDGE',
          'OJ41_SUPPORT_CASES', 'OJ41_CUSTOMERS', 'OJ41_RUN')
OBJECTS = [('VIEW', n) for n in ('OJ41_VISIBLE_CHUNKS', 'OJ41_VISIBLE_CONTRACTS',
           'OJ41_VISIBLE_DEVICES', 'OJ41_VISIBLE_KNOWLEDGE', 'ORAJAM41_ENV_PROBE')]
OBJECTS += [('FUNCTION', n) for n in ('OJ41_CONTRACT_TOOL', 'OJ41_KNOWLEDGE_TOOL', 'ORAJAM41_PROBE_STATUS')]
OBJECTS += [('PACKAGE', 'OJ41_AGENT_CTX'), ('PACKAGE', 'OJ41_CASE_CTX')] + [('TABLE', n) for n in TABLES]
AI = {
    'TEAM': ('USER_AI_AGENT_TEAMS', 'AGENT_TEAM_NAME', ('OJ41_SUPPORT_TEAM', 'ORAJAM41_SMOKE_TEAM')),
    'TASK': ('USER_AI_AGENT_TASKS', 'TASK_NAME', ('OJ41_SUPPORT_TASK', 'ORAJAM41_SMOKE_TASK')),
    'AGENT': ('USER_AI_AGENTS', 'AGENT_NAME', ('OJ41_SUPPORT_AGENT', 'ORAJAM41_SMOKE_AGENT')),
    'TOOL': ('USER_AI_AGENT_TOOLS', 'TOOL_NAME', ('OJ41_LOOKUP_CONTRACT', 'OJ41_SEARCH_KNOWLEDGE', 'ORAJAM41_SMOKE_TOOL')),
    'PROFILE': ('USER_CLOUD_AI_PROFILES', 'PROFILE_NAME', ('OJ41_BUSINESS_AI', 'ORAJAM41_GENAI_SMOKE', 'OJ41_NL2SQL_BASELINE', 'OJ41_NL2SQL_TUNED')),
}
MODEL = 'MULTILINGUAL_E5_LARGE'


def sql_template():
    statements = []
    for kind, (view, column, names) in AI.items():
        package = 'DBMS_CLOUD_AI' if kind == 'PROFILE' else 'DBMS_CLOUD_AI_AGENT'
        for name in names:
            statements.append(f"  SELECT COUNT(*) INTO n FROM {view} WHERE {column}='{name}';\n"
                f"  IF n > 0 THEN {package}.DROP_{kind}({kind.lower()}_name=>'{name}'); END IF;")
    for kind, name in OBJECTS:
        # No CASCADE CONSTRAINTS: unexpected external references must stop deletion.
        suffix = ' PURGE' if kind == 'TABLE' else ''
        statements.append(f"  SELECT COUNT(*) INTO n FROM user_objects WHERE object_type='{kind}' AND object_name='{name}';\n"
            f"  IF n > 0 THEN EXECUTE IMMEDIATE 'DROP {kind} {name}{suffix}'; END IF;")
    return """-- Destructive: back up the named demo assets before execution.
-- ORAJAM41USER on arakawalab only. Never drop the DB user or system-managed tables.
-- Change l_confirm only after reviewing scope. l_drop_model controls ONNX deletion.
DECLARE
  l_confirm VARCHAR2(80) := 'NOT_CONFIRMED';
  l_drop_model BOOLEAN := FALSE;
  n PLS_INTEGER;
  db_name VARCHAR2(128) := LOWER(SYS_CONTEXT('USERENV','DB_NAME'));
BEGIN
  IF l_confirm <> 'RESET_ORAJAM41_DEMO'
     OR SYS_CONTEXT('USERENV','SESSION_USER') <> 'ORAJAM41USER'
     OR SYS_CONTEXT('USERENV','CURRENT_SCHEMA') <> 'ORAJAM41USER'
     OR NOT (db_name='arakawalab' OR db_name LIKE '%\\_arakawalab' ESCAPE '\\') THEN
    RAISE_APPLICATION_ERROR(-20041, 'Explicit confirmation and expected database/schema required');
  END IF;
  DBMS_CLOUD_AI_AGENT.CLEAR_TEAM;
""" + '\n'.join(statements) + """
  IF l_drop_model THEN
    SELECT COUNT(*) INTO n FROM user_mining_models WHERE model_name='MULTILINGUAL_E5_LARGE';
    IF n > 0 THEN DBMS_VECTOR.DROP_ONNX_MODEL(model_name=>'MULTILINGUAL_E5_LARGE'); END IF;
  END IF;
END;
/
"""


def encode(value):
    if hasattr(value, 'read'): return value.read()
    if isinstance(value, array.array): return value.tolist()
    if isinstance(value, (datetime, date)): return value.isoformat()
    if isinstance(value, bytes): return value.hex()
    raise TypeError(type(value).__name__)


def save_query(cur, target, sql, **params):
    cur.execute(sql, params)
    data = dict(columns=[d[0] for d in cur.description], rows=cur.fetchall())
    # Resolve LOBs while the connection and cursor are still available.
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=encode), encoding='utf-8')
    return len(data['rows'])


def snapshot(conn, values, target):
    target.mkdir(parents=True, exist_ok=False)
    counts = {}
    with conn.cursor() as cur:
        save_query(cur, target/'objects.json', 'SELECT object_type,object_name,status FROM user_objects ORDER BY object_type,object_name')
        save_query(cur, target/'source.json', "SELECT name,type,line,text FROM user_source WHERE name IN ('OJ41_CASE_CTX','OJ41_AGENT_CTX','OJ41_CONTRACT_TOOL','OJ41_KNOWLEDGE_TOOL','ORAJAM41_PROBE_STATUS') ORDER BY name,type,line")
        for name in TABLES:
            cur.execute('SELECT COUNT(*) FROM user_tables WHERE table_name=:n', n=name)
            if cur.fetchone()[0]: counts[name] = save_query(cur, target/(name+'.json'), f'SELECT * FROM {name}')
        for _, (view, column, names) in AI.items():
            permitted = ','.join("'"+n+"'" for n in names)
            save_query(cur, target/(view+'.json'), f'SELECT * FROM {view} WHERE {column} IN ({permitted})')
        save_query(cur, target/'tool-history.json', "SELECT * FROM USER_AI_AGENT_TOOL_HISTORY WHERE task_name IN ('OJ41_SUPPORT_TASK','ORAJAM41_SMOKE_TASK')")
        # Verify all external-initializer files via the SAME RP used for model loading.
        prefix = values['OCI_MODEL_ONNX_URI'].rsplit('/', 1)[0] + '/'
        cur.execute("SELECT object_name,bytes FROM TABLE(DBMS_CLOUD.LIST_OBJECTS('OCI$RESOURCE_PRINCIPAL',:uri))", uri=prefix)
        objects = cur.fetchall()
        expected = {'multilingual_e5_large.onnx', 'multilingual_e5_large_0.data',
                    'multilingual_e5_large_1.data', 'multilingual_e5_large_external_data.json',
                    'multilingual_e5_large_largeTensor_0.data'}
        found = {n.rsplit('/',1)[-1] for n,size in objects if size > 0}
        if not expected <= found: raise ValueError('Required model source files are missing; reset stopped')
        (target/'model-source-files.json').write_text(json.dumps(objects, indent=2), encoding='utf-8')
    (target/'manifest.json').write_text(json.dumps(dict(complete=True, table_counts=counts, model_files_verified=True),indent=2),encoding='utf-8')
    print('Archive complete; model source files verified; table counts:', counts, flush=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--render', action='store_true', help='Only write the guarded SQL template')
    p.add_argument('--apply', action='store_true', help='Archive and delete the explicitly named demo assets')
    p.add_argument('--include-model', action='store_true', help='Also delete the imported ONNX model')
    a = p.parse_args()
    template = sql_template()
    if a.render:
        path = ROOT/'sql/cleanup/90_reset_demo.sql'
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(template, encoding='utf-8')
        print('Rendered guarded cleanup SQL'); return
    values = load_settings()
    target = ROOT/'local'/('rebuild-backup-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    with oracledb.connect(**db_parameters(values)) as conn:
        conn.call_timeout = 1200000
        guard(conn)
        snapshot(conn, values, target)
        if not a.apply: return
        statement = template.replace("'NOT_CONFIRMED'", "'RESET_ORAJAM41_DEMO'")
        if a.include_model: statement = statement.replace('l_drop_model BOOLEAN := FALSE;', 'l_drop_model BOOLEAN := TRUE;')
        start = time.perf_counter()
        with conn.cursor() as cur:
            cur.execute(statement.rsplit('\n/',1)[0])
            remaining = []
            for kind, name in OBJECTS:
                cur.execute('SELECT COUNT(*) FROM user_objects WHERE object_type=:t AND object_name=:n', t=kind, n=name)
                if cur.fetchone()[0]: remaining.append(name)
            for _, (view, column, names) in AI.items():
                for name in names:
                    cur.execute(f'SELECT COUNT(*) FROM {view} WHERE {column}=:n', n=name)
                    if cur.fetchone()[0]: remaining.append(name)
            cur.execute('SELECT COUNT(*) FROM user_mining_models WHERE model_name=:n', n=MODEL)
            models = cur.fetchone()[0]
            if remaining or (a.include_model and models): raise ValueError('Reset verification failed')
        result = dict(complete=True, model_deleted=a.include_model, remaining_named_objects=remaining, model_count=models, seconds=round(time.perf_counter()-start,3))
        (target/'reset-result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result),flush=True)

if __name__ == '__main__': main()
