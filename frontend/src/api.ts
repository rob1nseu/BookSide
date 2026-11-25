export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch("/api" + path, {
    ...options,
    headers: {
      "X-LearNest": "1",
      ...(!(options.body instanceof FormData)
        ? { "Content-Type": "application/json" }
        : {}),
      ...options.headers,
    },
  });
  if (!response.ok) {
    let detail = "请求失败，请稍后重试";
    try {
      const data = await response.json();
      detail = typeof data.detail === "string" ? data.detail : "输入格式不正确";
    } catch {
      /* no provider content exposed */
    }
    throw new Error(detail);
  }
  return response.json();
}
export const send = <T>(path: string, body: unknown, method = "POST") =>
  api<T>(path, { method, body: JSON.stringify(body) });
