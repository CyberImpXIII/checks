"""todo-valid's reading of `todo check`, against stand-in tools spelled out by
hand: each way the output can break its contract is red (error), never ok;
FAIL lines become findings, WARN and INFO lines do not. The real tool is held
to the same reading in tests/test_contract.py."""
from tests.helpers import Case, repo, write

OK_ROWS = "  ok    schema\n  ok    render\n  ok    history\n"


def fake(body):
    return f"#!/usr/bin/env bash\ncat <<'OUT'\n{body}OUT\n"


class TodoValid(Case):
    def run_with(self, out, code=0):
        ws = self.tmp / "ws"
        write(ws / "CLAUDE.md", "# top\n")
        write(ws / "tools" / "todo" / "todo", fake(out) + f"exit {code}\n", 0o755)
        r = repo(ws / "r", {"TODO.md": "# r TODO\n", "todo.json": "{}\n"})
        return self.cli_json("one", "todo-valid", r, "--root", ws)[1]["results"][0]

    def test_clean_check_is_ok_and_warn_is_not_a_finding(self):
        res = self.run_with("  WARN  reports   tx-1     unpaired\n" + OK_ROWS +
                            "todo check r: 1 open, 0 closed; 0 failed, 1 warning(s)\n")
        self.assertEqual(res["status"], "ok", res["lines"])

    def test_fail_lines_are_findings(self):
        res = self.run_with("  ok    schema\n  FAIL  render    -        TODO.md is not the render\n  ok    history\n"
                            "todo check r: 1 open, 0 closed; 1 failed, 0 warning(s)\n", 1)
        self.assertEqual(res["status"], "fail")
        self.assertEqual(res["lines"], ["todo check: render -: TODO.md is not the render"])

    def test_broken_contracts_are_errors(self):
        cases = {
            "no summary": (OK_ROWS, 0),
            "count disagrees": (OK_ROWS + "todo check r: 1 open, 0 closed; 2 failed, 0 warning(s)\n", 1),
            "exit disagrees": (OK_ROWS + "todo check r: 1 open, 0 closed; 0 failed, 0 warning(s)\n", 1),
            "render silent": ("  ok    schema\ntodo check r: 1 open, 0 closed; 0 failed, 0 warning(s)\n", 0),
        }
        for what, (out, code) in cases.items():
            with self.subTest(case=what):
                res = self.run_with(out, code)
                self.assertEqual(res["status"], "error", res["lines"])
                self.assertIn("did not keep the contract", "\n".join(res["lines"]))

    def test_no_tool_is_unchecked(self):
        ws = self.tmp / "ws"
        write(ws / "CLAUDE.md", "# top\n")
        r = repo(ws / "r", {"TODO.md": "# r TODO\n", "todo.json": "{}\n"})
        res = self.cli_json("one", "todo-valid", r, "--root", ws)[1]["results"][0]
        self.assertEqual(res["status"], "unchecked")
