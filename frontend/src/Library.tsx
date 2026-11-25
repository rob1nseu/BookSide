import { useEffect, useState } from "react";
import {
  Upload,
  FileText,
  BookOpen,
  Plus,
  Archive,
  Trash2,
} from "lucide-react";
import { api, send } from "./api";
import { statusLabel } from "./components";
import type { Document, Space } from "./types";
export default function Library({
  open,
  onError,
}: {
  open: (id: string) => void;
  onError: (s: string) => void;
}) {
  const [spaces, setSpaces] = useState<Space[]>([]);
  const [docs, setDocs] = useState<Document[]>([]);
  const [create, setCreate] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [showArchive, setShowArchive] = useState(false);
  async function refresh() {
    const [s, d] = await Promise.all([
      api<Space[]>("/spaces"),
      api<Document[]>("/documents"),
    ]);
    setSpaces(s);
    setDocs(d);
  }
  useEffect(() => {
    void refresh().catch((e) => onError(e.message));
    const timer = setInterval(() => void refresh().catch(() => {}), 1800);
    return () => clearInterval(timer);
  }, []);
  async function upload(files: FileList | null) {
    if (!files?.length) return;
    if (files.length > 10) {
      onError("一次最多上传 10 个文件");
      return;
    }
    setBusy(true);
    try {
      const ids: string[] = [];
      for (const file of Array.from(files)) {
        const form = new FormData();
        form.append("file", file);
        const doc = await api<Document>("/documents", {
          method: "POST",
          body: form,
        });
        ids.push(doc.id);
      }
      setSelected((old) => [...new Set([...old, ...ids])]);
      await refresh();
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function start() {
    setBusy(true);
    try {
      const space = await send<Space>("/spaces", {
        name,
        document_ids: selected,
      });
      open(space.id);
    } catch (e) {
      onError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="library">
      <div className="library-heading">
        <div>
          <p className="eyeline">给好奇心，留一点空间。</p>
          <h1>今天，想学懂什么？</h1>
          <p className="muted">带上你的教材，一次只学懂一个小问题。</p>
        </div>
        <button className="primary" onClick={() => setCreate(!create)}>
          <Plus size={18} />
          新建学习
        </button>
      </div>
      {create && (
        <section className="create-space">
          <h2>从一份资料开始</h2>
          <label className="upload-zone">
            <Upload size={30} />
            <strong>{busy ? "正在上传…" : "选择 PDF 或 PPTX"}</strong>
            <span>可以一次选择多份教材与课件 · 单文件不超过 50 MiB</span>
            <input
              type="file"
              aria-label="上传学习资料"
              accept=".pdf,.pptx"
              multiple
              disabled={busy}
              onChange={(e) => void upload(e.target.files)}
            />
          </label>
          {docs.length > 0 && (
            <fieldset>
              <legend>选择本次学习的资料</legend>
              {docs.map((doc) => (
                <div className="document-row" key={doc.id}>
                  <label className="inline">
                    <input
                      type="checkbox"
                      checked={selected.includes(doc.id)}
                      onChange={(e) =>
                        setSelected((old) =>
                          e.target.checked
                            ? [...old, doc.id]
                            : old.filter((id) => id !== doc.id),
                        )
                      }
                    />
                    <FileText size={17} />
                    <span>{doc.name}</span>
                  </label>
                  <span className={"doc-status " + doc.status}>
                    {statusLabel[doc.status]}
                  </span>
                  {doc.error && <span className="error-text">{doc.error}</span>}
                  {doc.status === "failed" && (
                    <button
                      onClick={() =>
                        void send(`/documents/${doc.id}/retry`, {})
                          .then(refresh)
                          .catch((e) => onError(e.message))
                      }
                    >
                      重试
                    </button>
                  )}
                </div>
              ))}
            </fieldset>
          )}
          <label>
            空间名称（可选）
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="例如：高等数学"
              maxLength={120}
            />
          </label>
          <div className="actions">
            <button
              className="primary"
              disabled={!selected.length || busy}
              onClick={start}
            >
              创建学习空间
            </button>
            <button onClick={() => setCreate(false)}>取消</button>
          </div>
        </section>
      )}
      <div className="section-title">
        <h2>我的学习空间</h2>
        <button className="text" onClick={() => setShowArchive(!showArchive)}>
          {showArchive ? "返回学习中" : "查看归档"}
        </button>
      </div>
      {spaces.filter((s) => !!s.archived === showArchive).length === 0 &&
      !create ? (
        <div className="empty">
          <BookOpen size={52} strokeWidth={1.2} />
          <h3>{showArchive ? "这里还没有归档空间" : "一个新的开始"}</h3>
          <p>上传教材，选一个章节，其余交给 Tutor。</p>
          <button onClick={() => setCreate(true)}>添加第一份学习资料</button>
        </div>
      ) : (
        <div className="space-list">
          {spaces
            .filter((s) => !!s.archived === showArchive)
            .map((space) => (
              <article key={space.id} className="space-row">
                <button className="space-open" onClick={() => open(space.id)}>
                  <span className="book-mark">
                    <BookOpen />
                  </span>
                  <span>
                    <strong>{space.name}</strong>
                    <small>
                      {space.chapter_count || 0} 个章节 ·{" "}
                      {space.mode === "review" ? "考前复习" : "章节学习"}
                    </small>
                  </span>
                </button>
                <button
                  className="icon"
                  aria-label={`归档 ${space.name}`}
                  onClick={() =>
                    void send(
                      `/spaces/${space.id}`,
                      { archived: !space.archived },
                      "PATCH",
                    )
                      .then(refresh)
                      .catch((e) => onError(e.message))
                  }
                >
                  <Archive size={18} />
                </button>
                <button
                  className="icon"
                  aria-label={`删除 ${space.name}`}
                  onClick={() => {
                    if (
                      confirm(
                        "删除这个学习空间及其聊天、作答和记忆？原始资料仍保留。",
                      )
                    )
                      void api(`/spaces/${space.id}`, { method: "DELETE" })
                        .then(refresh)
                        .catch((e) => onError(e.message));
                  }}
                >
                  <Trash2 size={18} />
                </button>
              </article>
            ))}
        </div>
      )}
      <p className="library-foot">少一点切换，多一点理解。</p>
    </main>
  );
}
