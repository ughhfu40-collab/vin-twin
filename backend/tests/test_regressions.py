from copy import deepcopy
from fastapi.testclient import TestClient
import pytest
from backend.engine import load_data,schedule,snapshot,policy_availability
from backend.models import DataSet
from backend.main import app
BASE=dict(delay=100,robot_minutes=0,decision_time=120,contribution=650000,policy='none')
def past(r):
    return sorted((v['id'],o['station'],o['start'],min(o['end'],120)) for v in r['vehicles'] for o in v['operations'] if o['start']<120)
@pytest.mark.parametrize('offset',[0,1,20,60,70])
def test_reorder_import_never_rewrites_past(offset):
    d=load_data();d['orders']=d['orders'][offset:]+d['orders'][:offset];DataSet.model_validate(d)
    before=schedule(BASE,d)
    if policy_availability(BASE,d)['reorder']['available']:
        after=schedule({**BASE,'policy':'reorder'},d)
        assert past(before)==past(after)
        assert [v['id'] for v in before['vehicles'] if not 49<=int(v['id'][-3:])<=60]==[v['id'] for v in after['vehicles'] if not 49<=int(v['id'][-3:])<=60]
    else:
        with pytest.raises(ValueError):schedule({**BASE,'policy':'reorder'},d)
def test_event_robot_time_source_and_duplicate_conflict():
    e={'id':'robot-late','occurred_at':210,'received_at':120,'source':'Сценарий аудита','kind':'assumption','event_type':'robot_down','payload':{'duration':40}}
    with TestClient(app) as c:
        s=c.post('/api/simulate',json={'events':[e,e]}).json()
        assert s['frames'][150]['stations'][0]['status']=='processing'
        assert s['frames'][210]['stations'][0]['status']=='down'
        assert s['params']['robot_start']==210 and s['incidents'][0]['received_at']==120
        conflict=deepcopy(e);conflict['payload']['duration']=60
        assert c.post('/api/simulate',json={'events':[e,conflict]}).status_code==422
@pytest.mark.parametrize('kind',['eta_updated','batch_received'])
def test_early_receipt_or_eta_supported(kind):
    e={'id':'early','occurred_at':200,'received_at':200,'source':'Демо WMS','kind':'fact','event_type':kind,'payload':{'eta':200} if kind=='eta_updated' else {}}
    with TestClient(app) as c:
        response=c.post('/api/simulate',json={'events':[e],'received_until':200});assert response.status_code==200
        s=response.json();assert s['eta']==200 and s['now']==200 and s['output']==75
        assert s['incidents'][0]['type']=='fact' and s['incidents'][0]['source']=='Демо WMS'
        assert s['frames'][200]['inventory']['A']==56
        again=c.post('/api/simulate',json={'events':[e,e],'received_until':200}).json()
        assert again['frames']==s['frames'] and again['input_version']==s['input_version']
def test_material_b_all_labels_and_chat(monkeypatch):
    d=load_data();d['reorder_allowed']=False;d['inventory']={'A':74,'B':0};d['supply']['kit']='B';d['supply']['quantity']=6
    with TestClient(app) as c:
        s=c.post('/api/simulate',json={**BASE,'data':d}).json();wait=s['material_waits'][0]
        assert wait['kit']=='B' and s['frames'][wait['start']]['stations'][2]['label']=='Ожидание комплекта B'
        assert s['incidents'][0]['title']=='Срок поставки B'
        answer=c.post('/api/chat',json={'snapshot_id':s['snapshot_id'],'question':'Почему?'}).json()
        assert 'комплект B' in answer['answer'] and 'комплект A' not in answer['answer']
def test_manual_conditions_are_assumptions():
    with TestClient(app) as c:
        s=c.post('/api/simulate',json=BASE).json()
        assert s['incidents'][0]['type']=='assumption' and s['incidents'][0]['source']=='Условие сценария'
