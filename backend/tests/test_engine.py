import asyncio
from copy import deepcopy
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from backend.engine import schedule,snapshot,load_data,apply_events,process,inventory_at
from backend.main import app
from backend.explanations import explain

BASE=dict(delay=0,robot_minutes=0,decision_time=120,contribution=650000,policy='none')

@pytest.mark.parametrize('delay,robot,expected',[(0,0,[75,75,75]),(100,0,[63,71,69]),(0,40,[68,68,68]),(100,40,[63,68,68])])
def test_reference(delay,robot,expected):
    assert [schedule({**BASE,'delay':delay,'robot_minutes':robot,'policy':p})['output'] for p in ['none','delivery','reorder']]==expected

@pytest.mark.parametrize('policy',['none','delivery','reorder'])
def test_temporal_inventory_invariants(policy):
    data=load_data();params={**BASE,'delay':100,'robot_minutes':40,'policy':policy};r=schedule(params,data)
    for v in r['vehicles']:
        previous=0
        for o in v['operations']:
            assert o['start']>=previous
            assert sum(b-a for a,b in o['segments'])==6
            assert all(b>a for a,b in o['segments'])
            previous=o['end']
    for k in range(6):
        ops=sorted((v['operations'][k] for v in r['vehicles']),key=lambda o:o['start'])
        assert all(b['start']>=a['end'] for a,b in zip(ops,ops[1:]))
    for t in range(0,1000):
        assert all(count>=0 for count in inventory_at(r,data,t).values())
    assert len(r['consumption'])==80
    assert len({c['vin'] for c in r['consumption']})==80
    assert inventory_at(r,data,1000)=={'A':14,'B':0}

def test_wait_and_boundaries():
    r=schedule({**BASE,'delay':100})
    assert r['material_waits'][0]['start']==300
    assert r['material_waits'][0]['end']==370
    normal=schedule(BASE)
    assert normal['vehicles'][0]['completion']==36
    assert normal['vehicles'][74]['completion']==480
    assert normal['vehicles'][75]['completion']==486
    assert process(146,6,(150,190))==(146,192,[[146,150],[190,192]])
    assert process(144,6,(150,190))==(144,150,[[144,150]])
    assert process(150,6,(150,190))==(190,196,[[190,196]])

@pytest.mark.parametrize('policy',['delivery','reorder'])
def test_past_frozen(policy):
    baseline=schedule({**BASE,'delay':100,'robot_minutes':40})
    action=schedule({**BASE,'delay':100,'robot_minutes':40,'policy':policy})
    def past(r):
        return sorted((v['id'],o['station'],o['start'],min(o['end'],120)) for v in r['vehicles'] for o in v['operations'] if o['start']<120)
    assert past(baseline)==past(action)

@pytest.mark.parametrize('decision',[289,350,480])
def test_reorder_rejected_after_launch(decision):
    with pytest.raises(ValueError): schedule({**BASE,'policy':'reorder','decision_time':decision})

def test_reorder_forbidden_data():
    data=load_data();data['reorder_allowed']=False
    with pytest.raises(ValueError): schedule({**BASE,'policy':'reorder'},data)
    s=snapshot(BASE,data)
    assert not s['policies'][2]['available']

def test_late_delivery():
    with pytest.raises(ValueError):schedule({**BASE,'policy':'delivery','decision_time':321})
    # Receiving the batch at 12:30 cannot be rewritten by a 13:00 decision.
    assert schedule({**BASE,'policy':'delivery','decision_time':300})==schedule(BASE)

def test_event_deduplication():
    data=load_data();events=json.loads((Path(__file__).parents[1]/'data/events.json').read_text())
    assert apply_events(data,events)==apply_events(data,events+events)
    assert apply_events(data,events,119)==data
    assert apply_events(data,events,120)['supply']['eta']==370
    assert apply_events(data,events)['supply']['quantity']==40

