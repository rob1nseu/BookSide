import { lazy, Suspense, useEffect, useRef, useState } from "react";
import {
  BookOpen,
  Check,
  FileText,
  MoreHorizontal,
  RefreshCw,
  Send,
  Square,
  Pencil,
} from "lucide-react";
import { api, send } from "./api";
import { Prose, statusLabel, verdictLabel } from "./components";
import type { Space, Page, Message, Run } from "./types";
const PdfReader = lazy(() => import("./PdfReader"));
const AnswerImage = lazy(() => import("./AnswerImage"));
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
  const chapter = space.chapters.find((c) => c.id === space.current_chapter);
  const question = chapter?.question;
  const draftKey = "draft:" + chapter?.id + ":" + (question?.id || "ask");
  const [selectedOption, setSelectedOption] = useState("");
  const [pages, setPages] = useState<Page[]>([]);
  const [reader, setReader] = useState(false);
  const [target, setTarget] = useState({ doc: "", page: 1 });
  const [draft, setDraft] = useState("");
  const [askMode, setAskMode] = useState(false);
  const [practice, setPractice] = useState(false);
  const [more, setMore] = useState(false);
  const [history, setHistory] = useState<Message[] | null>(null);
  const [reply, setReply] = useState<Run["result"]>(null);
  const [active, setActive] = useState<string | null>(null);
  const [progress, setProgress] = useState("");
  const [failed, setFailed] = useState(false);
  const pending = useRef<{
    action: string;
    text: string;
    chapterId: string;
    draftKey: string;
  } | null>(null);
  const source = useRef<EventSource | null>(null);
  const [lastAction, setLastAction] = useState<{
    action: string;
    text: string;
  } | null>(null);
  useEffect(() => {
    void Promise.all(
      space.documents
        .filter((d) => ["ready", "partial"].includes(d.status))
        .map((d) => api<Page[]>(`/documents/${d.id}/pages`)),
    )
      .then((all) => setPages(all.flat()))
      .catch((e) => onError(e.message));
  }, [space.documents.map((d) => d.id + d.status).join(",")]);
  useEffect(() => {
    if (chapter) {
      setTarget({ doc: chapter.document_id, page: chapter.start_page });
      setDraft(localStorage.getItem(draftKey) || "");
      setSelectedOption(localStorage.getItem("option:" + question?.id) || "");
      setPractice(
        space.mode === "review" ||
          chapter.attempts.some(
            (a) => a.question_id === chapter.question?.id,
          ) ||
          localStorage.getItem("practice:" + chapter.id) === "true",
      );
      setReply(null);
      setAskMode(false);
    }
  }, [chapter?.id, question?.id, space.mode]);
  useEffect(() => () => source.current?.close(), []);
  function watch(id: string) {
    if (active === id) return;
    source.current?.close();
    setActive(id);
    const stream = new EventSource(`/api/runs/${id}/events`);
    source.current = stream;
    stream.onmessage = (event) => {
      const state: Run = JSON.parse(event.data);
      setProgress(state.partial || "正在处理…");
      if (state.status !== "running") {
        stream.close();
        setActive(null);
        if (state.status === "done") {
          setFailed(false);
          const sent = pending.current;
          if (sent && (sent.action === "answer" || sent.action === "ask")) {
            setDraft((old) => (old === sent.text ? "" : old));
            if (localStorage.getItem(sent.draftKey) === sent.text)
              localStorage.removeItem(sent.draftKey);
          }
          setReply(state.result);
          void onRefresh();
          if (history)
            void api<Message[]>(`/messages?space_id=${space.id}`).then(
              setHistory,
            );
        } else if (state.status !== "cancelled") {
          setFailed(true);
          onError(state.error || "生成中断，请重试");
        }
      }
    };
    stream.onerror = () => {
      stream.close();
      setActive(null);
      onError("连接中断。刷新可恢复已保存结果和仍在执行的任务。");
    };
  }
  useEffect(() => {
    if (space.active_run && !active) watch(space.active_run);
  }, [space.active_run]);
  async function act(action: string, text = "") {
    if (!chapter) return;
    setLastAction({ action, text });
    setFailed(false);
    pending.current = { action, text, chapterId: chapter.id, draftKey };
    setMore(false);
    try {
      const result = await send<{ id: string }>(`/spaces/${space.id}/actions`, {
        action,
        text,
        chapter_id: chapter.id,
        request_key: crypto.randomUUID(),
        selected_option:
          action === "answer" && question?.kind === "choice"
            ? selectedOption || null
            : null,
        prepare_chapter: action === "teach",
      });
      watch(result.id);
    } catch (e) {
      setFailed(true);
      onError((e as Error).message);
    }
  }
  function cite(id: string) {
    const page = pages.find((p) => p.id === id);
    if (page) {
      setTarget({ doc: page.document_id, page: page.number });
      setReader(true);
    } else onError("暂时无法定位该引用，请打开资料列表查看");
  }
  const citations = (ids: string[] = []) => (
    <div className="citations">
      {ids.map((id) => {
        const page = pages.find((p) => p.id === id);
        return (
          <button className="text" key={id} onClick={() => cite(id)}>
            <BookOpen size={15} />
            {page
              ? `${space.documents.find((d) => d.id === page.document_id)?.name} · 第 ${page.number} 页`
              : "查看资料引用"}
          </button>
        );
      })}
    </div>
  );
  const currentDoc = space.documents.find((d) => d.id === target.doc);
  const attempts =
    chapter?.attempts.filter((a) => a.question_id === question?.id) || [];
  const lastAttempt = attempts.at(-1);
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
    const ids =
      space.mode === "review"
        ? space.review_queue
        : space.chapters.filter((c) => !c.is_group).map((c) => c.id);
    const next = ids[ids.indexOf(chapter!.id) + 1];
    if (next) {
      await send(`/spaces/${space.id}`, { chapter_id: next }, "PATCH");
      await onRefresh();
    } else onError("本轮已到最后一章，可以回看尚未验证的章节。");
  }
  return (
    <div className={"workspace-layout " + (reader ? "with-reader" : "")}>
      <main className="workspace">
        <header className="workspace-top">
          <span>
            {space.name} / {space.mode === "review" ? "考前复习" : "章节学习"}
          </span>
          <div>
            <button disabled={!!active || !chapter} onClick={switchMode}>
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
            旧目录可能包含重复章节。原学习记录将保留。
            <button
              disabled={!!active}
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
          <div className="preparation-status" role="status">
            同章其他小节正在后台准备，可随时选择小节优先学习。
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
        {!chapter ? (
          <section className="empty">
            <BookOpen size={48} />
            <h1>正在准备你的学习资料</h1>
            <p>目录准备好后，就可以选择章节开始。</p>
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
        ) : (
          <>
            <div className="task-scroll">
              <div className="task-heading">
                <div>
                  <h1>{chapter.title}</h1>
                  <p>{chapter.lesson?.objective || "一次只学懂一个小问题。"}</p>
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
              {space.mode === "review" && (
                <div className="notice">
                  本轮先关注核心概念与尚未验证的内容。随时可以退出，回到原学习位置。
                </div>
              )}
              {!chapter.lesson ? (
                <section className="start-task">
                  <span className="drawn-sprout">✳</span>
                  <h2>从这一章开始</h2>
                  <p>
                    全部资料已可检索；先准备当前小节，
                    <br />
                    同一大章的其他小节会在后台依次准备。
                  </p>
                  {chapter.preparation_error && (
                    <p role="alert">{chapter.preparation_error}</p>
                  )}
                  <button
                    className="primary"
                    disabled={!!active || !configured}
                    onClick={() => void act("teach")}
                  >
                    开始学习
                  </button>
                  {!configured && (
                    <p className="muted">
                      请先在设置中配置 DeepSeek。你仍可阅读资料。
                    </p>
                  )}
                </section>
              ) : (
                <>
                  <details className="lesson-details" open={!practice}>
                    <summary>回看本节讲解</summary>
                    <article className="lesson">
                      <h2>
                        <span />
                        先理解，再往前走
                      </h2>
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
                    </article>
                  </details>
                  {question ? (
                    <>
                      <section className="question">
                        <span className="question-mark">?</span>
                        <div>
                          <small>
                            核心问题 {chapter.question_index + 1} /{" "}
                            {chapter.question_count}
                            {chapter.hint_used ? " · 已使用提示" : ""}
                          </small>
                          <Prose>{question.prompt}</Prose>
                          {question.unit && (
                            <small>请在答案中注明单位：{question.unit}</small>
                          )}
                          {practice && question.kind === "choice" && (
                            <div className="options">
                              {question.options?.map((option) => (
                                <label key={option}>
                                  <input
                                    type="radio"
                                    name="answer"
                                    checked={selectedOption === option}
                                    onChange={() => {
                                      setSelectedOption(option);
                                      localStorage.setItem(
                                        "option:" + question.id,
                                        option,
                                      );
                                      setAskMode(false);
                                    }}
                                  />
                                  {option}
                                </label>
                              ))}
                            </div>
                          )}
                        </div>
                      </section>
                      {lastAttempt && (
                        <section
                          className={"feedback " + lastAttempt.feedback.verdict}
                        >
                          <h3>
                            {lastAttempt.disputed
                              ? "此判分存疑，已暂停作为学习依据"
                              : verdictLabel[lastAttempt.feedback.verdict]}
                            {lastAttempt.assisted ? " · 辅助完成" : ""}
                          </h3>
                          <Prose>{lastAttempt.feedback.explanation}</Prose>
                          {lastAttempt.feedback.missing.map((m) => (
                            <p key={m}>需补充：{m}</p>
                          ))}
                          <p>{lastAttempt.feedback.next_step}</p>
                          <button
                            className="text"
                            disabled={!!active}
                            onClick={async () => {
                              try {
                                if (!lastAttempt.disputed)
                                  await send(
                                    `/attempts/${lastAttempt.id}/dispute`,
                                    {},
                                  );
                                await onRefresh();
                                await act("retry_grade");
                              } catch (e) {
                                onError((e as Error).message);
                              }
                            }}
                          >
                            {lastAttempt.disputed
                              ? "重新核对这次作答"
                              : "判分有疑问，核对一次"}
                          </button>
                        </section>
                      )}
                    </>
                  ) : (
                    <div className="notice">
                      <Check size={20} />
                      本章这一轮核心问题已结束。当前记录：{chapter.state}
                      。未验证不等于不会。
                    </div>
                  )}
                  <div className="task-actions">
                    <button
                      className="primary"
                      disabled={!!active}
                      onClick={() => {
                        if (!question) {
                          void nextChapter();
                          return;
                        }
                        if (!practice) {
                          setPractice(true);
                          document
                            .querySelector(".task-scroll")
                            ?.scrollTo({ top: 0 });
                          localStorage.setItem(
                            "practice:" + chapter.id,
                            "true",
                          );
                          document
                            .querySelector<HTMLTextAreaElement>(
                              ".composer textarea",
                            )
                            ?.focus();
                        } else if (lastAttempt) {
                          void act("next");
                        } else
                          document
                            .querySelector<HTMLTextAreaElement>(
                              ".composer textarea",
                            )
                            ?.focus();
                      }}
                    >
                      {!question
                        ? "继续下一章"
                        : !practice
                          ? "来试一道题"
                          : lastAttempt
                            ? "继续下一题"
                            : "写下你的理解"}
                    </button>
                    <button
                      disabled={!!active}
                      onClick={() =>
                        void act("ask", "请换一种更直观的方式解释当前概念。")
                      }
                    >
                      <RefreshCw size={17} />
                      换个解释
                    </button>
                    <div className="more-wrap">
                      <button
                        onClick={() => setMore(!more)}
                        aria-expanded={more}
                      >
                        <MoreHorizontal />
                        更多
                      </button>
                      {more && (
                        <div className="more-menu">
                          {question && (
                            <>
                              <button
                                disabled={!!active}
                                onClick={() => void act("hint")}
                              >
                                给个提示
                              </button>
                              <button
                                disabled={!!active}
                                onClick={() => void act("solution")}
                              >
                                查看解答
                              </button>
                              <button
                                disabled={!!active}
                                onClick={() => void act("skip")}
                              >
                                跳过这一题
                              </button>
                            </>
                          )}
                          <button
                            disabled={!!active}
                            onClick={() => void act("train")}
                          >
                            针对性练一轮
                          </button>
                          <a href={`/api/spaces/${space.id}/export`} download>
                            导出学习记录
                          </a>
                        </div>
                      )}
                    </div>
                  </div>
                </>
              )}
              {reply?.text && (
                <section className="reply">
                  <strong>
                    {reply.supplement ? "课外补充" : "关于你的问题"}
                  </strong>
                  <Prose>{reply.text}</Prose>
                  {citations(reply.sources)}
                </section>
              )}
              {active && (
                <div className="run-progress" role="status">
                  <span className="spinner" />
                  {progress}
                  <button
                    onClick={() =>
                      void send(`/runs/${active}/cancel`, {})
                        .then(() => {
                          source.current?.close();
                          setActive(null);
                          void onRefresh();
                        })
                        .catch((e) => onError(e.message))
                    }
                  >
                    <Square size={13} />
                    取消
                  </button>
                </div>
              )}
              {lastAction && failed && !active && (
                <button
                  className="text retry-link"
                  onClick={() => void act(lastAction.action, lastAction.text)}
                >
                  重新发起上一请求
                </button>
              )}
              <section className="history">
                <button
                  className="text"
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
                    {history.length === 0 ? (
                      <p className="muted">还没有学习记录。</p>
                    ) : (
                      history.map((m) => (
                        <article key={m.id}>
                          <small>{m.role === "user" ? "你" : "Tutor"}</small>
                          <Prose>{m.text}</Prose>
                        </article>
                      ))
                    )}
                  </div>
                )}
              </section>
            </div>
            <form
              className="composer"
              onSubmit={(e) => {
                e.preventDefault();
                void act(
                  practice && question && !askMode ? "answer" : "ask",
                  draft,
                );
              }}
            >
              {practice && question && !askMode && (
                <Suspense fallback={null}>
                  <AnswerImage
                    key={question.id}
                    spaceId={space.id}
                    disabled={!!active}
                    onConfirm={(text) => {
                      const value = draft ? draft + "\n" + text : text;
                      setDraft(value);
                      localStorage.setItem(draftKey, value);
                    }}
                  />
                </Suspense>
              )}
              <div className="composer-mode">
                <span>
                  {practice && question && !askMode
                    ? "正在回答当前核心问题"
                    : "向 Tutor 提问，保留当前学习位置"}
                </span>
                {question && practice && (
                  <button
                    type="button"
                    className="text"
                    onClick={() => setAskMode(!askMode)}
                  >
                    {askMode ? "切回作答" : "我想先提问"}
                  </button>
                )}
              </div>
              <div className="composer-input">
                <textarea
                  rows={2}
                  aria-label="主输入框"
                  placeholder={
                    practice && !askMode
                      ? question?.kind === "choice"
                        ? "为什么选择这个选项？写下你的推理（可选）…"
                        : "说说你的理解，或上传手写答案…"
                      : "提问，或者说说你想先学什么…"
                  }
                  value={draft}
                  onChange={(e) => {
                    setDraft(e.target.value);
                    localStorage.setItem(draftKey, e.target.value);
                  }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                      e.preventDefault();
                      if (
                        (draft.trim() ||
                          (practice && !askMode && selectedOption)) &&
                        !active
                      )
                        void act(
                          practice && question && !askMode ? "answer" : "ask",
                          draft,
                        );
                    }
                  }}
                />
                <button
                  className="primary icon"
                  aria-label={
                    practice && question && !askMode ? "提交回答" : "发送提问"
                  }
                  disabled={
                    !!active ||
                    !(practice && !askMode && question?.kind === "choice"
                      ? selectedOption
                      : draft.trim()) ||
                    !configured
                  }
                >
                  <Send size={21} />
                </button>
              </div>
              <small>Ctrl + Enter 发送 · 练习可跳过，学习不用赶。</small>
            </form>
          </>
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
