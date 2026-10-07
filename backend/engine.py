"""Deterministic six-resource flow-shop, with pausable operations and batch inventory."""
from __future__ import annotations
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

STATIONS = ['Сварка', 'Покраска', 'Сборка-1', 'Сборка-2', 'Контроль', 'Выпуск']
POLICIES = {'none': ('Ничего не делать', 0), 'delivery': ('Срочная доставка', 380000), 'reorder': ('Перестановка VIN', 90000)}
DATA_PATH = Path(__file__).parent / 'data' / 'demo.json'

def load_data():
    return json.loads(DATA_PATH.read_text())

def clock(t):
    return f'{8 + int(t)//60:02d}:{int(t)%60:02d}'

def resolve_events(events, received_until):
    """Canonical received events; conflicting duplicate IDs are rejected."""
    by_id = {}
    for event in events:
        if event['id'] in by_id and by_id[event['id']] != event:
            raise ValueError(f"Конфликт события {event['id']}: один ID содержит разные данные")
        by_id[event['id']] = event
    return sorted((e for e in by_id.values() if e['received_at'] <= received_until),
                  key=lambda e: (e['received_at'], e['occurred_at'], e['id']))

def apply_events(data, events, received_until=120):
    result = deepcopy(data)
    for event in resolve_events(events, received_until):
        if event['event_type'] == 'eta_updated':
            result['supply']['eta'] = event['payload']['eta']
        elif event['event_type'] == 'batch_received':
            result['supply']['eta'] = event['occurred_at']
    return result

def reordered_orders(data):
    # Modify only the positions belonging to the permitted subset. Other VIN
    # keep their position even when an imported queue differs from the demo.
    target = [f'VIN-{n:03d}' for n in list(range(55,61))+list(range(49,55))]
    moved = set(target)
    by_id = {v['id']:v for v in data['orders']}
    replacements = iter(by_id[id] for id in target)
    return [next(replacements) if v['id'] in moved else v for v in data['orders']]


def process(start, duration, downtime):
    """[start,end) downtime; work ending at outage start is not interrupted."""
    a, b = downtime
    if b <= a:
        return start, start+duration, [[start,start+duration]]
    if a <= start < b:
        start = b
    end = start + duration
    segments = [[start, end]]
    if start < a < end:
        end += b-a
        segments = [[start, a], [b, end]]
    return start, end, segments

def policy_availability(params, data):
    decision = params['decision_time']
    base = schedule({**params, 'policy': 'none'}, data, check=False)
    proposed = reordered_orders(data)
    changed = {old['id'] for old,new in zip(data['orders'],proposed) if old['id'] != new['id']}
    started = any(v['id'] in changed and v['operations'][0]['start'] < decision for v in base['vehicles'])
    return {
        'none': {'available': True, 'reason': ''},
        'delivery': {'available': decision <= 320, 'reason': '' if decision <= 320 else 'Подтверждённый срок 13:20 уже прошёл: требуется новое предложение перевозчика.'},
        'reorder': {'available': data['reorder_allowed'] and not started, 'reason': '' if data['reorder_allowed'] and not started else 'Перестановка запрещена данными или часть VIN-049…060 уже начала маршрут.'},
    }

