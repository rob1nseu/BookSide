import { lazy, Suspense, useEffect, useState } from "react";
import { BookOpen, FileText, Pencil, Square } from "lucide-react";
import { api, send } from "./api";
import { Prose, statusLabel, verdictLabel } from "./components";
import type { Space, Page, Message } from "./types";
import { useRun } from "./useRun";
import AnswerEditor from "./AnswerEditor";
import Inquiry from "./Inquiry";
const PdfReader = lazy(() => import("./PdfReader"));
const ReviewPanel = lazy(() => import("./ReviewPanel"));
const Resources = lazy(() => import("./Resources"));

export default function Workspace({
  space,
  onRefresh,
  onError,
  configured,
  onOpen,
}: {
  space: Space;
  onRefresh: () => Promise<void>;
  onError: (s: string) => void;
  configured: boolean;
  onOpen: (id: string) => void;
}) {
  const chapter = space.chapters.find((c) => c.id === space.current_chapter),
    question = chapter?.question;
  const [pages, setPages] = useState<Page[]>([]);
  const [reader, setReader] = useState(false);
  const [target, setTarget] = useState({ doc: "", page: 1 });
  const [practice, setPractice] = useState(false);
  const [questionHelp, setQuestionHelp] = useState(false);
  const [lectureOpen, setLectureOpen] = useState(false);
  const [lastKind, setLastKind] = useState("");
  const [history, setHistory] = useState<Message[] | null>(null);
  const run = useRun(space.id, space.active_run, onRefresh, onError);
  const busy = !!run.active;
  useEffect(() => {
    let alive = true;
    void Promise.all(
      space.documents
        .filter((d) => ["ready", "partial"].includes(d.status))
        .map((d) => api<Page[]>(`/documents/${d.id}/pages`)),
    )
      .then((all) => {
        if (alive) setPages(all.flat());
      })
      .catch((e) => onError(e.message));
    return () => {
      alive = false;
    };
  }, [space.documents.map((d) => d.id + d.status).join(",")]);
  useEffect(() => {
    if (!chapter) return;
    setTarget({ doc: chapter.document_id, page: chapter.start_page });
    setPractice(
      localStorage.getItem("practice:" + chapter.id) === "true" ||
        chapter.attempts.some((a) => a.question_id === question?.id),
    );
    setQuestionHelp(false);
    setLectureOpen(false);
    setLastKind("");
    setHistory(null);
  }, [chapter?.id, space.mode]);
  useEffect(() => {
    setQuestionHelp(false);
    setLastKind("");
  }, [question?.id]);
  async function act(action: string, extra: Record<string, unknown> = {}) {
    if (!chapter) return false;
    setLastKind(action);
    return run.act({
      action,
      chapter_id: chapter.id,
      question_id: question?.id,
      ...extra,
    });
  }
  function cite(id: string) {
    const p = pages.find((p) => p.id === id);
    if (p) {
      setTarget({ doc: p.document_id, page: p.number });
      setReader(true);
    } else onError("暂时无法定位引用页，请打开资料查看。");
  }
  const citations = (ids: string[] = []) => (
    <div className="citations">
      {ids.map((id) => {
        const p = pages.find((p) => p.id === id);
        return (
          <button key={id} className="text" onClick={() => cite(id)}>
            <BookOpen size={15} />
            {p
              ? `${space.documents.find((d) => d.id === p.document_id)?.name} · 第 ${p.number} 页`
              : "查看原文"}
          </button>
        );
      })}
    </div>
  );
  const currentDoc = space.documents.find((d) => d.id === target.doc);
  const lastAttempt = chapter?.attempts
    .filter((a) => a.question_id === question?.id)
    .at(-1);
  async function switchMode() {
    try {
      await send(
        `/spaces/${space.id}`,
        { mode: space.mode === "review" ? "learn" : "review" },
        "PATCH",
      );
      await onRefresh();
    } catch (e) {
      onError((e as Error).message);
    }
  }
  async function nextChapter() {
    const chapters = space.chapters.filter((c) => !c.is_group);
    const next = chapters[chapters.findIndex((c) => c.id === chapter?.id) + 1];
    if (!next) {
      onError("已经到最后一节，可以回看或进入考前复习。");
      return;
    }
    try {
      await send(`/spaces/${space.id}`, { chapter_id: next.id }, "PATCH");
      await onRefresh();
    } catch (e) {
      onError((e as Error).message);
    }
  }
  return (
    <div className={"workspace-layout " + (reader ? "with-reader" : "")}>
      <main className="workspace">
        <header className="workspace-top">
          <span>
            {space.name} / {space.mode === "review" ? "考前复习" : "章节学习"}
          </span>
          <div>
            <button
              disabled={busy || !chapter}
              onClick={() => void switchMode()}
            >
              <BookOpen size={18} />
              {space.mode === "review" ? "返回章节学习" : "考前复习"}
            </button>
            <button disabled={!chapter} onClick={() => setReader(!reader)}>
              <FileText size={18} />
              阅读资料
            </button>
          </div>
        </header>
        {space.legacy_outline && (
          <div className="notice">
            原学习记录保留，可复用资料修正旧目录。
            <button
              disabled={busy}
              onClick={() =>
                void send<{ id: string }>(
                  `/spaces/${space.id}/rebuild-outline`,
                  {},
                )
                  .then((s) => onOpen(s.id))
                  .catch((e) => onError(e.message))
              }
            >
              用新目录创建学习空间
            </button>
          </div>
        )}
        {space.chapters.some((c) =>
          ["queued", "running"].includes(c.preparation),
        ) && (
          <div className="preparation-status">
            后台正在准备章节，不影响当前阅读。
            <button
              onClick={() =>
                void send(`/spaces/${space.id}/preparation/stop`, {})
                  .then(onRefresh)
                  .catch((e) => onError(e.message))
              }
            >
              暂停后台准备
            </button>
          </div>
        )}
        <div className="task-scroll">
          {!chapter ? (
            <section className="empty">
              <h1>正在准备学习资料</h1>
              {space.documents.map((d) => (
                <p key={d.id}>
                  {d.name} · {statusLabel[d.status]} {d.error}
                  {d.status === "failed" && (
                    <button
                      onClick={() =>
                        void send(`/documents/${d.id}/retry`, {})
                          .then(onRefresh)
                          .catch((e) => onError(e.message))
                      }
                    >
                      重试解析
                    </button>
                  )}
                </p>
              ))}
            </section>
          ) : space.mode === "review" ? (
            <Suspense fallback={<p>正在打开复习工作台…</p>}>
              <ReviewPanel
                key={chapter.parent_id || chapter.id}
                spaceId={space.id}
                chapterId={chapter.id}
                act={(body) => {
                  setLastKind(String(body.action));
                  return run.act(body);
                }}
                active={busy || !configured}
                result={run.result}
                onError={onError}
                cite={cite}
              />
            </Suspense>
          ) : (
            <>
              <div className="task-heading">
                <div>
                  <h1>
                    <Prose inline>{chapter.title}</Prose>
                  </h1>
                  <p>
                    <Prose inline>
                      {chapter.lesson?.objective || "一次只学懂一个小问题。"}
                    </Prose>
                  </p>
                </div>
                <button
                  className="icon"
                  aria-label="修改章节名称"
                  onClick={async () => {
                    const title = prompt("章节名称", chapter.title);
                    if (title?.trim())
                      try {
                        await send(
                          `/spaces/${space.id}/chapters/${chapter.id}`,
                          { title },
                          "PATCH",
                        );
                        await onRefresh();
                      } catch (e) {
                        onError((e as Error).message);
                      }
                  }}
                >
                  <Pencil size={16} />
                </button>
              </div>
              {!chapter.lesson ? (
                <section className="start-task">
                  <span className="drawn-sprout">✳</span>
                  <h2>从这一节开始</h2>
                  <p>先准备当前小节，所需先修知识会从讲义中检索。</p>
                  {chapter.preparation_error && (
                    <p role="alert">{chapter.preparation_error}</p>
                  )}
                  <button
                    className="primary"
                    disabled={busy || !configured}
                    onClick={() => void act("teach")}
                  >
                    开始学习
                  </button>
                  {!configured && (
                    <p>请先在设置中配置 DeepSeek，资料仍可阅读。</p>
                  )}
                </section>
              ) : (
                <>
                  <details className="lesson-details" open={!practice}>
                    <summary>回看本节讲解</summary>
                    <article className="lesson">
                      <h2>先理解，再往前走</h2>
                      <Prose>{chapter.lesson.explanation}</Prose>
                      {chapter.lesson.example && (
                        <div className="example">
                          <strong>举个例子</strong>
                          <Prose>{chapter.lesson.example}</Prose>
                        </div>
                      )}
                      {chapter.lesson.supplement && (
                        <div className="supplement">
                          <strong>课外补充</strong>
                          <Prose>{chapter.lesson.supplement}</Prose>
                        </div>
                      )}
                      {citations(chapter.lesson.sources)}
                      <button
                        disabled={busy || !configured}
                        onClick={() => {
                          setLectureOpen(true);
                          setQuestionHelp(false);
                          void act("ask", {
                            text: "请用更直观的例子重新解释当前小节的核心概念。",
                            question_id: null,
                          });
                        }}
                      >
                        换个解释
                      </button>
                    </article>
                  </details>
                  {question ? (
                    <>
                      <section className="question">
                        <span className="question-mark">?</span>
                        <div className="question-content">
                          <small>
                            核心问题 {chapter.question_index + 1} /{" "}
                            {chapter.question_count}
                            {chapter.hint_used ? " · 已获得辅助" : ""}
                          </small>
                          <Prose>{question.prompt}</Prose>
                          {question.unit && (
                            <small>单位：{question.unit}</small>
                          )}
                          <div className="question-tools">
                            <button
                              disabled={busy}
                              onClick={() => {
                                setQuestionHelp(!questionHelp);
                                setLectureOpen(false);
                              }}
                            >
                              {questionHelp ? "返回作答" : "问这道题"}
                            </button>
                            {practice && (
                              <button
                                disabled={busy}
                                onClick={() => void act("hint")}
                              >
                                给个提示
                              </button>
                            )}
                          </div>
                          {questionHelp ? (
                            <Inquiry
                              key={question.id}
                              scopeKey={`question:${question.id}`}
                              title={`正在问第 ${chapter.question_index + 1} 题 · ${chapter.title}`}
                              button="发送题目问题"
                              sources={run.result?.sources}
                              supplement={run.result?.supplement}
                              cite={cite}
                              disabled={busy || !configured}
                              historyUrl={`/messages?space_id=${space.id}&question_id=${question.id}`}
                              onSend={(text) => act("ask_question", { text })}
                              reply={
                                lastKind === "ask_question"
                                  ? run.result?.text
                                  : undefined
                              }
                            />
                          ) : practice && !lectureOpen ? (
                            <AnswerEditor
                              key={question.id}
                              question={question}
                              spaceId={space.id}
                              disabled={busy || !configured}
                              onSubmit={(value) => act("answer", value)}
                            />
                          ) : !practice ? (
                            <button
                              className="primary"
                              disabled={busy}
                              onClick={() => {
                                setPractice(true);
                                setLectureOpen(false);
                                localStorage.setItem(
                                  "practice:" + chapter.id,
                                  "true",
                                );
                              }}
                            >
                              来试一道题
                            </button>
                          ) : (
                            <p>答案草稿已保留，关闭讲义提问即可继续作答。</p>
                          )}
                        </div>
                      </section>
                      {lastAttempt && (
                        <section
                          className={"feedback " + lastAttempt.feedback.verdict}
                        >
                          <h3>
                            {lastAttempt.disputed
                              ? "此判分存疑"
                              : verdictLabel[lastAttempt.feedback.verdict]}
                            {lastAttempt.assisted ? " · 辅助完成" : ""}
                          </h3>
                          <Prose>{lastAttempt.feedback.explanation}</Prose>
                          {citations(lastAttempt.feedback.sources)}
                          {lastAttempt.feedback.missing.map((m) => (
                            <div key={m}>
                              需补充：<Prose>{m}</Prose>
                            </div>
                          ))}
                          <Prose>{lastAttempt.feedback.next_step}</Prose>
                          <button
                            disabled={busy}
                            onClick={async () => {
                              try {
                                if (!lastAttempt.disputed)
                                  await send(
                                    `/attempts/${lastAttempt.id}/dispute`,
                                    {},
                                  );
                                await act("retry_grade");
                              } catch (e) {
                                onError((e as Error).message);
                              }
                            }}
                          >
                            判分有疑问，核对一次
                          </button>
                        </section>
                      )}
                      <div className="task-actions">
                        {lastAttempt && (
                          <button
                            className="primary"
                            disabled={busy}
                            onClick={() => void act("next")}
                          >
                            继续下一题
                          </button>
                        )}
                        <button
                          disabled={busy}
                          onClick={() => void act("skip")}
                        >
                          跳过这一题
                        </button>
                        <details className="more-actions">
                          <summary>更多</summary>
                          <button
                            disabled={busy}
                            onClick={() => void act("solution")}
                          >
                            查看解答
                          </button>
                          <button
                            disabled={busy}
                            onClick={() => void act("train")}
                          >
                            针对性练一轮
                          </button>
                        </details>
                      </div>
                    </>
                  ) : (
                    <div className="notice">
                      本轮核心问题已结束 · {chapter.state}
                      <button onClick={() => void nextChapter()}>
                        继续下一章
                      </button>
                      <button disabled={busy} onClick={() => void act("train")}>
                        针对性练一轮
                      </button>
                    </div>
                  )}
                </>
              )}
              {["hint", "solution"].includes(lastKind) && run.result?.text && (
                <section className="reply">
                  <Prose>{run.result.text}</Prose>
                  {citations(run.result.sources)}
                </section>
              )}
              <Suspense fallback={null}>
                <Resources
                  key={chapter.document_id}
                  spaceId={space.id}
                  documentId={chapter.document_id}
                />
              </Suspense>
              <details className="learning-tools">
                <summary>学习记录与准备选项</summary>
                <button
                  disabled={busy || !configured}
                  onClick={() =>
                    void send(`/spaces/${space.id}/preparation`, {})
                      .then(onRefresh)
                      .catch((e) => onError(e.message))
                  }
                >
                  后台准备整章
                </button>
                <a href={`/api/spaces/${space.id}/export`} download>
                  导出学习记录
                </a>
                <button
                  onClick={() => {
                    if (history) setHistory(null);
                    else
                      void api<Message[]>(`/messages?space_id=${space.id}`)
                        .then(setHistory)
                        .catch((e) => onError(e.message));
                  }}
                >
                  {history ? "收起" : "展开"}学习记录
                </button>
                {history && (
                  <div className="history-list">
                    {history.map((m) => (
                      <article key={m.id}>
                        <small>{m.role === "user" ? "你" : "Tutor"}</small>
                        <Prose>{m.text}</Prose>
                      </article>
                    ))}
                  </div>
                )}
              </details>
            </>
          )}
        </div>
        {busy && (
          <div className="run-progress" role="status">
            <span className="spinner" />
            {run.progress}
            <button
              disabled={run.active === "pending"}
              onClick={() => void run.cancel()}
            >
              <Square size={13} />
              取消
            </button>
          </div>
        )}
        {chapter && space.mode !== "review" && (
          <footer className="lecture-dock">
            <button
              aria-expanded={lectureOpen}
              onClick={() => {
                setLectureOpen(!lectureOpen);
                setQuestionHelp(false);
              }}
            >
              {lectureOpen ? "关闭讲义提问，返回学习" : "问讲义"}
              <span> · {chapter.title}</span>
            </button>
            {lectureOpen && (
              <Inquiry
                key={chapter.id}
                scopeKey={`lecture:${chapter.id}`}
                title={`正在问讲义 · ${chapter.title} · 第 ${chapter.start_page} 页起`}
                button="发送讲义问题"
                sources={run.result?.sources}
                supplement={run.result?.supplement}
                cite={cite}
                disabled={busy || !configured}
                historyUrl={`/messages?space_id=${space.id}&chapter_id=${chapter.id}`}
                onSend={(text) => act("ask", { text, question_id: null })}
                reply={lastKind === "ask" ? run.result?.text : undefined}
              />
            )}
          </footer>
        )}
      </main>
      {reader && currentDoc && (
        <Suspense fallback={<aside className="reader">正在打开阅读器…</aside>}>
          <PdfReader
            document={currentDoc}
            page={target.page}
            pages={pages.filter((p) => p.document_id === currentDoc.id)}
            onPage={(page) => setTarget({ ...target, page })}
            close={() => setReader(false)}
          />
        </Suspense>
      )}
    </div>
  );
}
