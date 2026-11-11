#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Doc Guard - static drift checks for CLI commands inside Markdown docs.

Standard library only. Documentation commands are NEVER executed. The only
command this tool may run is a user-supplied `--help` invocation during
`capture`, and that is guarded by a strict whitelist.

    python -X utf8 docguard.py <command> [options]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path

FORMAT_VERSION = 1
FENCE_RE = re.compile(r"^ {0,3}```([A-Za-z0-9_+-]*)[ \t]*\n(.*?)^ {0,3}```[ \t]*$", re.M | re.S)
CHOICES_RE = re.compile(r"\{([a-zA-Z][a-zA-Z0-9_,\-]*)\}")
LONG_FLAG_RE = re.compile(r"(?<![\w-])--([A-Za-z][A-Za-z0-9-]*)")
SHORT_FLAG_RE = re.compile(r"(?<![\w-])-([A-Za-z]),\s+--[A-Za-z]")
SHELL_META = (";", "&&", "||", "|", ">", "<", "`", "$(", "\n", "\r")
COMMAND_LANGS = {"bash", "sh", "shell", "console", "zsh"}
# 无语言标签 / text 块语义不明（常是目录树），只提示、不解析命令，避免误报
AMBIGUOUS_LANGS = {"", "text", "txt"}
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build"}

LEVELS = {"ERROR": "ERROR", "WARN": "WARN", "INFO": "INFO"}


def now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8-sig")


def write_text(p: Path, text: str, atomic: bool = False) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    if atomic:
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(text, encoding="utf-8", newline="\n")
        os.replace(tmp, p)
    else:
        p.write_text(text, encoding="utf-8", newline="\n")


def json_dump(data) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


# --------------------------------------------------------------------------
# capability spec
# --------------------------------------------------------------------------

def parse_help(text: str) -> tuple[list[str], list[str]]:
    """Extract subcommands and flags from common argparse/click/cobra help."""
    subs: list[str] = []

    def add_choices(chunk: str) -> None:
        for m in CHOICES_RE.finditer(chunk):
            for part in m.group(1).split(","):
                part = part.strip()
                if re.fullmatch(r"[a-zA-Z][a-zA-Z0-9_-]*", part):
                    subs.append(part)

    # 只从 usage 行与 positional arguments 段取子命令，避免把
    # "--format {txt,md}" 这类选项取值误当成子命令。
    for line in text.splitlines():
        if line.strip().lower().startswith("usage:"):
            # usage 行里也可能有 "--op {copy,move}"，先移除选项取值再抽子命令
            cleaned = re.sub(r"--[A-Za-z][A-Za-z0-9-]*\s+\{[^}]*\}", "", line)
            add_choices(cleaned)
    m = re.search(r"^positional arguments:\s*$", text, re.M | re.I)
    if m:
        for line in text[m.end():].splitlines()[1:8]:
            if re.match(r"^\s+\{", line):
                add_choices(line)
                break
            if line and not line[0].isspace():
                break
    if not subs:  # 兜底：非 argparse 风格的帮助文本
        for line in text.splitlines():
            if "--" not in line:
                add_choices(line)
    # "Available Commands:" / "Commands:" sections (cobra / click style)
    m = re.search(r"^(?:Available\s+Commands|Commands|COMMANDS)\s*:\s*$", text, re.M | re.I)
    if m:
        for line in text[m.end():].splitlines()[1:]:
            if not line.strip():
                if subs and line == "":
                    continue
                break
            am = re.match(r"^\s{1,6}([a-zA-Z][a-zA-Z0-9_-]*)\s{2,}\S", line)
            if am:
                subs.append(am.group(1))
            elif line and not line.startswith(" ") and not line.startswith("\t"):
                break
    longs = ["--" + x for x in LONG_FLAG_RE.findall(text)]
    shorts = ["-" + x for x in SHORT_FLAG_RE.findall(text)]
    flags = sorted(set(longs + shorts))
    return sorted(set(subs)), flags


def load_spec(path: Path) -> dict:
    spec = json.loads(read_text(path))
    for key in ("tool", "subcommands", "flags"):
        if key not in spec:
            raise ValueError(f"能力清单缺少字段 {key}：{path}")
    spec.setdefault("aliases", [])
    spec.setdefault("command_flags", {})
    return spec


