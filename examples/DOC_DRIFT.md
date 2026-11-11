# 文档命令漂移报告 · novel.py

- 检查时间：2026-11-11 23:59:38｜严格模式：否
- 文档 1 个｜代码块 6 个｜检查命令 4 条｜跳过 5 条
- ERROR 1｜WARN 1｜INFO 1
- 判定口径：只做静态比对，未执行文档中的任何命令；跳过行不代表通过。

| 级别 | 位置 | 类型 | 命令 | 问题 | 建议 |
| --- | --- | --- | --- | --- | --- |
| ERROR | sample-doc.md:25 | UNKNOWN_SUBCOMMAND | `python -X utf8 scripts/novel.py outline --volume 1` | 子命令 outline 不在能力清单中 | 可用子命令：check, count, draft, export, init, query, rebuild, retcon, settle, status |
| WARN | sample-doc.md:31 | UNKNOWN_FLAG | `python -X utf8 scripts/novel.py check --root ./my-book --chapter 1 --verbos` | 参数 --verbos 不在允许集合中 | 检查拼写，或把它补进 spec 的 flags / command_flags |
| INFO | sample-doc.md:42 | UNLABELED_BLOCK | `(代码块)` | 含目标命令的代码块未标注语言，已跳过其中的行（可能是目录树） | 补上 ```bash 语言标签后再检查 |

## 能力清单

- 子命令：check, count, draft, export, init, query, rebuild, retcon, settle, status
- 全局参数：--chapter, --confirm, --file, --force, --format, --genre, --help, --json, --limit, --max, --min, --note, --outline-version, --platform, --pov, --root, --scope, --target, --term, --title, --volume, -h
- 清单来源：`examples/help-novel.txt`

> CLI 改动后需重新 capture；报告只反映「子命令/参数是否存在」，不判断语义与运行成功率。
