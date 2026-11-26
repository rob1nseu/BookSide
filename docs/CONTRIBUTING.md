# 为 BookSide 做贡献

欢迎提交问题反馈、教材解析案例、界面改进和小范围修复。

1. 说明问题、复现步骤和预期行为，分享教材前确认可以公开。
2. 保持修改聚焦，说明如何验证；不要提交真实密钥、私有教材、数据库或本机日志。
3. 安装依赖与启动方式见根目录 README。前端修改应通过 `npm run build`，Python 修改应通过 `uv run ruff check backend scripts desktop`。
4. 提交前运行 `uv run python scripts/check_secrets.py`。

内部测试与开发记录保留在维护者本地，当前公开仓库不包含它们。提交修复时请附可复现的验证步骤或最小验证脚本。不要通过删除数据迁移或绕过内容检查来解决问题。
