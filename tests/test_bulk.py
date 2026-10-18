import json

import pytest

from webinar_demo.bulk import generate, read_manifest, read_part


def test_deterministic_shards_and_special_characters(tmp_path):
    a=tmp_path/'a'; b=tmp_path/'b'
    ma=generate(a,33,16); mb=generate(b,33,16)
    assert ma==mb
    assert [p['rows'] for p in ma['parts']]==[16,16,1]
    for p in ma['parts']:
        assert (a/p['file']).read_bytes()==(b/p['file']).read_bytes()
    rows=[r for p in read_manifest(a)['parts'] for r in read_part(a,ma,p)]
    assert len(rows)==33
    assert '\n' in rows[15][4] and '"' in rows[15][4] and ',' in rows[15][4]


def test_tampering_stops_before_database(tmp_path):
    m=generate(tmp_path,2,1)
    (tmp_path/m['parts'][0]['file']).write_bytes(b'changed')
    with pytest.raises(ValueError,match='ハッシュ'): read_manifest(tmp_path)


def test_manifest_rejects_path_escape(tmp_path):
    m=generate(tmp_path,2,1); m['parts'][0]['file']='../other.csv'
    (tmp_path/'manifest.json').write_text(json.dumps(m),encoding='utf-8')
    with pytest.raises(ValueError,match='定義'): read_manifest(tmp_path)


@pytest.mark.parametrize('rows,size',[(0,1),(1,0),(1,10001)])
def test_invalid_size(tmp_path,rows,size):
    with pytest.raises(ValueError): generate(tmp_path,rows,size)