def ident_tokens(spec: dict) -> list[str]:
    return list(dict.fromkeys([spec["tool"], *spec.get("aliases", [])]))


# --------------------------------------------------------------------------
# capture
# --------------------------------------------------------------------------

def safe_help_command(cmd: str) -> list[str]:
    if not re.search(r"(?:--help|-h)\s*$", cmd.strip()):
        raise ValueError("capture --cmd 只允许运行以 --help / -h 结尾的命令")
    for bad in SHELL_META:
        if bad in cmd:
            raise ValueError(f"capture --cmd 不允许包含 shell 元字符：{bad!r}")
    argv = shlex.split(cmd)
    if not argv:
        raise ValueError("命令为空")
    return argv


def cmd_capture(args) -> int:
    out = Path(args.out).resolve()
    if args.help_file:
        text = read_text(Path(args.help_file))
        source = str(args.help_file)
    elif args.cmd:
        argv = safe_help_command(args.cmd)
        try:
            proc = subprocess.run(argv, timeout=20, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", shell=False)
            text = (proc.stdout or "") + "\n" + (proc.stderr or "")
        except (OSError, subprocess.SubprocessError) as exc:
            raise SystemExit(f"错误：获取 --help 失败：{exc}")
        source = args.cmd
    else:
        raise SystemExit("错误：需要 --help-file 或 --cmd。")
    subs, flags = parse_help(text)
    if not subs:
        print("警告：未从帮助文本中识别出子命令，请检查 spec 或用 inspect 复核。", file=sys.stderr)
    spec = {
        "format_version": FORMAT_VERSION,
        "tool": args.tool,
        "aliases": sorted(set([args.tool, *filter(None, args.alias)])),
        "subcommands": subs,
        "flags": flags,
        "command_flags": {},
        "source": source,
        "captured_at": now(),
    }
    write_text(out, json_dump(spec), atomic=True)
    print(f"已生成能力清单：{out}")
    print(f"工具：{args.tool}｜子命令 {len(subs)} 个｜参数 {len(flags)} 个")
    print(f"子命令：{', '.join(subs) or '（未识别）'}")
    print("提醒：文档里若用变量代指脚本，请把别名补进 aliases；子命令专属参数补进 command_flags。")
    return 0


def cmd_inspect(args) -> int:
    spec = load_spec(Path(args.spec))
    print(f"工具：{spec['tool']}｜来源：{spec.get('source', '—')}｜采集时间：{spec.get('captured_at', '—')}")
    print(f"别名：{', '.join(ident_tokens(spec))}")
    print(f"子命令（{len(spec['subcommands'])}）：{', '.join(spec['subcommands']) or '（空）'}")
    print(f"全局参数（{len(spec['flags'])}）：{', '.join(spec['flags']) or '（空）'}")
    for cmd, flags in spec.get("command_flags", {}).items():
        print(f"  {cmd} 专属：{', '.join(flags)}")
    return 0


# --------------------------------------------------------------------------
# markdown parsing and checking
# --------------------------------------------------------------------------

def collect_docs(target: Path, report_name: str) -> list[Path]:
    if target.is_file():
        return [target] if target.suffix.lower() == ".md" else []
    docs = []
    for p in target.rglob("*.md"):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.name == report_name:
            continue
        docs.append(p)
    return sorted(docs)


def normalize_lines(block: str) -> list[tuple[int, str]]:
    """Return (relative_line_no, command) with continuations merged."""
    out: list[tuple[int, str]] = []
    buf, start = "", 1
    for i, raw in enumerate(block.splitlines(), 1):
        line = raw.strip()
        if line.startswith("$ "):
            line = line[2:].strip()
        if not buf:
            start = i
        if line.endswith("\\"):
            buf += line[:-1].rstrip() + " "
            continue
        merged = (buf + line).strip()
        buf = ""
        if merged:
            out.append((start, merged))
    if buf.strip():
        out.append((start, buf.strip()))
    return out


def tokenize(line: str) -> list[str]:
    try:
        return shlex.split(line, posix=True)
    except ValueError:
        return line.split()


def check_line(line: str, spec: dict) -> tuple[str | None, list[dict]]:
    """Return (status, findings). status None means the line was checked."""
    if line.startswith("#") or not line:
        return "SKIP_COMMENT", []
    if any(meta in line for meta in SHELL_META):
        return "SKIP_COMPLEX", []
    if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", line):
        return "SKIP_ASSIGN", []
    tokens = tokenize(line)
    idents = ident_tokens(spec)
    def is_tool_token(tok: str, alias: str) -> bool:
        # 只接受「整个 token 就是别名」或「路径以别名结尾」，避免把
        # 说明文字里提到的工具名（如 echo "novel.py is ..."）误判成命令。
        return tok == alias or tok.endswith("/" + alias) or tok.endswith("\\" + alias)

    idx = None
    for i, tok in enumerate(tokens):
        if any(alias and is_tool_token(tok, alias) for alias in idents):
            idx = i
            break
    if idx is None:
        return "SKIP_OTHER", []

    rest = tokens[idx + 1:]
    sub = next((t for t in rest if not t.startswith("-") and not t.startswith("$")), None)
    findings: list[dict] = []
    allowed = set(spec["flags"]) | set(spec.get("command_flags", {}).get(sub or "", []))
    if sub is None:
        findings.append({
            "level": "WARN", "type": "MISSING_SUBCOMMAND",
            "detail": "只写了工具名，没有子命令",
            "suggestion": "补上子命令，或确认该行只是演示环境变量设置",
        })
    elif sub not in spec["subcommands"]:
        findings.append({
            "level": "ERROR", "type": "UNKNOWN_SUBCOMMAND",
            "detail": f"子命令 {sub} 不在能力清单中",
            "suggestion": "可用子命令：" + ", ".join(spec["subcommands"]),
        })
    for tok in rest:
        if tok.startswith("--"):
            flag = tok.split("=", 1)[0]
            if flag not in allowed and flag != "--help":
                findings.append({
                    "level": "WARN", "type": "UNKNOWN_FLAG",
                    "detail": f"参数 {flag} 不在允许集合中",
                    "suggestion": "检查拼写，或把它补进 spec 的 flags / command_flags",
                })
    return None, findings


def cmd_check(args) -> int:
    spec = load_spec(Path(args.spec))
    target = Path(args.docs).resolve()
    report_path = Path(args.report) if args.report else None
    docs = collect_docs(target, report_path.name if report_path else "DOC_DRIFT.md")
    if not docs:
        raise SystemExit(f"错误：{target} 下没有找到 Markdown 文档。")

    findings: list[dict] = []
    stats = {"files": len(docs), "checked": 0, "skipped": 0, "blocks": 0,
             "ERROR": 0, "WARN": 0, "INFO": 0}
    base = target if target.is_dir() else target.parent
    for doc in docs:
        text = read_text(doc)
        for m in FENCE_RE.finditer(text):
            lang = (m.group(1) or "").lower()
            if lang not in COMMAND_LANGS and lang not in AMBIGUOUS_LANGS:
                continue
            stats["blocks"] += 1
            start_line = text[:m.start()].count("\n") + 1
            block = m.group(2)
            has_target = any(alias and alias in block for alias in ident_tokens(spec))
            if lang in AMBIGUOUS_LANGS:
                if lang == "" and has_target:
                    findings.append({
                        "level": "INFO", "type": "UNLABELED_BLOCK",
                        "file": str(doc.relative_to(base)) if base in doc.parents or doc == base else doc.name,
                        "line": start_line, "command": "(代码块)",
                        "detail": "含目标命令的代码块未标注语言，已跳过其中的行（可能是目录树）",
                        "suggestion": "补上 ```bash 语言标签后再检查",
                    })
                continue
            for rel, line in normalize_lines(block):
                status, items = check_line(line, spec)
                if status:
                    stats["skipped"] += 1
                    continue
                stats["checked"] += 1
                for it in items:
                    it.update({"file": str(doc.relative_to(base)) if base in doc.parents else doc.name,
                               "line": start_line + rel, "command": line})
                    findings.append(it)
    for f in findings:
        stats[f["level"]] = stats.get(f["level"], 0) + 1
    if args.strict:
        for f in findings:
            if f["level"] == "WARN":
                f["level"] = "ERROR"
        stats["ERROR"] += stats["WARN"]
        stats["WARN"] = 0

    result = {"tool": spec["tool"], "checked_at": now(), "strict": bool(args.strict),
              "stats": stats, "findings": findings}
    report_md = render_report(result, spec)
    if report_path:
        write_text(report_path, report_md, atomic=True)
    if args.json:
        print(json_dump(result), end="")
    else:
        print(f"文档命令检查 · {spec['tool']}")
        print(f"扫描 {stats['files']} 个文档｜检查 {stats['checked']} 条命令｜"
              f"跳过 {stats['skipped']} 条（非目标命令/复杂行/注释）")
        print(f"ERROR {stats['ERROR']}｜WARN {stats['WARN']}｜INFO {stats['INFO']}")
        for f in findings:
            print(f"  [{f['level']:<5}] {f['file']}:{f['line']} {f['type']}")
            print(f"      命令: {f['command']}")
            print(f"      问题: {f['detail']}")
            print(f"      建议: {f['suggestion']}")
        if not findings:
            print("未发现漂移。")
        if report_path:
            print(f"报告：{report_path}")
        print("注意：跳过数不计入已验证；复杂 shell 行不做语义猜测。")
    return 1 if stats["ERROR"] else 0


def render_report(result: dict, spec: dict) -> str:
    s = result["stats"]
    lines = [
        f"# 文档命令漂移报告 · {result['tool']}",
        "",
        f"- 检查时间：{result['checked_at']}｜严格模式：{'是' if result['strict'] else '否'}",
        f"- 文档 {s['files']} 个｜代码块 {s['blocks']} 个｜检查命令 {s['checked']} 条｜跳过 {s['skipped']} 条",
        f"- ERROR {s['ERROR']}｜WARN {s['WARN']}｜INFO {s['INFO']}",
        "- 判定口径：只做静态比对，未执行文档中的任何命令；跳过行不代表通过。",
        "",
        "| 级别 | 位置 | 类型 | 命令 | 问题 | 建议 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for f in result["findings"]:
        esc = lambda v: str(v).replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {f['level']} | {esc(f['file'])}:{f['line']} | {f['type']} | "
                     f"`{esc(f['command'])}` | {esc(f['detail'])} | {esc(f['suggestion'])} |")
    if not result["findings"]:
        lines.append("| — | — | — | — | 无发现项 | — |")
    lines += ["", "## 能力清单", "",
              f"- 子命令：{', '.join(spec['subcommands']) or '（空）'}",
              f"- 全局参数：{', '.join(spec['flags']) or '（空）'}",
              f"- 清单来源：`{spec.get('source', '—')}`",
              "",
              "> CLI 改动后需重新 capture；报告只反映「子命令/参数是否存在」，不判断语义与运行成功率。",
              ""]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Doc Guard · 文档命令示例的静态漂移检查（仅标准库）")
    sub = p.add_subparsers(dest="command", required=True)

    q = sub.add_parser("capture", help="从 --help 生成能力清单")
    g = q.add_mutually_exclusive_group(required=True)
    g.add_argument("--help-file", help="已保存的帮助文本（推荐，纯静态）")
    g.add_argument("--cmd", help="仅允许以 --help 结尾的命令，受白名单约束")
    q.add_argument("--tool", required=True, help="工具标识，如 novel.py")
    q.add_argument("--out", required=True, help="输出 spec.json 路径")
    q.add_argument("--alias", action="append", default=[], help="额外别名，可重复")
    q.set_defaults(func=cmd_capture)

    q = sub.add_parser("inspect", help="查看能力清单")
    q.add_argument("--spec", required=True)
    q.set_defaults(func=cmd_inspect)

    q = sub.add_parser("check", help="检查 Markdown 文档")
    q.add_argument("--spec", required=True)
    q.add_argument("--docs", required=True, help="Markdown 文件或目录")
    q.add_argument("--report", default="", help="Markdown 报告路径，如 DOC_DRIFT.md")
    q.add_argument("--json", action="store_true", help="stdout 输出 JSON")
    q.add_argument("--strict", action="store_true", help="把 WARN 升级为 ERROR")
    q.set_defaults(func=cmd_check)
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 3
    except (OSError, json.JSONDecodeError) as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    sys.exit(main())
