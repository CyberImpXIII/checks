"""`repro` and `cli-declared` (PLAN-architecture.md §12): each input the
declaration carries is shown to change the result -- the volatile list, the
fixture, `{fixture}` in env and in args -- and each way a read verb can give
a different answer twice is shown red alone. Checks run through the CLI
(`checks one`), the way a repo runs them; checkslib/repro.py's comparison is
also held directly."""
import json
import unittest

from tests.helpers import Case, repo, write
from checkslib import repro

TOOL = """#!/usr/bin/env python3
import json, os, sys, time
verb = sys.argv[1] if len(sys.argv) > 1 else "help"
args = sys.argv[2:]
if verb == "help":
    print("tool <verb>\\n\\n" + "".join(f"  tool {v}   does {v}\\n" for v in
          ("count", "stamp", "plain", "tick", "env", "cache", "rewrite", "order")))
elif verb == "count":
    where = args[args.index("--dir") + 1] if "--dir" in args else os.environ["TOOL_DATA"]
    rows = sorted(open(os.path.join(where, "rows.txt")).read().split())
    print(json.dumps({"rows": rows, "n": len(rows)}))
elif verb == "stamp":
    print(json.dumps({"at": time.time_ns(), "runs": [{"took": time.time_ns(), "ok": True}]}))
elif verb == "plain":
    print("rows: 3")
elif verb == "tick":
    with open("ticks.txt", "a") as f:
        f.write("x")
    n = len(open("ticks.txt").read())
    print(json.dumps({"ticks": n}))
    sys.exit(0 if n == 1 else 1)
elif verb == "env":
    leaked = sorted(k for k in ("CHECKS_WORKSPACE", "CHECKS_PARAMS", "CHECKS_ROSTER_NAMES") if k in os.environ)
    print("leaked: " + ",".join(leaked) if leaked else json.dumps({"leaked": []}))
elif verb == "cache":
    os.makedirs("cache", exist_ok=True)
    open(os.path.join("cache", "c.txt"), "w").write("same every time")
    print(json.dumps({"rows": 3}))
elif verb == "rewrite":
    data = open("rows.txt").read()
    open("rows.txt", "w").write(data)
    print(json.dumps({"rows": 3}))
elif verb == "order":
    keys = ["a", "b"] if not os.path.exists("seen") else ["b", "a"]
    open("seen", "w").close()
    print(json.dumps({k: 1 for k in keys}))
"""
VERBS = ["count", "stamp", "plain", "tick", "env", "cache", "rewrite", "order"]


