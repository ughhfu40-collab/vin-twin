"""Aggregate case analytics. Historical stage counts are never summed as cars."""
from pathlib import Path
import json
import math
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

SECTIONS = ['Сварка', 'Окраска', 'Сборка']

class FactoryRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, allow_inf_nan=False)
    scope: Literal['unknown', 'shift', 'day'] = 'unknown'
    workdays: int = Field(default=22, strict=True, ge=1, le=31)
    excluded_minutes_per_shift: int = Field(default=0, strict=True, ge=0, le=479)
    ideal_cycle_minutes: dict[str, float] = Field(default_factory=dict)
    target_reject_percent: float = Field(default=2, ge=0, le=100)


def validate_case(data):
    """Validate arithmetic and joins, without claiming measurement completeness."""
    targets=data['targets']
    for key in ['shifts','shift_hours','critical_downtime_minutes','monthly_output']:
        value=targets[key]
        if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<=0:
            raise ValueError(f'Некорректная цель: {key}')
    if targets['shifts']*targets['shift_hours']>24:
        raise ValueError('Смены не могут занимать более 24 часов в сутки')
    for key in ['oee_percent','reject_percent']:
        if not 0<=targets[key]<=100:
            raise ValueError(f'Некорректная доля: {key}')
    quality={}
    for row in data['quality']:
        key=(row['date'],row['section'])
        if key in quality:raise ValueError('Повтор строки качества: '+str(key))
        produced,rejects=row['produced'],row['rejects']
        if type(produced) is not int or type(rejects) is not int or produced<=0 or not 0<=rejects<=produced:
            raise ValueError('Неверные объёмы качества: '+str(key))
        quality[key]=row
    seen=set()
    for row in data['production']:
        key=(row['date'],row['section'])
        if key in seen:raise ValueError('Повтор производственной строки: '+str(key))
        seen.add(key)
        if row['section'] not in SECTIONS or key not in quality:
            raise ValueError('Нет согласованной строки качества: '+str(key))
        if type(row['plan']) is not int or row['plan']<=0 or type(row['actual']) is not int or row['actual']<0:
            raise ValueError('Неверный план или факт: '+str(key))
        if quality[key]['produced']!=row['actual']:
            raise ValueError('Факт производства и объём качества не совпадают: '+str(key))
        if not math.isfinite(row['run_hours']) or row['run_hours']<=0 or not 0<=row['load_percent']<=100:
            raise ValueError('Неверное время работы или загрузка: '+str(key))
    if seen!=set(quality) or {section for _,section in seen}!=set(SECTIONS):
        raise ValueError('Производство и качество должны покрывать одинаковые участки и даты')
    for row in data['downtime']:
        if type(row['minutes']) is not int or row['minutes']<0:
            raise ValueError('Неверная длительность простоя')
    for row in data['monthly_plan']:
        if type(row['plan']) is not int or row['plan']<0:
            raise ValueError('Неверный месячный план')
    return {'status':'passed','production_rows':len(data['production']),'quality_rows':len(quality),
            'checks':['Уникальность строк по дате и участку','Совпадение факта производства и объёма качества',
                      'Брак не превышает обработанный объём','Положительное время работы и корректные доли',
                      'Неотрицательные простои и планы'],
            'note':'Арифметическая согласованность не подтверждает полноту журнала или достоверность измерений.'}


def load_case():
    data=json.loads((Path(__file__).parent / 'data/factory-case.json').read_text())
    validate_case(data)
    return data


