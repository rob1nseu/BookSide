import { lazy, Suspense, useEffect, useRef, type ReactNode } from "react";
import { X } from "lucide-react";
const MarkdownView = lazy(() => import("./MarkdownView"));

export function Brand() {
  return (
    <div className="brand">
      <img src="/app-icon.svg" alt="BookSide 奶龙读书" width={40} height={40} />
      <div>
        <strong>BookSide</strong>
        <span>书边 · 极简学习</span>
      </div>
    </div>
  );
}
export function Prose({
  children,
  inline = false,
}: {
  children: string;
  inline?: boolean;
}) {
  return (
    <Suspense fallback={<span className="prose">{children}</span>}>
      <MarkdownView inline={inline}>{children}</MarkdownView>
    </Suspense>
  );
}
export function Dialog({
  title,
  close,
  children,
  wide = false,
}: {
  title: string;
  close: () => void;
  children: ReactNode;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const d = ref.current!;
    d.showModal();
    const cancel = (e: Event) => {
      e.preventDefault();
      close();
    };
    d.addEventListener("cancel", cancel);
    return () => {
      d.removeEventListener("cancel", cancel);
      d.close();
    };
  }, [close]);
  return (
    <dialog
      ref={ref}
      className={wide ? "modal wide" : "modal"}
      aria-label={title}
    >
      <header>
        <h2>{title}</h2>
        <button className="icon" onClick={close} aria-label="关闭">
          <X />
        </button>
      </header>
      {children}
    </dialog>
  );
}
export const statusLabel: Record<string, string> = {
  uploaded: "已上传",
  parsing: "解析中",
  indexing: "建立索引",
  ready: "可用",
  partial: "部分可用",
  failed: "解析失败",
};
export const verdictLabel: Record<string, string> = {
  correct: "理解得不错",
  partial: "再补充一点",
  incorrect: "一起检查一下",
  uncertain: "暂无法判断",
};
