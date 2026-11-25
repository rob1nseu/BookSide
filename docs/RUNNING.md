# 本地运行 LearNest

要求 Python 3.11+、Node.js 22.12+（本机验证为 24.10.0）和 uv。项目使用 `uv.lock` 与 `frontend/package-lock.json` 固定依赖。

## 最快启动（Windows PowerShell）

在项目根目录运行：

```powershell
.\scripts\start.ps1
```

打开 http://127.0.0.1:8765 。脚本安装 Python 依赖、在必要时安装前端依赖、构建前端，再启动本机 FastAPI。首次启动需要网络下载依赖。退出用 Ctrl+C。

进入左下角「设置」，填写 DeepSeek 模型名称与新密钥，先保存，再点击「验证连接」。默认模型为 `deepseek-flash`，可按账户实际可用模型修改。密钥仅存储在 `data/model.local.json`，不由 GET 接口返回，不进入源码、测试或模型运行日志。密钥由本机后端用于向 DeepSeek 鉴权；图片识别也调用 DeepSeek，不是离线识别。

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

浏览器测试会占用 8765、5173 端口，请先停止手动开发服务器。测试后端使用临时目录和显式演示模型，不读写真实资料。截图保存到系统临时目录 `learnest-review-map.png`、`learnest-review-mobile.png`、`learnest-math-mobile.png` 等。桌面自测隐藏窗口，测试画布、模拟拖动、位置保存、菜单和后台进程生命周期，不替代真实桌面的人工交互验收。

真实 API 冒烟测试必须主动启用，可能产生供应商用量：

```powershell
uv run python scripts/smoke_model.py --live
uv run python scripts/smoke_review.py --live
```

仅输出模型、状态、用量和校验结果，不输出密钥或回答正文。第二条测试生成原创临时资料，检查导图、出题、原图转写和仅图片判分；读取本机模型配置，不读写用户课程。普通测试不发送真实模型请求。

## 数据、备份与诊断

- 数据目录默认为根目录 `data/`，可设置 `LEARNEST_DATA_DIR`。SQLite 迁移在启动时按编号自动执行。
- `learnest.sqlite3` 保存空间、章节、作答、消息、长期记忆、任务与诊断；`files/` 保存不可变原文件。多个空间复用原文件，但学习记录不共用。
- 在停止应用后复制整个数据目录即可备份；恢复时先停止应用，再恢复该目录。若备份包含 `model.local.json`，请按含密钥文件保护，分享资料备份前移除该文件。
- 学习区「学习记录与准备选项 → 导出学习记录」导出当前空间 JSON，含讲义/题目提问、复习导图与会话、图片元信息，不含图片二进制、密钥或 Partner 私聊。完整图片随数据库备份。删除空间会删除其图片及复习记录，不删除原始资料或独立陪聊。
- `/api/diagnostics` 提供近期模型运行、解析任务、耗时、用量与错误摘要，不含密钥和完整对话。
- 被中断的生成标为 interrupted；被中断的解析标为失败并可重试。模型取消不会提交迟到状态。网络断开后刷新可恢复已保存内容。

当前实现边界与验证结果见 [IMPLEMENTATION.md](IMPLEMENTATION.md)。

## 本轮反馈对应的操作

- 目录按“大章 → 小节”展示，大章可折叠。优先保留 PDF 前两级书签，无书签时识别正文编号标题、过滤重复页眉；更深标题包含在所属小节正文内。没有可靠标题时仍按页分组，不保证所有 PDF 排版均能还原目录。
- 旧空间点击“用新目录创建学习空间”，即可复用资料创建修正后的目录。旧空间及题目、作答全部保留，避免旧记录被错配。
- 导入即建立全文检索。点击“开始学习”只准备当前小节；需要提前准备时，展开“学习记录与准备选项 → 后台准备整章”，可随时停止。前台操作优先，后台只更新简短状态。服务重启后未完成任务显示可重试，不自动恢复付费调用。
- 选择题先点选选项，输入框单独填写理由；选项不覆盖理由，二者均用于判分和复核。选对但理由有误不计为完全掌握。
- 支持 PNG/JPEG 答案图片（最大 5 MiB），可上传、拖拽或粘贴。看到“已附原图”后即可直接提交；“查看 / 修改识别文字”是可选步骤。原图与题目绑定并存入本机数据库，刷新后保留，转写和判分会把原图发送至 DeepSeek。识别失败时可重试或继续用原图判分，模糊手写仍可能需要人工核对。
- 题目内“你的答案 → 提交答案”负责判分；“问这道题”只求助；底部“问讲义”只询问章节内容。三者的草稿与对话隔离，切换不会吞掉未提交答案。
- “考前复习 → 生成章节思维导图”生成一次后保存。点击节点可看摘要、跳转原文、提问或针对性练习；“本章练一轮”优先覆盖弱项和未验证节点。跳过和辅助完成不标成独立通过，刷新后可继续本轮；退出回到原学习位置。
- 公式兼容四种常用 LaTeX 定界符、矩阵和多行推导。若模型输出了非法 LaTeX，保留可读内容，不保证自动修正任意公式。

## 推送 GitHub 前的密钥检查

`data/`、`.env.*` 和任意路径的 `model.local.json` / `model.local.tmp` 已忽略。不要使用 `git add -f` 强制加入这些文件，不要把密钥写进源码。

当前工作副本已启用提交前、推送前钩子；新克隆需要执行一次：

```powershell
git config core.hooksPath .githooks
uv run python scripts/check_secrets.py --staged --history
```

检查只输出命中的路径或 Git 对象编号，不输出密钥值。它检查常见密钥格式及本地配置路径，是额外保护，不替代对暂存内容的检查。已经在聊天中出现的密钥建议轮换，并只在本机设置中更新。
