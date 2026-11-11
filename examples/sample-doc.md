# 示例文档（故意包含过时的命令）

这份文档用来演示 `doc-guard` 能抓到什么。里面既有正确示例，也有 CLI 改版后遗留的死命令。

## 安装

```bash
git clone https://example.com/novel.git
cd novel
```

## 快速开始

```bash
R=./my-book
P=scripts/novel.py

python -X utf8 scripts/novel.py init --root $R --title "我的书"
python -X utf8 $P status --root $R --json
```

## 规划卷纲（这段已过时）

```bash
python -X utf8 scripts/novel.py outline --volume 1
```

## 检查章节

```bash
python -X utf8 scripts/novel.py check --root ./my-book --chapter 1 --verbos
```

## 复杂命令（会被跳过，不做语义猜测）

```bash
python -X utf8 scripts/novel.py status --root . | head -5
```

## 没有语言标签的代码块

```
python -X utf8 scripts/novel.py export --root ./my-book --format txt
```
