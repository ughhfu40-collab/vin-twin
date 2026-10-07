"""Export the clearly labeled homepage example from the Python source of truth."""
from pathlib import Path
import json
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.engine import snapshot
s=snapshot(dict(delay=100,robot_minutes=0,robot_start=150,policy='none',decision_time=120,contribution=650000))
result={'model_version':s['model_version'],'delay':100,'contribution':650000,'baseline':s['baseline_output'],'policies':s['policies']}
output=ROOT/'frontend/app/reference-results.json'
if '--check' in sys.argv:
    assert json.loads(output.read_text())==result,'Homepage reference is stale. Run scripts/export_reference.py.'
else:
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print('Homepage reference matches the simulation')
