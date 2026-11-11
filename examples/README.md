# 示例：抓出 README 里的死命令

这组文件是一次真实跑通的检查，用的 CLI 是同作者的 [`workbuddy-webnovel-writer`](https://github.com/LiQingfeng111/workbuddy-webnovel-writer) 里的 `scripts/novel.py`。

| 文件 | 说明 |
| --- | --- |
| `help-novel.txt` | 把 `novel.py --help` 与 10 个子命令各自的 `--help` 拼接而成；这样 `--title`、`--chapter` 等子命令专属参数也会进入能力清单，减少误报 |
| `spec.novel.json` | `capture` 生成的能力清单，含 `aliases`（`$P`、`scripts/novel.py`） |
| `sample-doc.md` | **故意写错**的示例文档：一条过时子命令、一个拼错的参数、一个无语言标签代码块，另有非目标命令与管道命令用于演示跳过 |
| `DOC_DRIFT.md` | `check` 生成的报告 |

## 复现

在仓库根目录：

```bash
P=scripts/docguard.py

python -X utf8 $P capture --help-file examples/help-novel.txt \
  --tool novel.py --out examples/spec.novel.json \
  --alias '$P' --alias 'scripts/novel.py'

python -X utf8 $P inspect --spec examples/spec.novel.json

python -X utf8 $P check --spec examples/spec.novel.json \
  --docs examples/sample-doc.md --report examples/DOC_DRIFT.md
```

`check` 的退出码是 1，因为报告里有：

- **ERROR** `UNKNOWN_SUBCOMMAND`：`outline` 不在 `novel.py` 的 10 个子命令里；
- **WARN** `UNKNOWN_FLAG`：`--verbos` 拼错；
- **INFO** `UNLABELED_BLOCK`：代码块没标语言。

同时如实报告「跳过 5 条」——`git clone`、`cd`、管道命令等不做语义猜测，不算已验证。

## 自检自己的仓库

把某个项目所有子命令的 `--help` 拼成一个文件再 `capture`，是推荐用法：argparse 的顶层帮助不列子命令专属参数，只扫顶层会误报一堆 `UNKNOWN_FLAG`。例如：

```bash
CLI=../agent-receipt/scripts/receipt.py
H=/tmp/receipt-help.txt
python -X utf8 $CLI --help > $H
for c in init add verify attest handoff resume history; do
  python -X utf8 $CLI $c --help >> $H
done
python -X utf8 scripts/docguard.py capture --help-file $H --tool receipt.py --out /tmp/spec.json
python -X utf8 scripts/docguard.py check --spec /tmp/spec.json --docs ../agent-receipt/README.md
```
