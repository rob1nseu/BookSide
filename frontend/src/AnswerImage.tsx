import { useEffect, useRef, useState } from "react";

export default function AnswerImage({
  spaceId,
  onConfirm,
  disabled,
}: {
  spaceId: string;
  onConfirm: (text: string) => void;
  disabled: boolean;
}) {
  const [preview, setPreview] = useState("");
  const [text, setText] = useState<string | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => () => controller.current?.abort(), []);
  useEffect(
    () => () => {
      if (preview) URL.revokeObjectURL(preview);
    },
    [preview],
  );
  async function recognize(file?: File) {
    if (!file) return;
    if (file.size > 5 * 1024 * 1024) {
      setNote("图片不能超过 5 MiB");
      return;
    }
    controller.current?.abort();
    const request = new AbortController();
    controller.current = request;
    setPreview(URL.createObjectURL(file));
    setText(null);
    setNote("");
    setBusy(true);
    const body = new FormData();
    body.append("file", file);
    try {
      const response = await fetch(`/api/spaces/${spaceId}/answer-image`, {
        method: "POST",
        headers: { "X-LearNest": "1" },
        body,
        signal: request.signal,
      });
      const data = await response.json();
      if (!response.ok)
        throw new Error(
          typeof data.detail === "string" ? data.detail : "识别失败，请重试",
        );
      setText(data.text);
      setNote((data.uncertain ? "部分内容可能不清晰。" : "") + data.note);
    } catch (error) {
      if (!request.signal.aborted) setNote((error as Error).message);
    } finally {
      if (!request.signal.aborted) setBusy(false);
    }
  }
  return (
    <div className="answer-image">
      <label className="image-upload">
        上传答案图片
        <input
          type="file"
          aria-label="上传答案图片"
          accept="image/png,image/jpeg"
          disabled={disabled || busy}
          onChange={(e) => {
            void recognize(e.target.files?.[0]);
            e.target.value = "";
          }}
        />
      </label>
      {preview && (
        <div className="image-review">
          <img src={preview} alt="待核对的答案图片" />
          <div>
            {busy && <p role="status">正在识别答案…</p>}
            {note && <p role="status">{note}</p>}
            {text !== null && (
              <>
                <label>
                  核对识别结果
                  <textarea
                    aria-label="核对识别结果"
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                  />
                </label>
                <button
                  type="button"
                  disabled={disabled || !text.trim()}
                  onClick={() => {
                    onConfirm(text);
                    setPreview("");
                    setText(null);
                    setNote("");
                  }}
                >
                  确认并填入作答
                </button>
              </>
            )}
            <button
              type="button"
              onClick={() => {
                controller.current?.abort();
                setBusy(false);
                setPreview("");
                setText(null);
                setNote("");
              }}
            >
              移除图片
            </button>
          </div>
        </div>
      )}
      <small>图片发送至 DeepSeek 识别；确认后再提交判分。</small>
    </div>
  );
}
