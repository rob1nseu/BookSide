# 仓库维护边界

- `backend/`、`frontend/src/`、`desktop/` 是运行代码；三个目录中的测试/资源也是交付内容。
- `start.ps1` 是唯一的 Windows 启动实现；`start.cmd` 支持双击；`scripts/start.ps1` 是兼容旧命令的转发入口。
- `scripts/` 保留资料样例、性能测试、教学评测、真实模型冒烟测试、密钥检查与旧数据迁移工具。这些是独立命令，不因没有被应用 import 就属于死代码。
- `tests/evaluation/cases.json` 是人工教学评测案例，保留；实际运行报告写入忽略的 `data/evaluations/`。
- `data/` 与 `.local/` 用于个人资料、模型配置、报告和设计草稿，不提交。
- 锁文件、数据库迁移及字体许可证必须保留，不作为“精简”对象。

本轮删除：无引用的旧校徽 PNG、旧书本 PNG、早期页面设计大图。历史算术评测报告移至本地 `data/evaluations/`，不丢弃本机结果。此前撤回的 Windows 打包脚本、旧桌宠实现仍保持删除状态。当前应用图标为 `frontend/public/app-icon.svg`：仅两种填充色，像素坐标，无内嵌位图，无外部请求。

`.gitignore` 修正了对 `.env.example` 和整个 `tests/` 的误忽略。添加新的私密输出目录时，应先补充忽略规则；不要为了避免提交本地资料而忽略整个源码或测试目录。已跟踪文件必须单独检查，历史记录不由 `.gitignore` 改写。
