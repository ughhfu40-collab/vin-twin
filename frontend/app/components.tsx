import type { Snapshot } from "./types";
import { clock, n } from "./format";
export function Icon({ name, size = 20 }: { name: string; size?: number }) {
  const paths: Record<string, React.ReactNode> = {
    overview: (
      <>
        <rect x="3" y="3" width="7" height="7" rx="1" />
        <rect x="14" y="3" width="7" height="7" rx="1" />
        <rect x="3" y="14" width="7" height="7" rx="1" />
        <rect x="14" y="14" width="7" height="7" rx="1" />
      </>
    ),
    scenarios: (
      <>
        <path d="M5 4v16M19 4v16M12 4v16" />
        <circle cx="5" cy="8" r="2" />
        <circle cx="12" cy="16" r="2" />
        <circle cx="19" cy="10" r="2" />
      </>
    ),
    vin: (
      <>
        <path d="M4 7h16v12H4zM8 3v4M16 3v4M7 11h4M7 15h10" />
      </>
    ),
    chat: (
      <>
        <path d="M20 4H4v13h4v4l5-4h7zM8 8h8M8 12h5" />
      </>
    ),
    report: (
      <>
        <path d="M6 3h8l4 4v14H6zM14 3v5h4M9 12h6M9 16h6" />
      </>
    ),
    sun: (
      <>
        <circle cx="12" cy="12" r="4" />
        <path d="M12 1v3M12 20v3M1 12h3M20 12h3M4 4l2 2M18 18l2 2M4 20l2-2M18 6l2-2" />
      </>
    ),
    close: <path d="M6 6l12 12M18 6L6 18" />,
    play: <path d="M8 4l12 8-12 8z" />,
    pause: <path d="M8 4v16M16 4v16" />,
    check: <path d="M4 12l5 5L20 6" />,
    alert: (
      <>
        <path d="M12 3L2 21h20zM12 9v5M12 17v1" />
      </>
    ),
    reset: (
      <>
        <path d="M4 10a8 8 0 111 9M4 3v7h7" />
      </>
    ),
    search: (
      <>
        <circle cx="10" cy="10" r="6" />
        <path d="M15 15l6 6" />
      </>
    ),
    upload: (
      <>
        <path d="M12 16V3M7 8l5-5 5 5M4 16v5h16v-5" />
      </>
    ),
  };
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name] || paths.overview}
    </svg>
  );
}
export function Metric({
  title,
  value,
  unit,
  detail,
  icon,
  emphasis = false,
  warning = false,
}: {
  title: string;
  value: number | string;
  unit: string;
  detail: string;
  icon: string;
  emphasis?: boolean;
  warning?: boolean;
}) {
  return (
    <section
      className={`panel metric ${emphasis ? "metric-emphasis" : ""} ${warning ? "metric-warning" : ""}`}
    >
      <div className="metric-label">
        <span>{title}</span>
        <Icon name={icon} />
      </div>
      <div className="metric-value">
        {typeof value === "number" ? n(value) : value}
        <span>{unit}</span>
      </div>
      <p>{detail}</p>
    </section>
  );
}
export function OutputChart({ snap, time }: { snap: Snapshot; time: number }) {
  const w = 750,
    h = 175;
  const points = snap.frames
    .filter((f) => f.time % 6 === 0 || f.time === 480)
    .map(
      (f) =>
        `${40 + (f.time / 480) * (w - 70)},${h - 20 - (f.actual_output / 80) * (h - 40)}`,
    )
    .join(" ");
  const x = 40 + (snap.now / 480) * (w - 70);
  return (
    <div className="output-chart">
      <svg
        viewBox={`0 0 ${w} ${h + 30}`}
        role="img"
        aria-label={`Прогноз выпуска ${snap.output} автомобилей к 16:00`}
      >
        <defs>
          <linearGradient id="area" x1="0" y1="0" x2="0" y2="1">
            <stop stopColor="var(--accent)" stopOpacity=".17" />
            <stop offset="1" stopColor="var(--accent)" stopOpacity="0" />
          </linearGradient>
        </defs>
        {[0, 25, 50, 75].map((v) => (
          <g key={v}>
            <line
              x1="40"
              x2={w - 30}
              y1={h - 20 - (v / 80) * (h - 40)}
              y2={h - 20 - (v / 80) * (h - 40)}
              stroke="var(--border)"
              strokeDasharray="3 4"
            />
            <text x="10" y={h - 16 - (v / 80) * (h - 40)}>
              {v}
            </text>
          </g>
        ))}
        <rect
          x={x}
          y="8"
          width={w - 30 - x}
          height={h - 25}
          fill="var(--forecast-fill)"
        />
        <text x={x + 12} y="23" className="forecast-label">
          ПРОГНОЗ
        </text>
        <line
          x1={x}
          x2={x}
          y1="25"
          y2={h - 20}
          stroke="var(--muted)"
          strokeDasharray="4 4"
        />
        <line
          x1="40"
          x2={w - 30}
          y1={h - 20 - (snap.plan / 80) * (h - 40)}
          y2={h - 20 - (snap.plan / 80) * (h - 40)}
          stroke="var(--muted)"
          strokeDasharray="5 5"
        />
        <polygon
          points={`40,${h - 20} ${points} ${w - 30},${h - 20}`}
          fill="url(#area)"
        />
        <polyline
          points={points}
          stroke="var(--accent)"
          fill="none"
          strokeWidth="2.5"
        />
        <circle
          cx={40 + (time / 480) * (w - 70)}
          cy={h - 20 - (snap.frames[time].actual_output / 80) * (h - 40)}
          r="4"
          fill="var(--accent)"
        />
        {[0, 120, 240, 360, 480].map((t) => (
          <text
            key={t}
            x={40 + (t / 480) * (w - 70)}
            y={h + 6}
            textAnchor={t === 0 ? "start" : t === 480 ? "end" : "middle"}
          >
            {clock(t)}
          </text>
        ))}
        <text x={w - 30} y="12" textAnchor="end">
          План {snap.plan}
        </text>
      </svg>
    </div>
  );
}
