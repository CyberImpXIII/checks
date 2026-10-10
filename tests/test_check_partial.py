"""check-partial (PLAN-small-tasks.md §3.7), through the CLI, on THE shared
runner (checkslib/parts.py) rendered into a fixture repo: the real runner is
ok; each mutant of it alone turns exactly its own scenario red (killed,
changed, hung), so each scenario is shown able to fail by itself and each
property the runner claims is shown to change the result; a resume that runs
nothing is red too (the counterfactual of rerunning everything); a runner that
writes the repo's own progress file is named; and the UNCHECKED paths (no
dev.sh, no CHECK_PARTS, nested) and the not-executable fail."""
import importlib.util
import os

from tests.helpers import Case, TOOL_ROOT, write

_spec = importlib.util.spec_from_file_location("fx_partial", TOOL_ROOT / "source" / "fixtures" / "check-partial.py")
fx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fx)

FAST = {"CHECKS_CHECK_PARTIAL_RUN_TIMEOUT": "8"}

# Each mutant -> (the one scenario it turns red, a line it must print).
CASES = {
    "late": ("killed", "killed: a run killed while p2 hung left no progress file with `passed_steps`"
                       " at PROGRESS_FILE (passed by then: p1)"),
    "eager": ("killed", "killed: a run killed while p2 hung left `passed_steps` ['p1', 'p2', 'p3'],"
                        " but the parts that had passed were ['p1']"),
    "rerun": ("changed", "changed: after an edit to p3's file only, `--resume` ran p1, p2, p3 (wanted p3 alone)"),
    "skip": ("changed", "changed: after an edit to p3's file only, `--resume` ran no part (wanted p3 alone)"),
    "drop-skipped": ("changed", "changed: `--resume` reported 1 part(s), p1=None, p2=None (wanted all 3, each ok:"
                                " a skipped part passed, so N of M counts it)"),
    "no-limit": ("hung", "hung: one part past its timeout_s (2s) held the whole run: it did not finish in 8s"),
    "count": ("hung", "hung: the text run said `check: 3 of 3 passed; failed: p2 (timeout after 2s; no output)`"
                      " (wanted 2 of 3 passed)"),
    "unnamed": ("hung", "hung: the text run's failed list named nothing in"
                        " `check: 2 of 3 passed; failed: (timeout after 2s)` (wanted p2 alone)"),
}


class CheckPartial(Case):
    def one(self, r, env=None):
        return self.cli_json("one", "check-partial", r, env=dict(FAST, **(env or {})))[1]["results"][0]

    def scenarios(self, result):
        return sorted({line.split(":", 1)[0] for line in result["lines"]})

    def test_the_real_runner_is_ok(self):
        r = self.one(fx.repo(self.tmp))
        self.assertEqual(r["status"], "ok", r["lines"])
        self.assertEqual(r["lines"], ["killed, changed and hung: each shown on a three-part suite (with N of M, text and --json)"])

    def test_the_fixture_runs_the_real_runner_byte_for_byte(self):
        repo = fx.repo(self.tmp)
        self.assertEqual((repo / "parts.py").read_bytes(), (TOOL_ROOT / "checkslib" / "parts.py").read_bytes())

    def test_every_mutant_is_tested_and_aims_at_one_place(self):
        self.assertEqual(sorted([*CASES, "own-file"]), sorted(fx.MUTANTS))
        for name in fx.MUTANTS:
            with self.subTest(mutant=name):
                self.assertNotEqual(fx.mutate((name,)), fx.mutate())
        with self.assertRaises(ValueError):
            fx.MUTANTS["bogus"] = ("this text is in no runner", "")
            try:
                fx.mutate(("bogus",))
            finally:
                del fx.MUTANTS["bogus"]

    def test_each_mutant_alone_fails_its_own_scenario_alone(self):
        for i, (mutant, (scenario, line)) in enumerate(CASES.items()):
            with self.subTest(mutant=mutant):
                r = self.one(fx.repo(self.tmp / str(i), (mutant,)))
                self.assertEqual(r["status"], "fail", r["lines"])
                self.assertEqual(self.scenarios(r), [scenario], r["lines"])
                self.assertIn(line, r["lines"])

    def test_a_runner_writing_the_repos_own_progress_file_is_named(self):
        repo = fx.repo(self.tmp, ("own-file",))
        r = self.one(repo)
        self.assertEqual(r["status"], "fail")
        own = [x for x in r["lines"] if "the repo's own .progress/check.json" in x]
        self.assertEqual(len(own), 1, r["lines"])
        self.assertTrue((repo / ".progress" / "check.json").is_file())

    def test_a_repo_progress_file_from_another_run_is_not_a_finding(self):
        repo = fx.repo(self.tmp)
        write(repo / ".progress" / "check.json", '{"pid": 1, "state": "passed"}\n')
        self.assertEqual(self.one(repo)["status"], "ok")

    def test_unchecked_and_not_executable(self):
        bare = fx.repo(self.tmp / "bare")
        os.remove(bare / "dev.sh")
        self.assertEqual(self.one(bare)["status"], "unchecked")
        plain = fx.repo(self.tmp / "plain")
        write(plain / "dev.sh", "#!/usr/bin/env bash\necho no parts here\n", 0o755)
        r = self.one(plain)
        self.assertEqual((r["status"], "never mentions CHECK_PARTS" in r["lines"][0]), ("unchecked", True), r)
        nested = self.one(fx.repo(self.tmp / "nested"), env={"CHECKS_CHECK_PARTIAL_ACTIVE": "1"})
        self.assertEqual(nested["status"], "unchecked")
        noexec = fx.repo(self.tmp / "noexec")
        os.chmod(noexec / "dev.sh", 0o644)
        r = self.one(noexec)
        self.assertEqual((r["status"], r["lines"]), ("fail", ["dev.sh: not executable (it is run directly, as ./dev.sh)"]))
