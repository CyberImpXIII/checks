"""hooks-installed's reading of `hooks copies --json`, against a stand-in tool
spelled out by hand (the real tool is held to the same reading in
tests/test_contract.py).

The rule under test (decision 19, 2026-10-04): a missing or drifted copy is
covered when the user settings register that shared hook in place, as
`user_scope` reports it: a `kind: source` row whose `file` (or `test`) is the
copy, with `registered: true`. `false`, no row, or no user settings file:
not covered (red). `null`, or a `user_scope.error`: unknown, so UNCHECKED and
never ok. A not-executable copy is never covered. Each case below changes
only the user-scope input, so the input is shown to change the result; the
mutants at the bottom show each clause of the rule is load-bearing."""
import json
import os
import shutil

from tests.helpers import Case, TOOL_ROOT, repo, run_cli, write

HOOK = "#!/usr/bin/env bash\ncat >/dev/null 2>&1\nexit 0\n"
A, TA, B, LIB = ".claude/hooks/a.sh", ".claude/hooks/test-a.sh", ".claude/hooks/b.sh", ".claude/lib/w.sh"
CHECK = TOOL_ROOT / "source" / "hooks-installed.py"
CONTRACT = "did not keep the contract"


def row(file, registered, kind="source", test=None):
    r = {"file": file, "kind": kind, "event": "PreToolUse", "matcher": "Bash",
         "command": f"/src/{os.path.basename(file)}", "registered": registered}
    if kind == "source":
        r["test"] = test if test is not None else file.replace("/hooks/", "/hooks/test-")
    return r


def scope(rows, exists=True, error=None):
    return {"settings": "/home/u/.claude/settings.json", "exists": exists, "error": error, "source": "/src",
            "hooks": rows, "left_per_repo": [], "ok": None}


def report(files, user_scope):
    rep = {"root": "<ws>", "ok": False, "unresolved": [],
           "locations": [{"path": "r", "files": [{"file": f, "status": s} for f, s in files]}]}
    if user_scope is not None:
        rep["user_scope"] = user_scope
    return rep


DRIFT = [(A, "drift"), (TA, "missing")]


