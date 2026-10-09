"""check-partial (PLAN-small-tasks.md §3.7), through the CLI on the fixture's
hand-written parts runner: the working runner is ok; each fault alone turns
exactly its own scenario red (killed, changed, hung), so each scenario is
shown able to fail by itself; a resume that runs nothing is red too (the
counterfactual of rerunning everything); a runner that writes the repo's own
progress file is named; and the UNCHECKED paths (no dev.sh, no CHECK_PARTS,
nested) and the not-executable fail."""
import importlib.util
import os

from tests.helpers import Case, TOOL_ROOT, write

_spec = importlib.util.spec_from_file_location("fx_partial", TOOL_ROOT / "source" / "fixtures" / "check-partial.py")
fx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fx)

FAST = {"CHECKS_CHECK_PARTIAL_RUN_TIMEOUT": "8"}


class CheckPartial(Case):
    def one(self, r, env=None):
        return self.cli_json("one", "check-partial", r, env=dict(FAST, **(env or {})))[1]["results"][0]

    def scenarios(self, result):
        return sorted({line.split(":", 1)[0] for line in result["lines"]})

    def test_a_working_runner_is_ok(self):
        r = self.one(fx.repo(self.tmp))
        self.assertEqual(r["status"], "ok", r["lines"])
        self.assertEqual(r["lines"], ["killed, changed and hung: each shown on a three-part suite"])

    def test_each_fault_alone_fails_its_own_scenario_alone(self):
        cases = {
            "late": ("killed", "killed: a run killed while p2 hung left no progress file with `passed_steps`"
                               " at PROGRESS_FILE (passed by then: p1)"),
            "rerun": ("changed", "changed: after an edit to p3's file only, `--resume` ran p1, p2, p3 (wanted p3 alone)"),
            "no-limit": ("hung", "hung: one part past its timeout_s (2s) held the whole run: it did not finish in 8s"),
            "eager": ("killed", "killed: a run killed while p2 hung left `passed_steps` ['p1', 'p2', 'p3'],"
                                " but the parts that had passed were ['p1']"),
            "skip": ("changed", "changed: after an edit to p3's file only, `--resume` ran no part (wanted p3 alone)"),
        }
        for i, (fault, (scenario, line)) in enumerate(cases.items()):
            with self.subTest(fault=fault):
                r = self.one(fx.repo(self.tmp / str(i), (fault,)))
                self.assertEqual(r["status"], "fail")
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
