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
        _, rep = copies(ws)
        # hooks also lists a `repos:` destination that is absent (to report it missing);
        # only folders that exist are walked locations.
        theirs = sorted(l["path"] for l in rep["locations"] if (ws / l["path"]).is_dir())
        ours = sorted(runner.rel(p, ws) for p in runner.discover(ws))
        self.assertEqual(ours, theirs)
        self.assertIn("x/y/z/w", ours)
        self.assertNotIn("too/deep/for/the/walk", ours)

    def test_hooks_installed_red_exactly_when_hooks_copies_says_so(self):
        ws = self.fixture_ws()
        os.makedirs(ws / "tools", exist_ok=True)
        os.symlink(HOOKS.parent, ws / "tools" / "hooks")
        code, rep = copies(ws)
        self.assertEqual(code, 1, "fixture repos hold no copies: hooks copies must say missing")
        statuses = {f["status"] for l in rep["locations"] for f in l["files"]}
        self.assertTrue(statuses <= {"ok", "missing", "drift", "not-executable", "extra"}, statuses)
        res = self.cli_json("one", "hooks-installed", ws / "a", "--root", ws)[1]["results"][0]
        self.assertEqual(res["status"], "fail")
        self.assertTrue(all(l.endswith(": missing") for l in res["lines"]), res["lines"])

    @unittest.skipUnless(WORKSPACE and (WORKSPACE / "tools" / "checks").is_dir(), WHY)
    def test_real_workspace_agrees_for_this_repo(self):
        code, rep = copies(WORKSPACE)
        mine = [l for l in rep["locations"] if l["path"] == "tools/checks"]
        self.assertEqual(len(mine), 1)
        bad = [f for f in mine[0]["files"] if f["status"] in ("missing", "drift", "not-executable")]
        res = self.cli_json("one", "hooks-installed", WORKSPACE / "tools" / "checks")[1]["results"][0]
        self.assertEqual(res["status"], "fail" if bad else "ok", res["lines"])


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
