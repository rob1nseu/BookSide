# LearNest

极简学习：上传教材，按章节学习，用问题验证理解，用思维导图复习。

## 从源码运行

准备 Git、[uv](https://docs.astral.sh/uv/getting-started/installation/) 与 Node.js 22.12+。
Python 依赖由 `uv.lock` 固定，前端依赖由 `package-lock.json` 固定。

```sh
git clone https://github.com/rob1nseu/LearNest.git
cd LearNest
uv sync --locked
cd frontend
npm ci
npm run build
cd ..
uv run uvicorn backend.app.main:create_app --factory --host 127.0.0.1 --port 8765
```

浏览器打开 **http://127.0.0.1:8765**，在设置中配置自己的模型服务。
课程与配置默认保存在项目的 `data/`，已排除版本控制；不要提交密钥或私人教材。

Windows PowerShell 可使用快捷脚本：

```powershell
.\start.ps1
# 可选：同时显示桌面宠物
.\start.ps1 -Desktop
```

macOS/Linux 也可以按上面的通用命令运行网页应用；当前桌面宠物的实机验证范围为 Windows。
不再维护 Windows exe/安装包或 Docker。浏览器是完整学习入口，桌面宠物是可选功能。

也可双击根目录 `start.cmd`；带桌宠运行：`start.cmd -Desktop`，演示：`start.cmd -Demo`。
`start.cmd` 只负责调用同目录的 PowerShell 脚本。`start.ps1` 根据自己的位置定位项目，按锁文件安装依赖、构建网页，再启动本地后端；因此从其他目录调用也可以运行。旧 `scripts/start.ps1` 仅保留转发，启动逻辑只维护一份。`start.ps1 -Check` 只检查工具是否可用，不安装、不启动服务。

## 提交到 GitHub

`.gitignore` 排除本地密钥、课程数据、依赖目录、构建产物、缓存、日志、人工反馈 Word 文件与本地评测报告。源码、测试、依赖锁文件、迁移、配置模板和字体许可证保留在 Git 中。
提交前运行 `uv run python scripts/check_secrets.py`；可用 `git config core.hooksPath .githooks` 启用提交/推送检查。
忽略规则不会自动取消已经跟踪的文件，也不会清除历史提交中的内容；本轮检查未发现已跟踪的私密配置文件。

## 开发与测试

前端热更新：在 `frontend` 中运行 `npm run dev`，访问 http://127.0.0.1:5173；后端用上面的命令启动，可附加 `--reload`。

```sh
uv run pytest -q
cd frontend
npm test
npm run test:e2e
```

浏览器测试需先运行 `npx playwright install chromium`，并释放 8765、5173 端口。
桌面测试：`uv run --group desktop pytest backend/tests/test_companion.py -q`。

详细说明见 [运行文档](docs/RUNNING.md)、[产品设计](prompt.md) 与 [实现记录](docs/IMPLEMENTATION.md)。
