"""rendered-matches and regenerate (PLAN-repo-setup.md §7.10), through the CLI:
the rebuild runs in a scratch copy (never the repo), deletes first (so a
generator that renders nothing is caught), reports each category on its own,
keeps record files safe, accounts for every committable file at the top, stops
when nested, and errors when the rebuild does not finish."""
import json
import time

from tests.helpers import Case, git, repo, write

RENDER = "#!/usr/bin/env bash\nset -e\ntr a-z A-Z < src.txt > out.txt\n"


class Rebuild(Case):
    def node(self, render=RENDER, node=None, extra=None, commit=True):
        doc = node or {"rebuild": ["./render.sh"], "generated": ["out.txt"],
                       "record": ["src.txt", "render.sh", "CLAUDE.md"]}
        files = dict({"node.json": json.dumps(doc), "src.txt": "one\ntwo\n", "out.txt": "ONE\nTWO\n"}, **(extra or {}))
        r = repo(self.tmp / "r", files, commit=False)
        write(r / "render.sh", render, 0o755)
        if commit:
            git(r, "add", "-A")
            git(r, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "t")
        return r

    def one(self, check, r, env=None):
        return self.cli_json("one", check, r, env=env)[1]["results"][0]

    def both(self, r, env=None):
        return {c: self.one(c, r, env) for c in ("rendered-matches", "regenerate")}

    def test_a_clean_render_passes_both(self):
        r = self.node()
        for c, res in self.both(r).items():
            self.assertEqual(res["status"], "ok", (c, res))

    def test_drift_is_red_and_the_repo_is_never_touched(self):
        r = self.node(render=RENDER + "touch touched\n")
        write(r / "out.txt", "ONE\nTWO\nTHREE\n")
        drift = "drift: out.txt: the render differs from the file (first at line 3)"
        got = self.both(r)
        self.assertEqual(got["rendered-matches"]["lines"], [drift])
        self.assertEqual(got["regenerate"]["lines"],
                         [drift, "unaccounted: touched: named by neither generated nor record (written by the rebuild)"])
        self.assertEqual((r / "out.txt").read_text(), "ONE\nTWO\nTHREE\n")
        self.assertFalse((r / "touched").exists())

    def test_a_generator_that_renders_nothing_is_caught_because_it_deletes_first(self):
        r = self.node(render="#!/usr/bin/env bash\ntrue\n")
        res = self.one("rendered-matches", r)
        self.assertEqual(res["lines"], ["missing: out.txt: the rebuild did not render it"])
        self.assertTrue((r / "out.txt").is_file())

    def test_absent_and_a_failed_rebuild(self):
        r = self.node(node={"rebuild": ["./render.sh"], "generated": ["out.txt", "gone.txt"],
                            "record": ["src.txt", "render.sh", "CLAUDE.md"]},
                      render="#!/usr/bin/env bash\ntr a-z A-Z < src.txt > out.txt\necho broke >&2\nexit 4\n")
        res = self.one("rendered-matches", r)
        self.assertEqual(res["lines"], ["absent: gone.txt: listed as generated, but the tree to be committed has no such file",
                                        "rebuild: `./render.sh` exited 4: broke",
                                        "missing: gone.txt: the rebuild did not render it"])

    def test_record_files_and_unaccounted_are_regenerate_only(self):
        r = self.node(render=RENDER + "echo changed >> src.txt\necho new > made.txt\n", extra={"stray.txt": "x\n"})
        self.assertEqual(self.one("rendered-matches", r)["status"], "ok")
        res = self.one("regenerate", r)
        self.assertEqual(res["lines"], ["record: src.txt: changed by the rebuild",
                                        "unaccounted: made.txt: named by neither generated nor record (written by the rebuild)",
                                        "unaccounted: stray.txt: named by neither generated nor record"])

    def test_the_view_is_what_a_commit_would_carry(self):
        """Uncommitted edits count, a deleted tracked file is gone, an ignored file never counts."""
        r = self.node(extra={"old.txt": "x\n", ".gitignore": "cache/\n"},
                      node={"rebuild": ["./render.sh"], "generated": ["out.txt"],
                            "record": ["src.txt", "render.sh", "CLAUDE.md", ".gitignore", "new.txt"]})
        (r / "old.txt").unlink()
        write(r / "cache" / "big.txt", "instance state\n")
        write(r / "new.txt", "untracked, not ignored\n")
        self.assertEqual(self.one("regenerate", r)["status"], "ok")
        write(r / "src.txt", "one\nTWO-ish\n")                  # uncommitted source change, render not redone
        self.assertEqual(self.one("regenerate", r)["lines"],
                         ["drift: out.txt: the render differs from the file (first at line 2)"])

    def test_origin_is_substituted_and_the_rebuild_runs_in_the_copy(self):
        write(self.tmp / "gen.sh", "#!/usr/bin/env bash\n[ \"$PWD\" != \"$CHECKS_ORIGIN\" ] || exit 9\n"
                                   "tr a-z A-Z < src.txt > out.txt\n", 0o755)
        r = self.node(node={"rebuild": ["bash", "{origin}/../gen.sh"], "generated": ["out.txt"],
                            "record": ["src.txt", "render.sh", "CLAUDE.md"]})
        self.assertEqual(self.one("rendered-matches", r)["status"], "ok")

    def test_the_guard_reaches_the_rebuild_and_a_nested_run_is_unchecked(self):
        r = self.node(render='#!/usr/bin/env bash\n[ -n "$CHECKS_REBUILD_ACTIVE" ] || exit 7\ntr a-z A-Z < src.txt > out.txt\n')
        self.assertEqual(self.one("rendered-matches", r)["status"], "ok")
        for c, res in self.both(r, env={"CHECKS_REBUILD_ACTIVE": "1"}).items():
            self.assertEqual(res["status"], "unchecked", c)
            self.assertIn("nested inside a rebuild", res["lines"][0])

    def test_a_rebuild_that_does_not_finish_is_an_error(self):
        r = self.node(render="#!/usr/bin/env bash\nsleep 30 & wait\n")
        t0 = time.monotonic()
        res = self.one("rendered-matches", r, env={"CHECKS_REBUILD_TIMEOUT": "1"})
        self.assertLess(time.monotonic() - t0, 20)
        self.assertEqual(res["status"], "error")
        self.assertIn("did not finish in 1.0s", "\n".join(res["lines"]))

    def test_a_bad_node_json_is_reported_and_never_rebuilt(self):
        r = self.node(render=RENDER + "touch \"$CHECKS_ORIGIN/ran\"\n",
                      node={"rebuild": ["./render.sh"], "generated": ["../outside.txt"], "record": []})
        res = self.one("rendered-matches", r)
        self.assertEqual(res["lines"], ["node.json: paths-inside: $.generated: `../outside.txt` is not a path inside the repo"])
        self.assertFalse((r / "ran").exists())

    def test_no_node_json_and_no_git_are_unchecked(self):
        r = repo(self.tmp / "r")
        self.assertEqual(self.one("rendered-matches", r)["status"], "unchecked")
        p = self.tmp / "plain"
        write(p / "node.json", json.dumps({"rebuild": ["true"], "generated": [], "record": []}))
        res = self.one("rendered-matches", p)
        self.assertEqual(res["status"], "unchecked")
        self.assertIn("not a git repo", res["lines"][0])

    def test_regenerate_runs_only_at_the_top(self):
        r = self.node()
        ran = {x["check"] for x in self.cli_json("run", r)[1]["results"]}
        self.assertIn("rendered-matches", ran)
        self.assertNotIn("regenerate", ran)
        ran = {x["check"] for x in self.cli_json("run", r, "--root", r)[1]["results"]}
        self.assertIn("regenerate", ran)


if __name__ == "__main__":
    import unittest
    unittest.main()
