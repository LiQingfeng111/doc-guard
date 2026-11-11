# Doc Guard · 文档命令守卫

> 死链有人查，**死命令**没人查。
>
> 从 CLI 的 `--help` 生成能力清单，静态校验 README 里的 shell 命令示例：子命令还在吗？参数拼对了吗？**全程不执行文档里的任何命令。**

[English summary](#english-summary) · [快速开始](#快速开始) · [与现有工具的差异](#与现有工具的差异)

## 问题

CLI 改了子命令（`outline` → `plan`）、删了参数（`--legacy`）、加了必填项，README 里的示例却没人同步。读者复制粘贴就报错，而 CI 里的链接检查全绿——因为链接没坏，坏的是命令。

现有工具都没覆盖这一层：

| 项目 | 做什么 | 不做什么 |
| --- | --- | --- |
| [`lycheeverse/lychee`](https://github.com/lycheeverse/lychee) ★4121 · Apache-2.0 | 检查 Markdown/HTML 里的 URL 与邮箱是否可达 | 不解析 shell 命令、不比对 CLI 能力 |
| [`danielhirt/kedge`](https://github.com/danielhirt/kedge) ★1 · Apache-2.0 | 比较代码锚点的 AST 指纹，判断 steering doc 是否过期 | 不读 fenced code block 里的命令，不解析 `--help` |
| [`SysRunAI/Markdown-Code-Runner`](https://github.com/SysRunAI/Markdown-Code-Runner) ★0 · MIT | 抽取并**执行** Markdown 代码块 | 会真的跑命令（危险、慢、依赖环境），不做静态能力比对 |
| `doctest` / `mdsh` / `tldr` | 校验 Python 示例、执行文档、速查页 | 不针对任意 CLI 的子命令/参数集合 |
| [`agent-sh/agnix`](https://github.com/agent-sh/agnix) ★478 | 校验 AGENTS.md / SKILL.md 等配置合规 | 不校验文档中的命令示例 |

按 `readme command examples verify cli`、`cli documentation examples drift check`、`help output snapshot test cli` 检索 GitHub，没有对应实现。`doc-guard` 补的就是这一格。

## 我的版本改进了什么

1. **能力清单来自 CLI 自己**：解析 `--help` 的子命令与 `--flags`，不维护第二份易过期的手写文档；清单可人工补 `aliases` 与 `command_flags`。
2. **只静态比对，不执行文档命令**：相比 Markdown-Code-Runner 更安全、更快、可在无依赖环境的 CI 里跑。`capture --cmd` 也只允许 `--help`。
3. **定位到文件 + 行号 + 原命令**：报告直接可改，不给一堆模糊告警。
4. **可复验、可进 CI**：`DOC_DRIFT.md` + JSON，`ERROR` 退出码 1，`--strict` 把警告升级为阻断。
5. **零依赖**：Python 3.9 标准库，跨平台，不需要 Node/Rust/网络。
6. **能自检**：作者用自己的三个 CLI 项目跑过一轮，见 [示例](#示例与自检)。

## 快速开始

```bash
# 1. 生成能力清单（纯静态，推荐）
python -X utf8 scripts/novel.py --help > help.txt
python -X utf8 scripts/docguard.py capture --help-file help.txt --tool novel.py --out spec.json

# 2. 检查文档
python -X utf8 scripts/docguard.py check --spec spec.json --docs README.md

# 3. 看结果
cat DOC_DRIFT.md
```

也可以让工具自己取帮助文本（受严格白名单约束）：

```bash
python -X utf8 scripts/docguard.py capture \
  --cmd "python -X utf8 scripts/novel.py --help" --tool novel.py --out spec.json
```

**WorkBuddy 技能安装**：

```bash
git clone https://github.com/LiQingfeng111/doc-guard.git \
  "$HOME/.workbuddy-ai/skills/doc-guard"
```

重启会话后，说「检查一下 README 里的命令有没有过时」即可触发。

## 输出示例

```
文档命令检查 · novel.py
扫描 2 个 Markdown 文件｜检查 14 条命令｜跳过 9 条（非目标命令/复杂行）
ERROR 1｜WARN 2｜INFO 0

  [ERROR] README.md:41 UNKNOWN_SUBCOMMAND
      命令: python -X utf8 scripts/novel.py outline --volume 1
      问题: 子命令 outline 不在能力清单中
      建议: 可用子命令 init, status, draft, count, check, query, settle, retcon, export, rebuild
  [WARN ] README.md:57 UNKNOWN_FLAG
      命令: python -X utf8 scripts/novel.py verify --root . --verbos
      问题: --verbos 不在允许的参数中
      建议: 检查拼写，或把它补进 spec 的 command_flags
```

有 ERROR 时退出码 1，可直接放进 CI；`DOC_DRIFT.md` 是同内容的 Markdown 报告。

## 能力清单

`capture` 生成，可提交进仓库、可手工修订：

```json
{
  "tool": "novel.py",
  "aliases": ["scripts/novel.py", "$P"],
  "subcommands": ["init", "status", "draft", "count", "check"],
  "flags": ["--root", "--json", "--help"],
  "command_flags": { "check": ["--chapter", "--file"] },
  "source": "help.txt",
  "captured_at": "2026-11-11 23:40:00"
}
```

- `aliases`：文档里用变量代指脚本时（`$P`、`$CLI`）必须补，否则那些行会被跳过；
- `command_flags`：argparse 的顶层 `--help` 通常不列子命令专属参数，手工补上可消除误报；
- `subcommands`：CLI 每次改动后重新 `capture`，旧 spec 会给出错误结论。

## 检查规则

| 规则 | 级别 |
| --- | --- |
| `UNKNOWN_SUBCOMMAND` 子命令不在清单中 | ERROR |
| `MISSING_SUBCOMMAND` 只写了工具名 | WARN |
| `UNKNOWN_FLAG` 参数不在允许集合 | WARN（`--strict` → ERROR） |
| `UNLABELED_BLOCK` 含命令的代码块没标语言 | INFO |

处理细节：去 `$ ` 提示符、合并 `\` 续行、跳过注释/空行、`--flag=value` 归一为 `--flag`；含 `;` `&&` `|` `>` 反引号的复杂行标 SKIPPED 并在汇总里如实列出；不含 tool/alias 的行（git、cd、echo、变量赋值）跳过。

## 安全边界

- **绝不执行文档里的命令**。检查阶段只做文本解析与集合比对。
- `capture --cmd` 必须满足：以 `--help` 或 `-h` 结尾、不含 `; && || | > < \` $` 与换行、20 秒超时、`shell=False` 执行。
- 不修改用户的 Markdown；只写 `DOC_DRIFT.md` 与可选 JSON 报告。
- 只判断「子命令/参数是否存在」，不判断语义、取值或运行成功率；不做网络请求。

## 示例与自检

`examples/` 里有一份真实 `--help` 文本、生成的 `spec.json`、一份**故意写错**的示例文档，以及 `check` 跑出来的 `DOC_DRIFT.md` 报告。

作者用它自检了本账号下另外三个 CLI 项目（长篇网文写作、Agent Receipt、File Plan）的 README，结果颇有说服力：

- **抓到 1 处真实漂移**：`agent-receipt/README.md` 里的示例写了 `--required`，而 CLI 实际只提供 `--optional`（默认必需）。该文档已修正。
- **暴露了工具自身的 2 个误报并已修复**：无语言标签的目录树块被当成命令；`--op {copy,move,...}` 的选项取值混进子命令清单。
- 修复后三个仓库的 README 全部 `ERROR 0 / WARN 0`，只剩 1 条 INFO（目录树块未标语言）。

复现方式见 [`examples/README.md`](examples/README.md)。

## CI 集成

```yaml
- name: 生成 CLI 能力清单
  run: |
    python -X utf8 scripts/mycli.py --help > help.txt
    python -X utf8 scripts/docguard.py capture --help-file help.txt --tool mycli.py --out spec.json
- name: 检查文档命令漂移
  run: python -X utf8 scripts/docguard.py check --spec spec.json --docs . --strict
```

把 `spec.json` 一起提交，就能在 PR 里看到「改了 CLI 但没改文档」的直接证据。

## FAQ

**Q：会不会误报很多？** 未知参数默认只是 WARN；补 `command_flags` / `aliases` 后可降到零。复杂 shell 行标 SKIPPED，不猜语义。

**Q：支持哪些 CLI 帮助格式？** argparse / click / cobra 的常见格式（`{a,b,c}` 选择列表、`Available Commands:` 段、`--flag` 列表）。解析结果建议用 `inspect` 看一眼再提交。

**Q：为什么不用 `markdown-link-check` 那套？** 它们处理的是 URL，本工具处理的是命令语法与能力集合，输入和判定都不同。

**Q：能自动修复文档吗？** 不能，也刻意不做。改文档需要理解语义，工具只给精确定位与建议。

## English Summary

A zero-dependency, static checker for CLI commands embedded in Markdown docs. `capture` builds a capability spec (subcommands + flags) from a CLI's `--help` output; `check` parses fenced shell blocks and reports unknown subcommands, mistyped flags and unlabeled blocks, with file, line, original command and suggestions. It never executes commands from documentation. Emits a Markdown report, JSON and CI-friendly exit codes.

## 许可证

[MIT](LICENSE) © 2026 LiQingfeng111

本项目为独立实现，未复制上述参考项目的代码或文档；仅在设计思路上参考并致谢。