def analyze(req: FactoryRequest):
    data = load_case()
    data_checks = validate_case(data)
    targets = data['targets']
    monthly_target = targets['monthly_output']
    shift_minutes = targets['shift_hours'] * 60
    if req.excluded_minutes_per_shift >= shift_minutes:
        raise ValueError('Перерывы должны быть короче смены')
    if set(req.ideal_cycle_minutes) - set(SECTIONS):
        raise ValueError('Неизвестный участок для идеального цикла')
    if any(not math.isfinite(v) or v <= 0 or v > 60 for v in req.ideal_cycle_minutes.values()):
        raise ValueError('Идеальный цикл должен быть больше 0 и не более 60 минут')
    rows = []
    planned_minutes = (shift_minutes - req.excluded_minutes_per_shift) * (1 if req.scope == 'shift' else targets['shifts']) if req.scope != 'unknown' else None
    for p in data['production']:
        q = next(q for q in data['quality'] if (q['date'], q['section']) == (p['date'], p['section']))
        quality = (q['produced'] - q['rejects']) / q['produced'] * 100
        reject = q['rejects'] / q['produced'] * 100
        availability = p['run_hours'] * 60 / planned_minutes * 100 if planned_minutes else None
        cycle = req.ideal_cycle_minutes.get(p['section'])
        performance = cycle * p['actual'] / (p['run_hours'] * 60) * 100 if cycle else None
        valid_time = availability is None or availability <= 100 + 1e-9
        valid = performance is None or performance <= 100 + 1e-9
        oee = availability * performance * quality / 10000 if availability is not None and performance is not None and valid and valid_time else None
        rows.append({**p, 'rejects': q['rejects'], 'good': q['produced'] - q['rejects'],
                     'reject_percent': reject, 'quality_percent': quality,
                     'plan_percent': p['actual'] / p['plan'] * 100,
                     'quality_breach': reject > data['targets']['reject_percent'],
                     'availability_percent': availability, 'performance_percent': performance,
                     'oee_percent': oee, 'oee_status': 'invalid_time' if not valid_time else 'invalid_cycle' if not valid else 'missing_inputs' if oee is None else 'below_target' if oee < targets['oee_percent'] else 'target_met'})
    summaries = []
    for section in SECTIONS:
        selected = [r for r in rows if r['section'] == section]
        produced = sum(r['actual'] for r in selected)
        rejects = sum(r['rejects'] for r in selected)
        # Integer reduction must bring the final aggregate rate to or below the requested target.
        allowed = math.floor(produced * req.target_reject_percent / 100 + 1e-9)
        summaries.append({'section': section, 'produced': produced, 'rejects': rejects,
                          'good': produced - rejects, 'reject_percent': rejects / produced * 100,
                          'quality_breach': rejects / produced * 100 > targets['reject_percent'],
                          'to_limit_rejects': max(0, rejects - math.floor(produced * data['targets']['reject_percent'] / 100 + 1e-9)),
                          'preventable_rejects_scenario': max(0, rejects - allowed)})
    downtime = []
    for d in data['downtime']:
        daily = sum(e['minutes'] for e in data['downtime'] if (e['equipment'], e['date']) == (d['equipment'], d['date']))
        downtime.append({**d, 'recorded_daily_minutes': daily, 'remaining_to_limit': targets['critical_downtime_minutes'] - daily,
                         'breach': daily > targets['critical_downtime_minutes'], 'near_limit': daily >= .8 * targets['critical_downtime_minutes']})
    assembly = next(s for s in summaries if s['section'] == 'Сборка')
    multiplier = targets['shifts'] if req.scope == 'shift' else 1 if req.scope == 'day' else None
    monthly = None
    invalid_time = any(row['oee_status']=='invalid_time' for row in rows)
    if multiplier and not invalid_time:
        days = len({r['date'] for r in rows if r['section'] == 'Сборка'})
        gross_per_day = assembly['produced'] / days * multiplier
        good_per_day = assembly['good'] / days * multiplier
        observed = [row for row in rows if row['section']=='Сборка']
        gross_range = [min(row['actual'] for row in observed)*multiplier*req.workdays, max(row['actual'] for row in observed)*multiplier*req.workdays]
        good_range = [min(row['good'] for row in observed)*multiplier*req.workdays, max(row['good'] for row in observed)*multiplier*req.workdays]
        monthly = {'sample_days':days,'gross_scenario_range':gross_range,'good_scenario_range':good_range,'gross_per_day': gross_per_day, 'good_at_assembly_per_day': good_per_day,
                   'gross_scenario': gross_per_day * req.workdays,
                   'good_at_assembly_scenario': good_per_day * req.workdays,
                   'gap_gross': max(0, monthly_target - gross_per_day * req.workdays),
                   'required_gross_per_day': monthly_target / req.workdays,
                   'required_days_at_current_gross': math.ceil(monthly_target / gross_per_day),
                   'required_days_at_current_good_assembly': math.ceil(monthly_target / good_per_day) if good_per_day else None}
    monthly_total = sum(p['plan'] for p in data['monthly_plan'])
    result = {'source': data['source'], 'data': data, 'data_checks':data_checks, 'planned_minutes':planned_minutes, 'params': req.model_dump(), 'rows': rows,
              'sections': summaries, 'downtime': downtime, 'assembly': assembly,
              'monthly_plan_total': monthly_total, 'monthly_plan_gap': max(0, monthly_target - monthly_total), 'monthly_plan_surplus':max(0,monthly_total-monthly_target),
              'monthly_scenario': monthly, 'monthly_status':'invalid_time' if invalid_time else 'calculated' if monthly else 'missing_scope', 'quality_breach_rows': sum(r['quality_breach'] for r in rows),
              'recorded_downtime_minutes': sum(d['minutes'] for d in data['downtime']),
              'limitations': [
                'Период строк (смена или сутки) не указан. Календарь рабочих дней не предоставлен.',
                'OEE — сценарная оценка: требует планового времени, идеального цикла и годных изделий; загрузка и выполнение плана не заменяют OEE.',
                'Объёмы последовательных участков нельзя складывать как уникальные автомобили.',
                '237 годных изделий на сборке — не подтверждённый выход склада: данные финального контроля отсутствуют.',
                'Журнал простоев содержит отдельные записи; полнота суток и критичность оборудования не подтверждены.',
                'Два дня наблюдений не подтверждают месячный прогноз, вероятность отказа или ML-модель.',
                'Агрегаты не содержат VIN, BOM и времени операций; исторические строки не калибруют VIN-симуляцию.',
              ]}
    result['report'] = factory_report(result)
    return result


