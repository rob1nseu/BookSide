import { useEffect, useRef, useState } from "react";
import {
  getDocument,
  GlobalWorkerOptions,
  type PDFDocumentProxy,
} from "pdfjs-dist";
import worker from "pdfjs-dist/build/pdf.worker.min.mjs?url";
import { ChevronLeft, ChevronRight, X, Download } from "lucide-react";
import type { Document, Page } from "./types";
GlobalWorkerOptions.workerSrc = worker;
export default function PdfReader({
  document,
  page,
  pages,
  onPage,
  close,
}: {
  document: Document;
  page: number;
  pages: Page[];
  onPage: (n: number) => void;
  close: () => void;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const holder = useRef<HTMLDivElement>(null);
  const [pdf, setPdf] = useState<PDFDocumentProxy>();
  const [error, setError] = useState("");
  const [width, setWidth] = useState(420);
  useEffect(() => {
    if (document.kind !== "pdf") return;
    setPdf(undefined);
    setError("");
    const task = getDocument({
      url: `/api/documents/${document.id}/file`,
      cMapUrl: "/pdf/cmaps/",
      cMapPacked: true,
      standardFontDataUrl: "/pdf/standard_fonts/",
      wasmUrl: "/pdf/wasm/",
    });
    task.promise
      .then(setPdf)
      .catch(() => setError("无法显示 PDF，可下载原文件查看。"));
    return () => {
      void task.destroy();
    };
  }, [document.id, document.kind]);
  useEffect(() => {
    if (!holder.current) return;
    const observer = new ResizeObserver((entries) =>
      setWidth(Math.max(240, entries[0].contentRect.width - 28)),
    );
    observer.observe(holder.current);
    return () => observer.disconnect();
  }, []);
  useEffect(() => {
    if (!pdf || !canvas.current) return;
    let cancelled = false;
    let task:
      | ReturnType<Awaited<ReturnType<PDFDocumentProxy["getPage"]>>["render"]>
      | undefined;
    void pdf
      .getPage(Math.min(Math.max(1, page), pdf.numPages))
      .then((p) => {
        if (cancelled || !canvas.current) return;
        const viewport = p.getViewport({
          scale: width / p.getViewport({ scale: 1 }).width,
        });
        const el = canvas.current;
        const ratio = window.devicePixelRatio || 1;
        el.width = viewport.width * ratio;
        el.height = viewport.height * ratio;
        el.style.width = viewport.width + "px";
        el.style.height = viewport.height + "px";
        task = p.render({
          canvas: el,
          viewport,
          transform: [ratio, 0, 0, ratio, 0, 0],
        });
        return task.promise;
      })
      .catch((e) => {
        if (e.name !== "RenderingCancelledException" && !cancelled)
          setError("页面渲染失败，请重新打开阅读器。");
      });
    return () => {
      cancelled = true;
      task?.cancel();
    };
  }, [pdf, page, width]);
  const current = pages.find((p) => p.number === page);
  const count = pdf?.numPages || pages.length;
  return (
    <aside className="reader" aria-label="资料阅读器">
      <header>
        <strong title={document.name}>{document.name}</strong>
        <button className="icon" onClick={close} aria-label="关闭阅读器">
          <X />
        </button>
      </header>
      <div className="reader-toolbar">
        <button
          className="icon"
          aria-label="上一页"
          disabled={page <= 1}
          onClick={() => onPage(page - 1)}
        >
          <ChevronLeft />
        </button>
        <span>
          文件第 {page} / {count || "…"} 页
        </span>
        <button
          className="icon"
          aria-label="下一页"
          disabled={page >= count}
          onClick={() => onPage(page + 1)}
        >
          <ChevronRight />
        </button>
        <a
          className="icon"
          href={`/api/documents/${document.id}/file`}
          download={document.name}
          aria-label="下载原文件"
        >
          <Download size={18} />
        </a>
      </div>
      <div className="reader-body" ref={holder}>
        {error && <p role="alert">{error}</p>}
        {current?.warning && <p className="notice">{current.warning}</p>}
        {document.kind === "pdf" ? (
          <canvas ref={canvas} aria-label={`PDF 第 ${page} 页`} />
        ) : (
          <article>
            <small>幻灯片文字 · 非原版视觉还原</small>
            <h3>{current?.title}</h3>
            <p className="preserve">{current?.text}</p>
            {current?.notes && (
              <>
                <h4>演讲者备注</h4>
                <p>{current.notes}</p>
              </>
            )}
          </article>
        )}
      </div>
    </aside>
  );
}
