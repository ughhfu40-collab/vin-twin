import type { Vehicle } from "./types";
export function vinState(v: Vehicle, t: number) {
  if (t >= v.completion) return { label: "Завершён", status: "done" };
  const o = v.operations.find((x) => x.end > t)!;
  if (t >= o.start) {
    const processing = o.segments.some(([a, b]) => a <= t && t < b);
    return {
      label: processing ? "В обработке" : "Пауза оборудования",
      status: processing ? "processing" : "down",
    };
  }
  if (o.material_wait && o.material_wait[0] <= t && t < o.material_wait[1])
    return { label: "Ожидает материал", status: "material" };
  return {
    label: o.previous_ready <= t ? "Ожидает ресурс" : "В очереди",
    status: "resource",
  };
}
