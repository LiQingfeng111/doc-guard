# -*- coding: utf-8 -*-
"""Unit tests for scripts/docguard.py (standard library only).

    python -m unittest discover -s tests -v
"""

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("docguard", REPO / "scripts" / "docguard.py")
dg = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dg)

HELP = """usage: novel.py [-h] [--root ROOT] [--json] {init,status,draft,check,export} ...

WorkBuddy novel tools

positional arguments:
  {init,status,draft,check,export}
                        command to run

options:
  -h, --help            show this help message and exit
  --root ROOT           book root
  --json                machine readable output
  --allow-commands      authorize command checks
"""


class DocGuardTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.help_file = self.root / "help.txt"
        self.help_file.write_text(HELP, encoding="utf-8")
        self.spec_file = self.root / "spec.json"
        self.cli("capture", "--help-file", str(self.help_file), "--tool", "novel.py",
                 "--out", str(self.spec_file), "--alias", "$P")

    def tearDown(self):
        self._tmp.cleanup()

    def cli(self, command, *extra):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = dg.main([command, *extra])
        return code, buf.getvalue()

    def doc(self, name, text):
        p = self.root / name
        p.write_text(text, encoding="utf-8")
        return p

    def check(self, doc_path, *extra):
        return self.cli("check", "--spec", str(self.spec_file), "--docs", str(doc_path), *extra)

    def test_parse_help(self):
        subs, flags = dg.parse_help(HELP)
        self.assertIn("init", subs)
        self.assertIn("export", subs)
        self.assertIn("--root", flags)
        self.assertIn("--json", flags)

    def test_option_choices_are_not_subcommands(self):
        text = HELP + "  --format {txt,md}   output format\n"
        subs, flags = dg.parse_help(text)
        self.assertNotIn("md", subs)
        self.assertNotIn("txt", subs)
        self.assertIn("--format", flags)

    def test_usage_option_choices_not_subcommands(self):
        text = "usage: plan.py {init,add,build,apply} ... --op {copy,move,delete} ...\n"
        subs, _ = dg.parse_help(text)
        self.assertIn("init", subs)
        self.assertIn("apply", subs)
        for value in ("copy", "move", "delete"):
            self.assertNotIn(value, subs)

    def test_unlabeled_tree_block_is_not_checked(self):
        p = self.doc("README.md", """```
scripts/novel.py            确定性工具（仅标准库）
└── references/             参考文档
```
""")
        code, out = self.check(p)
        self.assertEqual(code, 0, out)
        self.assertNotIn("UNKNOWN_SUBCOMMAND", out)
        self.assertIn("UNLABELED_BLOCK", out)

    def test_capture_writes_spec(self):
        spec = json.loads(self.spec_file.read_text(encoding="utf-8"))
        self.assertEqual(spec["tool"], "novel.py")
        self.assertIn("$P", spec["aliases"])
        self.assertIn("status", spec["subcommands"])

    def test_safe_help_command_guards(self):
        with self.assertRaises(ValueError):
            dg.safe_help_command("python cli.py --version")
        with self.assertRaises(ValueError):
            dg.safe_help_command("python cli.py --help && rm -rf /")
        self.assertEqual(dg.safe_help_command("python cli.py --help")[-1], "--help")

    def test_inspect(self):
        code, out = self.cli("inspect", "--spec", str(self.spec_file))
        self.assertEqual(code, 0)
        self.assertIn("novel.py", out)
        self.assertIn("子命令", out)

    def test_clean_doc_passes(self):
        p = self.doc("README.md", """# Demo

```bash
python -X utf8 scripts/novel.py init --root ./book
python -X utf8 $P status --root ./book --json
```
""")
        code, out = self.check(p)
        self.assertEqual(code, 0, out)
        self.assertIn("未发现漂移", out)

    def test_unknown_subcommand_is_error(self):
        p = self.doc("README.md", """```bash
python -X utf8 scripts/novel.py outline --volume 1
```
""")
        code, out = self.check(p)
        self.assertEqual(code, 1)
        self.assertIn("UNKNOWN_SUBCOMMAND", out)
        self.assertIn("outline", out)

    def test_unknown_flag_warn_and_strict(self):
        p = self.doc("README.md", """```bash
python -X utf8 scripts/novel.py status --root . --verbos
```
""")
        code, out = self.check(p)
        self.assertEqual(code, 0)
        self.assertIn("UNKNOWN_FLAG", out)
        code, out = self.check(p, "--strict")
        self.assertEqual(code, 1)

    def test_skips_non_target_and_complex_lines(self):
        p = self.doc("README.md", """```bash
git clone https://example.com/repo.git
echo "novel.py is not a command here"
python -X utf8 scripts/novel.py status --root . | head -5
python -X utf8 scripts/novel.py status --root .
```
""")
        code, out = self.check(p)
        self.assertEqual(code, 0, out)
        self.assertIn("跳过 3 条", out)

    def test_unlabeled_block_info(self):
        p = self.doc("README.md", """```
python -X utf8 scripts/novel.py status --root .
```
""")
        code, out = self.check(p)
        self.assertEqual(code, 0)
        self.assertIn("UNLABELED_BLOCK", out)

    def test_continuation_and_prompt(self):
        p = self.doc("README.md", """```bash
$ python -X utf8 scripts/novel.py init \\
    --root ./book \\
    --title X
```
""")
        code, out = self.check(p)
        self.assertEqual(code, 0, out)
        self.assertIn("检查 1 条命令", out)

    def test_json_output(self):
        p = self.doc("README.md", """```bash
python -X utf8 scripts/novel.py outline
```
""")
        code, out = self.check(p, "--json")
        self.assertEqual(code, 1)
        data = json.loads(out)
        self.assertEqual(data["findings"][0]["type"], "UNKNOWN_SUBCOMMAND")

    def test_report_file_written(self):
        p = self.doc("README.md", """```bash
python -X utf8 scripts/novel.py outline
```
""")
        report = self.root / "DOC_DRIFT.md"
        self.check(p, "--report", str(report))
        self.assertTrue(report.is_file())
        self.assertIn("UNKNOWN_SUBCOMMAND", report.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
