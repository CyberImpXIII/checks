"""no-secrets reads what a commit would carry both ways: the working tree and
the staged copy of every path whose index entry differs from it
(PLAN-hard-gates.md §3 row 6). The staged state alone changes the result (the
gate-off probe), a staged deletion is still scanned, `allow` exempts a staged
copy too, and `checks one no-secrets PATH --json` keeps the one-result shape
setup's pre-commit reads (`.results[0].check == "no-secrets"`, `.status`)."""
import unittest

from tests.helpers import Case, git, repo, write

FAKE = "gh" + "p_" + "A1b2" * 9          # a GitHub token SHAPE, never a value
IGNORE = ".env\n"


class NoSecretsStaged(Case):
    def make(self):
        r = repo(self.tmp / "r", {".gitignore": IGNORE, "cfg.py": "TOKEN = None\n"})
        return r

    def result(self, r):
        code, doc = self.cli_json("one", "no-secrets", r)
        self.assertEqual(len(doc["results"]), 1, doc)
        res = doc["results"][0]
        self.assertEqual(res["check"], "no-secrets")
        return res

    def test_staged_only_secret_fails_and_unstaging_clears_it(self):
        r = self.make()
        self.assertEqual(self.result(r)["status"], "ok")
        write(r / "cfg.py", f"TOKEN = '{FAKE}'\n")
        git(r, "add", "cfg.py")
        write(r / "cfg.py", "TOKEN = None\n")              # working tree clean, index not
        res = self.result(r)
        self.assertEqual(res["status"], "fail", res)
        self.assertEqual(res["lines"], ["cfg.py:1: holds a GitHub token shape in the staged copy (value not shown)"])
        git(r, "reset", "-q", "cfg.py")                     # same working tree, nothing staged
        self.assertEqual(self.result(r)["status"], "ok")

    def test_staged_then_deleted_is_scanned(self):
        r = self.make()
        write(r / "new.py", f"K = '{FAKE}'\n")
        git(r, "add", "new.py")
        (r / "new.py").unlink()
        res = self.result(r)
        self.assertEqual(res["lines"], ["new.py:1: holds a GitHub token shape in the staged copy (value not shown)"])

    def test_working_tree_only_secret_still_fails(self):
        # the union, on purpose: commit -a or the next commit would carry it
        r = self.make()
        write(r / "cfg.py", f"TOKEN = '{FAKE}'\n")
        res = self.result(r)
        self.assertEqual(res["lines"], ["cfg.py:1: holds a GitHub token shape (value not shown)"])

    def test_same_secret_staged_and_in_tree_is_named_once_per_copy(self):
        r = self.make()
        write(r / "cfg.py", f"TOKEN = '{FAKE}'\n")
        git(r, "add", "cfg.py")
        res = self.result(r)                                # index == tree: one copy, one finding
        self.assertEqual(res["lines"], ["cfg.py:1: holds a GitHub token shape (value not shown)"])

    def test_allow_exempts_the_staged_copy(self):
        r = self.make()
        write(r / "checks.json", '{"no-secrets": {"allow": ["fixtures/*"]}}\n')
        write(r / "fixtures" / "f.txt", f"t = {FAKE}\n")
        git(r, "add", "fixtures/f.txt")
        write(r / "fixtures" / "f.txt", "t = none\n")
        self.assertEqual(self.result(r)["status"], "ok")


if __name__ == "__main__":
    unittest.main()