class Repro(Case):
    def one(self, r, check="repro"):
        return self.cli_json("one", check, r)[1]["results"][0]

    def make(self, read, verbs=VERBS):
        r = self.tmp / "r"
        if not r.exists():
            repo(r, {"fx/rows.txt": "b\na\nc\n"})
        write(r / "tool", TOOL, 0o755)
        write(r / "cli.json", json.dumps({"cli": "tool", "verbs": verbs, "read": read}))
        return r

    def fx(self, verbs, **more):
        return dict({"fixture": "fx", "env": {"TOOL_DATA": "{fixture}"}, "verbs": verbs}, **more)

    def test_a_reproducible_verb_is_ok_and_named(self):
        res = self.one(self.make(self.fx({"count": {"args": ["--json"]}})))
        self.assertEqual((res["status"], res["lines"]),
                         ("ok", ["the same answer twice: count (exit 0); fixture unchanged"]))
        res = self.one(self.make({"verbs": {"env": {"args": ["--json"]}}}))
        self.assertEqual(res["lines"], ["the same answer twice: env (exit 0); no fixture: run in the repo, tree not compared"])

    def test_the_volatile_list_turns_the_result(self):
        """The declared input changes the output: without it red, with it green."""
        bare = self.one(self.make(self.fx({"stamp": {"args": ["--json"]}})))
        self.assertEqual(bare["status"], "fail")
        self.assertEqual(len(bare["lines"]), 1, bare["lines"])
        self.assertTrue(bare["lines"][0].startswith(
            "`stamp`: two runs differ after the volatile fields are removed, first at $.at: "), bare["lines"])
        half = self.one(self.make(self.fx({"stamp": {"args": ["--json"], "volatile": ["at"]}})))
        self.assertEqual(half["status"], "fail")
        self.assertIn("first at $.runs[0].took", half["lines"][0])
        full = self.one(self.make(self.fx({"stamp": {"args": ["--json"], "volatile": ["at", "runs.*.took"]}})))
        self.assertEqual(full["status"], "ok", full["lines"])

    def test_a_volatile_path_that_removes_nothing_is_red(self):
        res = self.one(self.make(self.fx({"count": {"args": ["--json"], "volatile": ["generated_at", "rows.*.x"]}})))
        self.assertEqual(res["status"], "fail")
        self.assertEqual([l.split(" (", 1)[0] for l in res["lines"]],
                         ["`count`: volatile `generated_at` removes nothing in either run",
                          "`count`: volatile `rows.*.x` removes nothing in either run"])

    def test_the_fixture_env_is_what_points_the_cli_at_its_data(self):
        """Counterfactual for read.env: without it the verb has no data and prints no JSON."""
        res = self.one(self.make({"fixture": "fx", "verbs": {"count": {"args": ["--json"]}}}))
        self.assertEqual(res["status"], "fail")
        self.assertIn("`count`: run 1 printed no JSON document", res["lines"][0])

    def test_fixture_in_args_is_substituted(self):
        res = self.one(self.make({"fixture": "fx", "verbs": {"count": {"args": ["--json", "--dir", "{fixture}"]}}}))
        self.assertEqual(res["status"], "ok", res["lines"])

    def test_output_that_is_not_json_is_red(self):
        res = self.one(self.make(self.fx({"plain": {"args": ["--json"]}})))
        self.assertEqual(res["status"], "fail")
        self.assertEqual(len(res["lines"]), 2, res["lines"])            # both runs, every one found
        self.assertIn("`plain`: run 1 printed no JSON document (exit 0;", res["lines"][0])
        self.assertIn("rows: 3", res["lines"][0])

    def test_a_read_verb_that_writes_its_fixture_is_caught_and_the_repo_is_untouched(self):
        r = self.make(self.fx({"tick": {"args": ["--json"]}}))
        res = self.one(r)
        self.assertEqual(res["status"], "fail")
        self.assertEqual(res["lines"], ["`tick`: exit codes differ between runs: 0 vs 1",
                                        "`tick`: two runs differ after the volatile fields are removed, first at $.ticks: 1 vs 2",
                                        "`tick`: a read verb changed its fixture (1 path(s)): added ticks.txt"])
        self.assertFalse((r / "fx" / "ticks.txt").exists(), "both runs use a scratch copy, never the repo's fixture")

    def test_a_read_verb_that_writes_but_answers_the_same_is_caught_by_the_tree(self):
        """Counterfactual pair: `cache` answers the same twice yet adds files, so only
        the tree comparison turns it red; `rewrite` writes the same bytes back: no change."""
        res = self.one(self.make(self.fx({"cache": {"args": ["--json"]}, "rewrite": {"args": ["--json"]}})))
        self.assertEqual((res["status"], res["lines"]),
                         ("fail", ["`cache`: a read verb changed its fixture (2 path(s)): added cache, added cache/c.txt"]))
        res = self.one(self.make(self.fx({"rewrite": {"args": ["--json"]}})))
        self.assertEqual(res["status"], "ok", res["lines"])

    def test_key_order_is_compared(self):
        res = self.one(self.make(self.fx({"order": {"args": ["--json"]}})))
        self.assertEqual(res["status"], "fail")
        self.assertIn('first at $: keys ["a", "b"] vs ["b", "a"]', res["lines"][0])

    def test_the_runners_own_variables_do_not_reach_the_verb(self):
        """`env` prints no JSON when any of the runner's variables reaches it,
        and the runner always sets CHECKS_PARAMS for the check (runner.run_one):
        ok here means repro removed them."""
        res = self.one(self.make(self.fx({"env": {"args": ["--json"]}})))
        self.assertEqual(res["status"], "ok", res["lines"])

    def test_each_verb_is_judged_alone(self):
        res = self.one(self.make(self.fx({"count": {"args": ["--json"]}, "stamp": {"args": ["--json"]}})))
        self.assertEqual(res["status"], "fail")
        self.assertEqual(len(res["lines"]), 1, res["lines"])
        self.assertTrue(res["lines"][0].startswith("`stamp`:"))

    def test_nothing_declared_is_unchecked_never_ok(self):
        r = repo(self.tmp / "none")
        res = self.one(r)
        self.assertEqual(res["status"], "unchecked")
        self.assertIn("no cli.json", res["lines"][0])
        write(r / "tool", TOOL, 0o755)
        write(r / "cli.json", json.dumps({"cli": "tool", "verbs": ["count"]}))
        res = self.one(r)
        self.assertEqual(res["status"], "unchecked")
        self.assertIn("declares no `read` verbs", res["lines"][0])

    def test_a_cli_json_that_breaks_a_rule_is_unchecked_and_left_to_accessor(self):
        res = self.one(self.make(self.fx({"count": {"args": []}})))
        self.assertEqual(res["status"], "unchecked")
        self.assertIn("read-json", res["lines"][0])
        self.assertEqual(self.one(self.tmp / "r", "accessor")["status"], "fail")


