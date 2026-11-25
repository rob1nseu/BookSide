import { useState } from "react";
import { api, send } from "./api";
import type { Settings as ModelSettings } from "./types";
export default function Settings({
  settings,
  onChange,
}: {
  settings: ModelSettings;
  onChange: (s: ModelSettings) => void;
}) {
  const [model, setModel] = useState(settings.model);
  const [key, setKey] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  async function save() {
    setBusy(true);
    try {
      const s = await send<ModelSettings>(
        "/settings",
        { model, key: key || undefined },
        "PUT",
      );
      setKey("");
      onChange(s);
      setMessage("设置已保存在本机。尚未验证连接。");
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function check() {
    setBusy(true);
    try {
      const result = await send<{ demo: boolean; model: string }>(
        "/settings/check",
        {},
      );
      setMessage(
        result.demo
          ? "演示模式：未调用真实 API"
          : `${result.model} 真实连接验证成功`,
      );
    } catch (e) {
      setMessage((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="settings">
      <p className="muted">模型仅由本机后端调用，密钥不会返回给浏览器。</p>
      <label>
        服务商
        <input value="DeepSeek · https://api.deepseek.com" readOnly />
      </label>
      <label>
        模型名称
        <input value={model} onChange={(e) => setModel(e.target.value)} />
      </label>
      <label>
        API 密钥
        <input
          type="password"
          autoComplete="new-password"
          value={key}
          onChange={(e) => setKey(e.target.value)}
          placeholder={
            settings.configured
              ? "已配置；留空保持现有密钥"
              : "填写新密钥，仅保存到本机"
          }
        />
      </label>
      <p className="muted small">
        本机配置文件不纳入版本控制。共享电脑请保护数据目录。
      </p>
      <div className="actions">
        <button
          className="primary"
          disabled={busy || !model.trim()}
          onClick={save}
        >
          保存设置
        </button>
        <button
          disabled={busy || (!settings.configured && !settings.demo)}
          onClick={check}
        >
          验证连接
        </button>
      </div>
      <p role="status">{message}</p>
      <hr />
      <label className="inline">
        <input
          type="checkbox"
          checked={settings.memory_paused}
          onChange={async (e) => {
            try {
              await send(
                "/memory-settings",
                { paused: e.target.checked },
                "PUT",
              );
              onChange(await api<ModelSettings>("/settings"));
            } catch (err) {
              setMessage((err as Error).message);
            }
          }}
        />
        暂停长期记忆读取与写入
      </label>
      <p className="small muted">
        仍保存聊天记录、作答与学习进度。每积累一小段对话，后台整理摘要和稳定偏好；可在记忆面板查看或删除。
      </p>
    </div>
  );
}
