import { useEffect, useState } from "react";
import { Send, X, Sprout } from "lucide-react";
import { api, send } from "./api";
import { Prose } from "./components";
import type { Message, Run } from "./types";
export default function Partner({ close }: { close: () => void }) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [privateTurn, setPrivateTurn] = useState(false);
  const refresh = () => api<Message[]>("/messages").then(setMessages);
  useEffect(() => {
    void refresh().catch((e) => setError(e.message));
  }, []);
  async function chat(e: React.FormEvent) {
    e.preventDefault();
    if (!text.trim()) return;
    setBusy(true);
    setError("");
    try {
      const run = await send<{ id: string }>("/partner/actions", {
        action: "partner",
        text,
        private: privateTurn,
        request_key: crypto.randomUUID(),
      });
      setText("");
      await new Promise<void>((resolve, reject) => {
        const stream = new EventSource(`/api/runs/${run.id}/events`);
        stream.onmessage = (event) => {
          const state: Run = JSON.parse(event.data);
          if (state.status !== "running") {
            stream.close();
            state.status === "done"
              ? resolve()
              : reject(new Error(state.error || "生成已取消"));
          }
        };
        stream.onerror = () => {
          stream.close();
          reject(new Error("连接中断，请重新打开陪聊查看已保存记录"));
        };
      });
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="partner" aria-label="小芽陪聊">
      <header>
        <Sprout />
        <div>
          <strong>小芽</strong>
          <small>不赶进度，只陪你聊聊</small>
        </div>
        <button className="icon" onClick={close} aria-label="关闭陪聊">
          <X />
        </button>
      </header>
      <div className="partner-messages">
        {!messages.length && (
          <p className="muted">
            你好，我是小芽。学习之外，也可以在这里歇一会儿。
          </p>
        )}
        {messages.map((m) => (
          <div key={m.id} className={"chat " + m.role}>
            <small>{m.role === "user" ? "你" : "小芽"}</small>
            <Prose>{m.text}</Prose>
          </div>
        ))}
        {busy && <p role="status">小芽正在想怎么回应…</p>}
        {error && (
          <p role="alert" className="error-text">
            {error}
          </p>
        )}
      </div>
      <form onSubmit={chat}>
        <label className="inline small">
          <input
            type="checkbox"
            checked={privateTurn}
            onChange={(e) => setPrivateTurn(e.target.checked)}
          />
          本次不进入长期记忆
        </label>
        <div className="chat-input">
          <input
            aria-label="发送给小芽"
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder="跟小芽说点什么…"
          />
          <button
            className="icon primary"
            disabled={busy || !text.trim()}
            aria-label="发送陪聊"
          >
            <Send size={18} />
          </button>
        </div>
      </form>
    </section>
  );
}
