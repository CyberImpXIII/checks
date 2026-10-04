"""The repo's documented lists held equal to what is implemented, both ways:
the CLI's help and its commands, dev.sh's help and its case, vocab.json and
the code that reads it, each check's declared params and the params it reads,
the CLAUDE.md check table and `checks list`. And the roster audit shown to go
red on a planted read."""
import json
import re
import shutil
import unittest

from tests.helpers import Case, TOOL_ROOT, run_cli, write
from checkslib import api, cli, decl, runner

SOURCE = TOOL_ROOT / "source"
PARAM_READ = re.compile(r"""\.param\(\s*["'](\w+)["']""")


def table_rows(md, header_first_cell):
    lines = md.splitlines()
    for i, line in enumerate(lines):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.startswith("|") and cells[0] == header_first_cell:
            out = []
            for row in lines[i + 2:]:
                if not row.startswith("|"):
                    break
                out.append([c.strip() for c in row.strip().strip("|").split("|")])
            return out
    raise AssertionError(f"no table headed {header_first_cell!r}")


class Meta(unittest.TestCase):
    def test_cli_usage_equals_commands(self):
        documented = set(re.findall(r"^  checks (\w+)", cli.USAGE, re.M))
        self.assertEqual(documented, set(cli.COMMANDS))

    def test_dev_sh_usage_equals_its_case(self):
        text = (TOOL_ROOT / "dev.sh").read_text()
        usage = text.split("cat <<'EOF'", 1)[1].split("\nEOF", 1)[0]
        documented = set(re.findall(r"^  ([a-z][\w-]*)\s", usage, re.M))
        case = text.rsplit('case "${1:-}" in', 1)[1].split("\nesac", 1)[0]
        implemented = set(re.findall(r"^  ([a-z][\w-]*)\)", case, re.M))
        self.assertEqual(documented, implemented)
        self.assertTrue({"check", "test", "fixtures", "run", "audit"} <= implemented)

    def test_dev_sh_check_runs_every_step_it_documents(self):
        text = (TOOL_ROOT / "dev.sh").read_text()
        steps = set(re.search(r"for step in ([\w ]+); do", text).group(1).split())
        usage = text.split("cat <<'EOF'", 1)[1].split("\nEOF", 1)[0]
        documented = set(re.findall(r"^  ([a-z][\w-]*)\s", usage, re.M)) - {"check"}
        self.assertEqual(steps, documented)

    def test_vocab_keys_consumed_both_ways(self):
        code = (TOOL_ROOT / "checkslib" / "decl.py").read_text()
        read = set(re.findall(r"""\bd\[["'](\w+)["']\]""", code))
        self.assertEqual(read, set(decl.KEYS))

    def test_vocab_results_consumed_both_ways(self):
        statuses = {spec["status"] for spec in api.RESULTS.values()}
        self.assertEqual(set(runner.STATUS.values()), statuses)
        self.assertEqual(set(api.CODE), statuses)
        self.assertEqual(set(cli.MARK), statuses | {"error"})
        self.assertTrue(runner.RED <= statuses | {"error"})
        self.assertNotIn("unchecked", runner.RED)
        self.assertNotIn("ok", runner.RED)

    def test_each_check_reads_exactly_the_params_it_declares(self):
        entries, refused, faults = decl.load(SOURCE)
        self.assertEqual((refused, faults), ({}, []))
        for e in entries:
            with self.subTest(check=e.name):
                read = set(PARAM_READ.findall(e.path.read_text()))
                self.assertEqual(read, set(e.params))
                self.assertNotIn("_params", e.path.read_text())   # no way round ctx.param

    def test_claude_md_check_table_equals_checks_list(self):
        rows = table_rows((TOOL_ROOT / "CLAUDE.md").read_text(), "check")
        documented = {r[0].strip("`"): r[1].strip("`") for r in rows}
        p = run_cli("list", "--json")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        listed = {c["name"]: c["applies_to"] for c in json.loads(p.stdout)["checks"]}
        self.assertEqual(documented, listed)

    def test_every_documented_check_explains_itself(self):
        for e in decl.load(SOURCE)[0]:
            with self.subTest(check=e.name):
                p = run_cli("explain", e.name)
                self.assertEqual(p.returncode, 0)
                self.assertIn("Proves:", p.stdout)
                self.assertIn("To pass:", p.stdout)


class RosterAudit(Case):
    """`./dev.sh audit` (no-roster on this tool) goes red on a planted roster read,
    and is not red on an unplanted copy (the counterfactual)."""

    def copy_tool(self):
        dst = self.tmp / "tools" / "checks"
        shutil.copytree(TOOL_ROOT, dst, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        return dst

    def audit(self, copy, *names):
        args = ["one", "no-roster", copy] + (["--names", ",".join(names)] if names else [])
        return self.cli_json(*args)[1]["results"][0]

    def test_unplanted_copy_is_not_red(self):
        copy = self.copy_tool()
        self.assertEqual(self.audit(copy)["status"], "unchecked")
        self.assertEqual(self.audit(copy, "harness")["status"], "ok")

    def test_planted_path_read_is_red(self):
        copy = self.copy_tool()
        write(copy / "checkslib" / "sneak.py", "ROSTER = '../../.claude/" + "agents.manifest.json'\n")
        res = self.audit(copy)
        self.assertEqual(res["status"], "fail")
        self.assertIn("checkslib/sneak.py:1", res["lines"][0])

    def test_planted_name_is_red_only_when_names_are_passed(self):
        copy = self.copy_tool()
        write(copy / "checkslib" / "sneak.py", "WHO = 'har" + "ness'\n")
        self.assertEqual(self.audit(copy)["status"], "unchecked")
        res = self.audit(copy, "harness")
        self.assertEqual(res["status"], "fail")
        self.assertIn("names roster agent `harness`", res["lines"][0])


if __name__ == "__main__":
    unittest.main()
