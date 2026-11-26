import {
  lazy,
  Suspense,
  useCallback,
  useEffect,
  useState,
  useRef,
} from "react";
import {
  ArrowLeft,
  Settings as SettingsIcon,
  Menu,
  X,
  Brain,
} from "lucide-react";
import { api, send, ApiError } from "./api";
import { Brand, Dialog } from "./components";
import Library from "./Library";
import Workspace from "./Workspace";
import ResizeHandle from "./ResizeHandle";
import ChapterTree from "./ChapterTree";
import { useCompanion } from "./useCompanion";
import { learningStatus } from "./learningStatus";
import type { Settings as SettingsType, Space } from "./types";
const Settings = lazy(() => import("./Settings"));
const MemoryPanel = lazy(() => import("./MemoryPanel"));
export default function App() {
  useCompanion();
  const [id, setId] = useState<string | null>(() =>
    localStorage.getItem("bookside:space"),
  );
  const [space, setSpace] = useState<Space | null>(null);
  const [settings, setSettings] = useState<SettingsType | null>(null);
  const [panel, setPanel] = useState<"settings" | "memory" | null>(null);
  const [nav, setNav] = useState(false);
  const [error, setError] = useState("");
  const [networkStatus, setNetworkStatus] = useState("");
  const [loadError, setLoadError] = useState("");
  const [reload, setReload] = useState(0);
  useEffect(() => {
    const retries = new Map<string, string>();
    const listener = (event: Event) => {
      const { id, message } = (event as CustomEvent).detail;
      if (message) retries.set(id, message);
      else retries.delete(id);
      setNetworkStatus([...retries.values()].at(-1) || "");
    };
    window.addEventListener("bookside:retry", listener);
    return () => window.removeEventListener("bookside:retry", listener);
  }, []);
  const activeSpace = useRef(id);
  activeSpace.current = id;
  const refresh = useCallback(async () => {
    if (!id) return;
    const detail = await api<Space>(`/spaces/${id}?compact=true`);
    if (activeSpace.current === id) setSpace(detail);
  }, [id]);
  useEffect(() => {
    void api<SettingsType>("/settings")
      .then(setSettings)
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    setSpace(null);
    setLoadError("");
    let alive = true;
    if (id) {
      localStorage.setItem("bookside:space", id);
      void refresh().catch((e) => {
        if (!alive) return;
        if (e instanceof ApiError && e.status === 404) {
          setId(null);
          localStorage.removeItem("bookside:space");
        } else setLoadError(e.message);
      });
    } else localStorage.removeItem("bookside:space");
    return () => {
      alive = false;
    };
  }, [id, refresh, reload]);
  useEffect(() => {
    if (
      !space?.chapters.some((c) =>
        ["queued", "running"].includes(c.preparation),
      ) &&
      !space?.documents.some((d) =>
        ["uploaded", "parsing", "indexing"].includes(d.status),
      )
    )
      return;
    const controller = new AbortController();
    let inFlight = false;
    const timer = setInterval(async () => {
      if (document.hidden || inFlight || !space) return;
      inFlight = true;
      try {
        const status = await api<{
          chapters: Pick<
            Space["chapters"][number],
            "id" | "preparation" | "preparation_error" | "state"
          >[];
          documents: Pick<
            Space["documents"][number],
            "id" | "status" | "error"
          >[];
        }>(`/spaces/${space.id}/status`, { signal: controller.signal });
        if (controller.signal.aborted) return;
        const current = status.chapters.find(
          (c) => c.id === space.current_chapter,
        );
        if (
          status.chapters.length !== space.chapters.length ||
          (current?.preparation === "ready" &&
            !space.chapters.find((c) => c.id === current.id)?.lesson) ||
          status.documents.some(
            (d) =>
              d.status !==
              space.documents.find((old) => old.id === d.id)?.status,
          )
        ) {
          await refresh();
          return;
        }
        setSpace((old) => {
          if (!old || old.id !== space.id) return old;
          let changed = false;
          const chapters = old.chapters.map((c) => {
            const next = status.chapters.find((s) => s.id === c.id);
            if (
              next &&
              (c.preparation !== next.preparation ||
                c.state !== next.state ||
                c.preparation_error !== next.preparation_error)
            ) {
              changed = true;
              return { ...c, ...next };
            }
            return c;
          });
          return changed ? { ...old, chapters } : old;
        });
      } catch (e) {
        if (!controller.signal.aborted) setError((e as Error).message);
      } finally {
        inFlight = false;
      }
    }, 2500);
    return () => {
      clearInterval(timer);
      controller.abort();
    };
  }, [
    space?.id,
    space?.current_chapter,
    space?.chapters.map((c) => c.preparation).join(","),
    space?.documents.map((d) => d.status).join(","),
    refresh,
  ]);
  const closePanel = useCallback(() => setPanel(null), []);
  async function choose(chapterId: string) {
    try {
      await send(`/spaces/${id}`, { chapter_id: chapterId }, "PATCH");
      await refresh();
      setNav(false);
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <div className="app">
      <button
        className="mobile-menu icon"
        onClick={() => setNav(!nav)}
        aria-label="展开导航"
      >
        <Menu />
      </button>
      <aside className={"sidebar " + (nav ? "open" : "")}>
        <Brand />
        <nav>
          {id ? (
            <>
              <button
                className="back"
                onClick={() => {
                  setId(null);
                  setNav(false);
                }}
              >
                <ArrowLeft size={18} />
                学习空间
              </button>
              <div className="course-heading">
                <strong>{space?.name || "正在读取…"}</strong>
                <span>
                  {space?.mode === "review" ? "复习章节" : "学习章节"}
                </span>
              </div>
              <div className="chapters">
                {space?.mode !== "review" && space ? (
                  <ChapterTree
                    chapters={space.chapters}
                    current={space.current_chapter}
                    choose={(id) => void choose(id)}
                  />
                ) : (
                  (space?.chapters || [])
                    .filter((chapter) => !chapter.parent_id)
                    .map((chapter, index) => (
                      <button
                        key={chapter.id}
                        className={
                          chapter.id === space?.current_chapter ||
                          chapter.id ===
                            space?.chapters.find(
                              (c) => c.id === space.current_chapter,
                            )?.parent_id
                            ? "chapter selected"
                            : "chapter"
                        }
                        onClick={() => {
                          const target = chapter.is_group
                            ? space?.chapters.find(
                                (c) =>
                                  c.parent_id === chapter.id && !c.is_group,
                              )
                            : chapter;
                          if (target) void choose(target.id);
                        }}
                      >
                        <span className="chapter-number">
                          {String(index + 1).padStart(2, "0")}
                        </span>
                        <span>
                          {chapter.title}
                          <small>思维导图与练习</small>
                        </span>
                      </button>
                    ))
                )}
              </div>
            </>
          ) : (
            <div className="nav-intro">
              <p>
                你的学习，
                <br />
                可以简单一点。
              </p>
              <span>选一章 · 学一点 · 想明白</span>
            </div>
          )}
        </nav>
        <div className="sidebar-bottom">
          <button onClick={() => setPanel("memory")}>
            <Brain size={19} />
            记忆
          </button>
          <button onClick={() => setPanel("settings")}>
            <SettingsIcon size={19} />
            设置
            {settings && !settings.configured && !settings.demo && (
              <small>待配置</small>
            )}
          </button>
        </div>
      </aside>
      <ResizeHandle
        target=".sidebar"
        storage="bookside-directory-width"
        initial={245}
        min={200}
        max={420}
        left
      />
      <div className="main-shell">
        {settings?.demo && (
          <div className="demo-banner">
            演示模式 · 模型回复为固定示例，不代表真实教学效果
          </div>
        )}
        {error && (
          <div className="notice-banner" role="status">
            <span>{learningStatus(error)}</span>
            <button
              className="icon"
              aria-label="关闭错误提示"
              onClick={() => setError("")}
            >
              <X size={18} />
            </button>
          </div>
        )}
        {networkStatus && (
          <div className="notice-banner" role="status">
            <span className="spinner" />
            {networkStatus}
          </div>
        )}
        {!id ? (
          <Library open={setId} onError={setError} />
        ) : space ? (
          <Workspace
            key={id}
            space={space}
            onRefresh={refresh}
            onError={setError}
            configured={!!(settings?.configured || settings?.demo)}
            onOpen={setId}
          />
        ) : (
          <div className="loading" role="status">
            {loadError ? (
              <>
                {loadError}{" "}
                <button onClick={() => setReload((v) => v + 1)}>
                  重新连接
                </button>
              </>
            ) : (
              <>
                <span className="spinner" />{" "}
                {networkStatus || "正在恢复学习位置…"}
              </>
            )}
          </div>
        )}
      </div>
      {panel && (
        <Dialog
          title={panel === "settings" ? "设置" : "记忆"}
          close={closePanel}
        >
          <Suspense fallback={<p>正在打开…</p>}>
            {panel === "settings" && settings ? (
              <Settings settings={settings} onChange={setSettings} />
            ) : (
              <MemoryPanel spaceId={id || undefined} />
            )}
          </Suspense>
        </Dialog>
      )}
    </div>
  );
}
