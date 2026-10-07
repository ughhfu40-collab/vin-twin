"use client";
import Link from "next/link";
import { useState } from "react";

const tabs = ["О проекте", "Возможности", "Как работает"];
const content = [
  [["Весь завод в одной картине", "Производственный поток от комплектующих до готового автомобиля. Понятные показатели для каждого участка."], ["Решения с опорой на данные", "Качество, простои и план показывают, где теряется выпуск и какие условия нужно уточнить."], ["Сценарий до действия", "Отдельная VIN-симуляция сравнивает последствия задержки поставки и остановки оборудования."]],
  [["Аналитика завода", "Шесть вкладок: обзор, качество, оборудование, план и OEE, диспетчер, исходные данные."], ["VIN-симуляция", "Паспорт автомобиля, комплектность деталей, расписание постов и сравнение вариантов восстановления выпуска."], ["Объяснения и отчёты", "Диспетчер объясняет расчёты. Отчёт сохраняет результаты текущего сценария и принятые допущения."]],
  [["Изучите исходные данные", "Откройте панель завода: в основе — тестовые таблицы кейса за 1–2 октября 2026 года."], ["Уточните параметры", "Выберите период учёта и рабочие дни. Для OEE задайте идеальный цикл каждого участка."], ["Сравните последствия", "В VIN-симуляции включите сбой, сравните решения диспетчера и сохраните отчёт для обсуждения."]],
];
export default function HomeContent() {
  const [active, setActive] = useState(0);
  return <div className="landing">
    <header className="land-header"><Link href="/" className="land-brand" aria-label="VIN-Twin, главная"><b>V:</b><span>VIN<span>TWIN</span></span></Link><span className="land-case">Кейс №2 · АЛЛЮР</span><Link href="/factory" className="land-open">Открыть панель ↗</Link></header>
    <main className="landing-main">
      <section className="land-hero"><div><p className="land-kicker">ЦИФРОВОЙ ДВОЙНИК ЗАВОДА</p><h1>Увидеть сбой.<br/><span>Сохранить выпуск.</span></h1><p className="land-description">VIN-Twin объединяет качество, оборудование и производственный план. Помогает увидеть потери и сравнить решения до их применения.</p><div className="land-actions"><Link href="/factory" className="land-primary">Аналитика завода →</Link><Link href="/dashboard" className="land-secondary">VIN-симуляция</Link></div><p className="land-caption">Учебный MVP · тестовые данные кейса</p></div>
      <div className="land-map" aria-label="Производственный поток"><div className="land-map-heading"><span>ПРОИЗВОДСТВЕННЫЙ ПОТОК</span><span>06 участков</span></div><ol>{["Комплектующие", "Сварка", "Окраска", "Сборка", "Контроль качества", "Готовая продукция"].map((name,i)=><li key={name}><span className="land-node">{String(i+1).padStart(2,"0")}</span><span>{name}</span><span className="land-node-arrow" aria-hidden="true">{i<5?"↓":"✓"}</span></li>)}</ol><div className="land-map-footer">Данные → расчёт → решение</div></div></section>
      <section aria-label="Описание проекта"><div className="land-tabs" role="tablist" aria-label="О VIN-Twin">{tabs.map((label,i)=><button key={label} id={`home-tab-${i}`} role="tab" aria-selected={active===i} aria-controls={`home-panel-${i}`} tabIndex={active===i?0:-1} onClick={()=>setActive(i)} onKeyDown={e=>{let next=i;if(e.key==="ArrowRight")next=(i+1)%3;else if(e.key==="ArrowLeft")next=(i+2)%3;else if(e.key==="Home")next=0;else if(e.key==="End")next=2;else return;e.preventDefault();setActive(next);document.getElementById(`home-tab-${next}`)?.focus();}}>{label}</button>)}</div>{content.map((cards,i)=><div className="land-cards" role="tabpanel" id={`home-panel-${i}`} aria-labelledby={`home-tab-${i}`} key={i} hidden={active!==i}>{cards.map(([title,text],n)=><article key={title}><small>0{n+1}</small><h2>{title}</h2><p>{text}</p></article>)}</div>)}</section>
    </main><footer className="land-footer"><span>VIN-Twin / 2026</span><span>Аналитика кейса и синтетическая VIN-модель</span><Link href="/factory">Перейти к данным ↗</Link></footer>
  </div>;
}
