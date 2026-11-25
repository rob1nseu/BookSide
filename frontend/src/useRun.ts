import { useCallback, useEffect, useRef, useState } from "react";
import { send } from "./api";
import type { Run } from "./types";

export function useRun(
  spaceId: string,
  activeRun: string | null,
  refresh: () => Promise<void>,
  onError: (s: string) => void,
) {
  const [active, setActive] = useState<string | null>(null);
  const [progress, setProgress] = useState("");
  const [result, setResult] = useState<Run["result"]>(null);
  const stream = useRef<EventSource | null>(null);
  const callbacks = useRef({ refresh, onError });
  callbacks.current = { refresh, onError };
  const pending = useRef<((ok: boolean) => void) | null>(null);
  const watch = useCallback((id: string) => {
    stream.current?.close();
    setActive(id);
    const source = new EventSource(`/api/runs/${id}/events`);
    stream.current = source;
    source.onmessage = async (e) => {
      const run: Run = JSON.parse(e.data);
      setProgress(run.partial || "正在处理…");
      if (run.status === "running") return;
      source.close();
      stream.current = null;
      if (run.status === "done") {
        setResult(run.result);
        try {
          await callbacks.current.refresh();
        } catch (e) {
          callbacks.current.onError((e as Error).message);
        }
      } else if (run.status !== "cancelled")
        callbacks.current.onError(run.error || "任务中断，请重试");
      pending.current?.(run.status === "done");
      pending.current = null;
      setActive(null);
    };
    source.onerror = () => {
      // EventSource reconnects with the same run id; no duplicate model request.
      setProgress("连接中断，正在恢复已提交的任务…");
    };
  }, []);
  useEffect(() => {
    if (activeRun && !stream.current) watch(activeRun);
  }, [activeRun, watch]);
  useEffect(
    () => () => {
      stream.current?.close();
      pending.current?.(false);
    },
    [],
  );
  const busy = useRef(false);
  async function act(body: Record<string, unknown>): Promise<boolean> {
    if (busy.current || stream.current) return false;
    busy.current = true;
    setActive("pending");
    setResult(null);
    setProgress("正在提交…");
    try {
      const run = await send<{ id: string }>(`/spaces/${spaceId}/actions`, {
        ...body,
        request_key: crypto.randomUUID(),
      });
      return await new Promise<boolean>((resolve) => {
        pending.current = resolve;
        watch(run.id);
      });
    } catch (e) {
      setActive(null);
      callbacks.current.onError((e as Error).message);
      return false;
    } finally {
      busy.current = false;
    }
  }
  async function cancel() {
    if (active && active !== "pending") {
      try {
        await send(`/runs/${active}/cancel`, {});
      } catch (e) {
        callbacks.current.onError((e as Error).message);
      }
    }
  }
  return {
    active,
    progress,
    result,
    act,
    cancel,
    clear: () => setResult(null),
  };
}
