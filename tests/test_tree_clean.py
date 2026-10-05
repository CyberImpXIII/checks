"""tree-clean runs only under `--roles audit` (never in a pre-commit `checks
run`), names a renamed file once, and is UNCHECKED outside a git repo."""
from tests.helpers import Case, git, repo, write


class TreeClean(Case):
    def checks(self, rep):
        return {r["check"]: r for r in rep["results"]}

    def test_runs_only_when_the_audit_role_is_passed(self):
        r = repo(self.tmp / "r")
        write(r / "dirty.txt", "x\n")
        self.assertNotIn("tree-clean", self.checks(self.cli_json("run", r)[1]))
        res = self.checks(self.cli_json("run", r, "--roles", "audit")[1])["tree-clean"]
        self.assertEqual(res["status"], "fail")
        self.assertEqual(res["lines"], ["uncommitted (??): dirty.txt"])

    def test_a_rename_is_one_finding(self):
        r = repo(self.tmp / "r", {"a.txt": "a\n"})
        git(r, "mv", "a.txt", "b.txt")
        res = self.cli_json("one", "tree-clean", r)[1]["results"][0]
        self.assertEqual(res["lines"], ["uncommitted (R): b.txt"])

    def test_outside_git_is_unchecked(self):
        (self.tmp / "plain").mkdir()
        res = self.cli_json("one", "tree-clean", self.tmp / "plain")[1]["results"][0]
        self.assertEqual(res["status"], "unchecked")
