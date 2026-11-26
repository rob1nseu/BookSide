import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { api, send } from "./api";
import { useRun } from "./useRun";

vi.mock("./api", () => ({ api: vi.fn(), send: vi.fn() }));
class Events {
  static instances: Events[] = [];
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  close = vi.fn();
  constructor(public url: string) {
    Events.instances.push(this);
  }
}
beforeEach(() => {
  vi.useFakeTimers();
  vi.resetAllMocks();
  Events.instances = [];
  vi.stubGlobal("EventSource", Events);
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

test("broken progress stream recovers the existing run through polling", async () => {
  const refresh = vi.fn().mockResolvedValue(undefined),
    error = vi.fn();
  vi.mocked(api).mockResolvedValue({
    id: "run-a",
    status: "done",
    result: { reply: "saved" },
  });
  const { result, unmount } = renderHook(() =>
    useRun("space", "run-a", refresh, error),
  );
  await act(async () => Events.instances[0].onmessage?.({ data: "{broken" }));
  expect(result.current.active).toBe("run-a");
  await act(async () => {
    await vi.advanceTimersByTimeAsync(10000);
  });
  expect(result.current.active).toBeNull();
  expect(refresh).toHaveBeenCalledTimes(1);
  expect(error).not.toHaveBeenCalled();
  expect(send).not.toHaveBeenCalled();
  unmount();
});

test("offline task stops spinning and reconnects without resubmitting", async () => {
  vi.mocked(api).mockRejectedValue(new Error("offline"));
  const { result, unmount } = renderHook(() =>
    useRun("space", "run-a", async () => {}, vi.fn()),
  );
  await act(async () => {
    await vi.advanceTimersByTimeAsync(30000);
  });
  expect(result.current.active).toBeNull();
  expect(result.current.disconnected).toBe("run-a");
  expect(result.current.notice).toContain("重新连接");
  await act(async () => {
    expect(await result.current.act({ action: "teach" })).toBe(false);
  });
  expect(send).not.toHaveBeenCalled();
  await act(async () => result.current.reconnect());
  expect(Events.instances.at(-1)?.url).toBe("/api/runs/run-a/events");
  expect(result.current.active).toBe("run-a");
  unmount();
});

test("late submit response after leaving the page cannot open a stream", async () => {
  let resolve!: (value: unknown) => void;
  vi.mocked(send).mockImplementation(
    () =>
      new Promise((r) => {
        resolve = r;
      }),
  );
  const { result, unmount } = renderHook(() =>
    useRun("space", null, async () => {}, vi.fn()),
  );
  let pending!: Promise<boolean>;
  act(() => {
    pending = result.current.act({ action: "teach" });
  });
  unmount();
  await act(async () => {
    resolve({ id: "late" });
    await pending;
  });
  expect(Events.instances).toHaveLength(0);
});
