"""The seams with tools/hooks, held by running the real tool (never a copy of
its rules): `checks all` walks the same repos `hooks copies` compares, and
hooks-installed reads `hooks copies --json` the way that tool means it.
Skipped, said out loud, when tools/hooks is not beside this tool."""
import json
import os
import subprocess
import unittest

from tests.helpers import Case, WORKSPACE, repo, write
from checkslib import runner

HOOKS = WORKSPACE / "tools" / "hooks" / "hooks" if WORKSPACE else None
HAVE_HOOKS = bool(HOOKS and os.access(HOOKS, os.X_OK))
WHY = "tools/hooks is not beside this tool: the contract with it went unchecked"


def copies(root):
    p = subprocess.run([str(HOOKS), "copies", str(root), "--json"], capture_output=True, text=True,
                       stdin=subprocess.DEVNULL, timeout=240)
    return p.returncode, json.loads(p.stdout)


@unittest.skipUnless(HAVE_HOOKS, WHY)
class WithHooks(Case):
    def fixture_ws(self):
        ws = self.tmp / "ws"
        write(ws / "CLAUDE.md", "# top\n")
        for r in ("a", "tools/b", "deep/er/c", "x/y/z/w"):
            repo(ws / r)
        repo(ws / "too" / "deep" / "for" / "the" / "walk")      # depth 5: neither walks it
        repo(ws / "nomd", claude_md=False)                       # a repo without CLAUDE.md
        repo(ws / ".dot")                                        # pruned by both
        repo(ws / "node_modules" / "pkg")                        # pruned by both
        return ws

    def test_discover_equals_hooks_copies_locations(self):
        ws = self.fixture_ws()
        # A plain folder (no git, no CLAUDE.md) holding a stray hook copy: hooks
        # lists it, to compare the copy; checks all does not run gates on it,
        # because it is not a repo. The one known difference, held here.
        write(ws / "plain" / ".claude" / "hooks" / "prefer-recipes.sh", "#!/usr/bin/env bash\n", 0o755)
        _, rep = copies(ws)
        # hooks also lists a `repos:` destination that is absent (to report it missing);
        # only folders that exist are walked locations.
        theirs = sorted(l["path"] for l in rep["locations"] if (ws / l["path"]).is_dir())
        ours = sorted(runner.rel(p, ws) for p in runner.discover(ws))
        self.assertIn("plain", theirs)
        self.assertNotIn("plain", ours)
        self.assertEqual(ours, [p for p in theirs if p != "plain"])
        self.assertIn("x/y/z/w", ours)
        self.assertNotIn("too/deep/for/the/walk", ours)

    def shim(self, ws, settings):
        """ws/tools/hooks/hooks: the real tool, told which user settings to read,
        so this test never depends on (or reads) the real ~/.claude/settings.json."""
        write(ws / "tools" / "hooks" / "hooks", f'#!/usr/bin/env bash\nexec "{HOOKS}" "$@" --settings "{settings}"\n',
              0o755)

    def test_hooks_installed_red_exactly_when_hooks_copies_says_so(self):
        ws = self.fixture_ws()
        self.shim(ws, self.tmp / "user" / "settings.json")             # no user settings file
        p = subprocess.run([str(ws / "tools" / "hooks" / "hooks"), "copies", str(ws), "--json"], capture_output=True,
                           text=True, stdin=subprocess.DEVNULL, timeout=240)
        rep = json.loads(p.stdout)
        self.assertEqual(p.returncode, 1, "fixture repos hold no copies: hooks copies must say missing")
        statuses = {f["status"] for l in rep["locations"] for f in l["files"]}
        self.assertTrue(statuses <= {"ok", "missing", "drift", "not-executable", "extra"}, statuses)
        self.assertIs(rep["user_scope"]["exists"], False)
        res = self.cli_json("one", "hooks-installed", ws / "a", "--root", ws)[1]["results"][0]
        self.assertEqual(res["status"], "fail")
        self.assertTrue(all(l.endswith(": missing; not covered by user scope (no user settings file)")
                            for l in res["lines"]), res["lines"])

    def test_hooks_installed_follows_the_real_user_scope_report(self):
        """The same missing copies, three user settings: the real `hooks userscope`
        proposal (registered: covered, ok), unparseable (unknown: unchecked), and
        one registering none of them (not covered: fail). The input changes the result."""
        ws = self.fixture_ws()
        user = self.tmp / "user"
        proposed = user / "settings.proposed.json"
        p = subprocess.run([str(HOOKS), "userscope", "--settings", str(user / "settings.json"), "--out", str(proposed)],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=120)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.shim(ws, proposed)
        p = subprocess.run([str(ws / "tools" / "hooks" / "hooks"), "copies", str(ws), "--json"], capture_output=True,
                           text=True, stdin=subprocess.DEVNULL, timeout=240)
        files = [f["file"] for l in json.loads(p.stdout)["locations"] if l["path"] == "a" for f in l["files"]]
        self.assertTrue(files, "hooks copies expects hooks in a fixture repo")
        cases = {"registered": (proposed, "ok"),
                 "unparseable": (write(user / "bad.json", "{not json"), "unchecked"),
                 "registers none": (write(user / "none.json", '{"hooks": {}}\n'), "fail")}
        for what, (settings, want) in cases.items():
            with self.subTest(settings=what):
                self.shim(ws, settings)
                res = self.cli_json("one", "hooks-installed", ws / "a", "--root", ws)[1]["results"][0]
                self.assertEqual(res["status"], want, res["lines"])
                if want == "ok":
                    self.assertEqual(res["lines"], ["covered by user scope: " + ", ".join(files)])

    @unittest.skipUnless(WORKSPACE and (WORKSPACE / "tools" / "checks").is_dir(), WHY)
    def test_real_workspace_agrees_for_this_repo(self):
        code, rep = copies(WORKSPACE)
        mine = [l for l in rep["locations"] if l["path"] == "tools/checks"]
        self.assertEqual(len(mine), 1)
        bad = [f for f in mine[0]["files"] if f["status"] in ("missing", "drift", "not-executable")]
        res = self.cli_json("one", "hooks-installed", WORKSPACE / "tools" / "checks")[1]["results"][0]
        if bad:     # covered or not is the rule, held above against fixed settings; here: never an error
            self.assertIn(res["status"], ("fail", "unchecked", "ok"), res["lines"])
        else:
            self.assertEqual(res["status"], "ok", res["lines"])
            self.assertEqual(res["lines"], ["repo copy: " + ", ".join(f["file"] for f in mine[0]["files"])])