@pytest.mark.parametrize('contribution,policy',[(0,'none'),(100000,'reorder'),(145000,'reorder'),(145001,'delivery'),(650000,'delivery')])
def test_sensitivity(contribution,policy):
    s=snapshot({**BASE,'contribution':contribution});assert s['recommended']==policy
    assert next(r for r in s['sensitivity'] if r['contribution']==contribution)['recommended']==policy
    assert any(t['contribution']==145000 and {t['left'],t['right']}=={'delivery','reorder'} for t in s['thresholds'])
def test_chat_change_and_vin(monkeypatch):
    with TestClient(app) as c:
        before=c.post('/api/simulate',json=BASE).json();after=c.post('/api/simulate',json={**BASE,'robot_minutes':40}).json()
        answer=c.post('/api/chat',json={'snapshot_id':after['snapshot_id'],'previous_snapshot_id':before['snapshot_id'],'question':'Почему рекомендация изменилась?'}).json()
        assert answer['intent']=='change' and 'Срочная доставка → Перестановка VIN' in answer['answer']
        assert 'длительность сбоя, мин: 0 → 40' in answer['answer'] and answer['previous_snapshot_id']==before['snapshot_id']
        vin=c.post('/api/chat',json={'snapshot_id':before['snapshot_id'],'question':'Почему VIN-049 ждёт?'}).json()
        assert vin['intent']=='vehicle' and 'VIN-049' in vin['answer'] and '13:00–14:10' in vin['answer']
        assert 'Такого VIN' in c.post('/api/chat',json={'snapshot_id':before['snapshot_id'],'question':'VIN-999?'}).json()['answer']
        assert 'истёк' in c.post('/api/chat',json={'snapshot_id':after['snapshot_id'],'previous_snapshot_id':'expired','question':'Что изменилось?'}).json()['answer']
def test_received_event_order_deterministic():
    events=[{'id':'a','occurred_at':120,'received_at':120,'source':'Демо','kind':'fact','event_type':'eta_updated','payload':{'eta':370}}, {'id':'b','occurred_at':130,'received_at':130,'source':'Демо','kind':'fact','event_type':'eta_updated','payload':{'eta':360}}]
    with TestClient(app) as c:
        a=c.post('/api/simulate',json={'events':events,'received_until':130}).json();b=c.post('/api/simulate',json={'events':list(reversed(events)),'received_until':130}).json()
        assert a['frames']==b['frames'] and a['input_version']==b['input_version']

def test_action_reuses_event_provenance_and_import():
    e={'id':'eta','occurred_at':120,'received_at':120,'source':'Демо поставщик','kind':'fact','event_type':'eta_updated','payload':{'eta':370}}
    with TestClient(app) as c:
        basis=c.post('/api/simulate',json={'events':[e]}).json()
        action=c.post('/api/simulate',json={'basis_snapshot_id':basis['snapshot_id'],'policy':'delivery'}).json()
        assert action['output']==71 and action['eta']==320
        assert action['incidents'][0]['type']=='fact' and action['incidents'][0]['source']=='Демо поставщик'
        reset=c.post('/api/simulate',json={'basis_snapshot_id':action['snapshot_id'],'policy':'none'}).json()
        assert reset['output']==63 and reset['eta']==370
        assert c.post('/api/simulate',json={'basis_snapshot_id':basis['snapshot_id'],'policy':'delivery','delay':0}).status_code==422

def test_zero_outage_no_false_pause():
    from backend.engine import process
    assert process(150,6,(151,151))==(150,156,[[150,156]])

def test_snapshots_survive_cache_restart(monkeypatch):
    from backend.main import snapshots
    with TestClient(app) as c:
        s=c.post('/api/simulate',json=BASE).json()
        snapshots.clear()
        report=c.post('/api/report',json={'snapshot_id':s['snapshot_id']})
        assert report.status_code==200 and '63' in report.json()['text']
        answer=c.post('/api/chat',json={'snapshot_id':s['snapshot_id'],'question':'Почему?'})
        assert answer.status_code==200 and '14:10' in answer.json()['answer']
        applied=c.post('/api/simulate',json={'basis_snapshot_id':s['snapshot_id'],'policy':'delivery'}).json()
        assert applied['output']==71
