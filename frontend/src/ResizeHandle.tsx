import { useEffect, useRef, useState } from "react";

/** Pixel size is presentation state only. Keyboard and pointer share the same limits. */
export default function ResizeHandle({ target, storage, initial = 360, min = 240, max = 700, left = false }: {
  target: string; storage: string; initial?: number; min?: number; max?: number; left?: boolean;
}) {
  const ref = useRef<HTMLButtonElement>(null);
  const [size, setSize] = useState(() => {
    try { const n = Number(localStorage.getItem(storage)); return n >= min && n <= max ? n : initial; }
    catch { return initial; }
  });
  useEffect(() => {
    const panel = ref.current?.parentElement?.querySelector<HTMLElement>(target);
    if (!panel) return;
    panel.style.setProperty("--panel-width", `${size}px`);
    if (left) ref.current?.parentElement?.style.setProperty("--sidebar-width", `${size}px`);
    try { localStorage.setItem(storage, String(size)); } catch { /* private storage unavailable */ }
  }, [size, storage, target, left]);
  return <button ref={ref} className={"resize-handle " + (left ? "sidebar-resize" : "")} role="separator" aria-label={left ? "调整目录宽度" : "调整侧栏宽度"}
    aria-orientation="vertical" aria-valuemin={min} aria-valuemax={max} aria-valuenow={size}
    onDoubleClick={() => setSize(initial)}
    onKeyDown={e => { if (e.key === "ArrowLeft" || e.key === "ArrowRight") { e.preventDefault(); setSize(s => Math.max(min, Math.min(max, s + (e.key === "ArrowLeft" ? 20 : -20) * (left ? -1 : 1)))); } }}
    onPointerDown={e => { e.currentTarget.setPointerCapture(e.pointerId); e.currentTarget.dataset.x = String(e.clientX); e.currentTarget.dataset.size = String(size); }}
    onPointerMove={e => { if (e.currentTarget.hasPointerCapture(e.pointerId)) setSize(Math.max(min, Math.min(max, Number(e.currentTarget.dataset.size) + (Number(e.currentTarget.dataset.x) - e.clientX) * (left ? -1 : 1)))); }}
    onPointerUp={e => e.currentTarget.releasePointerCapture(e.pointerId)} />;
}
