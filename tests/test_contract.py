"""The seams with tools/hooks, held by running the real tool (never a copy of
its rules): `checks all` walks the same repos `hooks copies` compares, and
hooks-installed reads `hooks copies --json` the way that tool means it.
Skipped, said out loud, when tools/hooks is not beside this tool."""
import json
import os
import shutil
import subprocess
import unittest

from tests.helpers import Case, GIT_ENV, WORKSPACE, repo, write
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

    def shim(self, ws, settings, hooks=None):
        """ws/tools/hooks/hooks: the real tool (or a clone of it), told which user
        settings to read, so this test never depends on (or reads) the real
        ~/.claude/settings.json."""
        write(ws / "tools" / "hooks" / "hooks",
              f'#!/usr/bin/env bash\nexec "{hooks or HOOKS}" "$@" --settings "{settings}"\n', 0o755)

    def test_hooks_installed_reads_the_real_source_uncommitted(self):
        """A clone of tools/hooks, every copy installed in ws/a from it (all ok),
        then ONE source file edited in the clone: the real `hooks copies` marks
        that copy drift with source_uncommitted true, and hooks-installed says
        unchecked. The same edit committed: source_uncommitted false, a real fail.
        Only the commit changes between the two runs."""
        ws = self.fixture_ws()
        clone = self.tmp / "hooksclone"
        subprocess.run(["git", "clone", "-q", "--local", str(HOOKS.parent), str(clone)], check=True,
                       capture_output=True, text=True, stdin=subprocess.DEVNULL)
        self.shim(ws, self.tmp / "user" / "settings.json", hooks=clone / "hooks")   # no user settings file
        run = lambda: json.loads(subprocess.run([str(ws / "tools" / "hooks" / "hooks"), "copies", str(ws), "--json"],
                                                capture_output=True, text=True, stdin=subprocess.DEVNULL,
                                                timeout=240).stdout)
        rows = lambda rep: {f["file"]: f for l in rep["locations"] if l["path"] == "a" for f in l["files"]}
        files = rows(run())
        self.assertTrue(files, "hooks copies expects hooks in a fixture repo")
        src = lambda f: clone / "source" / f.removeprefix(".claude/")     # .claude/hooks/x -> source/hooks/x
        for f in files:
            self.assertTrue(src(f).is_file(), f"no source at {src(f)} for {f}: the dest->source mapping went stale")
            shutil.copy2(src(f), write(ws / "a" / f, ""))
        self.assertEqual({f: r["status"] for f, r in rows(run()).items()}, {f: "ok" for f in files})
        res = self.cli_json("one", "hooks-installed", ws / "a", "--root", ws)[1]["results"][0]
        self.assertEqual(res["status"], "ok", res["lines"])
        edited = next(f for f in sorted(files)
                      if f.startswith(".claude/hooks/") and not os.path.basename(f).startswith("test-"))
        with open(src(edited), "a") as fh:
            fh.write("true\n")                          # a code line: `copies` compares by meaning
        row = rows(run())[edited]
        self.assertEqual((row["status"], row["source_uncommitted"]), ("drift", True))
        res = self.cli_json("one", "hooks-installed", ws / "a", "--root", ws)[1]["results"][0]
        self.assertEqual(res["status"], "unchecked", res["lines"])
        self.assertIn("source not committed", res["lines"][0])
        self.assertIn(edited, res["lines"][0])
        subprocess.run(["git", "-C", str(clone), "-c", "commit.gpgsign=false", "-c", "core.hooksPath=/dev/null",
                        "commit", "-q", "-am", "t"], check=True, capture_output=True, text=True,
                       env=dict(os.environ, **GIT_ENV), stdin=subprocess.DEVNULL)
        row = rows(run())[edited]
        self.assertEqual((row["status"], row["source_uncommitted"]), ("drift", False))
        res = self.cli_json("one", "hooks-installed", ws / "a", "--root", ws)[1]["results"][0]
        self.assertEqual(res["status"], "fail", res["lines"])
        self.assertEqual(res["lines"], [f"{edited}: drift; not covered by user scope (no user settings file)"])

    def test_hooks_installed_red_exactly_when_hooks_copies_says_so(self):
        ws = self.fixture_ws()
        self.shim(ws, self.tmp / "user" / "settings.json")             # no user settings file
        p = subprocess.run([str(ws / "tools" / "hooks" / "hooks"), "copies", str(ws), "--json"], capture_output=True,
                           text=True, stdin=subprocess.DEVNULL, timeout=240)
        rep = json.loads(p.stdout)
        self.assertEqual(p.returncode, 1, "fixture repos hold no copies: hooks copies must say missing")
        statuses = {f["status"] for l in rep["locations"] for f in l["files"]}
        self.assertTrue(statuses <= {"ok", "missing", "drift", "not-executable", "extra"}, statuses)
        flags = [f.get("source_uncommitted", "absent") for l in rep["locations"] for f in l["files"]]
        self.assertTrue(flags and all(v in (True, False, None) for v in flags), set(map(str, flags)))
        self.assertIs(rep["user_scope"]["exists"], False)
        res = self.cli_json("one", "hooks-installed", ws / "a", "--root", ws)[1]["results"][0]
        # The real tools/hooks may be mid-edit: a row whose source is not committed
        # is not judged (listed after the verdicts), whatever this test's moment.
        mine = [f for l in rep["locations"] if l["path"] == "a" for f in l["files"]]
        judged = [f"{f['file']}: missing; not covered by user scope (no user settings file)"
                  for f in mine if f["source_uncommitted"] is False]
        unjudged = [f["file"] for f in mine if f["source_uncommitted"] is not False]
        self.assertTrue(judged, "every source uncommitted: settle with tools/hooks clean")
        self.assertEqual(res["status"], "fail")
        self.assertEqual(res["lines"][:len(judged)], judged)
        self.assertEqual([l.split(":")[0] for l in res["lines"][len(judged):]], unjudged)
        self.assertTrue(all("not judged, tools/hooks" in l for l in res["lines"][len(judged):]), res["lines"])

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
        # A support file (.claude/lib/, .claude/bin/) is judged by its
        # `user_scope.support` row (hooks 6eb9c65): with every hook registered,
        # a lib each reader finds beside itself is covered; one still read from
        # the repo copy fails naming the row's `why`. The check follows the row
        # (generic), and today's split, as hooks stated it, is pinned so a change
        # on their side shows here. Then the uncovered ones are given as repo
        # copies so the rest is about the settings.
        support_rows = {s["file"]: s for s in json.loads(p.stdout)["user_scope"]["support"]}
        support = [f for f in files if not f.startswith(".claude/hooks/")]
        self.assertTrue(support, "tools/hooks ships no lib/bin file: drop this half")
        self.assertEqual({f: support_rows[f]["covered"] for f in support if f in support_rows},
                         {".claude/lib/ledger.sh": True, ".claude/lib/extra-stores.sh": True,
                          ".claude/lib/write-targets.sh": False, ".claude/bin/commit.sh": False},
                         "hooks' support split changed: settle the pin with tools/hooks")
        uncovered = [f for f in support if support_rows[f]["covered"] is not True]
        res = self.cli_json("one", "hooks-installed", ws / "a", "--root", ws)[1]["results"][0]
        self.assertEqual((res["status"], res["lines"]), ("fail", [
            f"{f}: missing; not covered by user scope ({support_rows[f]['why']})" for f in uncovered]))
        for f in uncovered:
            (ws / "a" / f).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(HOOKS.parent / "source" / f.removeprefix(".claude/"), ws / "a" / f)
        hooks = [f for f in files if f not in uncovered]
        support = uncovered
        cases = {"registered": (proposed, "ok"),
                 "unparseable": (write(user / "bad.json", "{not json"), "unchecked"),
                 "registers none": (write(user / "none.json", '{"hooks": {}}\n'), "fail")}
        for what, (settings, want) in cases.items():
            with self.subTest(settings=what):
                self.shim(ws, settings)
                res = self.cli_json("one", "hooks-installed", ws / "a", "--root", ws)[1]["results"][0]
                self.assertEqual(res["status"], want, res["lines"])
                if want == "ok":
                    self.assertEqual(res["lines"], ["repo copy: " + ", ".join(support),
                                                    "covered by user scope: " + ", ".join(hooks)])

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

    def test_todo_store_follows_the_real_todo_init_and_check(self):
        """todo-store: no store is the lag; the real `todo init` clears it
        (ok, naming the real summary line); a hand edit turns it red again."""
        ws = self.tmp / "ws"
        write(ws / "CLAUDE.md", "# top\n")
        os.makedirs(ws / "tools", exist_ok=True)
        os.symlink(TODO.parent, ws / "tools" / "todo")
        r = repo(ws / "r")
        one = lambda: self.cli_json("one", "todo-store", r, "--root", ws)[1]["results"][0]  # noqa: E731
        res = one()
        self.assertEqual(res["status"], "fail", res["lines"])
        self.assertTrue(res["lines"][0].startswith("lag: no todo.json:"), res["lines"])
        todo = lambda *a: subprocess.run([str(TODO), "-C", str(r), "--root", str(ws), *a], capture_output=True,
                                         text=True, stdin=subprocess.DEVNULL, timeout=120)
        self.assertEqual(todo("init", "--prefix", "tx").returncode, 0)
        self.assertEqual(todo("add", "--kind", "note", "a note").returncode, 0)
        res = one()
        self.assertEqual(res["status"], "ok", res["lines"])
        self.assertTrue(res["lines"][0].startswith("todo check "), res["lines"])
        md = r / "TODO.md"
        os.chmod(md, 0o644)
        md.write_text(md.read_text() + "\n- a hand-added line\n")
        res = one()
        self.assertEqual(res["status"], "fail", res["lines"])
        self.assertTrue(any(l.startswith("lag: todo check: render ") for l in res["lines"]), res["lines"])


if __name__ == "__main__":
    unittest.main()