TODO = WORKSPACE / "tools" / "todo" / "todo" if WORKSPACE else None
HAVE_TODO = bool(TODO and os.access(TODO, os.X_OK))


@unittest.skipUnless(HAVE_TODO, "tools/todo is not beside this tool: todo-valid's contract with it went unchecked")
class WithTodo(Case):
    """todo-valid reads the real `todo check` as it means it: ok on a fresh
    store, red on a hand edit of TODO.md (the render gate), never ok then."""

    def test_todo_valid_follows_the_real_todo_check(self):
        ws = self.tmp / "ws"
        write(ws / "CLAUDE.md", "# top\n")
        os.makedirs(ws / "tools", exist_ok=True)
        os.symlink(TODO.parent, ws / "tools" / "todo")
        r = repo(ws / "r")
        todo = lambda *a: subprocess.run([str(TODO), "-C", str(r), "--root", str(ws), *a], capture_output=True,
                                         text=True, stdin=subprocess.DEVNULL, timeout=120)
        self.assertEqual(todo("init", "--prefix", "tx").returncode, 0)
        self.assertEqual(todo("add", "--kind", "note", "a note").returncode, 0)
        res = self.cli_json("one", "todo-valid", r, "--root", ws)[1]["results"][0]
        self.assertEqual(res["status"], "ok", res["lines"])
        md = r / "TODO.md"
        os.chmod(md, 0o644)
        md.write_text(md.read_text() + "\n- a hand-added line\n")
        self.assertEqual(todo("check").returncode, 1, "a hand edit must fail the real todo check")
        res = self.cli_json("one", "todo-valid", r, "--root", ws)[1]["results"][0]
        self.assertEqual(res["status"], "fail", res["lines"])
        self.assertTrue(any(l.startswith("todo check: render ") for l in res["lines"]), res["lines"])


if __name__ == "__main__":
    unittest.main()
