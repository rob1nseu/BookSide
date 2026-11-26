import { recovering } from "./learningStatus";
export class ApiError extends Error {
  constructor(
    message: string,
    public status = 0,
  ) {
    super(message);
  }
}

function wait(ms: number, signal?: AbortSignal | null) {
  return new Promise<void>((resolve, reject) => {
    const abort = () => {
      clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", abort);
      resolve();
    }, ms);
    if (signal?.aborted) abort();
    else signal?.addEventListener("abort", abort, { once: true });
  });
}

export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  // Only reads and actions with a server-enforced idempotency key may be replayed.
  const method = (options.method || "GET").toUpperCase();
  let keyed = false;
  try {
    keyed =
      method === "POST" &&
      /\/spaces\/[^/]+\/actions$/.test(path) &&
      !!JSON.parse(String(options.body)).request_key;
  } catch {
    /* uploads and other writes are never replayed */
  }
  const attempts = method === "GET" || keyed ? 3 : 1;
  const id = crypto.randomUUID();
  let retrying = false;
  try {
    for (let attempt = 0; attempt < attempts; attempt++) {
      const controller = new AbortController();
      const abort = () => controller.abort();
      options.signal?.addEventListener("abort", abort, { once: true });
      if (options.signal?.aborted) abort();
      const timeout = attempts > 1 ? setTimeout(abort, 15000) : undefined;
      try {
        const response = await fetch("/api" + path, {
          ...options,
          signal: controller.signal,
          headers: {
            "X-BookSide": "1",
            ...(!(options.body instanceof FormData)
              ? { "Content-Type": "application/json" }
              : {}),
            ...options.headers,
          },
        });
        if (!response.ok) {
          let detail = "连接暂时不可用，请稍后重试";
          try {
            const data = await response.json();
            detail =
              typeof data.detail === "string" ? data.detail : "输入格式不正确";
          } catch {
            /* do not expose raw provider/server responses */
          }
          throw new ApiError(detail, response.status);
        }
        try {
          return await response.json();
        } catch {
          throw new ApiError("收到的内容不完整，请重新加载", 502);
        }
      } catch (caught) {
        if (options.signal?.aborted) throw caught;
        const error = controller.signal.aborted
          ? new ApiError("本地服务响应较慢，请稍后重试", 408)
          : caught;
        const transient =
          error instanceof TypeError ||
          (error instanceof ApiError &&
            [0, 408, 429, 500, 502, 503, 504].includes(error.status));
        if (!transient || attempt === attempts - 1) {
          throw error instanceof TypeError
            ? new ApiError("连接暂时不可用，学习记录仍保留，请重试")
            : error;
        }
        retrying = true;
        window.dispatchEvent(
          new CustomEvent("bookside:retry", {
            detail: {
              id,
              message: recovering,
            },
          }),
        );
        await wait(600 * 2 ** attempt + Math.random() * 150, options.signal);
      } finally {
        clearTimeout(timeout);
        options.signal?.removeEventListener("abort", abort);
      }
    }
    throw new ApiError("请稍后重试");
  } finally {
    if (retrying)
      window.dispatchEvent(
        new CustomEvent("bookside:retry", { detail: { id, message: "" } }),
      );
  }
}
export const send = <T>(path: string, body: unknown, method = "POST") =>
  api<T>(path, { method, body: JSON.stringify(body) });
