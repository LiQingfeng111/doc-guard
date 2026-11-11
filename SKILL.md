---
name: doc-guard
description: 文档命令示例的漂移检查。当用户要检查 README / 使用文档里的命令行示例是否过时、CLI 改了参数后想知道哪些文档需要同步、给项目加文档一致性 CI 门禁，或需要「文档里写的命令还能不能跑」的静态核对时使用。从 CLI 的 --help 生成能力清单，再与 Markdown 代码块中的命令逐条比对，报告未知子命令、拼错的参数与缺失的示例；只做静态比对，绝不执行文档里的命令。也适用于批量自检多个仓库的 README。
agent_created: true
---

# 文档命令守卫（Doc Guard）

## 定位

`lychee` 这类工具能查出文档里的**死链**，但没人查文档里的**死命令**：CLI 把 `outline` 改成 `plan`、删掉 `--legacy` 参数之后，README 里的示例还是旧的，读者复制粘贴就报错。

`kedge` 查的是代码锚点的 AST 指纹，`Markdown-Code-Runner` 会真的执行代码块（危险且慢），`doctest` 只管 Python 代码。本技能补的是中间那一层：**纯静态地校验 shell 命令示例与 CLI 实际能力是否一致**。

## 三条铁律

1. **不执行文档里的任何命令。** 检查过程只读 Markdown 文本与能力清单。`capture --cmd` 也只允许运行以 `--help` 结尾的命令，且拒绝任何 shell 元字符。
2. **能力清单来自 CLI 自己。** 子命令与参数从 `--help` 输出抽取，不靠人维护第二份文档；清单可人工补充别名与子命令专属参数。
3. **报告可复验、可进 CI。** 输出 `DOC_DRIFT.md` 与 JSON，含文件、行号、原命令、问题类型与建议；有 ERROR 时退出码 1，可加 `--strict` 把警告也变成阻断。

## 快速判定

| 用户意图 | 动作 |
| --- | --- |
| 「检查 README 里的命令还对新不对」 | `capture` 生成 spec → `check` 扫描文档 → 报告漂移 |
| 刚改了 CLI 子命令/参数 | 重新 `capture`（旧 spec 作废）→ `check` → 按报告改文档 |
| 给仓库加文档门禁 | CI 里跑 `check --strict`，把 `DOC_DRIFT.md` 作为产物 |
| 多个仓库批量自检 | 每个工具一份 spec，逐份 `check`，汇总报告 |
| 想看当前识别到哪些命令 | `inspect --spec ...` |

## 工作流

1. **生成能力清单**：优先 `capture --help-file help.txt`（纯静态）；也支持 `capture --cmd "python cli.py --help"`（受严格白名单约束）。产出的 `spec.json` 可提交进仓库。
2. **人工补充**：若文档里用变量代指脚本（如 `$P`），把别名写进 spec 的 `aliases`；若某子命令有专属参数，写进 `command_flags`。
3. **检查**：`check --spec spec.json --docs README.md`（也可传目录，递归找 `*.md`）。
4. **呈报**：区分 ERROR（未知子命令）与 WARN（未知参数、缺语言标签）；不要把 WARN 说成通过，也不要把跳过检查的行算作已验证。
5. **修复**：改的是**文档或 spec**，不是让工具去改 CLI；修复后重跑 `check` 直到干净。

## 能力清单格式

```json
{
  "tool": "novel.py",
  "aliases": ["scripts/novel.py", "$P"],
  "subcommands": ["init", "status", "draft", "count"],
  "flags": ["--root", "--json", "--force"],
  "command_flags": { "check": ["--chapter", "--file"] },
  "source": "help.txt",
  "captured_at": "2026-11-11 23:40:00"
}
```

`flags` 是全局参数；判定某条命令的参数时取 `flags ∪ command_flags[子命令]`。

## 检查规则

从 Markdown 的 `bash` / `sh` / `shell` / `console` / `zsh`（或无语言标签）代码块逐行取命令：

- 去掉 `$ ` 提示符、合并 `\` 续行、跳过注释与空行；
- 含 shell 元字符（`;`、`&&`、`|`、`>`、`` ` ``、`$()`）的复杂行标记 SKIPPED，不猜测其语义；
- 命令行必须含 `tool` 或 `aliases` 之一才检查，其余（`git clone`、`cd`、`echo`、变量赋值）跳过；
- 取工具标识之后第一个非参数 token 作为子命令，与 `subcommands` 比对；
- 逐个 `--flag` 与允许集合比对，`--flag=value` 按 `--flag` 处理。

| 问题类型 | 级别 | 含义 |
| --- | --- | --- |
| `UNKNOWN_SUBCOMMAND` | ERROR | 文档用了 CLI 已不存在的子命令 |
| `MISSING_SUBCOMMAND` | WARN | 只写了工具名，没有子命令 |
| `UNKNOWN_FLAG` | WARN（`--strict` 升为 ERROR） | 参数不在能力清单里 |
| `UNLABELED_BLOCK` | INFO | 含命令的代码块没标语言 |

## 确定性脚本

`scripts/docguard.py`，Python 3.9+，仅标准库。

| 命令 | 作用 |
| --- | --- |
| `capture --help-file <文件> --tool <标识> --out spec.json` | 从帮助文本抽取能力清单（推荐） |
| `capture --cmd "<cli> --help" --tool <标识> --out spec.json` | 运行 `--help` 后抽取，受白名单约束 |
| `inspect --spec spec.json` | 打印识别到的子命令与参数 |
| `check --spec spec.json --docs <文件/目录> [--strict] [--json] [--report DOC_DRIFT.md]` | 扫描文档并生成报告 |

## 关键约束

- 不执行文档中的命令；`capture --cmd` 只接受以 `--help` / `-h` 结尾、不含 shell 元字符的命令，20 秒超时。
- 不修改用户的 Markdown；只写 `DOC_DRIFT.md` 与可选的 JSON 报告。
- 能力清单是「CLI 当前能力」的快照，CLI 一改就要重新 `capture`；用旧 spec 检查会给出错误结论。
- 只做静态比对，不判断命令语义是否正确、参数取值是否合理，也不验证命令实际能否运行成功。
- 文档里用变量代指脚本时，必须补 `aliases`，否则那些行会被跳过 —— 报告里要如实列出跳过数。