def factory_report(r):
    lines = ['VIN-Twin · Анализ данных кейса', r['source'], 'Период: 01–02.10.2026',
             f"План моделей: {r['monthly_plan_total']} · цель: {r['data']['targets']['monthly_output']} · разрыв: {r['monthly_plan_gap']}",
             f"Сборка: {r['assembly']['produced']} обработано, {r['assembly']['rejects']} брак, {r['assembly']['good']} годных до финального контроля.",
             f"Нарушения качества: {r['quality_breach_rows']} из {len(r['rows'])} строк."]
    for s in r['sections']:
        lines.append(f"{s['section']}: {s['rejects']}/{s['produced']}, брак {s['reject_percent']:.2f}%; сценарий цели {r['params']['target_reject_percent']}% требует предотвратить {s['preventable_rejects_scenario']} дефектов при том же объёме.")
    for row in r['rows']:
        score = f"{row['oee_percent']:.2f}%" if row['oee_percent'] is not None else {"invalid_time":"время работы выше планового", "invalid_cycle":"несовместимый идеальный цикл", "missing_inputs":"недостаточно входов"}.get(row["oee_status"],row["oee_status"])
        lines.append(f"OEE {row['date']} / {row['line']}: {score}")
    lines.append(f"Допущения: период={r['params']['scope']}, рабочих дней={r['params']['workdays']}, перерывы на смену={r['params']['excluded_minutes_per_shift']} мин, идеальные циклы={r['params']['ideal_cycle_minutes']}")
    if r['monthly_scenario']:
        m = r['monthly_scenario']
        lines.append(f"Линейный сценарий: {m['gross_scenario']:.0f} обработанных на сборке; {m['good_at_assembly_scenario']:.0f} годных до финального контроля. Это не подтверждённый месячный прогноз.")
        lines.append(f"Чувствительность к темпу наблюдаемых дней: {m['gross_scenario_range'][0]:.0f}–{m['gross_scenario_range'][1]:.0f} обработанных; {m['good_scenario_range'][0]:.0f}–{m['good_scenario_range'][1]:.0f} годных на сборке. Это не доверительный интервал.")
        if m['required_days_at_current_good_assembly'] is None:
            lines.append('При текущем темпе нет годных изделий на сборке: цель по годному выпуску недостижима.')
    elif r['monthly_status']=='invalid_time':
        lines.append('Месячный сценарий не рассчитан: время работы выше планового. Уточните период строк и перерывы.')
    lines.append('Контроль таблиц: арифметическая согласованность пройдена; полнота измерений не подтверждена.')
    lines.extend(['Ограничения:', *r['limitations']])
    return '\n'.join(lines)

class FactoryChatRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True, allow_inf_nan=False)
    analysis: FactoryRequest = Field(default_factory=FactoryRequest)
    question: str = Field(min_length=1, max_length=600)