def schedule(params, data=None, check=True):
    data = data or load_data()
    policy = params.get('policy', 'none')
    if check and policy != 'none':
        availability = policy_availability(params, data)[policy]
        if not availability['available']:
            raise ValueError(availability['reason'])
    eta = params.get('eta_override')
    if eta is None:
        eta = data['supply']['eta'] + params['delay']
    if policy == 'delivery':
        eta = min(eta, 320)
        if eta < params['decision_time']:
            # A batch already received is immutable; accelerating it cannot change history.
            eta = params.get('eta_override')
    if eta is None:
        eta = data['supply']['eta'] + params['delay']
    orders = list(data['orders'])
    if policy == 'reorder':
        orders = reordered_orders(data)
    available = [0]*6
    used = {'A': 0, 'B': 0}
    vehicles, consumption, material_waits = [], [], []
    robot_start = params.get('robot_start',150)
    downtime = (robot_start, robot_start+params['robot_minutes'])
    for order in orders:
        ops = []
        previous = 0
        for k in range(6):
            resource_ready = available[k]
            candidate = max(previous, resource_ready)
            material_ready = 0
            wait = None
            if k == 2:
                kit = order['kit']
                if used[kit] >= data['inventory'][kit]:
                    if kit != data['supply']['kit'] or used[kit] >= data['inventory'][kit] + data['supply']['quantity']:
                        raise ValueError(f'Недостаточно комплектов {kit} даже после поставки')
                    material_ready = eta
                if material_ready > candidate:
                    wait = [candidate, material_ready]
                    material_waits.append({'vin': order['id'], 'station': k, 'start': candidate, 'end': material_ready, 'kit': kit})
                candidate = max(candidate, material_ready)
            start, end, segments = process(candidate, 6, downtime if k == 0 else (0,0))
            if k == 2:
                used[order['kit']] += 1
                consumption.append({'vin': order['id'], 'kit': order['kit'], 'time': start})
            ops.append({'station': k, 'start': start, 'end': end, 'segments': segments, 'previous_ready': previous,
                        'resource_ready': resource_ready, 'material_wait': wait})
            available[k] = end
            previous = end
        vehicles.append({**order, 'operations': ops, 'completion': previous})
    return {'vehicles': vehicles, 'consumption': consumption, 'material_waits': material_waits, 'eta': eta,
            'output': sum(v['completion'] <= 480 for v in vehicles)}

def station_frame(result, t, params):
    frames = []
    for k, name in enumerate(STATIONS):
        ops = [(v, v['operations'][k]) for v in result['vehicles']]
        active = next(((v,o) for v,o in ops if o['start'] <= t < o['end']), None)
        queue = [v['id'] for v,o in ops if o['previous_ready'] <= t < o['start']]
        work = sum(max(0, min(t,b)-a) for _,o in ops for a,b in o['segments'] if a < t)
        status, label, vin = 'idle', 'Нет входных VIN', None
        if k == 0 and params.get('robot_start',150) <= t < params.get('robot_start',150)+params['robot_minutes']:
            status, label = 'down', 'Робот недоступен'
            vin = active[0]['id'] if active else None
        elif active:
            status, label, vin = 'processing', 'Обработка', active[0]['id']
        elif any(w['station'] == k and w['start'] <= t < w['end'] for w in result['material_waits']):
            wait = next(w for w in result['material_waits'] if w['station']==k and w['start'] <= t < w['end'])
            status, label = 'material', f"Ожидание комплекта {wait['kit']}"
        elif queue:
            status, label = 'resource', 'Ожидание ресурса'
        frames.append({'name': name, 'status': status, 'label': label, 'vin': vin, 'queue': queue,
                       'utilization': round(100*work/t,1) if t else None})
    return frames

def inventory_at(result, data, t):
    inventory = dict(data['inventory'])
    if t >= result['eta']:
        inventory[data['supply']['kit']] += data['supply']['quantity']
    for item in result['consumption']:
        if item['time'] <= t:
            inventory[item['kit']] -= 1
    return inventory

