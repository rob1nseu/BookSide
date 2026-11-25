import { useEffect, useRef, useState } from "react";
import { api } from "./api";

export default function AnswerImage({
  spaceId,
  target,
  attachment,
  onAttachment,
  onConfirm,
  disabled,
  onBusy,
}: {
  spaceId: string;
  target: string;
  attachment: string;
  onAttachment: (id: string) => void;
  onConfirm: (text: string) => void;
  disabled: boolean;
  onBusy: (busy: boolean) => void;
}) {
  const [preview, setPreview] = useState("");
  const [text, setText] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [phase, setPhase] = useState("");
  const controller = useRef<AbortController | null>(null);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(
    () => () => {
      if (preview) URL.revokeObjectURL(preview);
    },
    [preview],
  );
  async function transcribe(id: string, signal: AbortSignal) {
    setPhase("正在识别，可直接提交原图或等待识别结果…");
    try {
      const data = await api<{
        text: string;
        uncertain: boolean;
        note: string;
      }>(`/spaces/${spaceId}/attachments/${id}/transcribe`, {
        method: "POST",
        signal,
      });
      if (signal.aborted) return;
      setText(data.text);
      setNote(
        (data.uncertain
          ? "有不清晰的内容，请核对原图。"
          : "识别完成，判分时仍会查看原图。") + data.note,
      );
      setPhase("");
    } catch (e) {
      if (!signal.aborted) {
        setPhase("");
        setNote(
          (e as Error).message + "；图片已保留，可以重试识别或直接提交原图。",
        );
      }
    }
  }
  async function upload(file?: File) {
    if (!file || disabled) return;
    if (file.size > 5 * 1024 * 1024) {
      setNote("图片不能超过 5 MiB，请缩小后重试。");
      return;
    }
    if (!["image/png", "image/jpeg"].includes(file.type)) {
      setNote("请选择 PNG 或 JPEG 图片。");
      return;
    }
    controller.current?.abort();
    const request = new AbortController();
    controller.current = request;
    onAttachment("");
    setPreview(URL.createObjectURL(file));
    setText(null);
    setNote("");
    setPhase("正在上传图片…");
    onBusy(true);
    const body = new FormData();
    body.append("file", file);
    try {
      const data = await api<{ id: string }>(
        `/spaces/${spaceId}/answer-image?recognize=false&target=${encodeURIComponent(target)}`,
        { method: "POST", body, signal: request.signal },
      );
      if (request.signal.aborted) return;
      onAttachment(data.id);
      onBusy(false);
      void transcribe(data.id, request.signal);
    } catch (e) {
      if (!request.signal.aborted) {
        setPhase("");
        setPreview("");
        setNote((e as Error).message);
      }
    } finally {
      if (!request.signal.aborted) onBusy(false);
    }
  }
  return (
    <div
      className="answer-image"
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        e.preventDefault();
        void upload(e.dataTransfer.files[0]);
      }}
    >
      <button
        type="button"
        disabled={disabled}
        onClick={() => input.current?.click()}
      >
        上传答案图片
      </button>
      <button
        type="button"
        disabled={disabled}
        onClick={async () => {
          try {
            const items = await navigator.clipboard.read();
            for (const item of items) {
              const type = item.types.find((t) =>
                ["image/png", "image/jpeg"].includes(t),
              );
              if (type) {
                void upload(
                  new File([await item.getType(type)], "answer.png", { type }),
                );
                return;
              }
            }
            setNote("剪贴板中没有图片，可以拖拽或选择文件。");
          } catch {
            setNote("无法读取剪贴板，请拖拽或选择图片文件。");
          }
        }}
      >
        粘贴图片
      </button>
      <input
        ref={input}
        type="file"
        aria-label="上传答案图片"
        accept="image/png,image/jpeg"
        hidden
        disabled={disabled}
        onChange={(e) => {
          void upload(e.target.files?.[0]);
          e.target.value = "";
        }}
      />
      <small>可拖拽 PNG/JPEG；原图随答案发送至 DeepSeek。</small>
      {note && <p role="status">{note}</p>}
      {phase && <p role="status">{phase}</p>}
      {(preview || attachment) && (
        <div className="image-review">
          <img
            src={preview || `/api/spaces/${spaceId}/attachments/${attachment}`}
            alt="当前题目的答案图片"
          />
          <div>
            {attachment && <span>已附原图 · 可提交判分</span>}
            {text !== null && (
              <details>
                <summary>查看 / 修改识别文字</summary>
                <textarea
                  aria-label="核对识别结果"
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                />
                <button
                  type="button"
                  disabled={disabled || !text.trim()}
                  onClick={() => onConfirm(text)}
                >
                  确认并填入作答
                </button>
              </details>
            )}
            {attachment && !phase && (
              <button
                type="button"
                disabled={disabled}
                onClick={() => {
                  controller.current?.abort();
                  const c = new AbortController();
                  controller.current = c;
                  void transcribe(attachment, c.signal);
                }}
              >
                重新识别
              </button>
            )}
            <button
              type="button"
              disabled={disabled}
              onClick={() => {
                controller.current?.abort();
                setPreview("");
                setText(null);
                setPhase("");
                setNote("");
                onAttachment("");
                onBusy(false);
              }}
            >
              移除图片
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
