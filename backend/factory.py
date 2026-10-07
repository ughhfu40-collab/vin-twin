"""Aggregate case analytics. Historical stage counts are never summed as cars."""
from pathlib import Path
import json
import math
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field

SECTIONS = ['Сварка', 'Окраска', 'Сборка']

class FactoryRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    scope: Literal['unknown', 'shift', 'day'] = 'unknown'
    workdays: int = Field(default=22, ge=1, le=31)
    ideal_cycle_minutes: dict[str, float] = Field(default_factory=dict)
    target_reject_percent: float = Field(default=2, ge=0, le=100)


def load_case():
    return json.loads((Path(__file__).parent / 'data/factory-case.json').read_text())


def analyze(req: FactoryRequest):
    data = load_case()
    if set(req.ideal_cycle_minutes) - set(SECTIONS):
        raise ValueError('Неизвестный участок для идеального цикла')
    if any(not math.isfinite(v) or v <= 0 or v > 60 for v in req.ideal_cycle_minutes.values()):
        raise ValueError('Идеальный цикл должен быть больше 0 и не более 60 минут')
    rows = []
    planned_minutes = 480 if req.scope == 'shift' else 960 if req.scope == 'day' else None
    for p in data['production']:
        q = next(q for q in data['quality'] if (q['date'], q['section']) == (p['date'], p['section']))
        quality = (q['produced'] - q['rejects']) / q['produced'] * 100
        reject = q['rejects'] / q['produced'] * 100
        availability = p['run_hours'] * 60 / planned_minutes * 100 if planned_minutes else None
        cycle = req.ideal_cycle_minutes.get(p['section'])
        performance = cycle * p['actual'] / (p['run_hours'] * 60) * 100 if cycle else None
        valid = performance is None or performance <= 100 + 1e-9
        oee = availability * performance * quality / 10000 if availability is not None and performance is not None and valid else None
        rows.append({**p, 'rejects': q['rejects'], 'good': q['produced'] - q['rejects'],
                     'reject_percent': reject, 'quality_percent': quality,
                     'plan_percent': p['actual'] / p['plan'] * 100,
                     'quality_breach': reject > data['targets']['reject_percent'],
                     'availability_percent': availability, 'performance_percent': performance,
                     'oee_percent': oee, 'oee_status': 'invalid_cycle' if not valid else 'missing_inputs' if oee is None else 'below_target' if oee < 85 else 'target_met'})
    summaries = []
    for section in SECTIONS:
        selected = [r for r in rows if r['section'] == section]
        produced = sum(r['actual'] for r in selected)
        rejects = sum(r['rejects'] for r in selected)
        # Integer reduction must bring the final aggregate rate to or below the requested target.
        allowed = math.floor(produced * req.target_reject_percent / 100 + 1e-9)
        summaries.append({'section': section, 'produced': produced, 'rejects': rejects,
                          'good': produced - rejects, 'reject_percent': rejects / produced * 100,
                          'quality_breach': rejects / produced * 100 > 2,
                          'to_limit_rejects': max(0, rejects - math.floor(produced * data['targets']['reject_percent'] / 100 + 1e-9)),
                          'preventable_rejects_scenario': max(0, rejects - allowed)})
    downtime = []
    for d in data['downtime']:
        daily = sum(e['minutes'] for e in data['downtime'] if (e['equipment'], e['date']) == (d['equipment'], d['date']))
        downtime.append({**d, 'recorded_daily_minutes': daily, 'remaining_to_limit': 60 - daily,
                         'breach': daily > 60, 'near_limit': daily >= 48})
    assembly = next(s for s in summaries if s['section'] == 'Сборка')
    multiplier = 2 if req.scope == 'shift' else 1 if req.scope == 'day' else None
    monthly = None
    if multiplier:
        days = len({r['date'] for r in rows if r['section'] == 'Сборка'})
        gross_per_day = assembly['produced'] / days * multiplier
        good_per_day = assembly['good'] / days * multiplier
        monthly = {'gross_per_day': gross_per_day, 'good_at_assembly_per_day': good_per_day,
                   'gross_scenario': gross_per_day * req.workdays,
                   'good_at_assembly_scenario': good_per_day * req.workdays,
                   'gap_gross': max(0, 5500 - gross_per_day * req.workdays),
                   'required_gross_per_day': 5500 / req.workdays,
                   'required_days_at_current_gross': math.ceil(5500 / gross_per_day),
                   'required_days_at_current_good_assembly': math.ceil(5500 / good_per_day)}
    monthly_total = sum(p['plan'] for p in data['monthly_plan'])
    result = {'source': data['source'], 'data': data, 'params': req.model_dump(), 'rows': rows,
              'sections': summaries, 'downtime': downtime, 'assembly': assembly,
              'monthly_plan_total': monthly_total, 'monthly_plan_gap': 5500 - monthly_total,
              'monthly_scenario': monthly, 'quality_breach_rows': sum(r['quality_breach'] for r in rows),
              'recorded_downtime_minutes': sum(d['minutes'] for d in data['downtime']),
              'limitations': [
                'Период строк (смена или сутки) не указан. Календарь рабочих дней не предоставлен.',
                'OEE требует планового времени, идеального цикла и годных изделий; загрузка и выполнение плана не заменяют OEE.',
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
             f"План моделей: {r['monthly_plan_total']} · цель: 5500 · разрыв: {r['monthly_plan_gap']}",
             f"Сборка: {r['assembly']['produced']} обработано, {r['assembly']['rejects']} брак, {r['assembly']['good']} годных до финального контроля.",
             f"Нарушения качества: {r['quality_breach_rows']} из 6 строк."]
    for s in r['sections']:
        lines.append(f"{s['section']}: {s['rejects']}/{s['produced']}, брак {s['reject_percent']:.2f}%; сценарий цели {r['params']['target_reject_percent']}% требует предотвратить {s['preventable_rejects_scenario']} дефектов при том же объёме.")
    for row in r['rows']:
        score = f"{row['oee_percent']:.2f}%" if row['oee_percent'] is not None else row['oee_status']
        lines.append(f"OEE {row['date']} / {row['line']}: {score}")
    lines.append(f"Допущения: период={r['params']['scope']}, рабочих дней={r['params']['workdays']}, идеальные циклы={r['params']['ideal_cycle_minutes']}")
    if r['monthly_scenario']:
        m = r['monthly_scenario']
        lines.append(f"Линейный сценарий: {m['gross_scenario']:.0f} обработанных на сборке; {m['good_at_assembly_scenario']:.0f} годных до финального контроля. Это не подтверждённый месячный прогноз.")
    lines.extend(['Ограничения:', *r['limitations']])
    return '\n'.join(lines)

class FactoryChatRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    analysis: FactoryRequest = Field(default_factory=FactoryRequest)
    question: str = Field(min_length=1, max_length=600)


def case_explanation(req: FactoryChatRequest):
    r = analyze(req.analysis)
    question = req.question.lower()
    if any(w in question for w in ['oee', 'эффективност', 'загруз']):
        text = 'OEE = доступность × производительность × качество. Загрузка из таблицы и выполнение плана не заменяют OEE. '
        missing = [row for row in r['rows'] if row['oee_percent'] is None]
        if missing:
            text += 'Не рассчитан для части строк: выберите период строк и задайте идеальный цикл. P выше 100% означает несовместимый идеальный цикл; результат не обрезается искусственно. '
        else:
            text += 'По введённым допущениям: ' + '; '.join(f"{row['date']} {row['line']}: {row['oee_percent']:.2f}%" for row in r['rows']) + '. '
        intent = 'oee'
    elif any(w in question for w in ['план', '5500', '5 500', 'месяц']):
        text = f"Планы моделей дают {r['monthly_plan_total']}, до цели 5500 не хватает {r['monthly_plan_gap']} автомобилей. Дополнительный объём нужно распределить по моделям и проверить ресурсы. "
        if r['monthly_scenario']:
            m = r['monthly_scenario']
            text += f"При выбранном периоде {r['params']['scope']} и {r['params']['workdays']} рабочих днях линейный сценарий сборки даёт {m['gross_scenario']:.0f} обработанных, {m['good_at_assembly_scenario']:.0f} годных до финального контроля. Для валовой цели требуется {m['required_gross_per_day']:.1f} авто в сутки. Это экстраполяция двух дней, а не подтверждённый прогноз. "
        else:
            text += 'Месячную мощность не экстраполируем, пока неизвестен период строк. '
        intent = 'plan'
    elif any(w in question for w in ['просто', 'оборуд', 'риск', 'отказ']):
        d = max(r['downtime'], key=lambda x: x['recorded_daily_minutes'])
        text = f"Ближе всего к лимиту {d['equipment']}: {d['recorded_daily_minutes']} минут в известной суточной записи; запас {d['remaining_to_limit']} минут до лимита 60. Причина: {d['reason']}. Проверить цепь и полноту журнала. Критичность оборудования и длительности остальных остановок не подтверждены. По двум дням нельзя оценить вероятность будущего отказа. "
        intent = 'equipment'
    elif any(w in question for w in ['узк', 'потер', 'производит']):
        worst = min(r['rows'], key=lambda x: x['plan_percent'])
        text = f"Минимальное выполнение плана: {worst['line']} {worst['date']}, {worst['actual']}/{worst['plan']} ({worst['plan_percent']:.2f}%). Это кандидат для проверки, а не доказанное узкое место: отсутствуют межоперационные запасы, очереди, времена и VIN-связи. На окраске повышенный брак создаёт отдельную потерю качества. "
        intent = 'bottleneck'
    else:
        s = next(s for s in r['sections'] if s['section'] == 'Окраска')
        text = f"Окраска: {s['rejects']} дефектов из {s['produced']}, брак {s['reject_percent']:.2f}% против лимита 2%. Для сценарной цели {r['params']['target_reject_percent']}% при том же объёме необходимо предотвратить минимум {s['preventable_rejects_scenario']} дефектов. Проверьте причины дефектов и контроль процесса; связь брака с заменой фильтра данными не установлена. Эффект нельзя складывать по участкам как уникальные автомобили. "
        intent = 'quality'
    return {'answer': text, 'intent': intent, 'provider': 'Проверенные правила и расчёты Python', 'params': r['params']}
