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
    throw Error(
      typeof error.detail === "string"
        ? error.detail
        : "Некорректные параметры или формат данных.",
    );
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
