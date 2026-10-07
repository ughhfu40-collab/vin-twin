export async function api<T>(
  url: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/${url}`, {
      method: body === undefined ? "GET" : "POST",
      headers: body === undefined ? {} : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: signal
        ? AbortSignal.any([signal, AbortSignal.timeout(15000)])
        : AbortSignal.timeout(15000),
    });
  } catch (e) {
    if ((e as Error).name === "AbortError") throw e;
    throw Error(
      "Backend недоступен. Проверьте запуск Python и повторите расчёт.",
    );
  }
  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ detail: "Ошибка сервера" }));
    if (typeof error.detail === "string") throw Error(error.detail);
    if (Array.isArray(error.detail)) {
      const labels: Record<string, string> = {
        workdays: "Рабочие дни", excluded_minutes_per_shift: "Перерывы",
        target_reject_percent: "Цель брака", ideal_cycle_minutes: "Идеальный цикл",
        delay: "Задержка поставки", robot_minutes: "Длительность сбоя",
        robot_start: "Начало сбоя", decision_time: "Время решения",
        contribution: "Вклад автомобиля", question: "Вопрос",
      };
      const messages = error.detail.slice(0, 3).map((item: { loc?: string[]; type?: string; ctx?: Record<string, number> }) => {
        const field = item.loc?.find(part => labels[part]);
        const name = field ? labels[field] : "Параметры";
        if (item.type === "greater_than_equal") return `${name}: минимум ${item.ctx?.ge}.`;
        if (item.type === "less_than_equal") return `${name}: максимум ${item.ctx?.le}.`;
        if (item.type === "int_type" || item.type === "int_parsing") return `${name}: введите целое число.`;
        if (item.type === "string_too_short") return `${name}: заполните поле.`;
        return `${name}: проверьте значение и формат.`;
      });
      throw Error(messages.join(" "));
    }
    throw Error("Некорректные параметры или формат данных.");
  }
  return response.json();
}
export function download(
  text: string,
  name: string,
  type = "text/plain;charset=utf-8",
) {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
