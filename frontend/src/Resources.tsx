import { useEffect, useState } from "react";
import { api } from "./api";
import { ChevronDown } from "lucide-react";
type Resource = {
  id: string;
  title: string;
  url: string;
  topic: string;
  author: string;
  kind: string;
  language: string;
  prerequisite: string;
  description: string;
  reason: string;
  checked_on: string;
  source_url: string;
};
type Result = {
  document_name: string;
  topics: string[];
  matched_topics: string[];
  items: Resource[];
};
export default function Resources({
  spaceId,
  documentId,
}: {
  spaceId: string;
  documentId: string;
}) {
  const [open, setOpen] = useState(false),
    [topic, setTopic] = useState("");
  const [data, setData] = useState<Result | null>(null),
    [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    if (!open) return;
    const controller = new AbortController();
    setError("");
    setLoading(true);
    void api<Result>(
      `/spaces/${spaceId}/resources?document_id=${documentId}${topic ? `&topic=${encodeURIComponent(topic)}` : ""}`,
      { signal: controller.signal },
    )
      .then((result) => { if (!controller.signal.aborted) setData(result); })
      .catch((e) => {
        if (!controller.signal.aborted) setError(e.message);
      })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [spaceId, documentId, topic, open, retry]);
  return (
    <details
      className="resources"
      onToggle={(e) => setOpen(e.currentTarget.open)}
    >
      <summary>
        教材之外 <span>精选拓展</span>
      </summary>
      {open && (
        <div className="resource-content">
          <p className="muted">
            从另一位好老师的视角，再理解一次。按当前教材匹配，不影响学习进度。
          </p>
          {error ? (
            <p role="alert">
              {error}{" "}
              <button onClick={() => setRetry((v) => v + 1)}>重试</button>
            </p>
          ) : !data ? (
            <p role="status">正在匹配教材主题…</p>
          ) : (
            <>
              <div className="resource-filter">
                <span>{data.document_name}</span>
                <label>
                  <span>拓展方向</span>
                  <span className="resource-select">
                  <select
                    aria-label="拓展方向"
                    value={topic}
                    onChange={(e) => setTopic(e.target.value)}
                  >
                    <option value="">自动匹配教材</option>
                    {data.topics.map((t) => (
                      <option key={t}>{t}</option>
                    ))}
                  </select>
                  <ChevronDown size={16} aria-hidden="true" />
                  </span>
                </label>
              </div>
              {loading && <p role="status">正在更新拓展资料…</p>}
              {!loading && !data.items.length && (
                <p>
                  暂未找到足够可靠的主题匹配。可以选择相关方向；当前资源目录尚未覆盖所有学科。
                </p>
              )}
              {!loading && data.items.map((r, i) => (
                <article className="resource-row" key={r.id}>
                  <span className="resource-number">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <div>
                    <small>
                      {r.kind} · {r.language} · {r.author}
                    </small>
                    <h3>
                      <a href={r.url} target="_blank" rel="noopener noreferrer">
                        {r.title} <span aria-hidden="true">↗</span>
                      </a>
                    </h3>
                    <p>{r.description}</p>
                    <p className="resource-reason">{r.reason}</p>
                    <details>
                      <summary>学习建议与来源</summary>
                      <p>先修：{r.prerequisite}</p>
                      <p>
                        来源核对：{r.checked_on} ·{" "}
                        <a
                          href={r.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                        >
                          原始来源 ↗
                        </a>
                      </p>
                      <p>外部网站的可访问性与内容可能变化。</p>
                    </details>
                  </div>
                </article>
              ))}
            </>
          )}
        </div>
      )}
    </details>
  );
}