class CliDeclared(Case):
    def one(self, r):
        return self.cli_json("one", "cli-declared", r)[1]["results"][0]

    def test_each_lag_and_its_counterfactual(self):
        r = repo(self.tmp / "r")
        res = self.one(r)
        self.assertEqual((res["status"], res["lines"]),
                         ("fail", ["lag: no cli.json: this repo declares no CLI and no verbs (PLAN-architecture.md §12.1)"]))
        write(r / "tool", TOOL, 0o755)
        write(r / "cli.json", json.dumps({"cli": "tool", "verbs": []}))
        res = self.one(r)
        self.assertEqual(res["status"], "fail")
        self.assertIn("lag: cli.json: declares no verbs", res["lines"][0])
        write(r / "cli.json", json.dumps({"cli": "tool", "verbs": ["count", "purge"]}))
        res = self.one(r)
        self.assertEqual(res["status"], "fail")
        self.assertIn("lag: cli.json: verb-implemented:", res["lines"][0])
        write(r / "cli.json", json.dumps({"cli": "tool", "verbs": ["count", "stamp"],
                                          "read": {"verbs": {"stamp": {"args": ["--json"]}}}}))
        res = self.one(r)
        self.assertEqual((res["status"], res["lines"]), ("ok", ["2 verb(s) through `tool`; read verbs: stamp"]))

    def test_the_top_is_declared_by_its_claude_repo(self):
        """A folder that is not a git repo (the workspace top) with no cli.json
        of its own reads .claude/cli.json when .claude is a git repo; each
        condition taken away turns it back to the lag."""
        top = self.tmp / "top"
        inner = repo(top / ".claude")
        write(inner / "tool", TOOL, 0o755)
        write(inner / "cli.json", json.dumps({"cli": "tool", "verbs": ["count"]}))
        res = self.one(top)
        self.assertEqual((res["status"], res["lines"]), ("ok", [
            "1 verb(s) through `tool`; read verbs: none declared; "
            "declared in .claude/cli.json (not a git repo: its .claude repo holds it)"]))
        write(inner / "cli.json", json.dumps({"cli": "tool", "verbs": ["count", "purge"]}))
        res = self.one(top)
        self.assertEqual(res["status"], "fail")
        self.assertIn("lag: .claude/cli.json: verb-implemented:", res["lines"][0])
        write(inner / "cli.json", json.dumps({"cli": "tool", "verbs": ["count"]}))
        lag = "lag: no cli.json: this repo declares no CLI and no verbs (PLAN-architecture.md §12.1)"
        (inner / ".git").rename(inner / "git.off")          # .claude not a git repo
        self.assertEqual(self.one(top)["lines"], [lag])
        (inner / "git.off").rename(inner / ".git")
        (top / ".git").mkdir()                              # the folder is a git repo: its own root decides
        self.assertEqual(self.one(top)["lines"], [lag])
        (top / ".git").rmdir()
        write(top / "tool", TOOL, 0o755)                    # its own cli.json wins over .claude's
        write(top / "cli.json", json.dumps({"cli": "tool", "verbs": []}))
        self.assertIn("lag: cli.json: declares no verbs", self.one(top)["lines"][0])

    def test_it_runs_only_when_lags_are_asked_for(self):
        r = repo(self.tmp / "r")
        names = lambda *a: {x["check"] for x in self.cli_json("run", r, *a)[1]["results"]}  # noqa: E731
        self.assertNotIn("cli-declared", names())
        self.assertIn("cli-declared", names("--roles", "lag"))


class Compare(unittest.TestCase):
    """checkslib/repro.py held directly."""

    def test_strip_counts_what_each_path_removed(self):
        doc = {"a": 1, "l": [{"t": 1, "k": 2}, {"t": 3}], "m": {"x": 1, "y": 2}}
        got, removed = repro.strip(doc, ["a", "l.*.t", "m.*", "zz", "l.t"])
        self.assertEqual(got, {"l": [{"k": 2}, {}], "m": {}})
        self.assertEqual(removed, {"a": 1, "l.*.t": 2, "m.*": 2, "zz": 0, "l.t": 0})
        self.assertEqual(doc["a"], 1, "the input is not changed")

    def test_first_difference(self):
        self.assertIsNone(repro.first_difference({"a": [1, 2]}, {"a": [1, 2]}))
        self.assertEqual(repro.first_difference({"a": [1, 2]}, {"a": [1, 3]}), "$.a[1]: 2 vs 3")
        self.assertEqual(repro.first_difference([1], [1, 2]), "$: 1 items vs 2")
        self.assertEqual(repro.first_difference({"a": 1}, {"a": 1.0}), "$.a: 1 vs 1.0")

    def test_tree_changes_names_added_removed_and_changed(self):
        before = {"a": "sha256:1", "b": "sha256:2", "d": "dir", "l": "link:a"}
        after = {"a": "sha256:1", "b": "sha256:9", "l": "link:b", "n": "sha256:3"}
        self.assertEqual(repro.tree_changes(before, after), ["changed b", "removed d", "changed l", "added n"])
        self.assertEqual(repro.tree_changes(before, dict(before)), [])

    def test_compare_finds_every_fault(self):
        got = repro.compare("v", [(0, '{"a": 1}'), (1, '{"a": 2}')], ["gone"])
        self.assertEqual(len(got), 3, got)
        for want, line in zip(("volatile `gone` removes nothing", "exit codes differ between runs: 0 vs 1",
                               "two runs differ after the volatile fields are removed, first at $.a: 1 vs 2"), got):
            self.assertIn(want, line)
        self.assertEqual(repro.compare("v", [(0, '{"a": 1, "t": 1}'), (0, '{"a": 1, "t": 2}')], ["t"]), [])


if __name__ == "__main__":
    unittest.main()
