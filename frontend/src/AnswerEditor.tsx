import { lazy, Suspense, useState } from "react";
import type { Question } from "./types";
import { Prose } from "./components";
const AnswerImage = lazy(() => import("./AnswerImage"));
export type Answer = {
  text: string;
  selected_option: string | null;
  attachment_id: string | null;
};
export default function AnswerEditor({
  question,
  spaceId,
  disabled,
  onSubmit,
}: {
  question: Question;
  spaceId: string;
  disabled: boolean;
  onSubmit: (answer: Answer) => Promise<boolean>;
}) {
  const key = "answer:v2:" + spaceId + ":" + question.id;
  const [value, setValue] = useState<Answer>(() => {
    try {
      return (
        JSON.parse(localStorage.getItem(key) || "null") || {
          text: "",
          selected_option: null,
          attachment_id: null,
        }
      );
    } catch {
      return { text: "", selected_option: null, attachment_id: null };
    }
  });
  const [uploading, setUploading] = useState(false);
  function update(patch: Partial<Answer>) {
    setValue((old) => {
      const next = { ...old, ...patch };
      localStorage.setItem(key, JSON.stringify(next));
      return next;
    });
  }
  const canSubmit =
    !disabled &&
    !uploading &&
    (question.kind === "choice"
      ? !!value.selected_option
      : !!(value.text.trim() || value.attachment_id));
  async function submit() {
    if (canSubmit) await onSubmit(value);
  }
  return (
    <form
      className="answer-editor"
      onSubmit={(e) => {
        e.preventDefault();
        void submit();
      }}
    >
      {question.kind === "choice" && (
        <fieldset className="options">
          <legend>选择答案</legend>
          {question.options?.map((option) => (
            <label key={option}>
              <input
                type="radio"
                name={question.id}
                disabled={disabled}
                checked={value.selected_option === option}
                onChange={() => update({ selected_option: option })}
              />
              <Prose>{option}</Prose>
            </label>
          ))}
        </fieldset>
      )}
      <label className="answer-label">
        {question.kind === "choice" ? "选择理由（可选）" : "你的答案"}
        <textarea
          aria-label="作答输入框"
          rows={3}
          value={value.text}
          disabled={disabled}
          placeholder={
            question.kind === "choice"
              ? "为什么这样选择？理由能帮助定位误解。"
              : "写下解题过程，或上传手写答案。"
          }
          onChange={(e) => update({ text: e.target.value })}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
              e.preventDefault();
              void submit();
            }
          }}
        />
      </label>
      <Suspense fallback={<p>正在打开图片附件…</p>}>
        <AnswerImage
          spaceId={spaceId}
          target={question.id}
          attachment={value.attachment_id || ""}
          onAttachment={(id) => update({ attachment_id: id || null })}
          onConfirm={(text) =>
            update({ text: value.text ? value.text + "\n" + text : text })
          }
          disabled={disabled || uploading}
          onBusy={setUploading}
        />
      </Suspense>
      <button className="primary" disabled={!canSubmit}>
        提交答案
      </button>
      <small>只有提交答案才会判分；提问不会提交这里的草稿。</small>
    </form>
  );
}
