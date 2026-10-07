"""Run production Next + FastAPI and verify the shared-origin API, no external network."""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import time
import httpx

ROOT=Path(__file__).resolve().parents[1]
# Both servers run in the same environment/network namespace.
with tempfile.TemporaryDirectory(prefix='vin-twin-check-') as tmp:
    with open(Path(tmp)/'backend.log','w+') as back_log, open(Path(tmp)/'frontend.log','w+') as front_log:
        backend=subprocess.Popen([sys.executable,'-m','uvicorn','backend.main:app','--host','127.0.0.1','--port','8000'],cwd=ROOT,env={**os.environ,'VIN_STATE_PATH':str(Path(tmp)/'snapshots.sqlite3')},stdout=back_log,stderr=subprocess.STDOUT)
        frontend=subprocess.Popen(['node','node_modules/next/dist/bin/next','start','--hostname','127.0.0.1','--port','3000'],cwd=ROOT/'frontend',stdout=front_log,stderr=subprocess.STDOUT)
        try:
            with httpx.Client(base_url='http://127.0.0.1:3000',timeout=15,trust_env=False) as client:
                for attempt in range(100):
                    try:
                        response=client.get('/api/health')
                        if response.status_code==200:break
                    except httpx.HTTPError:pass
                    if backend.poll() is not None or frontend.poll() is not None:raise RuntimeError('Server exited during startup')
                    time.sleep(.2)
                else:raise RuntimeError('Shared-origin API failed to start')
                assert 'Увидеть сбой.' in client.get('/').text
                assert 'Диспетчер смены' in client.get('/dashboard').text
                assert client.get('/dashboard?scenario=delay').status_code==200
                assert client.get('/dashboard?view=vin').status_code==200
                assert client.get('/factory').status_code==200
                case=client.post('/api/factory/analyze',json={}).json()
                assert case['monthly_plan_gap']==700 and case['assembly']['good']==237
                assert client.get('/api/factory/data').status_code==200
                explanation=client.post('/api/factory/chat',json={'question':'Где резерв качества?'}).json()
                assert '4.33%' in explanation['answer']
                assert response.json()['status']=='ok'
                assert client.get('/api/state').status_code==200
                for d,r,expected in [(0,0,[75,75,75]),(100,0,[63,71,69]),(0,40,[68,68,68]),(100,40,[63,68,68])]:
                    result=client.post('/api/simulate',json={'delay':d,'robot_minutes':r})
                    result.raise_for_status();s=result.json()
                    assert [p['output'] for p in s['policies']]==expected
                s=client.post('/api/simulate',json={'delay':100,'policy':'delivery'}).json()
                assert s['output']==71 and s['policies'][1]['effect']==4820000
                sid=s['snapshot_id']
                answer=client.post('/api/chat',json={'snapshot_id':sid,'question':'Какое действие выгоднее?'}).json()
                assert answer['snapshot_id']==sid and '71' in answer['answer']
                report=client.post('/api/report',json={'snapshot_id':sid,'time':120}).json()
                assert report['snapshot_id']==sid and '4,820,000' in report['text']
                assert client.post('/api/simulate',json={'delay':-1}).status_code==422
                print(json.dumps({'production_frontend':'ok','shared_origin_api':'ok','reference_outputs':12,'chat_report_snapshot':'ok','invalid_input':422},ensure_ascii=False))
        except Exception:
            back_log.seek(0);front_log.seek(0)
            print(back_log.read());print(front_log.read())
            raise
        finally:
            for process in (frontend,backend):
                process.terminate()
            for process in (frontend,backend):
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait()
