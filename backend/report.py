from .engine import clock, POLICIES

def report(s,t):
    f=s['frames'][t]
    current=next(p for p in s['policies'] if p['policy']==s['params']['policy'])
    lines=['VIN-Twin · Передача смены','Демонстрационные данные',f"Снимок: {s['snapshot_id']}",f"Данные: {s['source']} · {s['updated_at']}",f"Версия входов: {s['input_version']} · модель {s['model_version']}",f"Выбранное время: {clock(t)} · {'Прогноз' if t>s['now'] else 'Реконструкция факта'}",'',f"Выпуск к выбранному времени: {f['actual_output']}",f"Прогноз на 16:00: {s['output']} · план {s['plan']} · недовыпуск {max(0,s['plan']-s['output'])}",f"Теоретическая мощность: {s['capacity']} · штатный выпуск: {s['baseline_output']}",f"Остатки A/B: {f['inventory']['A']}/{f['inventory']['B']} · ETA: {clock(s['eta'])}",'','Инциденты:']
    lines += [f"• {i['title']}: {i['detail']} Источник: {i['source']} ({'факт' if i['type']=='fact' else 'сценарное допущение'})." for i in s['incidents']] or ['Нет инцидентов.']
    lines += ['',f"Затронутые VIN ({len(s['affected'])}): {', '.join(s['affected']) or 'нет'}",f"После смены ({len(s['after_shift'])}): {', '.join(s['after_shift'])}",'','Сравнение действий:']
    lines += [f"• {p['name']}: выпуск {p['output']}, спасено {p['saved']}, затраты {p['cost']:,} ₸, условный эффект {p['effect']:,} ₸." if p['available'] else f"• {p['name']}: недоступно. {p['reason']}" for p in s['policies']]
    lines += ['', 'Чувствительность экономики:']
    lines += [f"• Вклад {r['contribution']:,} ₸: {POLICIES[r['recommended']][0]}." for r in s['sensitivity']]
    lines += ['',f"Выбрана политика: {current['name']}",f"Затраты: {current['cost']:,} ₸ · эффект: {current['effect']:,} ₸",'Действие применено только к сценарию; поручение на завод не отправлено.','','Допущения и ограничения:']+s['assumptions']
    return {'snapshot_id':s['snapshot_id'],'text':'\n'.join(lines)}
