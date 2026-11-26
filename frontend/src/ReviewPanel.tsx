import { lazy, Suspense, useEffect, useState, useRef } from "react";
import { api } from "./api";
import { Prose, verdictLabel } from "./components";
import AnswerEditor from "./AnswerEditor";
import Inquiry from "./Inquiry";
import type { Concept } from "./MindMap";
import type { Feedback, Question, Run } from "./types";
const MindMap = lazy(() => import("./MindMap"));
type ReviewAttempt = {
  id: string;
  position: number;
  node_id: string;
  feedback?: Feedback;
  assisted?: boolean;
  skipped?: boolean;
};
type Review = {
  title: string;
  map: { title: string; nodes: Concept[] } | null;
  states: Record<string, string>;
  round_states: Record<string, string>;
  session: {
    id: string;
    status: string;
    position: number;
    count: number;
    question: (Question & { node_id: string }) | null;
    attempts: ReviewAttempt[];
    assisted: boolean;
  } | null;
};
export default function ReviewPanel({
  spaceId,
  chapterId,
  act,
  active: running,
  result,
  onError,
  cite,
}: {
  spaceId: string;
  chapterId: string;
  act: (body: Record<string, unknown>) => Promise<boolean>;
  active: boolean;
  result: Run["result"];
  onError: (s: string) => void;
  cite: (id: string) => void;
}) {
  const [data, setData] = useState<Review | null>(null);
  const [selected, setSelected] = useState("");
  const [mode, setMode] = useState<"map" | "practice">("map");
  const [help, setHelp] = useState(false);
  const [askNode, setAskNode] = useState(false);
  const [replyScope, setReplyScope] = useState("");
  const [refreshing, setRefreshing] = useState(false);
  const [loadError, setLoadError] = useState("");
  const wasRunning = useRef(running);
  const active = running || refreshing;
  async function reload() {
    const value = await api<Review>(
      `/spaces/${spaceId}/review?chapter_id=${chapterId}`,
    );
    setData(value);
    setLoadError("");
    return value;
  }
  useEffect(() => {
    let alive = true;
    void api<Review>(`/spaces/${spaceId}/review?chapter_id=${chapterId}`)
      .then((v) => {
        if (alive) {
          setData(v);
          if (v.session?.status === "active") setMode("practice");
        }
      })
      .catch((e) => {
        if (alive) setLoadError(e.message);
      });
    return () => {
      alive = false;
    };
  }, [spaceId, chapterId]);
  useEffect(() => {
    const finished = wasRunning.current && !running;
    wasRunning.current = running;
    // After a browser reload there is no local perform() awaiting this run.
    if (finished && !refreshing) {
      void reload()
        .then((value) => {
          if (value.session?.status === "active") setMode("practice");
        })
        .catch((e) => setLoadError(e.message));
    }
  }, [running]);
  const session = data?.session,
    q = session?.question;
  useEffect(() => {
    setHelp(false);
    setReplyScope("");
  }, [q?.id]);
  const node = data?.map?.nodes.find((n) => n.id === selected);
  const attempt = session?.attempts
    .filter((a) => a.position === session.position)
    .at(-1);
  async function perform(action: string, extra: Record<string, unknown> = {}) {
    if (active) return false;
    setRefreshing(true);
    setReplyScope(action);
    try {
      const ok = await act({
        action,
        chapter_id: chapterId,
        session_id: session?.id,
        question_id: q?.id,
        ...extra,
      });
      if (ok) {
        try {
          await reload();
        } catch (e) {
          onError((e as Error).message);
        }
      }
      return ok;
    } finally {
      setRefreshing(false);
    }
  }
  if (!data)
    return loadError ? (
      <div role="alert">
        {loadError}
        <button
          onClick={() => void reload().catch((e) => setLoadError(e.message))}
        >
          重新打开复习
        </button>
      </div>
    ) : (
      <p role="status">正在打开章节复习…</p>
    );
  return (
    <section className="review-panel">
      <div className="review-heading">
        <div>
          <small>考前复习 · 先看结构，再用题目验证</small>
          <h1>
            <Prose inline>{data.title}</Prose>
          </h1>
        </div>
        {data.map && (
          <div className="review-tabs">
            <button
              aria-pressed={mode === "map"}
              onClick={() => setMode("map")}
            >
              章节导图
            </button>
            <button
              aria-pressed={mode === "practice"}
              onClick={() => setMode("practice")}
            >
              复习练习
            </button>
          </div>
        )}
      </div>
      {!data.map ? (
        <div className="start-task">
          <h2>把这一章串起来</h2>
          <p>从讲义提炼概念、条件与易混点，生成一次后保留。无需先学完本章。</p>
          <button
            className="primary"
            disabled={active}
            onClick={() => void perform("review_map")}
          >
            生成章节思维导图
          </button>
        </div>
      ) : (
        <>
          {mode === "map" && (
            <>
              <Suspense fallback={<p>正在打开导图…</p>}>
                <MindMap
                  title={data.title}
                  concepts={data.map.nodes}
                  states={data.states}
                  selected={selected}
                  onSelect={(id) => {
                    setSelected(id);
                    setAskNode(false);
                    setReplyScope("");
                  }}
                />
              </Suspense>
              {node ? (
                <article className="concept-detail">
                  <h2>
                    <Prose inline>{node.label}</Prose>
                  </h2>
                  <Prose>{node.summary}</Prose>
                  <div className="citations">
                    {node.sources.map((id) => (
                      <button key={id} onClick={() => cite(id)}>
                        查看讲义原页
                      </button>
                    ))}
                  </div>
                  <button
                    disabled={active}
                    onClick={() => setAskNode(!askNode)}
                  >
                    问这个知识点
                  </button>
                  <button
                    className="primary"
                    disabled={active || session?.status === "active"}
                    onClick={async () => {
                      if (await perform("review_start", { node_id: node.id })) {
                        setMode("practice");
                        setHelp(false);
                      }
                    }}
                  >
                    练一下
                  </button>
                  {askNode && (
                    <Inquiry
                      key={node.id}
                      scopeKey={`node:${spaceId}:${chapterId}:${node.id}`}
                      title={`正在问讲义 · ${node.label}`}
                      button="发送讲义问题"
                      sources={result?.sources}
                      supplement={result?.supplement}
                      cite={cite}
                      historyUrl={`/messages?space_id=${spaceId}&chapter_id=${chapterId}&node_id=${node.id}`}
                      disabled={active}
                      reply={
                        replyScope === "review_node" ? result?.text : undefined
                      }
                      onSend={(text) =>
                        perform("review_node", { node_id: node.id, text })
                      }
                    />
                  )}
                </article>
              ) : (
                <p className="muted">
                  选中一个节点，查看要点、讲义来源或针对性练习。
                </p>
              )}
              <button
                className="primary"
                disabled={active}
                onClick={async () => {
                  if (session?.status === "active") setMode("practice");
                  else if (await perform("review_start")) {
                    setMode("practice");
                    setHelp(false);
                  }
                }}
              >
                {session?.status === "active" ? "继续本轮练习" : "本章练一轮"}
              </button>
            </>
          )}
          {mode === "practice" && (
            <>
              {!session && (
                <div className="start-task">
                  <h2>用几道题检查理解</h2>
                  <p>优先覆盖需巩固和尚未验证的知识点。</p>
                  <button
                    className="primary"
                    disabled={active}
                    onClick={() => void perform("review_start")}
                  >
                    开始本章练习
                  </button>
                </div>
              )}
              {session?.status === "active" && q && (
                <>
                  <p className="review-position">
                    第 {session.position + 1} / {session.count} 题 ·{" "}
                    {data.map.nodes.find((n) => n.id === q.node_id)?.label}
                    {session.assisted ? " · 已获得辅助" : ""}
                  </p>
                  <section className="question review-question">
                    <div>
                      <Prose>{q.prompt}</Prose>
                      <div className="question-tools">
                        <button
                          disabled={active}
                          onClick={() => setHelp(!help)}
                        >
                          {help ? "返回作答" : "问这道题"}
                        </button>
                        <button
                          disabled={active}
                          onClick={() => void perform("review_hint")}
                        >
                          给个提示
                        </button>
                      </div>
                      {help ? (
                        <Inquiry
                          key={q.id}
                          scopeKey={`review-help:${q.id}`}
                          title={`正在问第 ${session.position + 1} 题`}
                          button="发送题目问题"
                          sources={result?.sources}
                          supplement={result?.supplement}
                          cite={cite}
                          historyUrl={`/messages?space_id=${spaceId}&session_id=${session.id}&question_id=${q.id}`}
                          disabled={active}
                          onSend={(text) => perform("review_help", { text })}
                          reply={
                            replyScope === "review_help"
                              ? result?.text
                              : undefined
                          }
                        />
                      ) : (
                        <AnswerEditor
                          key={q.id}
                          spaceId={spaceId}
                          question={q}
                          disabled={active}
                          onSubmit={(value) => perform("review_answer", value)}
                        />
                      )}
                    </div>
                  </section>
                  {replyScope === "review_hint" && result?.text && (
                    <div className="reply">
                      <Prose>{result.text}</Prose>
                    </div>
                  )}
                  {attempt?.feedback && (
                    <section className={"feedback " + attempt.feedback.verdict}>
                      <h3>
                        {verdictLabel[attempt.feedback.verdict]}
                        {attempt.assisted ? " · 辅助完成" : ""}
                      </h3>
                      <Prose>{attempt.feedback.explanation}</Prose>
                      <div className="citations">
                        {attempt.feedback.sources.map((id, i) => (
                          <button key={id} onClick={() => cite(id)}>
                            查看引用 {i + 1}
                          </button>
                        ))}
                      </div>
                      {attempt.feedback.missing.map((m) => (
                        <div key={m}>
                          需补充：<Prose>{m}</Prose>
                        </div>
                      ))}
                      <Prose>{attempt.feedback.next_step}</Prose>
                      <button
                        onClick={() => {
                          setSelected(q.node_id);
                          setMode("map");
                        }}
                      >
                        回导图补习这个知识点
                      </button>
                    </section>
                  )}
                  <div className="task-actions">
                    <button
                      className="primary"
                      disabled={active}
                      onClick={() => void perform("review_next")}
                    >
                      {attempt ? "继续下一题" : "跳过，保持未验证"}
                    </button>
                    <button
                      disabled={active}
                      onClick={() => void perform("review_end")}
                    >
                      结束本轮
                    </button>
                  </div>
                </>
              )}
              {session?.status === "done" && (
                <section className="review-summary">
                  <h2>本轮复习完成</h2>
                  {["本轮已验证", "需巩固", "未验证"].map((state) => (
                    <div key={state}>
                      <h3>{state}</h3>
                      <Prose>
                        {data
                          .map!.nodes.filter(
                            (n) =>
                              (data.round_states[n.id] || "未验证") === state,
                          )
                          .map((n) => n.label)
                          .join("、") || "暂无"}
                      </Prose>
                    </div>
                  ))}
                  <p>
                    建议先回看需巩固的节点，再用新题验证。跳过和辅助完成不计为独立通过。
                  </p>
                  <button onClick={() => setMode("map")}>返回导图</button>
                  <button
                    disabled={active}
                    onClick={() => void perform("review_start")}
                  >
                    再练一轮新题
                  </button>
                </section>
              )}
            </>
          )}
        </>
      )}
    </section>
  );
}
