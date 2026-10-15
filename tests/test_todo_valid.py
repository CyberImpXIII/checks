"""todo-valid's and todo-store's reading of `todo check` (one reading,
checkslib/todocheck.py), against stand-in tools spelled out by hand: each way
the output can break its contract is red (error) in BOTH checks, never ok;
FAIL lines become findings, WARN and INFO lines do not. todo-store's own
half: a repo with no todo.json is a `lag:` finding, and it runs only when
lags are asked for. The real tool is held to the same reading in
tests/test_contract.py."""
from tests.helpers import Case, repo, write

OK_ROWS = "  ok    schema\n  ok    render\n  ok    history\n"
CLEAN = OK_ROWS + "todo check r: 1 open, 0 closed; 0 failed, 0 warning(s)\n"
CHECKS = ("todo-valid", "todo-store")


def fake(body):
    return f"#!/usr/bin/env bash\ncat <<'OUT'\n{body}OUT\n"


class TodoValid(Case):
    def run_with(self, out, code=0, check="todo-valid"):
        ws = self.tmp / "ws"
        write(ws / "CLAUDE.md", "# top\n")
        write(ws / "tools" / "todo" / "todo", fake(out) + f"exit {code}\n", 0o755)
        r = ws / "r"
        if not r.exists():
            repo(r, {"TODO.md": "# r TODO\n", "todo.json": "{}\n"})
        return self.cli_json("one", check, r, "--root", ws)[1]["results"][0]

    def test_clean_check_is_ok_and_warn_is_not_a_finding(self):
        for check in CHECKS:
            with self.subTest(check=check):
                res = self.run_with("  WARN  reports   tx-1     unpaired\n" + OK_ROWS +
                                    "todo check r: 1 open, 0 closed; 0 failed, 1 warning(s)\n", check=check)
                self.assertEqual(res["status"], "ok", res["lines"])

    def test_fail_lines_are_findings(self):
        out = ("  ok    schema\n  FAIL  render    -        TODO.md is not the render\n  ok    history\n"
               "todo check r: 1 open, 0 closed; 1 failed, 0 warning(s)\n")
        for check, prefix in (("todo-valid", ""), ("todo-store", "lag: ")):
            with self.subTest(check=check):
                res = self.run_with(out, 1, check=check)
                self.assertEqual(res["status"], "fail")
                self.assertEqual(res["lines"], [prefix + "todo check: render -: TODO.md is not the render"])

    def test_broken_contracts_are_errors(self):
        cases = {
            "no summary": (OK_ROWS, 0),
            "count disagrees": (OK_ROWS + "todo check r: 1 open, 0 closed; 2 failed, 0 warning(s)\n", 1),
            "exit disagrees": (OK_ROWS + "todo check r: 1 open, 0 closed; 0 failed, 0 warning(s)\n", 1),
            "render silent": ("  ok    schema\ntodo check r: 1 open, 0 closed; 0 failed, 0 warning(s)\n", 0),
        }
        for check in CHECKS:
            for what, (out, code) in cases.items():
                with self.subTest(check=check, case=what):
                    res = self.run_with(out, code, check=check)
                    self.assertEqual(res["status"], "error", res["lines"])
                    self.assertIn("did not keep the contract", "\n".join(res["lines"]))

    def test_no_tool_is_unchecked(self):
        ws = self.tmp / "ws"
        write(ws / "CLAUDE.md", "# top\n")
        r = repo(ws / "r", {"TODO.md": "# r TODO\n", "todo.json": "{}\n"})
        for check in CHECKS:
            with self.subTest(check=check):
                res = self.cli_json("one", check, r, "--root", ws)[1]["results"][0]
                self.assertEqual(res["status"], "unchecked", res["lines"])
                self.assertIn("no tools/todo", res["lines"][0])


class TodoStore(Case):
    LAG = ("lag: no todo.json: this repo's work is invisible to `todo ready` and `todo dispatchable` "
           "(PLAN-architecture.md §11 S1)")

    def test_no_store_is_a_lag_and_a_store_is_its_counterfactual(self):
        ws = self.tmp / "ws"
        write(ws / "CLAUDE.md", "# top\n")
        write(ws / "tools" / "todo" / "todo", fake(CLEAN), 0o755)
        r = repo(ws / "r", {"TODO.md": "# r TODO\n\n## Own bugs\n\n- a bug\n"})
        one = lambda c: self.cli_json("one", c, r, "--root", ws)[1]["results"][0]  # noqa: E731
        res = one("todo-store")
        self.assertEqual((res["status"], res["lines"]), ("fail", [self.LAG]))
        self.assertEqual(one("todo-valid")["status"], "ok", "no store is a lag, never a pre-commit fault")
        write(r / "todo.json", "{}\n")
        res = one("todo-store")
        self.assertEqual((res["status"], res["lines"]),
                         ("ok", ["todo check r: 1 open, 0 closed; 0 failed, 0 warning(s)"]))

    def test_no_store_and_no_tool_is_still_the_lag(self):
        """The tool is needed only to judge a store; a missing store is the
        finding whatever is beside the top."""
        r = repo(self.tmp / "r")
        res = self.cli_json("one", "todo-store", r)[1]["results"][0]
        self.assertEqual((res["status"], res["lines"]), ("fail", [self.LAG]))

    def test_it_runs_only_when_lags_are_asked_for(self):
        r = repo(self.tmp / "r")
        names = lambda *a: {x["check"] for x in self.cli_json("run", r, *a)[1]["results"]}  # noqa: E731
        self.assertNotIn("todo-store", names())
        self.assertIn("todo-store", names("--roles", "lag"))