def test_economics_recommendation():
    s=snapshot({**BASE,'delay':100})
    assert [(p['saved'],p['effect']) for p in s['policies']]==[(0,0),(8,4820000),(6,3810000)]
    assert s['recommended']=='delivery'
    assert snapshot(BASE)['recommended']=='none'
    assert snapshot({**BASE,'delay':100,'robot_minutes':40})['recommended']=='reorder'
    assert len(s['affected'])!=s['plan']-s['output']
    assert len(s['after_shift'])==17

def test_more_inventory_earlier_eta():
    data=load_data();data['inventory']['A']+=5
    assert schedule({**BASE,'delay':100},data)['output']>=schedule({**BASE,'delay':100})['output']
    assert schedule({**BASE,'delay':90})['output']>=schedule({**BASE,'delay':100})['output']

@pytest.mark.parametrize('question', ['Какое действие выгоднее?', 'Какую политику выбрать?', 'Что рекомендуешь сделать?'])
def test_local_explanations_do_not_call_external_services(monkeypatch, question):
    import httpx
    s=snapshot({**BASE,'delay':100});s['snapshot_id']='test-snapshot'
    async def forbidden_request(*args,**kwargs):
        raise AssertionError('External API requests are not allowed')
    monkeypatch.setattr(httpx.AsyncClient,'request',forbidden_request)
    answer=asyncio.run(explain(question,s))
    assert answer['source_mode']=='local'
    assert '71' in answer['answer'] and '4,820,000' in answer['answer']
    assert all(ref in s['facts'] for ref in answer['fact_refs'])

def test_api_snapshots_report_validation(monkeypatch):
    with TestClient(app) as client:
        assert client.get('/api/health').status_code==200
        assert client.get('/api/state').json()['data']['inventory']=={'A':48,'B':6}
        response=client.post('/api/simulate',json={**BASE,'delay':100})
        assert response.status_code==200
        s=response.json();sid=s['snapshot_id']
        assert s['output']==63
        answer=client.post('/api/chat',json={'snapshot_id':sid,'question':'Почему?'}).json()
        assert answer['snapshot_id']==sid
        assert '13:00' in answer['answer'] and '14:10' in answer['answer']
        report=client.post('/api/report',json={'snapshot_id':sid,'time':120}).json()
        assert report['snapshot_id']==sid and '4,820,000' in report['text']
        assert client.post('/api/simulate',json={'delay':-1}).status_code==422
        assert client.post('/api/simulate',json={'delay':1.5}).status_code==422
        assert client.post('/api/simulate',json={'policy':'unknown'}).status_code==422
        assert client.post('/api/chat',json={'snapshot_id':'missing','question':'test'}).status_code==404
        assert client.post('/api/chat',json={'snapshot_id':sid,'question':'x'*2001}).status_code==422
        assert client.post('/api/simulate',content='x'*262145).status_code==413
        data=load_data();data['orders'][1]['id']='VIN-001'
        assert client.post('/api/simulate',json={'data':data}).status_code==422
        assert client.post('/api/simulate',json={'data':load_data()}).status_code==200

def test_api_event_replay():
    events=json.loads((Path(__file__).parents[1]/'data/events.json').read_text())
    with TestClient(app) as client:
        a=client.post('/api/simulate',json={'events':events,'received_until':119}).json()
        b=client.post('/api/simulate',json={'events':events*2,'received_until':120}).json()
        assert a['output']==75 and b['output']==63
        assert b['params']['delay']==100 and b['params']['robot_minutes']==40


def test_unknown_question_returns_model_assumptions():
    s=snapshot(BASE);s['snapshot_id']='unknown-question'
    answer=asyncio.run(explain('Привет, расскажи анекдот',s))
    assert answer['source_mode']=='local'
    assert answer['intent']=='assumptions'
    assert answer['fact_refs']==['assumptions']
    assert answer['answer']=='\n'.join(s['facts']['assumptions'])
