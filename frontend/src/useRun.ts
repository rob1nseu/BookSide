import { useCallback, useEffect, useRef, useState } from "react";
import { api, send } from "./api";
import type { Run } from "./types";
import { learningStatus, recovering } from "./learningStatus";

export function useRun(
  spaceId: string,
  activeRun: string | null,
  refresh: () => Promise<void>,
  onError: (s: string) => void,
) {
  const [active, setActive] = useState<string | null>(null);
  const [progress, setProgress] = useState("");
  const [notice, setNotice] = useState("");
  const [result, setResult] = useState<Run["result"]>(null);
  const stream = useRef<EventSource | null>(null);
  const watchdog = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [disconnected, setDisconnected] = useState<string | null>(null);
  const detached = useRef<string | null>(null);
  const callbacks = useRef({ refresh, onError });
  callbacks.current = { refresh, onError };
  const pending = useRef<((ok: boolean) => void) | null>(null);
  const mounted = useRef(true);
  const watch = useCallback((id: string) => {
    stream.current?.close();
    if (watchdog.current) clearTimeout(watchdog.current);
    detached.current = null;
    setDisconnected(null);
    setNotice("");
    setActive(id);
    const source = new EventSource(`/api/runs/${id}/events`);
    stream.current = source;
    const receive = async (run: Run) => {
      if (stream.current !== source) return;
      setProgress(learningStatus(run.partial || "正在准备学习内容…", true));
      if (run.status === "running") return;
      source.close();
      stream.current = null;
      if (watchdog.current) clearTimeout(watchdog.current);
      if (run.status === "done") {
        setResult(run.result);
        try {
          await callbacks.current.refresh();
        } catch (e) {
          setNotice("内容已保存，暂未能刷新页面。请重新加载学习区。");
        }
      } else if (run.status !== "cancelled")
        setNotice(learningStatus(run.error || "这次还没准备好，请稍后再试。"));
      pending.current?.(run.status === "done");
      pending.current = null;
      setActive(null);
    };
    source.onmessage = (e) => {
      try {
        const value = JSON.parse(e.data);
        if (
          !value ||
          value.id !== id ||
          !["running", "done", "failed", "cancelled", "interrupted"].includes(
            value.status,
          )
        ) {
          throw new Error("Incomplete progress");
        }
        void receive(value);
      } catch {
        setProgress(recovering);
      }
    };
    let failures = 0;
    const poll = async () => {
      if (stream.current !== source) return;
      try {
        const run = await api<Run>(`/runs/${id}`);
        failures = 0;
        await receive(run);
      } catch {
        if (stream.current !== source) return;
        failures++;
        setProgress(recovering);
        if (failures >= 3) {
          source.close();
          stream.current = null;
          detached.current = id;
          setDisconnected(id);
          setActive(null);
          setNotice(
            "暂时无法连接本地服务。任务可能仍在运行，重新连接即可查看，不会重复提交。",
          );
          pending.current?.(false);
          pending.current = null;
          return;
        }
      }
      if (stream.current === source)
        watchdog.current = setTimeout(() => void poll(), 10000);
    };
    watchdog.current = setTimeout(() => void poll(), 10000);
    source.onerror = () => {
      // EventSource reconnects with the same run id; no duplicate model request.
      setProgress(recovering);
    };
  }, []);
  useEffect(() => {
    if (activeRun && !stream.current) watch(activeRun);
  }, [activeRun, watch]);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      stream.current?.close();
      stream.current = null;
      if (watchdog.current) clearTimeout(watchdog.current);
      pending.current?.(false);
      pending.current = null;
    };
  }, []);
  const busy = useRef(false);
  async function act(body: Record<string, unknown>): Promise<boolean> {
    if (busy.current || stream.current || detached.current) return false;
    busy.current = true;
    setActive("pending");
    setResult(null);
    setNotice("");
    setProgress("正在提交…");
    try {
      const run = await send<{ id: string }>(`/spaces/${spaceId}/actions`, {
        ...body,
        request_key: crypto.randomUUID(),
      });
      if (!mounted.current) return false;
      return await new Promise<boolean>((resolve) => {
        pending.current = resolve;
        watch(run.id);
      });
    } catch (e) {
      setActive(null);
      setNotice((e as Error).message);
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
    notice,
    dismissNotice: () => setNotice(""),
    disconnected,
    reconnect: () => {
      if (detached.current) watch(detached.current);
    },
    result,
    act,
    cancel,
    clear: () => setResult(null),
  };
}
