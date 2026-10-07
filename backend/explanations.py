import re
from .engine import clock, STATIONS, POLICIES

INTENTS = {'risk':['waits','eta','incidents'], 'cause':['waits','eta','incidents'], 'vins':['affected','after_shift'],
           'vehicle':['vehicle'], 'action':['recommendation','policies'], 'change':['comparison','recommendation','policies'],
           'economics':['sensitivity','thresholds'], 'assumptions':['assumptions']}

def classify(question):
    q=question.lower()
    if re.search(r'(?:vin|вин)[\s-]*(\d{1,3})\b',q):return 'vehicle'
    if any(x in q for x in ['допущ','огранич','модель']): return 'assumptions'
    if any(x in q for x in ['вклад','марж','порог','чувствитель','экономик']):return 'economics'
    if any(x in q for x in ['vin','вин','затрон']): return 'vins'
    if any(x in q for x in ['измен','помен']): return 'change'
    if any(x in q for x in ['выгод','действ','лучше','рекоменд','делать','политик','выбрать']): return 'action'
    if any(x in q for x in ['почему','причин']): return 'cause'
    if any(x in q for x in ['риск','останов','когда','ожидан','задерж','постав','сбой','простой']):return 'risk'
    return 'assumptions'

def comparison(current,previous):
    if not previous:
        return {'available':False,'detail':'Предыдущий снимок не выбран или истёк. Причину изменения нельзя подтвердить; текущая рекомендация рассчитана по доступным условиям.'}
    changes=[]
    labels={'delay':'задержка поставки, мин','robot_minutes':'длительность сбоя, мин','robot_start':'начало сбоя, мин от 08:00',
            'contribution':'вклад автомобиля, ₸','decision_time':'время решения, мин от 08:00','eta_override':'срок партии, мин от 08:00','policy':'выбранная политика'}
    for key,label in labels.items():
        old,new=previous['params'].get(key),current['params'].get(key)
        if old!=new:changes.append(f'{label}: {old if old is not None else "по плану"} → {new if new is not None else "по плану"}')
    if previous['input_version']!=current['input_version']:changes.append('изменился набор входных данных или событий')
    return {'available':True,'previous_snapshot_id':previous['snapshot_id'],'old_recommendation':previous['recommended'],
            'new_recommendation':current['recommended'],'old_policies':previous['policies'],'changes':changes}

def render(intent,s,time=120):
    facts=s['facts']
    if intent in ['risk','cause']:
        waits=facts['waits']
        text=(f"Сборка-1 ожидает комплект {waits[0]['kit']} с {clock(waits[0]['start'])} до {clock(waits[0]['end'])}: начальный запас исчерпан, партия ещё не доступна. " if waits else 'Ожидания материала в выбранной политике нет. ')
        if s['params']['robot_minutes']:
            incident=next((i for i in s['incidents'] if i['id']=='robot'),None)
            text+=f"Сварка недоступна с {clock(s['params'].get('robot_start',150))} на {s['params']['robot_minutes']} мин. "
            text+=('Это полученный демонстрационный факт. ' if incident and incident['type']=='fact' else 'Это сценарное условие, не ML-прогноз. ')
        return text+f"Прогноз выпуска — {facts['output']}, план — {facts['plan']}."
    if intent=='vehicle':
        v=facts['vehicle']
        if not v:return 'Такого VIN в текущем наборе нет. Используйте VIN-001…080.'
        route='; '.join(f"{STATIONS[o['station']]} {clock(o['start'])}–{clock(o['end'])}" for o in v['operations'])
        waits=[f"комплект {v['kit']}: {clock(o['material_wait'][0])}–{clock(o['material_wait'][1])}" for o in v['operations'] if o['material_wait']]
        active=next((o for o in v['operations'] if o['end']>time),None)
        state='Завершён' if not active else f"{STATIONS[active['station']]}: "+('обработка или пауза оборудования' if active['start']<=time else 'ожидает начало операции')
        return f"{v['id']} · комплект {v['kit']}. В {clock(time)}: {state}. Завершение {clock(v['completion'])}, штатно {clock(v['baseline_completion'])}, изменение {v['delay_minutes']} мин. Ожидание материала: {', '.join(waits) or 'прямого ожидания нет; задержка может передаваться от предыдущих VIN'}. Маршрут: {route}."
    if intent=='vins':
        ids=facts['affected']
        return f"Затронуто задержкой {len(ids)} VIN: {', '.join(ids) or 'нет'}. После смены завершатся {len(facts['after_shift'])} VIN. Это отдельные показатели; недовыпуск относительно плана — {facts['deficit']}."
    if intent=='economics':
        pairs='; '.join(f"{POLICIES[t['left']][0]} / {POLICIES[t['right']][0]}: одинаковый эффект при вкладе {t['contribution']:,.0f} ₸" for t in facts['thresholds'])
        examples='; '.join(f"вклад {r['contribution']:,} ₸ → {POLICIES[r['recommended']][0]}" for r in facts['sensitivity'])
        return f"Выбор зависит от вклада автомобиля, а не только от выпуска. {pairs or 'При этих результатах положительных порогов переключения нет'}. {examples}. Вклад — демонстрационное допущение; оценка не подтверждённая прибыль."
    if intent=='change':
        c=facts['comparison']
        if not c['available']:return c['detail']+' '+render('action',s,time)
        old,new=c['old_recommendation'],c['new_recommendation']
        oldrow=next(p for p in c['old_policies'] if p['policy']==old)
        newrow=next(p for p in s['policies'] if p['policy']==new)
        text=f"Рекомендация {'изменилась' if old!=new else 'сохранилась'}: {POLICIES[old][0]} → {POLICIES[new][0]}. "
        text+='Изменения условий: '+('; '.join(c['changes']) or 'значимых изменений нет')+'. '
        text+=f"Ранее лучший условный эффект {oldrow['effect']:,} ₸; сейчас {newrow['effect']:,} ₸. "
        if old!=new:
            current_old=next(p for p in s['policies'] if p['policy']==old)
            text+=f"Прежний вариант в новых условиях: {current_old['effect']:,} ₸. " if current_old['available'] else f"Прежний вариант недоступен: {current_old['reason']} "
        return text+render('action',s,time)
    if intent=='action':
        r=next(p for p in facts['policies'] if p['policy']==facts['recommendation'])
        comparison_text='; '.join(f"{p['name']}: {p['output']} автомобилей, спасено {p['saved']}, эффект {p['effect']:,} ₸" for p in facts['policies'] if p['available'])
        return f"Рекомендация: {r['name']}. Ранжирование — максимум условного эффекта при тех же сбоях. {comparison_text}. Эффект относится к текущей смене и не является подтверждённой прибылью."
    return '\n'.join(facts['assumptions'])

async def explain(question,s,previous=None,time=120):
    # Request-specific facts are separate from the immutable production snapshot.
    s={**s,'facts':{**s['facts']}}
    s['facts']['incidents']=s['incidents']
    s['facts']['comparison']=comparison(s,previous)
    match=re.search(r'(?:vin|вин)[\s-]*(\d{1,3})\b',question.lower())
    id=f"VIN-{int(match.group(1)):03d}" if match else None
    s['facts']['vehicle']=next((v for v in s['vehicles'] if v['id']==id),None)
    intent=classify(question)
    return {'snapshot_id':s['snapshot_id'],'previous_snapshot_id':previous['snapshot_id'] if previous else None,
            'intent':intent,'fact_refs':INTENTS[intent], 'source_mode':'local','answer':render(intent,s,time)}