def snapshot(params, data=None):
    data = data or load_data()
    availability = policy_availability(params, data)
    results = {p: schedule({**params, 'policy': p}, data) for p in POLICIES if availability[p]['available']}
    if params['policy'] not in results:
        raise ValueError(availability[params['policy']]['reason'])
    chosen, no_action = results[params['policy']], results['none']
    baseline = schedule({**params, 'delay': 0, 'robot_minutes': 0, 'eta_override':None, 'policy': 'none'}, data)
    baseline_by_id = {v['id']: v for v in baseline['vehicles']}
    rows = []
    for policy, (name, cost) in POLICIES.items():
        r = results.get(policy)
        saved = r['output'] - no_action['output'] if r else None
        rows.append({'policy': policy, 'name': name, 'cost': cost, 'output': r['output'] if r else None,
                     'saved': saved, 'effect': saved*params['contribution']-cost if r else None, **availability[policy]})
    recommended = max((r for r in rows if r['available']), key=lambda r: (r['effect'], -r['cost']))['policy']
    for v in chosen['vehicles']:
        b = baseline_by_id[v['id']]
        v['baseline_completion'] = b['completion']
        v['delay_minutes'] = v['completion']-b['completion']
        v['affected'] = any(o['end'] > bo['end'] for o,bo in zip(v['operations'],b['operations']))
    affected = [v['id'] for v in chosen['vehicles'] if v['affected']]
    after_shift = [v['id'] for v in chosen['vehicles'] if v['completion'] > 480]
    frames = [{'time': t, 'actual_output': sum(v['completion'] <= t for v in chosen['vehicles']),
               'inventory': inventory_at(chosen, data, t), 'stations': station_frame(chosen,t,params)} for t in range(481)]
    incidents = []
    kit = data['supply']['kit']
    if params['delay'] or params.get('eta_override') is not None:
        incidents.append({'id': 'eta', 'title': f'Срок поставки {kit}', 'type': 'assumption', 'received_at': params['decision_time'],
                          'source': 'Условие сценария', 'detail': f"ETA {clock(chosen['eta'])}; плановый срок {clock(data['supply']['eta'])}."})
    if params['robot_minutes']:
        robot_start = params.get('robot_start',150)
        incidents.append({'id': 'robot', 'title': 'Недоступность робота сварки', 'type': 'assumption', 'received_at': params['decision_time'],
                          'source': 'Условие сценария', 'detail': f"{clock(robot_start)}–{clock(robot_start+params['robot_minutes'])}; не ML-прогноз."})
    sensitivity = []
    contributions = sorted(set([0,50000,100000,145000,250000,650000,1000000,params['contribution']]))
    for contribution in contributions:
        effects = {p['policy']:p['saved']*contribution-p['cost'] for p in rows if p['available']}
        winner = max((p for p in rows if p['available']),key=lambda p:(effects[p['policy']],-p['cost']))
        sensitivity.append({'contribution':contribution,'recommended':winner['policy'],'effects':effects})
    thresholds = []
    valid = [p for p in rows if p['available']]
    for i,a in enumerate(valid):
        for b in valid[i+1:]:
            if a['saved'] != b['saved']:
                threshold = (a['cost']-b['cost'])/(a['saved']-b['saved'])
                if threshold >= 0:
                    thresholds.append({'left':a['policy'],'right':b['policy'],'contribution':round(threshold,2)})
    facts = {'output': chosen['output'], 'baseline': baseline['output'], 'plan': data['plan'],
             'deficit': max(0,data['plan']-chosen['output']), 'affected': affected, 'after_shift': after_shift,
             'eta': chosen['eta'], 'waits': chosen['material_waits'], 'recommendation': recommended, 'policies': rows,
             'assumptions': data['assumptions'], 'sensitivity':sensitivity, 'thresholds':thresholds}
    version = sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()[:12]
    return {'params': params, 'input_version': version, 'model_version': '1.1.0', 'source': 'Демонстрационный набор JSON v1',
            'updated_at': '2026-10-06T10:00:00+05:00', 'now': 120, 'capacity': 80, 'baseline_output': baseline['output'],
            'plan': data['plan'], 'supply': data['supply'], **chosen, 'affected': affected, 'after_shift': after_shift, 'policies': rows,
            'recommended': recommended, 'sensitivity':sensitivity, 'thresholds':thresholds, 'incidents': incidents, 'frames': frames, 'facts': facts, 'assumptions': data['assumptions']}
