import pytest
from webinar_demo.array_embeddings import payload_for, validate_output


def result(i=1,text='passage: 本文',size=1024):
    return dict(embed_id=i,embed_data=text,embed_vector=[0.1]*size)


def test_array_output_reordered_ids_are_mapped():
    r=validate_output([(1,'a'),(3,'b')],[result(3,'b'),result(1,'a')])
    assert set(r)=={1,3} and len(r[3])==1024


@pytest.mark.parametrize('results',[
    [],[result(2)],[result(text='wrong')],[result(size=1023)],
    [dict(embed_id=1,embed_data='passage: 本文',embed_vector=[float('nan')]*1024)],
])
def test_array_invalid_output_rejected(results):
    with pytest.raises(ValueError): validate_output([(1,'passage: 本文')],results)


def test_array_duplicate_output_rejected():
    with pytest.raises(ValueError): validate_output([(1,'a'),(2,'b')],[result(1,'a'),result(1,'a')])


@pytest.mark.parametrize('rows',[[],[(1,'a'),(1,'b')],[(1,'')],[(1,'a'*4001)]])
def test_array_invalid_input_rejected(rows):
    with pytest.raises(ValueError): payload_for(rows)
