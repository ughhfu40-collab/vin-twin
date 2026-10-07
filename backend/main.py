from collections import OrderedDict
from uuid import uuid4
from pathlib import Path
import json
from hashlib import sha256
from threading import RLock
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from .models import SimulateRequest, SnapshotRequest, ChatRequest
from .engine import load_data, snapshot, apply_events, resolve_events, clock
from .explanations import explain
from .report import report
from .store import save_snapshot, read_snapshot

app=FastAPI(title='VIN-Twin',version='1.1.0')
snapshots=OrderedDict()
snapshot_lock=RLock()

@app.middleware('http')
async def limit_body(request:Request,call_next):
    if request.method=='POST':
        try:
            body=b''
            async for chunk in request.stream():
                body+=chunk
                if len(body)>262144:
                    return JSONResponse({'detail':'Запрос превышает 256 КиБ'},status_code=413)
            request._body=body
        except Exception:
            return JSONResponse({'detail':'Не удалось прочитать запрос'},status_code=400)
    return await call_next(request)

@app.get('/api/health')
def health():
    return {'status':'ok','model_version':'1.1.0','explanation_provider':'local'}

@app.get('/api/state')
def state():
    events=json.loads((Path(__file__).parent/'data/events.json').read_text())
    return {'now':120,'source':'Демонстрационный набор JSON v1','updated_at':'2026-10-06T10:00:00+05:00','data':load_data(),'events':events}

@app.post('/api/simulate')
def simulate(req:SimulateRequest):
    if req.basis_snapshot_id:
        if req.model_fields_set - {'basis_snapshot_id','policy'}:
            raise HTTPException(422,'Для действия по снимку передайте только basis_snapshot_id и policy')
        basis=get_snapshot(req.basis_snapshot_id)
        req=SimulateRequest.model_validate({**basis['_request'],'policy':req.policy,'basis_snapshot_id':None})
    data=req.data.model_dump() if req.data else load_data()
    params=req.model_dump(exclude={'data','events','received_until','basis_snapshot_id'})
    events=[e.model_dump() for e in req.events]
    try:
        received=resolve_events(events,req.received_until)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
    supply_event=None
    robot_event=None
    for event in received:
        if event['event_type'] in {'eta_updated','batch_received'}:
            supply_event=event
        elif event['event_type']=='robot_down':
            robot_event=event
    if supply_event:
        adapted=apply_events(data,received,req.received_until)
        params['eta_override']=adapted['supply']['eta']+req.delay
        params['delay']=max(0,params['eta_override']-data['supply']['eta'])
    if robot_event:
        params['robot_start']=robot_event['occurred_at']
        params['robot_minutes']=robot_event['payload']['duration']
    try:
        s=snapshot(params,data)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc
    s['snapshot_id']=str(uuid4())
    s['events']=events
    s['received_until']=req.received_until
    s['now']=req.received_until if events else 120
    s['source']=f"Демонстрационный импорт {data['version']}" if req.data else 'Демонстрационный набор JSON v1'
    s['updated_at']=f"Демо-время {clock(s['now'])}"
    for incident in s['incidents']:
        event=supply_event if incident['id']=='eta' else robot_event
        if event:
            incident['type']='fact' if event['kind']=='fact' and not (incident['id']=='eta' and req.delay) else 'assumption'
            incident['source']=event['source'] if incident['type']=='fact' else f"Сценарное условие · {event['source']}"
            incident['received_at']=event['received_at']
            incident['event_id']=event['id']
            if incident['id']=='eta':
                received_eta=event['payload']['eta'] if event['event_type']=='eta_updated' else event['occurred_at']
                incident['detail']=f"Полученный ETA {clock(received_eta)}; ETA в выбранной политике {clock(s['eta'])} (результат сценария)."
    s['facts']['incidents']=s['incidents']
    s['input_version'] = sha256(json.dumps({"data":data,"events":received,"received_until":req.received_until},sort_keys=True).encode()).hexdigest()[:12]
    s['_request']=req.model_dump()
    save_snapshot(s)
    with snapshot_lock:
        snapshots[s['snapshot_id']]=s
        while len(snapshots)>64: snapshots.popitem(last=False)
    return {k:v for k,v in s.items() if k!='_request'}

def get_snapshot(id):
    with snapshot_lock:
        s=snapshots.get(id)
    if s is None:
        s=read_snapshot(id)
    if s is None:
        raise HTTPException(404,'Снимок истёк или backend перезапущен. Пересчитайте сценарий.')
    return s

@app.post('/api/chat')
async def chat(req:ChatRequest):
    current=get_snapshot(req.snapshot_id)
    previous=None
    if req.previous_snapshot_id:
        try:previous=get_snapshot(req.previous_snapshot_id)
        except HTTPException:pass
    return await explain(req.question,current,previous,req.time)

@app.post('/api/report')
def shift_report(req:SnapshotRequest):
    return report(get_snapshot(req.snapshot_id),req.time)

# Separate aggregate analytics; no implicit calibration of VIN/BOM simulation.
from .factory import FactoryRequest, analyze, load_case

@app.get('/api/factory/data')
def factory_data():
    return load_case()

@app.post('/api/factory/analyze')
def factory_analyze(req: FactoryRequest):
    try:
        return analyze(req)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

from .factory import FactoryChatRequest, case_explanation

@app.post('/api/factory/chat')
def factory_chat(req: FactoryChatRequest):
    try:
        return case_explanation(req)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
