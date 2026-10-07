import pytest
from fastapi.testclient import TestClient
from backend.main import app
from backend.factory import FactoryRequest, analyze


def test_case_totals_not_double_counted():
    r=analyze(FactoryRequest())
    assert r['assembly']['produced']==240 and r['assembly']['good']==237
    assert r['monthly_plan_total']==4800 and r['monthly_plan_gap']==700
    assert r['quality_breach_rows']==3
    assert r['monthly_scenario'] is None
    assert all(row['oee_percent'] is None for row in r['rows'])


def test_weighted_quality_and_integer_target():
    r=analyze(FactoryRequest())
    paint=next(s for s in r['sections'] if s['section']=='Окраска')
    assert paint['reject_percent']==pytest.approx(10/231*100)
    assert paint['preventable_rejects_scenario']==6
    assert next(s for s in r['sections'] if s['section']=='Сварка')['preventable_rejects_scenario']==1


def test_downtime_per_equipment_per_day():
    r=analyze(FactoryRequest())
    assert r['recorded_downtime_minutes']==150
    assert not any(d['breach'] for d in r['downtime'])
    conveyor=next(d for d in r['downtime'] if d['equipment']=='Конвейер-03')
    assert conveyor['remaining_to_limit']==5 and conveyor['near_limit']


def test_month_scenario_scope_changes_capacity():
    shift=analyze(FactoryRequest(scope='shift'))['monthly_scenario']
    day=analyze(FactoryRequest(scope='day'))['monthly_scenario']
    assert shift['gross_scenario']==5280 and shift['good_at_assembly_scenario']==5214
    assert shift['required_days_at_current_gross']==23
    assert shift['required_days_at_current_good_assembly']==24
    assert day['gross_scenario']==2640


def test_oee_valid_formula_and_invalid_cycle_not_clipped():
    r=analyze(FactoryRequest(scope='shift',ideal_cycle_minutes={'Сборка':4}))
    row=next(row for row in r['rows'] if row['line']=='Сборка-1' and row['date']=='2026-10-01')
    assert row['performance_percent']>100 and row['oee_status']=='invalid_cycle' and row['oee_percent'] is None
    valid=analyze(FactoryRequest(scope='shift',ideal_cycle_minutes={'Сборка':3.9}))
    row=next(row for row in valid['rows'] if row['line']=='Сборка-1' and row['date']=='2026-10-01')
    assert row['oee_percent']==pytest.approx(120*3.9/480*100)

@pytest.mark.parametrize('payload',[{'scope':'year'},{'workdays':0},{'workdays':32},{'ideal_cycle_minutes':{'Сборка':0}},{'ideal_cycle_minutes':{'Unknown':4}}])
def test_invalid_inputs(payload):
    with TestClient(app) as c:
        assert c.post('/api/factory/analyze',json=payload).status_code==422


def test_case_api_and_explanation_report_agree():
    with TestClient(app) as c:
        assert c.get('/api/factory/data').json()['monthly_plan'][0]['plan']==2500
        r=c.post('/api/factory/analyze',json={}).json()
        assert '4800' in r['report'] and '237' in r['report']
        q=c.post('/api/factory/chat',json={'question':'Где резерв качества?'}).json()
        assert '4.33%' in q['answer'] and 'минимум 6' in q['answer']
        q=c.post('/api/factory/chat',json={'question':'Где узкое место?'}).json()
        assert '111/120' in q['answer'] and 'не доказанное' in q['answer']
