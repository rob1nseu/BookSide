import { useEffect, useState } from "react";
import { api, send } from "./api";
type Memory = {
  id: string;
  text: string;
  scope: string;
  source_id?: string;
  updated: string;
};
export default function MemoryPanel({ spaceId }: { spaceId?: string }) {
  const [items, setItems] = useState<Memory[]>([]);
  const [text, setText] = useState("");
  const [scope, setScope] = useState(spaceId ? "space" : "global");
  const [error, setError] = useState("");
  const refresh = () =>
    api<Memory[]>(
      `/memories?${scope === "partner" ? "partner=true" : spaceId ? "space_id=" + spaceId : ""}`,
    ).then(setItems);
  useEffect(() => {
    void refresh().catch((e) => setError(e.message));
  }, [spaceId, scope]);
  async function add() {
    try {
      await send("/memories", { scope, space_id: spaceId, text });
      setText("");
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <div>
      <p className="muted">
        只记住有助于下次交流的内容。通用偏好可跨课程，课程记忆留在当前空间。
      </p>
      <label>
        记住什么？
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="例如：请先举例，再讲定义"
        />
      </label>
      <label>
        作用范围
        <select value={scope} onChange={(e) => setScope(e.target.value)}>
          {spaceId && <option value="space">仅当前课程</option>}
          <option value="global">所有课程的通用偏好</option>
          <option value="partner">仅小芽陪聊</option>
        </select>
      </label>
      <button className="primary" disabled={!text.trim()} onClick={add}>
        保存记忆
      </button>
      <p className="error-text" role="status">
        {error}
      </p>
      {items.map((item) => (
        <article className="memory-item" key={item.id}>
          <p>{item.text}</p>
          <small>
            {item.scope === "global"
              ? "通用偏好"
              : item.scope === "partner"
                ? "小芽陪聊"
                : "当前课程"}{" "}
            ·{" "}
            {item.source_id
              ? "来源消息 " + item.source_id.slice(0, 8)
              : "用户主动保存"}
          </small>
          <div className="actions">
            <button
              onClick={async () => {
                const value = prompt("修改记忆", item.text);
                if (value?.trim())
                  try {
                    await send(
                      `/memories/${item.id}`,
                      { text: value },
                      "PATCH",
                    );
                    await refresh();
                  } catch (e) {
                    setError((e as Error).message);
                  }
              }}
            >
              修改
            </button>
            <button
              onClick={async () => {
                try {
                  await api(`/memories/${item.id}`, { method: "DELETE" });
                  await refresh();
                } catch (e) {
                  setError((e as Error).message);
                }
              }}
            >
              删除
            </button>
          </div>
        </article>
      ))}
    </div>
  );
}
