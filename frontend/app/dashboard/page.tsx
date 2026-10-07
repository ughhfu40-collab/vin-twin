"use client";
import { useEffect, useRef, useState } from "react";
import type { Params, Policy, Snapshot, Chat } from "../types";
import { Icon, Metric, OutputChart } from "../components";
import { clock, n } from "../format";
import { api, download } from "../services";
import { vinState } from "../timeline";
const presets = [
  { name: "Штатная смена", delay: 0, robot_minutes: 0, robot_start: 150 },
  { name: "Задержка поставки", delay: 100, robot_minutes: 0, robot_start: 150 },
  { name: "Отказ робота", delay: 0, robot_minutes: 40, robot_start: 150 },
  { name: "Оба сбоя", delay: 100, robot_minutes: 40, robot_start: 150 },
];
const initial: Params = {
  delay: 0,
  robot_minutes: 0,
  policy: "none",
  decision_time: 120,
  contribution: 650000,
};
export default function Dashboard() {
  const [tab, setTab] = useState("overview");
  const [params, setParams] = useState<Params>(initial);
  const [snap, setSnap] = useState<Snapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [time, setTime] = useState(120);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(6);
  const [theme, setTheme] = useState("dark");
  const [search, setSearch] = useState("");
  const [filter, setFilter] = useState("all");
  const [selected, setSelected] = useState<string | null>(null);
  const [station, setStation] = useState<number | null>(null);
  const [panel, setPanel] = useState<"chat" | "report" | null>(null);
  const [question, setQuestion] = useState("Какое действие выгоднее?");
  const [chat, setChat] = useState<Chat | null>(null);
  const [report, setReport] = useState("");
  const [panelBusy, setPanelBusy] = useState(false);
  const [panelError, setPanelError] = useState("");
  const [notice, setNotice] = useState("");
  const [customData, setCustomData] = useState<unknown>();
  const [events, setEvents] = useState<unknown[]>([]);
  const [replay, setReplay] = useState<number | null>(null);
  const sequence = useRef(0);
  const abort = useRef<AbortController | null>(null);
  const liveSnapshot = useRef("");
  const activeSnapshot = useRef("");
  const previousSnapshot = useRef("");
  const focusReturn = useRef<HTMLElement | null>(null);
  const drawerRef = useRef<HTMLElement | null>(null);
  const imported = useRef(customData);
  imported.current = customData;
  async function calculate(
    p: Params,
    data: unknown = imported.current,
    replayTime: number | null = null,
    basis: string | null = null,
  ) {
    const id = ++sequence.current;
    abort.current?.abort();
    const c = new AbortController();
    abort.current = c;
    setLoading(true);
    liveSnapshot.current = "";
    setError("");
    setPanelBusy(false);
    setPanelError("");
    setChat(null);
    setReport("");
    try {
      const s = await api<Snapshot>(
        "simulate",
        basis
          ? { basis_snapshot_id: basis, policy: p.policy }
          : {
              delay: p.delay,
              robot_minutes: p.robot_minutes,
              robot_start: p.robot_start ?? 150,
              eta_override: p.eta_override ?? null,
              policy: p.policy,
              decision_time: p.decision_time,
              contribution: p.contribution,
              ...(data ? { data } : {}),
              ...(replayTime !== null
                ? { events, received_until: replayTime }
                : {}),
            },
        c.signal,
      );
      if (id !== sequence.current) return false;
      previousSnapshot.current = activeSnapshot.current;
      activeSnapshot.current = s.snapshot_id;
      liveSnapshot.current = s.snapshot_id;
      setSnap(s);
      setParams(s.params);
      return true;
    } catch (e) {
      if ((e as Error).name !== "AbortError" && id === sequence.current)
        setError((e as Error).message);
      return false;
    } finally {
      if (id === sequence.current) setLoading(false);
    }
  }
  useEffect(() => {
    const query = new URLSearchParams(window.location.search);
    const view = query.get("view");
    if (view && ["overview", "scenarios", "vin"].includes(view)) setTab(view);
    const start =
      query.get("scenario") === "delay" ? { ...initial, delay: 100 } : initial;
    calculate(start);
    api<{ events: unknown[] }>("state")
      .then((x) => setEvents(x.events))
      .catch(() => {});
    const saved = localStorage.getItem("vin-theme");
    if (saved) setTheme(saved);
    return () => abort.current?.abort();
  }, []); // initial load only
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem("vin-theme", theme);
  }, [theme]);
  useEffect(() => {
    if (!playing) return;
    const timer = setInterval(
      () =>
        setTime((t) => {
          if (t + speed >= 480) {
            setPlaying(false);
            return 480;
          }
          return t + speed;
        }),
      500,
    );
    return () => clearInterval(timer);
  }, [playing, speed]);
  useEffect(() => {
    if (replay === null || replay >= 120) return;
    const timer = setTimeout(
      () => setReplay((t) => Math.min(120, (t ?? 0) + 30)),
      800,
    );
    return () => clearTimeout(timer);
  }, [replay]);
  useEffect(() => {
    if (replay !== null) {
      setTime(replay);
      calculate({ ...initial }, undefined, replay);
    }
  }, [replay]);
  useEffect(() => {
    setChat(null);
    setReport("");
    setPanelError("");
  }, [snap?.snapshot_id]);
  const modalOpen = panel !== null || selected !== null || station !== null;
  useEffect(() => {
    if (!modalOpen) return;
    focusReturn.current = document.activeElement as HTMLElement;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    drawerRef.current?.focus();
    const close = () => {
      setPanel(null);
      setSelected(null);
      setStation(null);
    };
    const listener = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
      if (e.key === "Tab") {
        const elements = drawerRef.current?.querySelectorAll<HTMLElement>(
          'button:not(:disabled),a[href],input,textarea,select,[tabindex="0"]',
        );
        if (!elements?.length) return;
        const first = elements[0],
          last = elements[elements.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", listener);
    return () => {
      document.body.style.overflow = previousOverflow;
      document.removeEventListener("keydown", listener);
      focusReturn.current?.focus();
    };
  }, [modalOpen]);
  function scenario(p: Params) {
    setReplay(null);
    setPlaying(false);
    return calculate({ ...p, eta_override: null });
  }
  async function ask(q = question) {
    if (!snap || loading || error || !q.trim()) return;
    setQuestion(q);
    setPanelBusy(true);
    setPanelError("");
    const id = snap.snapshot_id;
    try {
      const answer = await api<Chat>("chat", {
        snapshot_id: id,
        previous_snapshot_id: previousSnapshot.current || null,
        question: q,
        time,
      });
      if (liveSnapshot.current === id) setChat(answer);
    } catch (e) {
      if (liveSnapshot.current === id) setPanelError((e as Error).message);
    } finally {
      if (liveSnapshot.current === id) setPanelBusy(false);
    }
  }
  async function openReport() {
    if (!snap || loading || error) return;
    setPanel("report");
    setPanelBusy(true);
    setPanelError("");
    const id = snap.snapshot_id;
    try {
      const r = await api<{ text: string }>("report", {
        snapshot_id: id,
        time,
      });
      if (liveSnapshot.current === id) setReport(r.text);
    } catch (e) {
      if (liveSnapshot.current === id) setPanelError((e as Error).message);
    } finally {
      if (liveSnapshot.current === id) setPanelBusy(false);
    }
  }
  async function copyReport() {
    try {
      await navigator.clipboard.writeText(report);
      setNotice("Отчёт скопирован");
    } catch {
      setPanelError("Копирование недоступно в браузере. Скачайте отчёт.");
    }
  }
  async function importFile(file: File | undefined) {
    if (!file) return;
    if (file.size > 200000) {
      setError("Размер файла не должен превышать 200 КиБ");
      return;
    }
    try {
      const data = JSON.parse(await file.text());
      setReplay(null);
      const ok = await calculate(initial, data);
      if (ok) {
        setCustomData(data);
        setNotice("Набор проверен и загружен");
      }
    } catch {
      setError("Файл должен содержать корректный JSON");
    }
  }
  async function example() {
    try {
      const state = await api<{ data: unknown }>("state");
      download(
        JSON.stringify(state.data, null, 2),
        "vin-twin-import-example.json",
        "application/json",
      );
    } catch (e) {
      setError((e as Error).message);
    }
  }
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(""), 5000);
    return () => clearTimeout(timer);
  }, [notice]);
  const frame = snap?.frames[time];
  const chosen = snap?.policies.find((x) => x.policy === snap.params.policy);
  const recommended = snap?.policies.find((x) => x.policy === snap.recommended);
  const vin = snap?.vehicles.find((x) => x.id === selected);
  const future = snap ? time > snap.now : false;
  const filtered =
    snap?.vehicles.filter(
      (v) =>
        v.id.toLowerCase().includes(search.toLowerCase()) &&
        (filter === "all" ||
          (filter === "affected" && v.affected) ||
          (filter === "late" && v.completion > 480)),
    ) ?? [];
  async function applyPolicy(policy: Policy) {
    if (!snap) return;
    setReplay(null);
    setPlaying(false);
    const ok = await calculate(
      { ...params, policy },
      undefined,
      null,
      snap.snapshot_id,
    );
    if (ok) setNotice("Политика применена к демонстрационному сценарию");
  }
  function closeDrawer() {
    setPanel(null);
    setSelected(null);
    setStation(null);
  }
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a className="brand" href="/" aria-label="VIN-Twin, главная страница">
          <span className="brand-mark">
            V<span>:</span>
          </span>
          <span>
            VIN<span className="brand-light">TWIN</span>
            <small>PRODUCTION INTELLIGENCE</small>
          </span>
        </a>
        <div className="workspace-label">РАБОЧЕЕ ПРОСТРАНСТВО</div>
        <nav aria-label="Основные разделы">
          <a href="/factory" style={{display:"block",padding:"12px 16px",color:"var(--accent)",fontSize:13}}>Аналитика кейса ↗</a>
          {[
            ["overview", "Обзор"],
            ["scenarios", "Сценарии"],
            ["vin", "VIN-реестр"],
          ].map(([id, label]) => (
            <button
              key={id}
              className={`nav-item ${tab === id ? "active" : ""}`}
              onClick={() => setTab(id)}
              aria-current={tab === id ? "page" : undefined}
            >
              <Icon name={id} />
              {label}
              {id === "vin" && <span className="nav-count">80</span>}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <button
            className="nav-item"
            disabled={loading || !snap || !!error}
            onClick={() => {
              setPanel("chat");
              setPanelError("");
            }}
          >
            <Icon name="chat" />
            Диспетчер<span className="tiny-tag">ЛОКАЛЬНО</span>
          </button>
          <button
            className="nav-item"
            onClick={openReport}
            disabled={loading || !snap || !!error}
          >
            <Icon name="report" />
            Передача смены
          </button>
          <div className="plant-label">
            <span className="plant-monogram">VT</span>
            <div>
              Демонстрационная линия<small>6 ресурсов · 1 смена</small>
            </div>
          </div>
        </div>
      </aside>
      <main>
        <header className="topbar">
          <div className="breadcrumb">
            Производство <span>/</span> Смена 01 <span>/</span>{" "}
            <b>
              {tab === "overview"
                ? "Обзор"
                : tab === "scenarios"
                  ? "Сценарии"
                  : "VIN-реестр"}
            </b>
          </div>
          <div className="topbar-actions">
            <span className="demo-badge">Демонстрационные данные</span>
            <button
              className="icon-button"
              aria-label="Переключить тему"
              onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
            >
              <Icon name="sun" />
            </button>
            <span className="avatar">ДС</span>
          </div>
        </header>
        <div className="main-content">
          <div className="page-heading">
            <div>
              <div className="eyebrow">VIN-TWIN / ОПЕРАЦИОННЫЙ ЦЕНТР</div>
              <h1>
                {tab === "overview"
                  ? "Диспетчер смены"
                  : tab === "scenarios"
                    ? "Сценарии и решения"
                    : "Каждый VIN в потоке"}
              </h1>
              <p>
                {tab === "overview"
                  ? "Состояние линии и последствия решений в одной модели."
                  : tab === "scenarios"
                    ? "Сравните три политики при одинаковых условиях."
                    : "Маршрут, комплектация и прогноз завершения."}
              </p>
            </div>
            <button
              className="button"
              onClick={openReport}
              disabled={loading || !snap || !!error}
            >
              <Icon name="report" />
              Отчёт смены
            </button>
          </div>
          <div className="scenario-bar">
            <span className="bar-label">СЦЕНАРИЙ</span>
            <div className="preset-group">
              {presets.map((p) => (
                <button
                  key={p.name}
                  disabled={loading || (replay !== null && replay < 120)}
                  className={`preset ${params.delay === p.delay && params.robot_minutes === p.robot_minutes ? "selected" : ""}`}
                  onClick={() => scenario({ ...params, ...p, policy: "none" })}
                >
                  {p.name}
                </button>
              ))}
            </div>
            <span className="shift-info">08:00 — 16:00</span>
          </div>
          {error && (
            <div className="error-box" role="alert">
              <Icon name="alert" />
              <span>{error}</span>
              <button className="button" onClick={() => calculate(params)}>
                Повторить
              </button>
            </div>
          )}
          {notice && (
            <div className="notice" role="status">
              {notice}
            </div>
          )}
          {loading && (
            <div className="loading-line" role="status">
              Пересчитываем снимок…
            </div>
          )}
          {!snap && !error && (
            <div className="empty-state">Подключение к расчётному движку…</div>
          )}
          {snap && frame && (
            <div
              className={loading || error ? "results stale" : "results"}
              aria-busy={loading}
            >
              <div className="kpi-grid">
                <Metric
                  title={
                    future ? "Выпуск к выбранному времени" : "Факт выпуска"
                  }
                  value={frame.actual_output}
                  unit="авто"
                  detail={`${clock(time)} · ${future ? "прогноз" : "реконструкция факта"}`}
                  icon="vin"
                />
                <Metric
                  title="Прогноз на конец смены"
                  value={snap.output}
                  unit={`/ ${snap.plan}`}
                  detail={`Штатно ${snap.baseline_output} · мощность ${snap.capacity}`}
                  icon="scenarios"
                  emphasis
                />
                <Metric
                  title="Недовыпуск к плану"
                  value={Math.max(0, snap.plan - snap.output)}
                  unit="авто"
                  detail={`План смены: ${snap.plan} автомобилей`}
                  icon="alert"
                  warning={snap.output < snap.plan}
                />
                <Metric
                  title="Условный эффект в смене"
                  value={n(chosen?.effect ?? 0)}
                  unit="₸"
                  detail={`Спасено ${chosen?.saved ?? 0} · затраты ${n(chosen?.cost ?? 0)} ₸`}
                  icon="check"
                />
              </div>
              {tab === "overview" && (
                <>
                  <section className="panel flow-panel">
                    <div className="section-head">
                      <div>
                        <span className="eyebrow">ЦИФРОВОЙ ПОТОК</span>
                        <h2>Производственная линия</h2>
                      </div>
                      <span
                        className={`time-badge ${future ? "forecast" : ""}`}
                      >
                        {future ? "Прогноз" : "Факт"} · {clock(time)}
                      </span>
                    </div>
                    <div className="flow-canvas">
                      <svg
                        viewBox="0 0 1100 210"
                        role="img"
                        aria-label={`Шесть ресурсов производственной линии в ${clock(time)}`}
                      >
                        <defs>
                          <pattern
                            id="grid"
                            width="22"
                            height="22"
                            patternUnits="userSpaceOnUse"
                          >
                            <circle
                              cx="1"
                              cy="1"
                              r=".6"
                              fill="currentColor"
                              opacity=".11"
                            />
                          </pattern>
                        </defs>
                        <rect width="1100" height="210" fill="url(#grid)" />
                        {frame.stations.map((s, i) => {
                          const x = 17 + i * 181;
                          return (
                            <g
                              key={s.name}
                              className={`station station-${s.status}`}
                              role="button"
                              tabIndex={0}
                              aria-label={`${s.name}: ${s.label}, очередь ${s.queue.length}`}
                              onClick={() => setStation(i)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter" || e.key === " ") {
                                  e.preventDefault();
                                  setStation(i);
                                }
                              }}
                            >
                              <path
                                className="connector"
                                d={`M${x + 155} 82h27`}
                                strokeDasharray="4 4"
                              />
                              <rect
                                className="station-box"
                                x={x}
                                y={27}
                                width="158"
                                height="115"
                                rx="8"
                              />
                              <text x={x + 13} y="49" className="station-index">
                                {String(i + 1).padStart(2, "0")} / ПОСТ
                              </text>
                              <circle
                                className="status-indicator"
                                cx={x + 141}
                                cy="44"
                                r="4"
                              />
                              <text x={x + 13} y="82" className="station-name">
                                {s.name}
                              </text>
                              <text x={x + 13} y="108" className="station-vin">
                                {s.vin || "—"}
                              </text>
                              <text
                                x={x + 13}
                                y="128"
                                className="station-state"
                              >
                                {s.status === "processing"
                                  ? "▶ "
                                  : s.status === "down"
                                    ? "⚠ "
                                    : s.status === "material"
                                      ? "◷ "
                                      : "○ "}
                                {s.label}
                              </text>
                              <text x={x + 3} y="166" className="station-queue">
                                Очередь: {s.queue.length}
                              </text>
                              <text x={x + 3} y="187" className="station-queue">
                                Загрузка:{" "}
                                {s.utilization === null
                                  ? "—"
                                  : `${s.utilization}%`}
                              </text>
                            </g>
                          );
                        })}
                      </svg>
                    </div>
                    <div className="legend">
                      {[
                        ["processing", "Обработка"],
                        ["material", "Ожидание материала"],
                        ["resource", "Ожидание ресурса"],
                        ["down", "Недоступность"],
                        ["idle", "Нет входных VIN"],
                      ].map(([id, name]) => (
                        <span key={id}>
                          <i className={id} />
                          {name}
                        </span>
                      ))}
                    </div>
                    <div className="timeline">
                      <button
                        className="icon-button play-button"
                        aria-label={playing ? "Пауза" : "Воспроизвести"}
                        onClick={() => setPlaying((p) => !p)}
                      >
                        <Icon name={playing ? "pause" : "play"} />
                      </button>
                      <div className="timeline-track">
                        <div className="timeline-labels">
                          <span>08:00</span>
                          <span className="now-label">
                            Сейчас {clock(snap.now)}
                          </span>
                          <span>16:00</span>
                        </div>
                        <input
                          aria-label="Время симуляции"
                          type="range"
                          min="0"
                          max="480"
                          step="1"
                          value={time}
                          onChange={(e) => {
                            setTime(+e.target.value);
                            setPlaying(false);
                          }}
                        />
                        <div className="timeline-labels muted">
                          <span>Реконструкция</span>
                          <span>После {clock(snap.now)} — прогноз</span>
                        </div>
                      </div>
                      <strong>{clock(time)}</strong>
                      <select
                        aria-label="Скорость воспроизведения"
                        value={speed}
                        onChange={(e) => setSpeed(+e.target.value)}
                      >
                        <option value="1">1×</option>
                        <option value="6">6×</option>
                        <option value="12">12×</option>
                      </select>
                    </div>
                  </section>
                  <div className="overview-grid">
                    <section className="panel chart-panel">
                      <div className="section-head">
                        <div>
                          <span className="eyebrow">РЕЗУЛЬТАТ СМЕНЫ</span>
                          <h2>Траектория выпуска</h2>
                        </div>
                        <span className="chart-key">
                          <i />
                          Выбранная политика
                        </span>
                      </div>
                      <OutputChart snap={snap} time={time} />
                    </section>
                    <section className="panel supply-panel">
                      <div className="section-head">
                        <div>
                          <span className="eyebrow">КОМПЛЕКТУЮЩИЕ</span>
                          <h2>Запасы и поставка</h2>
                        </div>
                        <span className="tiny-tag">A / B</span>
                      </div>
                      <div className="inventory-row">
                        <div>
                          <span>Жгут A</span>
                          <strong>
                            {frame.inventory.A}
                            <small>компл.</small>
                          </strong>
                        </div>
                        <div>
                          <span>Жгут B</span>
                          <strong>
                            {frame.inventory.B}
                            <small>компл.</small>
                          </strong>
                        </div>
                      </div>
                      <div className="eta-row">
                        <span>
                          Партия {snap.supply.quantity} × {snap.supply.kit} ·
                          ETA
                        </span>
                        <b>{clock(snap.eta)}</b>
                      </div>
                      <div
                        className={`risk-note ${snap.material_waits.length ? "warn" : ""}`}
                      >
                        <Icon
                          name={snap.material_waits.length ? "alert" : "check"}
                        />
                        <div>
                          <strong>
                            {snap.material_waits.length
                              ? "Риск ожидания на сборке-1"
                              : "Материал доступен по плану"}
                          </strong>
                          <p>
                            {snap.material_waits.length
                              ? `${clock(snap.material_waits[0].start)}–${clock(snap.material_waits[0].end)} · комплект ${snap.material_waits[0].kit}`
                              : "Ожидание материала не прогнозируется."}
                          </p>
                        </div>
                      </div>
                    </section>
                  </div>
                  <div className="overview-grid lower-grid">
                    <section className="panel">
                      <div className="section-head">
                        <h2>Лента инцидентов</h2>
                        <button
                          className="text-button"
                          disabled={
                            loading ||
                            events.length === 0 ||
                            (replay !== null && replay < 120)
                          }
                          onClick={() => {
                            setReplay(0);
                            setNotice(
                              "Воспроизведение: обновление ETA и сценарное условие робота поступят в 10:00",
                            );
                          }}
                        >
                          Воспроизвести события
                        </button>
                      </div>
                      {snap.incidents.length ? (
                        snap.incidents.map((i) => (
                          <button
                            className="incident"
                            key={i.id}
                            onClick={() => {
                              setTime(
                                i.id === "eta"
                                  ? (snap.material_waits[0]?.start ?? snap.now)
                                  : (params.robot_start ?? 150),
                              );
                              setStation(i.id === "eta" ? 2 : 0);
                            }}
                          >
                            <span
                              className={`incident-symbol ${i.type === "fact" ? "amber" : "red"}`}
                            >
                              <Icon name="alert" />
                            </span>
                            <span>
                              <strong>{i.title}</strong>
                              <small>{i.detail}</small>
                              <small>
                                {i.source} ·{" "}
                                {i.type === "fact"
                                  ? "Факт"
                                  : "Сценарное допущение"}
                              </small>
                            </span>
                            <time>{clock(i.received_at)}</time>
                          </button>
                        ))
                      ) : (
                        <div className="no-incidents">
                          <Icon name="check" />
                          <span>Штатный сценарий. Инцидентов нет.</span>
                        </div>
                      )}
                    </section>
                    <section className="panel recommendation">
                      <div className="section-head">
                        <h2>Рекомендация диспетчеру</h2>
                        <span className="tiny-tag">ДВИЖОК</span>
                      </div>
                      <h3>{recommended?.name}</h3>
                      <p>
                        {recommended?.policy === "none"
                          ? "Бездействие даёт наибольший условный эффект при заданных условиях."
                          : `Сохранит ${recommended?.saved} автомобилей относительно бездействия.`}
                      </p>
                      <div className="recommendation-value">
                        {n(recommended?.effect ?? 0)}{" "}
                        <span>₸ / условный эффект</span>
                      </div>
                      <div className="action-row">
                        <button
                          className="button primary"
                          disabled={
                            loading ||
                            !!error ||
                            recommended?.policy === params.policy
                          }
                          onClick={() => applyPolicy(snap.recommended)}
                        >
                          {recommended?.policy === params.policy
                            ? "Политика выбрана"
                            : "Применить к сценарию"}
                        </button>
                        <button
                          className="button"
                          onClick={() => setTab("scenarios")}
                        >
                          Сравнить
                        </button>
                      </div>
                    </section>
                  </div>
                </>
              )}
              {tab === "scenarios" && (
                <>
                  <section className="panel scenario-controls">
                    <div className="section-head">
                      <h2>Условия расчёта</h2>
                      <span className="muted">
                        Решение принимается в {clock(params.decision_time)}
                      </span>
                    </div>
                    <form
                      onSubmit={(e) => {
                        e.preventDefault();
                        const fd = new FormData(e.currentTarget);
                        scenario({
                          delay: Number(fd.get("delay")),
                          robot_minutes: Number(fd.get("robot")),
                          robot_start: Number(fd.get("robot_start")),
                          decision_time: Number(fd.get("decision")),
                          contribution: Number(fd.get("contribution")),
                          policy: "none",
                        });
                      }}
                      key={`${params.delay}-${params.robot_minutes}-${params.robot_start}-${params.decision_time}-${params.contribution}`}
                    >
                      <label>
                        Задержка поставки, мин
                        <input
                          name="delay"
                          type="number"
                          min="0"
                          max="400"
                          required
                          defaultValue={params.delay}
                        />
                      </label>
                      <label>
                        Длительность отказа робота, мин
                        <input
                          name="robot"
                          type="number"
                          min="0"
                          max="180"
                          required
                          defaultValue={params.robot_minutes}
                        />
                      </label>
                      <label>
                        Начало отказа, мин от 08:00
                        <input
                          name="robot_start"
                          type="number"
                          min="0"
                          max="480"
                          required
                          defaultValue={params.robot_start ?? 150}
                        />
                      </label>
                      <label>
                        Время решения, мин от 08:00
                        <input
                          name="decision"
                          type="number"
                          min="0"
                          max="480"
                          required
                          defaultValue={params.decision_time}
                        />
                      </label>
                      <label>
                        Вклад автомобиля, ₸
                        <input
                          name="contribution"
                          type="number"
                          min="0"
                          max="10000000"
                          required
                          defaultValue={params.contribution}
                        />
                      </label>
                      <button className="button primary" disabled={loading}>
                        Пересчитать
                      </button>
                    </form>
                  </section>
                  <div className="section-head policies-heading">
                    <h2>Три пути развития смены</h2>
                    <span className="muted">
                      Сравнение с бездействием при тех же сбоях
                    </span>
                  </div>
                  <div className="policy-grid">
                    {snap.policies.map((p) => (
                      <section
                        key={p.policy}
                        className={`panel policy-card ${p.policy === snap.recommended ? "best" : ""}`}
                      >
                        <div className="policy-top">
                          <span className="eyebrow">
                            {p.policy === "none"
                              ? "01 / FIFO"
                              : p.policy === "delivery"
                                ? "02 / ЛОГИСТИКА"
                                : "03 / ОЧЕРЕДЬ"}
                          </span>
                          {p.policy === snap.recommended && (
                            <span className="best-badge">Рекомендуем</span>
                          )}
                        </div>
                        <h3>{p.name}</h3>
                        <div className="policy-output">
                          {n(p.output)}
                          <span>автомобилей к 16:00</span>
                        </div>
                        <dl>
                          <div>
                            <dt>Спасено</dt>
                            <dd>
                              {p.saved !== null ? `+${p.saved}` : "—"} авто
                            </dd>
                          </div>
                          <div>
                            <dt>Затраты</dt>
                            <dd>{n(p.cost)} ₸</dd>
                          </div>
                          <div className="effect-row">
                            <dt>Условный эффект</dt>
                            <dd>{n(p.effect)} ₸</dd>
                          </div>
                        </dl>
                        <p className="policy-description">
                          {p.policy === "none"
                            ? "Текущая очередь и срок поставки."
                            : p.policy === "delivery"
                              ? "Та же партия прибывает не позже 13:20."
                              : "После VIN-048 запускаем VIN-055…060 с запасом B."}
                        </p>
                        {!p.available && (
                          <p className="unavailable">{p.reason}</p>
                        )}
                        <button
                          className={`button ${p.policy === snap.recommended ? "primary" : ""}`}
                          disabled={
                            loading ||
                            !!error ||
                            !p.available ||
                            params.policy === p.policy
                          }
                          onClick={() => applyPolicy(p.policy)}
                        >
                          {params.policy === p.policy
                            ? "Выбрано"
                            : p.available
                              ? "Применить к сценарию"
                              : "Недоступно"}
                        </button>
                      </section>
                    ))}
                  </div>
                  <div className="scenario-footer">
                    <p>
                      Эффект = спасённые автомобили × {n(params.contribution)} ₸
                      − затраты. Оценка в рамках одной смены; не подтверждённая
                      прибыль предприятия.
                    </p>
                    <button
                      className="button"
                      onClick={() => applyPolicy("none")}
                      disabled={loading}
                    >
                      <Icon name="reset" />
                      Сбросить политику
                    </button>
                  </div>
                  <section className="panel sensitivity-panel">
                    <div className="section-head">
                      <div>
                        <span className="eyebrow">ЭКОНОМИКА И ДОПУЩЕНИЯ</span>
                        <h2>Когда меняется лучшее решение?</h2>
                      </div>
                      <span className="muted">Расчёт при тех же сбоях</span>
                    </div>
                    <div className="table-scroll">
                      <table>
                        <thead>
                          <tr>
                            <th>Вклад автомобиля</th>
                            <th>Рекомендация</th>
                            <th>Эффект доставки</th>
                            <th>Эффект перестановки</th>
                          </tr>
                        </thead>
                        <tbody>
                          {snap.sensitivity.map((row) => (
                            <tr
                              key={row.contribution}
                              className={
                                row.contribution === params.contribution
                                  ? "sensitivity-current"
                                  : ""
                              }
                            >
                              <td>
                                {n(row.contribution)} ₸
                                {row.contribution === params.contribution
                                  ? " · выбран"
                                  : ""}
                              </td>
                              <td>
                                {
                                  snap.policies.find(
                                    (p) => p.policy === row.recommended,
                                  )?.name
                                }
                              </td>
                              <td>{n(row.effects.delivery ?? null)} ₸</td>
                              <td>{n(row.effects.reorder ?? null)} ₸</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <div className="sensitivity-notes">
                      <p>
                        Это проверка чувствительности, а не оценка реальной
                        маржи. При одинаковом эффекте выбирается действие с
                        меньшими затратами.
                      </p>
                      {snap.thresholds.map((t) => (
                        <p key={`${t.left}-${t.right}`}>
                          {snap.policies.find((p) => p.policy === t.left)?.name}{" "}
                          и{" "}
                          {
                            snap.policies.find((p) => p.policy === t.right)
                              ?.name
                          }
                          : одинаковый эффект при вкладе {n(t.contribution)} ₸.
                        </p>
                      ))}
                    </div>
                  </section>
                  <section className="panel data-panel">
                    <div>
                      <h2>Импорт демонстрационных данных</h2>
                      <p>
                        JSON: 80 VIN, комплекты A/B, партия, маршрут и
                        разрешение перестановки. Проверяется на сервере.
                      </p>
                    </div>
                    <div className="action-row">
                      <button className="button" onClick={example}>
                        Пример JSON
                      </button>
                      <label className="button import-button">
                        <Icon name="upload" />
                        Импортировать
                        <input
                          type="file"
                          accept=".json,application/json"
                          onChange={(e) => {
                            importFile(e.target.files?.[0]);
                            e.target.value = "";
                          }}
                        />
                      </label>
                      {customData !== undefined && (
                        <button
                          className="button"
                          onClick={() => {
                            setCustomData(undefined);
                            calculate(initial, null);
                            setNotice("Возвращены исходные демо-данные");
                          }}
                        >
                          Вернуть демо
                        </button>
                      )}
                    </div>
                  </section>
                </>
              )}
              {tab === "vin" && (
                <section className="panel vin-panel">
                  <div className="section-head">
                    <div>
                      <h2>VIN-реестр</h2>
                      <p>
                        {filtered.length} из 80 заказов · состояние на{" "}
                        {clock(time)}
                      </p>
                    </div>
                    <div className="table-controls">
                      <label className="search-input">
                        <Icon name="search" />
                        <input
                          aria-label="Поиск VIN"
                          placeholder="Найти VIN…"
                          value={search}
                          onChange={(e) => setSearch(e.target.value)}
                        />
                      </label>
                      <select
                        aria-label="Фильтр VIN"
                        value={filter}
                        onChange={(e) => setFilter(e.target.value)}
                      >
                        <option value="all">Все VIN</option>
                        <option value="affected">
                          Затронутые ({snap.affected.length})
                        </option>
                        <option value="late">
                          После смены ({snap.after_shift.length})
                        </option>
                      </select>
                    </div>
                  </div>
                  <div className="table-scroll">
                    <table>
                      <thead>
                        <tr>
                          <th>VIN</th>
                          <th>Комплект</th>
                          <th>Статус</th>
                          <th>Завершение</th>
                          <th>Штатно</th>
                          <th>Изменение</th>
                        </tr>
                      </thead>
                      <tbody>
                        {filtered.map((v) => {
                          const state = vinState(v, time);
                          return (
                            <tr key={v.id}>
                              <td>
                                <button
                                  className="vin-link"
                                  onClick={() => setSelected(v.id)}
                                >
                                  {v.id}
                                </button>
                              </td>
                              <td>
                                <span className={`kit kit-${v.kit}`}>
                                  {v.kit}
                                </span>
                              </td>
                              <td>
                                <span className={`status-pill ${state.status}`}>
                                  {state.label}
                                </span>
                              </td>
                              <td className={v.completion > 480 ? "late" : ""}>
                                {clock(v.completion)}
                              </td>
                              <td>{clock(v.baseline_completion)}</td>
                              <td>
                                {v.delay_minutes > 0
                                  ? `+${v.delay_minutes} мин`
                                  : v.delay_minutes < 0
                                    ? `${v.delay_minutes} мин`
                                    : "—"}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                    {filtered.length === 0 && (
                      <div className="empty-state">
                        VIN по этому запросу не найден. Измените поиск или
                        фильтр.
                      </div>
                    )}
                  </div>
                </section>
              )}
              <details className="assumptions">
                <summary>Допущения модели и источники данных</summary>
                <ul>
                  {snap.assumptions.map((x) => (
                    <li key={x}>{x}</li>
                  ))}
                </ul>
                <p>
                  VIN-001…080 — демонстрационные идентификаторы. Система не
                  подключена к MES/WMS или оборудованию.
                </p>
              </details>
              <footer className="data-footer">
                <span>
                  {snap.source} · {snap.updated_at}
                </span>
                <span>
                  Снимок {snap.snapshot_id.slice(0, 8)} · входы{" "}
                  {snap.input_version} · v{snap.model_version}
                </span>
              </footer>
            </div>
          )}
        </div>
      </main>
      {modalOpen && (
        <>
          <div className="scrim" onClick={closeDrawer} />
          <aside
            className={`drawer ${panel === "report" ? "report-drawer" : ""}`}
            ref={drawerRef}
            tabIndex={-1}
            role="dialog"
            aria-modal="true"
            aria-label={
              panel === "chat"
                ? "Диспетчер"
                : panel === "report"
                  ? "Отчёт передачи смены"
                  : (selected ?? "Производственный ресурс")
            }
          >
            <div className="drawer-header">
              <div>
                <span className="eyebrow">VIN-TWIN</span>
                <h2>
                  {panel === "chat"
                    ? "Диспетчер"
                    : panel === "report"
                      ? "Передача смены"
                      : (selected ?? frame?.stations[station ?? 0].name)}
                </h2>
              </div>
              <button
                className="icon-button"
                aria-label="Закрыть панель"
                onClick={closeDrawer}
              >
                <Icon name="close" />
              </button>
            </div>
            {panelError && (
              <div className="error-box" role="alert">
                {panelError}
              </div>
            )}
            {panel === "chat" && (
              <>
                <div className="drawer-info">
                  Ответы по снимку {snap?.snapshot_id.slice(0, 8)}. Числа и
                  рекомендации берутся из расчётного движка.
                </div>
                <div className="prompt-list">
                  {[
                    "Что остановится и когда?",
                    "Почему возникнет ожидание?",
                    "Какие VIN затронуты?",
                    "Какое действие выгоднее?",
                    "Почему рекомендация изменилась?",
                    "Почему VIN-049 ждёт?",
                    "Как вклад влияет на выбор?",
                    "Какие допущения влияют на вывод?",
                  ].map((q) => (
                    <button
                      key={q}
                      onClick={() => ask(q)}
                      disabled={panelBusy || loading}
                    >
                      {q}
                    </button>
                  ))}
                </div>
                <form
                  className="chat-form"
                  onSubmit={(e) => {
                    e.preventDefault();
                    ask();
                  }}
                >
                  <label htmlFor="question">Вопрос диспетчеру</label>
                  <textarea
                    id="question"
                    value={question}
                    maxLength={2000}
                    onChange={(e) => setQuestion(e.target.value)}
                  />
                  <button
                    className="button primary"
                    disabled={panelBusy || loading || !question.trim()}
                  >
                    {panelBusy ? "Анализируем…" : "Получить объяснение"}
                  </button>
                </form>
                {chat && (
                  <div className="chat-answer">
                    <span className="tiny-tag">
                      ЛОКАЛЬНОЕ ОБЪЯСНЕНИЕ
                    </span>
                    <p>{chat.answer}</p>
                    <small>Ссылки на факты: {chat.fact_refs.join(", ")}</small>
                  </div>
                )}
                <p className="muted">
                  Прогноз отказа робота — заданное условие сценария. Обученная
                  ML-модель не заявляется.
                </p>
              </>
            )}
            {panel === "report" && (
              <>
                {panelBusy ? (
                  <p role="status">Формируем отчёт…</p>
                ) : report ? (
                  <>
                    <div className="action-row report-actions">
                      <button className="button" onClick={copyReport}>
                        Копировать
                      </button>
                      <button
                        className="button"
                        onClick={() =>
                          download(report, "vin-twin-shift-report.txt")
                        }
                      >
                        Скачать
                      </button>
                      <button className="button" onClick={() => window.print()}>
                        Печатать
                      </button>
                    </div>
                    <pre className="report-text">{report}</pre>
                  </>
                ) : (
                  <p>
                    Нажмите «Отчёт смены», чтобы сформировать отчёт по текущему
                    снимку.
                  </p>
                )}
              </>
            )}
            {vin && (
              <>
                <div className="vin-summary">
                  <span className={`kit kit-${vin.kit}`}>
                    Комплект {vin.kit}
                  </span>
                  <span className={`status-pill ${vinState(vin, time).status}`}>
                    {vinState(vin, time).label}
                  </span>
                </div>
                <div className="vin-completion">
                  <span>Прогноз завершения</span>
                  <strong>{clock(vin.completion)}</strong>
                  <p>
                    Штатно {clock(vin.baseline_completion)} · изменение{" "}
                    {vin.delay_minutes} мин.
                  </p>
                </div>
                <h3>Маршрут и время операций</h3>
                <ol className="route-list">
                  {vin.operations.map((o, i) => (
                    <li key={i}>
                      <span className="route-index">{i + 1}</span>
                      <div>
                        <strong>{snap?.frames[0].stations[i].name}</strong>
                        <p>
                          {clock(o.start)} — {clock(o.end)}
                          {o.segments.length > 1
                            ? " · операция приостановлена"
                            : ""}
                        </p>
                        {o.material_wait && (
                          <small className="late">
                            Ожидание материала: {clock(o.material_wait[0])}–
                            {clock(o.material_wait[1])}
                          </small>
                        )}
                      </div>
                    </li>
                  ))}
                </ol>
                <p className="drawer-info">
                  Время завершения после 16:00 не входит в выпуск текущей смены.
                </p>
              </>
            )}
            {station !== null && frame && (
              <>
                <div className="drawer-info">
                  {frame.stations[station].label} · {clock(time)} ·{" "}
                  {future ? "Прогноз" : "Факт"}
                </div>
                <div className="station-detail">
                  <p>
                    Текущий VIN: <b>{frame.stations[station].vin ?? "нет"}</b>
                  </p>
                  <p>
                    Загрузка:{" "}
                    <b>
                      {frame.stations[station].utilization ?? "нет данных"}
                      {frame.stations[station].utilization === null ? "" : "%"}
                    </b>
                  </p>
                  <p className="muted">
                    Время фактической обработки / прошедшее время смены. Паузы
                    исключены.
                  </p>
                </div>
                <h3>Очередь · {frame.stations[station].queue.length} VIN</h3>
                <div className="queue-list">
                  {frame.stations[station].queue.map((id) => (
                    <button
                      className="button"
                      key={id}
                      onClick={() => {
                        setStation(null);
                        setSelected(id);
                      }}
                    >
                      {id}
                    </button>
                  ))}
                </div>
                {!frame.stations[station].queue.length && (
                  <p className="muted">VIN, ожидающих этот ресурс, нет.</p>
                )}
              </>
            )}
          </aside>
        </>
      )}
    </div>
  );
}