class HooksInstalled(Case):
    def ws_with(self, rep):
        ws = self.tmp / "ws"
        write(ws / "CLAUDE.md", "# top\n")
        body = rep if isinstance(rep, str) else json.dumps(rep)
        write(ws / "tools" / "hooks" / "hooks", f"#!/usr/bin/env bash\ncat <<'EOF'\n{body}\nEOF\n", 0o755)
        r = ws / "r"
        if not r.exists():
            repo(r)
        return ws, r

    def run_with(self, rep, source=None, env=None):
        ws, r = self.ws_with(rep)
        extra = ("--source", source) if source else ()
        return self.cli_json("one", "hooks-installed", r, "--root", ws, *extra, env=env)[1]["results"][0]

    # -- the rule: the same copies, only the user-scope input changes -------------

    def test_repo_copies_say_repo_copy(self):
        res = self.run_with(report([(A, "ok"), (TA, "ok")], scope([row(A, False)])))
        self.assertEqual(res["status"], "ok", res["lines"])
        self.assertEqual(res["lines"], [f"repo copy: {A}, {TA}"])

    def test_registered_true_covers_a_drifted_copy_and_its_test(self):
        res = self.run_with(report(DRIFT, scope([row(A, True)])))
        self.assertEqual(res["status"], "ok", res["lines"])
        self.assertEqual(res["lines"], [f"covered by user scope: {A}, {TA}"])

    def test_registered_false_is_not_covered(self):
        res = self.run_with(report(DRIFT, scope([row(A, False)])))
        self.assertEqual(res["status"], "fail")
        self.assertEqual(res["lines"], [f"{A}: drift; not covered by user scope (not registered there)",
                                        f"{TA}: missing; not covered by user scope (not registered there)"])

    def test_registered_null_is_unchecked_never_ok(self):
        res = self.run_with(report(DRIFT, scope([row(A, None)])))
        self.assertEqual(res["status"], "unchecked", res["lines"])
        self.assertEqual(len(res["lines"]), 1)
        self.assertIn(f"coverage unknown for {A}, {TA}", res["lines"][0])

    def test_unreadable_user_settings_are_unchecked(self):
        res = self.run_with(report(DRIFT, scope([row(A, None)], error="settings.json: does not parse")))
        self.assertEqual(res["status"], "unchecked", res["lines"])
        self.assertIn("settings.json: does not parse", res["lines"][0])

    def test_no_user_settings_file_is_not_covered_never_an_error(self):
        res = self.run_with(report(DRIFT, scope([row(A, False)], exists=False)))
        self.assertEqual(res["status"], "fail", res["lines"])
        self.assertIn(f"{A}: drift; not covered by user scope (no user settings file)", res["lines"])

    def test_no_user_scope_row_for_the_file_is_not_covered(self):
        res = self.run_with(report([(LIB, "missing")], scope([row(A, True)])))
        self.assertEqual(res["status"], "fail")
        self.assertEqual(res["lines"], [f"{LIB}: missing; not covered by user scope (no shared hook of that name there)"])

    def test_a_plugin_row_does_not_cover_a_copy(self):
        res = self.run_with(report([(B, "missing")], scope([row(B, True, kind="plugin")])))
        self.assertEqual(res["status"], "fail", res["lines"])

    def test_not_executable_is_never_covered(self):
        res = self.run_with(report([(A, "not-executable")], scope([row(A, True)])))
        self.assertEqual(res["status"], "fail")
        self.assertEqual(res["lines"], [f"{A}: not-executable"])

    def test_mixed_lists_only_what_is_not_covered(self):
        rep = report([(A, "drift"), (B, "missing"), (".claude/hooks/c.sh", "ok")],
                     scope([row(A, False), row(B, True)]))
        res = self.run_with(rep)
        self.assertEqual(res["status"], "fail")
        self.assertEqual(res["lines"], [f"{A}: drift; not covered by user scope (not registered there)"])
        rep["user_scope"]["hooks"][0]["registered"] = None       # unknown beside a covered one: unchecked
        res = self.run_with(rep)
        self.assertEqual(res["status"], "unchecked", res["lines"])
        rep["user_scope"]["hooks"][1]["registered"] = False      # unknown beside a fail: red, both said
        res = self.run_with(rep)
        self.assertEqual(res["status"], "fail", res["lines"])
        self.assertEqual(res["lines"], [f"{B}: missing; not covered by user scope (not registered there)",
                                        f"{A}: drift; coverage by user scope unknown (registered: null)"])
        rep["user_scope"]["hooks"][0]["registered"] = True
        rep["user_scope"]["hooks"][1]["registered"] = True
        res = self.run_with(rep)
        self.assertEqual(res["status"], "ok", res["lines"])
        self.assertEqual(res["lines"], [f"repo copy: .claude/hooks/c.sh", f"covered by user scope: {A}, {B}"])

    def test_text_output_names_the_scope_on_ok(self):
        ws, r = self.ws_with(report(DRIFT, scope([row(A, True)])))
        p = run_cli("one", "hooks-installed", r, "--root", ws)
        self.assertEqual(p.returncode, 0, p.stdout)
        self.assertIn(f"covered by user scope: {A}, {TA}", p.stdout)

    # -- the shape: anything else is an error, never a guess ----------------------

    def test_a_report_not_in_the_stated_shape_is_an_error(self):
        bad = {
            "no user_scope": report(DRIFT, None),
            "user_scope not an object": report(DRIFT, ["x"]),
            "no exists": {**report(DRIFT, scope([row(A, True)])), "user_scope": {
                k: v for k, v in scope([row(A, True)]).items() if k != "exists"}},
            "hooks not a list": report(DRIFT, {**scope([]), "hooks": {}}),
            "registered a string": report(DRIFT, scope([row(A, "yes")])),
            "registered 1": report(DRIFT, scope([row(A, 1)])),
            "row without kind": report(DRIFT, scope([{k: v for k, v in row(A, True).items() if k != "kind"}])),
        }
        for what, rep in bad.items():
            with self.subTest(case=what):
                res = self.run_with(rep)
                self.assertEqual(res["status"], "error", res["lines"])
                self.assertIn(CONTRACT, "\n".join(res["lines"]))

    def test_a_clean_repo_with_a_broken_user_scope_is_still_an_error(self):
        res = self.run_with(report([(A, "ok")], None))
        self.assertEqual(res["status"], "error", res["lines"])

    # -- standalone: no hooks tool beside, so no source and no user scope ---------

    def test_standalone_present_executable_parses(self):
        r = repo(self.tmp / "lone")
        write(r / ".claude" / "hooks" / "a.sh", HOOK, 0o755)
        self.assertEqual(self.cli_json("one", "hooks-installed", r, "--root", self.tmp / "nows")[1]
                         ["results"][0]["status"], "ok")
        os.chmod(r / ".claude" / "hooks" / "a.sh", 0o644)
        res = self.cli_json("one", "hooks-installed", r, "--root", self.tmp / "nows")[1]["results"][0]
        self.assertEqual((res["status"], res["lines"]), ("fail", [".claude/hooks/a.sh: not executable"]))

    # -- mutants: each clause of the rule, broken, turns some case's result -------

    def test_each_mutant_is_killed(self):
        """A copy of the check with one clause broken must give a different
        result on the named case; a mutation that no longer applies to the
        source is itself a failure (the mutant went stale, not the rule)."""
        mutants = {
            "null counted as covered": ("registered is True", "registered is not False",
                                        report(DRIFT, scope([row(A, None)])), "unchecked"),
            "absent settings ignored": ('if not us["exists"]:', "if False:",
                                        report(DRIFT, scope([row(A, True)], exists=False)), "fail"),
            "settings error ignored": ('if us["error"] is not None:', "if False:",
                                       report(DRIFT, scope([row(A, True)], error="unreadable")), "unchecked"),
            "test file not matched": ('(h["file"], h.get("test"))', '(h["file"],)',
                                      report([(TA, "missing")], scope([row(A, True)])), "ok"),
            "plugin rows cover": ('h["kind"] == "source"', 'True',
                                  report([(B, "missing")], scope([row(B, True, kind="plugin")])), "fail"),
        }
        text = CHECK.read_text()
        for what, (old, new, rep, real) in mutants.items():
            with self.subTest(mutant=what):
                self.assertEqual(text.count(old), 1, f"mutation site {old!r} not found once: the mutant is stale")
                src = self.tmp / f"src-{what.replace(' ', '-')}"
                write(src / "hooks-installed.py", text.replace(old, new), 0o755)
                shutil.copy(TOOL_ROOT / "source" / "fixtures" / "hooks-installed.py",
                            write(src / "fixtures" / "hooks-installed.py", ""))
                self.assertEqual(self.run_with(rep)["status"], real, "the unmutated check, on this case")
                env = {"PYTHONPATH": str(TOOL_ROOT)}
                got = self.run_with(rep, source=src, env=env)
                self.assertNotIn(got["status"], (real, "error"), f"mutant survived: {got}")
