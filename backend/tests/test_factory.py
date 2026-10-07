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


def test_targets_are_read_from_case_data(monkeypatch):
    import backend.factory as factory
    data=factory.load_case()
    data['targets'].update(monthly_output=6000, reject_percent=5, oee_percent=99, critical_downtime_minutes=45, shifts=1)
    monkeypatch.setattr(factory,'load_case',lambda:data)
    r=factory.analyze(factory.FactoryRequest(scope='shift',ideal_cycle_minutes={'Сборка':3.9}))
    assert r['monthly_plan_gap']==1200
    assert r['monthly_scenario']['gross_scenario']==2640
    assert r['monthly_scenario']['required_gross_per_day']==pytest.approx(6000/22)
    assert not any(s['quality_breach'] for s in r['sections'])
    assembly=next(row for row in r['rows'] if row['line']=='Сборка-1' and row['date']=='2026-10-01')
    assert assembly['oee_status']=='below_target'
    conveyor=next(d for d in r['downtime'] if d['equipment']=='Конвейер-03')
    assert conveyor['breach'] and conveyor['remaining_to_limit']==-10
    assert 'цель: 6000' in r['report']


def test_surplus_is_not_negative_shortfall(monkeypatch):
    import backend.factory as factory
    data=factory.load_case();data['targets']['monthly_output']=4000
    monkeypatch.setattr(factory,'load_case',lambda:data)
    r=factory.analyze(factory.FactoryRequest())
    assert r['monthly_plan_gap']==0 and r['monthly_plan_surplus']==800


def test_breaks_and_impossible_running_time_are_explicit():
    r=analyze(FactoryRequest(scope='shift',excluded_minutes_per_shift=60,ideal_cycle_minutes={'Сборка':3.9}))
    assert r['planned_minutes']==420
    assert r['monthly_scenario'] is None and r['monthly_status']=='invalid_time'
    row=next(row for row in r['rows'] if row['line']=='Сборка-1' and row['date']=='2026-10-01')
    assert row['availability_percent']>100
    assert row['oee_status']=='invalid_time' and row['oee_percent'] is None
    assert 'время работы выше планового' in r['report']
    assert 'Месячный сценарий не рассчитан' in r['report']
    with TestClient(app) as c:
        answer=c.post('/api/factory/chat',json={'analysis':r['params'],'question':'Как выполнить месячный план?'}).json()['answer']
        assert 'время работы выше планового' in answer
    valid=analyze(FactoryRequest(scope='shift',excluded_minutes_per_shift=25,ideal_cycle_minutes={'Сварка':3.5}))
    row=next(row for row in valid['rows'] if row['section']=='Сварка' and row['date']=='2026-10-02')
    assert row['oee_percent']==pytest.approx(108*3.5/455*100)


def test_observed_range_is_scenario_sensitivity():
    r=analyze(FactoryRequest(scope='shift'))
    m=r['monthly_scenario']
    assert m['sample_days']==2
    assert m['gross_scenario_range']==[5236,5324]
    assert m['good_scenario_range']==[5148,5280]
    assert m['gross_scenario_range'][0]<=m['gross_scenario']<=m['gross_scenario_range'][1]
    assert 'не доверительный интервал' in r['report']


def test_no_good_assembly_output_has_no_finite_completion_date(monkeypatch):
    import backend.factory as factory
    data=factory.load_case()
    for row in data['quality']:
        if row['section']=='Сборка':row['rejects']=row['produced']
    monkeypatch.setattr(factory,'load_case',lambda:data)
    r=factory.analyze(factory.FactoryRequest(scope='shift'))
    assert r['monthly_scenario']['good_at_assembly_scenario']==0
    assert r['monthly_scenario']['required_days_at_current_good_assembly'] is None
    assert 'цель по годному выпуску недостижима' in r['report']


@pytest.mark.parametrize('mutation',['mismatch','duplicate','rejects','runtime'])
def test_case_table_validation_rejects_inconsistent_inputs(mutation):
    from backend.factory import load_case,validate_case
    data=load_case()
    if mutation=='mismatch':data['quality'][0]['produced']+=1
    if mutation=='duplicate':data['production'].append(data['production'][0].copy())
    if mutation=='rejects':data['quality'][0]['rejects']=999
    if mutation=='runtime':data['production'][0]['run_hours']=0
    with pytest.raises(ValueError):validate_case(data)


def test_questions_and_input_types_are_validated():
    with TestClient(app) as c:
        assert c.post('/api/factory/analyze',json={'workdays':True}).status_code==422
        assert c.post('/api/factory/analyze',json={'excluded_minutes_per_shift':-1}).status_code==422
        assert c.post('/api/factory/chat',json={'question':'   '}).status_code==422
        response=c.post('/api/factory/chat',json={'question':'Привет, расскажи анекдот'}).json()
        assert response['intent']=='help' and 'Поддерживаются вопросы' in response['answer']
        response=c.post('/api/factory/analyze',json={}).json()
        assert response['data_checks']['status']=='passed'
        assert response['data_checks']['production_rows']==6
