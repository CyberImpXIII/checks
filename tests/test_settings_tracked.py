"""settings-tracked (PLAN-repo-setup.md §7.9): each of its two findings shown
alone (untracked but not ignored; tracked but ignored), a staged file counts as
tracked, a negated ignore rule is not an ignore, no settings.json passes, and
outside git it is UNCHECKED. It runs in a pre-commit `checks run` (applies_to=all)."""
from tests.helpers import Case, git, repo, write

REL = ".claude/settings.json"
SETTINGS = '{"hooks": {}}\n'


class SettingsTracked(Case):
    def result(self, path):
        return self.cli_json("one", "settings-tracked", path)[1]["results"][0]

    def test_untracked_and_not_ignored_is_one_finding(self):
        r = repo(self.tmp / "r")
        write(r / REL, SETTINGS)
        res = self.result(r)
        self.assertEqual(res["status"], "fail")
        self.assertEqual(res["lines"], [f"{REL}: exists but git does not track it (git add it, unchanged)"])

    def test_tracked_but_ignored_is_one_finding(self):
        r = repo(self.tmp / "r", {REL: SETTINGS})
        write(r / ".gitignore", "settings.json\n")
        res = self.result(r)
        self.assertEqual(res["status"], "fail")
        self.assertEqual(res["lines"], [f"{REL}: git-ignored by .gitignore:1:settings.json"])

    def test_ignored_by_info_exclude_is_named(self):
        r = repo(self.tmp / "r", {REL: SETTINGS})
        write(r / ".git" / "info" / "exclude", "# local\n.claude\n")
        res = self.result(r)
        self.assertEqual(res["status"], "fail")
        self.assertEqual(len(res["lines"]), 1)
        self.assertIn("git-ignored by .git/info/exclude:2:.claude", res["lines"][0])

    def test_staged_counts_as_tracked(self):
        r = repo(self.tmp / "r")
        write(r / REL, SETTINGS)
        git(r, "add", REL)
        self.assertEqual(self.result(r)["status"], "ok")

    def test_negated_ignore_is_not_an_ignore(self):
        r = repo(self.tmp / "r", {REL: SETTINGS, ".gitignore": ".claude/*\n!.claude/settings.json\n"})
        self.assertEqual(self.result(r)["status"], "ok")
        # the counterfactual: without the negation the same repo is red
        write(r / ".gitignore", ".claude/*\n")
        self.assertEqual(self.result(r)["status"], "fail")

    def test_no_settings_json_passes(self):
        r = repo(self.tmp / "r", {".claude/settings.local.json": SETTINGS})
        self.assertEqual(self.result(r)["status"], "ok")

    def test_outside_git_is_unchecked(self):
        write(self.tmp / "plain" / REL, SETTINGS)
        res = self.result(self.tmp / "plain")
        self.assertEqual(res["status"], "unchecked")
        self.assertIn("not a git repo", res["lines"][0])

    def test_runs_in_a_pre_commit_run(self):
        r = repo(self.tmp / "r")
        write(r / REL, SETTINGS)
        res = {x["check"]: x for x in self.cli_json("run", r)[1]["results"]}
        self.assertEqual(res["settings-tracked"]["status"], "fail")
