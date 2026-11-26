# Windows 预览发行包

这是本地测试预览版，尚未完成干净 Windows 虚拟机、多显示器与完整教学质量人工验收。

## 使用

解压整个 `LearNest-windows-x64.zip`，运行文件夹中的 `LearNest.exe`。不要单独移动 exe；`_internal` 是运行时资源。
启动后浏览器打开 `http://127.0.0.1:8765`，宠物用于再次打开网页。关闭网页不会结束服务，右键宠物或托盘选择退出。
界面内设置自己的模型服务密钥。发行包不包含开发者的密钥、教材或数据库。

默认数据目录为 `%LOCALAPPDATA%/LearNest`；可用 `LEARNEST_DATA_DIR` 指定其他目录。数据库迁移前自动生成 SQLite 在线备份，位于数据目录的 `backups`。

## 从源码目录迁移

关闭正在运行的旧版应用。目标目录必须尚不存在，工具不会覆盖已有数据：

```powershell
uv run python scripts/migrate-local-data.py --source ./data --destination "$env:LOCALAPPDATA/LearNest"
```

迁移保留原始目录，复制数据库、上传文件和本机模型配置；这些数据只留在本机。

## 构建

```powershell
.\scripts\build-windows.ps1
```

构建采用显式资源清单，包含前端、数据库迁移、精选资源目录和宠物图片。运行时无需 Node、uv 或 Python；首次构建需要下载依赖。

构建使用独立 `.venv-build` 与 uv 管理的标准 CPython，且显式复制该解释器的 OpenSSL DLL，避免系统 PATH 中 Conda 库污染。生成 ZIP 前运行冻结程序自测；本机实际通过数据库、前端、Qt 图片、本地 HTTP 与校徽资源检查。

## 验收边界

- 桌面素材目前是四帧预览：待机、眨眼、挥手、拖动姿态。没有宣称完整连续行走动画。
- 原生 `--self-test <report.json>` 检查数据库迁移、前端资源和 Qt 图片加载，不等于实际桌面鼠标与多显示器验收。
- 本轮算术评测由程序生成标签，不能替代人工标注的教育场景评测。详见 `eval-arithmetic*.json`。
- 本机单用户软件，不提供公网部署、多用户认证或 Docker。
