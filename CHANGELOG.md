# 更新记录

## 1.0.0 (2026-11-11)

- 首个公开版本：`capture` / `inspect` / `check` 三条命令。
- 从 `--help` 抽取子命令与参数生成能力清单；静态校验 Markdown fenced code block 中的命令示例。
- ERROR/WARN/INFO 分级、Markdown + JSON 报告、CI 退出码、`--strict` 模式。
- 严格的安全边界：不执行文档命令；`capture --cmd` 仅限 `--help` 且拒绝 shell 元字符。
- WorkBuddy 技能入口、示例（含故意写错的命令）与单元测试。
- 自检三个已有 CLI 仓库时修复了两处误报：无语言标签的目录树块不再被解析为命令；usage 行中 `--flag {a,b}` 的选项取值不再混入子命令。同时抓到并修正了其中一个仓库 README 里的一处真实参数漂移（`--required`）。
