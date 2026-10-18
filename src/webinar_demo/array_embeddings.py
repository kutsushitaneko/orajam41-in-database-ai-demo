"""One UTL_TO_EMBEDDINGS invocation for a validated array of texts."""
import array
import json
import math

import oracledb

CALL = '''DECLARE
  src JSON_ARRAY_T := JSON_ARRAY_T.parse(:payload);
  inputs VECTOR_ARRAY_T := VECTOR_ARRAY_T();
  outputs VECTOR_ARRAY_T;
  result JSON_ARRAY_T := JSON_ARRAY_T();
BEGIN
  inputs.extend(src.get_size());
  FOR i IN 1..src.get_size() LOOP
    inputs(i) := src.get(i-1).to_clob();
  END LOOP;
  outputs := DBMS_VECTOR.UTL_TO_EMBEDDINGS(inputs,
    JSON('{"provider":"database","model":"MULTILINGUAL_E5_LARGE"}'));
  FOR i IN 1..outputs.count LOOP
    result.append(JSON_OBJECT_T.parse(outputs(i)));
  END LOOP;
  :result := result.to_clob();
END;'''


def payload_for(rows):
    if not rows or len({r[0] for r in rows}) != len(rows):
        raise ValueError('Input IDs must be nonempty and unique')
    chunks=[]
    for row_id, text in rows:
        if not text or len(text)>4000:
            raise ValueError('Input text must contain 1..4000 characters')
        chunks.append(dict(chunk_id=row_id,chunk_offset=1,chunk_length=len(text),chunk_data=text))
    return json.dumps(chunks,ensure_ascii=False)


def validate_output(rows, results):
    expected=dict(rows); vectors={}
    if len(results)!=len(rows): raise ValueError('Output count mismatch')
    for r in results:
        if not isinstance(r,dict) or not {"embed_id","embed_data","embed_vector"} <= r.keys():
            raise ValueError("Missing output fields")
        key=r['embed_id']
        if key not in expected or key in vectors or r['embed_data']!=expected[key]:
            raise ValueError('Output ID/text mismatch')
        v=r['embed_vector']
        if isinstance(v,str): v=json.loads(v)
        if len(v)!=1024 or not all(isinstance(x,(float,int)) and math.isfinite(x) for x in v):
            raise ValueError('Invalid embedding dimensions or values')
        vectors[key]=array.array('f',v)
    return vectors


def array_vectors(cur,rows):
    output=cur.var(oracledb.DB_TYPE_CLOB)
    cur.setinputsizes(payload=oracledb.DB_TYPE_CLOB)
    cur.execute(CALL,payload=payload_for(rows),result=output)
    value=output.getvalue()
    return validate_output(rows,json.loads(value.read() if hasattr(value,'read') else value))