def case_explanation(req: FactoryChatRequest):
    r = analyze(req.analysis)
    question = req.question.lower()
    if any(w in question for w in ['oee', 'эффективност', 'загруз']):
        text = 'OEE = доступность × производительность × качество. Загрузка из таблицы и выполнение плана не заменяют OEE. '
        missing = [row for row in r['rows'] if row['oee_percent'] is None]
        if missing:
            text += 'Не рассчитан для части строк: уточните период, перерывы и идеальный цикл. Время работы выше планового или P выше 100% означает несовместимые входы; результат не обрезается искусственно. '
        else:
            text += 'По введённым допущениям: ' + '; '.join(f"{row['date']} {row['line']}: {row['oee_percent']:.2f}%" for row in r['rows']) + '. '
        intent = 'oee'
    elif any(w in question for w in ['план', '5500', '5 500', 'месяц']):
        text = f"Планы моделей дают {r['monthly_plan_total']}, разрыв до цели {r['data']['targets']['monthly_output']}: {r['monthly_plan_gap']} автомобилей. Дополнительный объём нужно распределить по моделям и проверить ресурсы. "
        if r['monthly_scenario']:
            m = r['monthly_scenario']
            text += f"При выбранном периоде {r['params']['scope']} и {r['params']['workdays']} рабочих днях линейный сценарий сборки даёт {m['gross_scenario']:.0f} обработанных, {m['good_at_assembly_scenario']:.0f} годных до финального контроля. Для валовой цели требуется {m['required_gross_per_day']:.1f} авто в сутки. Это экстраполяция двух дней, а не подтверждённый прогноз. "
        elif r['monthly_status']=='invalid_time':
            text += 'Месячный сценарий заблокирован: время работы выше планового. Уточните период строк и перерывы. '
        else:
            text += 'Месячную мощность не экстраполируем, пока неизвестен период строк. '
        intent = 'plan'
    elif any(w in question for w in ['просто', 'оборуд', 'риск', 'отказ']):
        if not r['downtime']:
            return {'answer':'Журнал простоев пуст. Это не подтверждает отсутствие остановок: нужны записи оборудования и время событий.', 'intent':'equipment', 'provider':'Проверенные правила и расчёты Python', 'params':r['params']}
        d = max(r['downtime'], key=lambda x: x['recorded_daily_minutes'])
        text = f"Ближе всего к лимиту {d['equipment']}: {d['recorded_daily_minutes']} минут в известной суточной записи; запас {d['remaining_to_limit']} минут до лимита {r['data']['targets']['critical_downtime_minutes']}. Причина: {d['reason']}. Проверить указанную причину остановки и полноту журнала. Критичность оборудования и длительности остальных остановок не подтверждены. По двум дням нельзя оценить вероятность будущего отказа. "
        intent = 'equipment'
    elif any(w in question for w in ['узк', 'потер', 'производит']):
        worst = min(r['rows'], key=lambda x: x['plan_percent'])
        text = f"Минимальное выполнение плана: {worst['line']} {worst['date']}, {worst['actual']}/{worst['plan']} ({worst['plan_percent']:.2f}%). Это кандидат для проверки, а не доказанное узкое место: отсутствуют межоперационные запасы, очереди, времена и VIN-связи. На окраске повышенный брак создаёт отдельную потерю качества. "
        intent = 'bottleneck'
    elif any(w in question for w in ['качеств','брак','дефект','окраск']):
        s = next(s for s in r['sections'] if s['section'] == 'Окраска')
        text = f"Окраска: {s['rejects']} дефектов из {s['produced']}, брак {s['reject_percent']:.2f}% против лимита {r['data']['targets']['reject_percent']}%. Для сценарной цели {r['params']['target_reject_percent']}% при том же объёме необходимо предотвратить минимум {s['preventable_rejects_scenario']} дефектов. Проверьте причины дефектов и контроль процесса; связь брака с заменой фильтра данными не установлена. Эффект нельзя складывать по участкам как уникальные автомобили. "
        intent = 'quality'
    else:
        intent='help'
        text='Поддерживаются вопросы о качестве, простоях, месячном плане, узких местах и OEE. Выберите готовый вопрос; ответы опираются на текущий расчёт и не являются свободным диалогом.'
    return {'answer': text, 'intent': intent, 'provider': 'Проверенные правила и расчёты Python', 'params': r['params']}
