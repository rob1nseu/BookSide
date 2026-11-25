import { useEffect, useState } from "react";
import { api } from "./api";
import { Prose } from "./components";
import type { Message } from "./types";
export default function Inquiry({
  scopeKey,
  title,
  button,
  disabled,
  onSend,
  historyUrl,
  reply,
  sources,
  supplement,
  cite,
}: {
  scopeKey: string;
  title: string;
  button: string;
  disabled: boolean;
  onSend: (text: string) => Promise<boolean>;
  historyUrl?: string;
  reply?: string;
  sources?: string[];
  supplement?: boolean;
  cite?: (id: string) => void;
}) {
  const key = "inquiry:v2:" + scopeKey;
  const [text, setText] = useState(() => localStorage.getItem(key) || "");
  const [history, setHistory] = useState<Message[]>([]);
  const [error, setError] = useState("");
  useEffect(() => {
    if (historyUrl)
      void api<Message[]>(historyUrl)
        .then(setHistory)
        .catch((e) => setError(e.message));
  }, [historyUrl, reply]);
  async function submit() {
    if (disabled || !text.trim()) return;
    const sent = text;
    if (await onSend(sent)) {
      setText((old) => (old === sent ? "" : old));
      if (localStorage.getItem(key) === sent) localStorage.removeItem(key);
    }
  }
  return (
    <section className="inquiry">
      <strong>{title}</strong>
      {error && <p role="alert">{error}</p>}
      {history.length > 0 && (
        <details className="inquiry-history">
          <summary>此处的提问记录（{history.length}）</summary>
          {history.map((m) => (
            <article key={m.id}>
              <small>{m.role === "user" ? "你" : "Tutor"}</small>
              <Prose>{m.text}</Prose>
            </article>
          ))}
        </details>
      )}
      {reply && (
        <div className="reply">
          {supplement && <strong>课外补充 · 请与讲义区分</strong>}
          <Prose>{reply}</Prose>
          {cite && !!sources?.length && (
            <div className="citations">
              {sources.map((id, i) => (
                <button key={id} onClick={() => cite(id)}>
                  查看引用 {i + 1}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void submit();
        }}
      >
        <textarea
          aria-label={
            button === "发送题目问题" ? "题目提问输入框" : "讲义提问输入框"
          }
          rows={2}
          value={text}
          placeholder={
            button === "发送题目问题"
              ? "哪里没看懂？可以询问题意或请求提示。"
              : "针对当前章节或知识点提出问题。"
          }
          onChange={(e) => {
            setText(e.target.value);
            localStorage.setItem(key, e.target.value);
          }}
        />
        <button disabled={disabled || !text.trim()}>{button}</button>
      </form>
    </section>
  );
}
