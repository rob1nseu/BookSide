# 本地运行 LearNest

要求 Python 3.11+、Node.js 22.12+（本机验证为 24.10.0）和 uv。项目使用 `uv.lock` 与 `frontend/package-lock.json` 固定依赖。

## 最快启动（Windows PowerShell）

在项目根目录运行：

```powershell
.\scripts\start.ps1
```

打开 http://127.0.0.1:8765 。脚本安装 Python 依赖、在必要时安装前端依赖、构建前端，再启动本机 FastAPI。首次启动需要网络下载依赖。退出用 Ctrl+C。

进入左下角「设置」，填写 DeepSeek 模型名称与新密钥，先保存，再点击「验证连接」。默认模型为 `deepseek-flash`，可按账户实际可用模型修改。密钥仅存储在 `data/model.local.json`，不由 GET 接口返回，不进入源码、测试或模型运行日志。本次开发没有使用对话中贴出的密钥。

未配置模型时，上传、解析、创建学习空间、PDF 阅读及已有记录仍可用；新的模型教学与陪聊会明确报配置缺失。也可复制 `.env.example` 为 `.env`，在本机设置 `DEEPSEEK_API_KEY`。本地设置文件中的值优先于环境变量。

如 PowerShell 阻止运行脚本，可手动执行下方命令，无需全局更改执行策略。

## 开发运行

根目录终端：

```powershell
uv sync
uv run uvicorn backend.app.main:create_app --factory --host 127.0.0.1 --port 8765
```

第二个终端：

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

访问 http://127.0.0.1:5173 。Vite 将 `/api` 转发给本机后端。前端在启动与构建时复制 PDF.js 的 CMap、字体及 WASM 到忽略版本控制的 `public/pdf`，支持离线阅读中文 PDF。服务默认只接受本机 Host 和约定的开发来源，不面向公网部署。

## 生产构建与桌面入口

```powershell
cd frontend
npm.cmd ci
npm.cmd run build
cd ..
uv run uvicorn backend.app.main:create_app --factory --host 127.0.0.1 --port 8765
```

生产模式由同一个后端提供 `frontend/dist`，不需要 Node 常驻。桌面宠物使用：

```powershell
.\scripts\start.ps1 -Desktop
```

或者在完成构建后运行：

```powershell
uv sync --group desktop
uv run --group desktop python -m desktop.pet
```

单击小芽打开或聚焦 LearNest；拖动改变位置；右键选择陪聊、隐藏到托盘或退出。托盘菜单可以重新显示小芽。退出会关闭由该宠物实例启动的后端，复用已有后端时不结束外部服务。浏览器窗口标题必须保留 LearNest 才能被聚焦。浏览器/操作系统阻止前台切换时可能需要手动选中窗口。

## 明确标注的演示模式

```powershell
.\scripts\start.ps1 -Demo
```

演示模型只为体验流程提供固定回复，页面始终显示黄色演示提示，回复也带标记。它不提供可信的教学或评分。正常启动不会自动退回演示模型。不要把演示结果作为模型质量评测。

生成原创测试资料：

```powershell
uv run python scripts/make_samples.py
```

输出到 `data/samples`：两页中文数学 PDF、一页含备注的 PPTX，以及空白、损坏 PDF。没有内置虚构的个人学习记录；需要主动上传这些样例。

## 测试

```powershell
uv run pytest -q
uv run ruff check backend scripts desktop
cd frontend
npm.cmd test
npm.cmd run build
npx.cmd playwright install chromium
npm.cmd run test:e2e
cd ..
uv run --group desktop python -m desktop.pet --self-test
uv run python scripts/measure.py
```

浏览器测试会占用 8765、5173 端口，请先停止手动开发服务器。测试后端使用临时目录和显式演示模型，不读写真实资料。截图保存到系统临时目录 `learnest-desktop.png` / `learnest-mobile.png`。桌面自测隐藏窗口，测试画布、模拟拖动、位置保存、菜单和后台进程生命周期，不替代真实桌面的人工交互验收。

真实 API 冒烟测试必须主动启用，可能产生供应商用量：

```powershell
uv run python scripts/smoke_model.py --live
```

仅输出模型、日期、状态和用量，不输出密钥或回答正文。普通测试不发送真实模型请求。

## 数据、备份与诊断

- 数据目录默认为根目录 `data/`，可设置 `LEARNEST_DATA_DIR`。SQLite 迁移在启动时按编号自动执行。
- `learnest.sqlite3` 保存空间、章节、作答、消息、长期记忆、任务与诊断；`files/` 保存不可变原文件。多个空间复用原文件，但学习记录不共用。
- 在停止应用后复制整个数据目录即可备份；恢复时先停止应用，再恢复该目录。若备份包含 `model.local.json`，请按含密钥文件保护，分享资料备份前移除该文件。
- 学习区「更多 → 导出学习记录」导出当前空间 JSON，不含密钥或 Partner 私聊。删除学习空间不会删除原始资料，也不会删除独立的陪聊记录。
- `/api/diagnostics` 提供近期模型运行、解析任务、耗时、用量与错误摘要，不含密钥和完整对话。
- 被中断的生成标为 interrupted；被中断的解析标为失败并可重试。模型取消不会提交迟到状态。网络断开后刷新可恢复已保存内容。

当前实现边界与验证结果见 [IMPLEMENTATION.md](IMPLEMENTATION.md)。

