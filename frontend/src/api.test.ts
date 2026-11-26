import { afterEach, expect, test, vi } from "vitest";
import { api, send } from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

test("retries safe reads and emits inline recovery status", async () => {
  vi.useFakeTimers();
  const fetch = vi
    .fn()
    .mockResolvedValueOnce(new Response("", { status: 503 }))
    .mockResolvedValueOnce(new Response('{"ok":true}'));
  vi.stubGlobal("fetch", fetch);
  const listener = vi.fn();
  window.addEventListener("learnest:retry", listener);
  const pending = api("/settings");
  await vi.runAllTimersAsync();
  expect(await pending).toEqual({ ok: true });
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(listener.mock.calls[0][0].detail.message).toBe("有点小问题，等等哈...");
  expect(listener.mock.calls.at(-1)![0].detail.message).toBe("");
  window.removeEventListener("learnest:retry", listener);
});

test("replays only idempotent actions with the identical request key", async () => {
  vi.useFakeTimers();
  const fetch = vi
    .fn()
    .mockRejectedValueOnce(new TypeError("network"))
    .mockResolvedValueOnce(new Response('{"id":"same-run"}'));
  vi.stubGlobal("fetch", fetch);
  const pending = send("/spaces/example/actions", {
    action: "teach",
    request_key: "stable-key",
  });
  await vi.runAllTimersAsync();
  expect(await pending).toEqual({ id: "same-run" });
  expect(fetch.mock.calls[0][1].body).toBe(fetch.mock.calls[1][1].body);
});

test("does not replay uploads or auth failures", async () => {
  const fetch = vi.fn().mockResolvedValue(new Response("", { status: 401 }));
  vi.stubGlobal("fetch", fetch);
  await expect(api("/settings")).rejects.toMatchObject({ status: 401 });
  expect(fetch).toHaveBeenCalledTimes(1);
  fetch.mockReset().mockRejectedValue(new TypeError("offline"));
  await expect(send("/documents", {})).rejects.toThrow();
  expect(fetch).toHaveBeenCalledTimes(1);
});

test("cancelling backoff prevents another attempt", async () => {
  const fetch = vi.fn().mockRejectedValue(new TypeError("offline"));
  vi.stubGlobal("fetch", fetch);
  const controller = new AbortController();
  const pending = api("/settings", { signal: controller.signal });
  controller.abort();
  await expect(pending).rejects.toThrow();
  expect(fetch).toHaveBeenCalledTimes(1);
});
