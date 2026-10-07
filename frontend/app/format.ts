export const clock = (t: number) =>
  `${String(8 + Math.floor(t / 60)).padStart(2, "0")}:${String(t % 60).padStart(2, "0")}`;
export const n = (v: number | null) =>
  v === null ? "—" : v.toLocaleString("ru-RU");
