"""The practice rows (checkslib/practices.py, `checks practices`):

  - parse_md reads a PRACTICES-rows.md's four tables, a camelCase id included,
    and refuses a file whose stated counts it does not match (a dropped row is
    an error, never silent);
  - import_md leaves the blocked rows out, keeps recorded cells, keeps every
    byte of the `rules`, and refuses (writing nothing) when a blocked id is no
    row or a row with recorded cells would be dropped;
  - each cell state is earned from a check result (ok held, fail unjustified,
    unchecked/not-run unknown, partial unknown), a recorded cell is used only
    where no check decided, an unbuilt row stays red, and a principle rolls up;
  - the ratchet end to end through the CLI, on results from a real `checks all
    --json` of a test source: at the baseline exit 0, a planted red row exit 1,
    `--lower` refuses a higher count and writes a lower one, no baseline exit 2;
    the live run and `--from` that report agree (the input changes the output
    and both paths read it the same);
  - the real registry: its `keys` are the reader's row keys, and it validates
    against the workspace top."""
import importlib.util
import json
import unittest

from checkslib import practices
from tests.helpers import Case, TOOL_ROOT, WORKSPACE, repo, run_cli, write

_spec = importlib.util.spec_from_file_location("fx_practices", TOOL_ROOT / "source" / "fixtures" / "practices-valid.py")
fx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fx)

MD = """# Practices

Counts: 1 principles, 2 Part B rows, 1 Part C rows.

## Part A

| id | rule | sources | applies | held | status |
|---|---|---|---|---|---|
| `root-x` | the root | PLAN-x.md §5 | all | rollup of its rows | live |

## Part B

### Serving `root-x` (2 rows)

| id | rule | sources | applies | held | subject | status |
|---|---|---|---|---|---|---|
| `rules-classified` | every rule is classified | PLAN-x.md §5 **(wins)**; `gates:r#friday` | all | gate tools/checks/source/rules-gated.py | seam | live |
| `no-blobs` | no inline blobs | CLAUDE.md "Never write an inline script blob" | r, . | gate tools/hooks/source/hooks/no-inline-blobs.sh, the rest unbuilt | behaviour | live |

## Part C

| id | rule | sources | applies | held | status | own ids |
|---|---|---|---|---|---|---|
| `own-emailTools` | its own rows | gates:r#friday | r | prose | live | friday |

## Superseded

| id | rule | sources | status |
|---|---|---|---|
| `old-rule` | the old wording | PLAN-x.md §5 | superseded-by rules-classified |
"""


def _src(case, statuses):
    """A test source holding the two checks the fixture rows name, each exiting as told."""
    code = {"ok": "echo fine; exit 0", "fail": "echo broken here; exit 2", "unchecked": "echo cannot tell; exit 3"}
    for name, st in statuses.items():
        case.add_check(name, code[st])


class ParseMd(unittest.TestCase):
    def test_reads_every_table(self):
        rows = {r["id"]: r for r in practices.parse_md(MD)}
        self.assertEqual(list(rows), ["root-x", "rules-classified", "no-blobs", "own-emailTools", "old-rule"])
        self.assertEqual(rows["root-x"]["held"], {"kind": "rollup", "text": "rollup of its rows"})
        rc = rows["rules-classified"]
        self.assertEqual((rc["principle"], rc["sources"], rc["applies"], rc["subject"]),
                         ("root-x", ["PLAN-x.md §5", "gates:r#friday"], "all", ["seam"]))
        self.assertEqual(rc["held"]["check"], "rules-gated")
        nb = rows["no-blobs"]["held"]
        self.assertEqual((nb["via"], nb.get("partial"), rows["no-blobs"]["applies"]), ("hooks-installed", True, ["r", "."]))
        own = rows["own-emailTools"]
        self.assertEqual((own["part"], own["own_ids"], "principle" in own), ("C", ["friday"], False))
        self.assertEqual(rows["old-rule"]["status"], "superseded-by rules-classified")

    def test_a_dropped_row_is_an_error(self):
        broken = MD.replace("| `no-blobs` |", "| no-blobs |")
        with self.assertRaisesRegex(ValueError, "says 2 row\\(s\\) for root-x, and 1 were read"):
            practices.parse_md(broken)

    def test_not_a_practices_file(self):
        with self.assertRaisesRegex(ValueError, "not a PRACTICES-rows.md"):
            practices.parse_md("# x\n\n| `a` | b |\n")


class ImportMd(Case):
    def registry(self, rows, blocked):
        text = ('{\n "_comment": "c",\n "rules": [\n    {"id": "kept",   "rule": "laid out by hand"}\n ],\n'
                '  "practices": ' + json.dumps({"_comment": "p", "keys": fx.KEYS, "rows": rows, "blocked": blocked}) + "\n}\n")
        return write(self.tmp / "gates.json", text), text

    def test_blocked_out_cells_kept_rules_untouched(self):
        cells = {"r": {"state": "justified", "why": "r has none"}}
        reg, before = self.registry([{"id": "own-emailTools", "cells": cells}],
                                    [{"id": "no-blobs", "conflict": "C5", "why": "w"}])
        md = write(self.tmp / "P.md", MD)
        summary, problems = practices.import_md(md, reg)
        self.assertEqual(problems, [])
        self.assertEqual((summary["rows"], summary["live"], summary["blocked"]), (4, 3, 1))
        after = reg.read_text()
        self.assertEqual(after.split('  "practices": ')[0], before.split('  "practices": ')[0])
        block = json.loads(after)["practices"]
        ids = [r["id"] for r in block["rows"]]
        self.assertNotIn("no-blobs", ids)
        self.assertEqual(next(r for r in block["rows"] if r["id"] == "own-emailTools")["cells"], cells)

    def test_refusals_write_nothing(self):
        md = write(self.tmp / "P.md", MD)
        for rows, blocked, want in [
            ([], [{"id": "gone", "conflict": "C1", "why": "w"}], "blocked 'gone' is no row in P.md"),
            ([{"id": "vanished", "cells": {"r": {"state": "justified", "why": "w"}}}], [],
             "row 'vanished' carries recorded cells and is no longer imported"),
        ]:
            reg, before = self.registry(rows, blocked)
            summary, problems = practices.import_md(md, reg)
            self.assertIsNone(summary)
            self.assertIn(want, problems)
            self.assertEqual(reg.read_text(), before)


class Cells(unittest.TestCase):
    LOCS = [".", "r"]

    def table(self, results, rows=None):
        return practices.cells(rows or fx.ROWS, self.LOCS, results)

    def test_states_are_earned(self):
        t = self.table({".": {"rules-gated": {"status": "ok", "lines": []},
                              "hooks-installed": {"status": "unchecked", "lines": ["registered: null"]}},
                        "r": {"rules-gated": {"status": "fail", "lines": ["a", "b"]},
                              "hooks-installed": {"status": "ok", "lines": []}}})
        self.assertEqual(t["rules-classified"]["."]["state"], "held")
        self.assertEqual(t["rules-classified"]["r"]["state"], "unjustified")
        self.assertIn("(+1 more)", t["rules-classified"]["r"]["why"])
        self.assertEqual(t["no-blobs"]["."]["state"], "unknown")
        self.assertEqual(t["no-blobs"]["r"]["state"], "held")
        self.assertEqual(t["ask-first"]["r"], {"state": "justified", "why": "r sends nothing", "recorded": True})
        self.assertEqual(t["own-r"]["r"]["state"], "unknown")
        self.assertEqual({c["state"] for c in t["verbs-later"].values()}, {"unknown"})
        self.assertNotIn("old-rule", t)
        self.assertEqual(t["root-x"]["r"]["state"], "unjustified")   # rules-classified broke there
        self.assertEqual(t["root-x"]["."]["state"], "unknown")       # verbs-later, no-blobs unknown there
        self.assertEqual(practices.red(fx.ROWS, t), 1 + 1 + 2 + 1)  # rules-classified r, no-blobs ., verbs-later x2, own-r

    def test_no_result_and_partial_are_unknown(self):
        rows = json.loads(json.dumps(fx.ROWS))
        rows[1]["held"]["partial"] = True
        t = self.table({".": {"rules-gated": {"status": "ok", "lines": []}}}, rows)
        self.assertEqual(t["rules-classified"]["."]["state"], "unknown")
        self.assertIn("only partly held", t["rules-classified"]["."]["why"])
        self.assertEqual(t["rules-classified"]["r"]["state"], "unknown")
        self.assertIn("has no result here", t["rules-classified"]["r"]["why"])

    def test_a_recorded_cell_never_overrides_a_check_or_unbuilt(self):
        rows = json.loads(json.dumps(fx.ROWS))
        rows[1]["cells"] = {"r": {"state": "justified", "why": "w"}}
        rows[4]["cells"] = {"r": {"state": "justified", "why": "w"}}
        t = self.table({"r": {"rules-gated": {"status": "fail", "lines": ["x"]}}}, rows)
        self.assertEqual(t["rules-classified"]["r"]["state"], "unjustified")
        self.assertIn("the check decided", t["rules-classified"]["r"]["note"])
        self.assertEqual((t["verbs-later"]["r"]["state"], t["verbs-later"]["r"]["unbuilt"]), ("unknown", True))

    def test_principle_holds_when_every_row_does(self):
        rows = [r for r in fx.ROWS if r["id"] in ("root-x", "rules-classified")]
        t = self.table({loc: {"rules-gated": {"status": "ok", "lines": []}} for loc in self.LOCS}, rows)
        self.assertEqual({c["state"] for c in t["root-x"].values()}, {"held"})
        self.assertEqual(practices.red(rows, t), 0)


class _Workspace(Case):
    """A fixture workspace, a test source, a real `checks all --json` (no tests of its own)."""

    def setUp(self):
        super().setUp()
        self.ws = fx._ws(self.tmp, fx.ROWS)
        write(self.ws / "CLAUDE.md", "# top\n\n## Never write an inline script blob — ENFORCED\n")
        repo(self.ws / "r", {"gates.json": json.dumps({"rules": [{"id": "friday"}]}) + "\n"})
        _src(self, {"rules-gated": "ok", "hooks-installed": "fail"})
        self.reg = self.ws / "reg" / "gates.json"
        self.base = self.tmp / "baseline.json"
        p = run_cli("all", self.ws, "--source", self.src, "--json")
        self.report = write(self.tmp / "all.json", p.stdout)
        self.assertEqual(sorted(r["rel"] for r in json.loads(p.stdout)["repos"]), [".", "r"])

    def practices(self, *extra, live=False):
        args = ["practices", self.ws, "--source", self.src, "--registry", self.reg, "--baseline", self.base]
        p = run_cli(*args, *(() if live else ("--from", self.report)), *extra)
        return p.returncode, p.stdout + p.stderr


class Ratchet(_Workspace):
    """The CLI end to end, through the ratchet."""

    def ratchet(self, live=False):
        rc, out = self.practices("--json", live=live)
        return rc, json.loads(out[:out.rindex("}") + 1])["ratchet"]

    def test_no_baseline_cannot_say(self):
        rc, r = self.ratchet()
        self.assertEqual((rc, r["red"], r["baseline"], r["ok"]), (2, 5, None, False))

    def test_the_count_only_falls(self):
        rc, out = self.practices("--lower")
        self.assertEqual(rc, 0, out)
        self.assertIn("baseline none -> 5", out)
        self.assertEqual(self.ratchet(), (0, {"red": 5, "baseline": 5, "ok": True, "why": None}))
        self.assertEqual(self.ratchet(live=True)[1]["red"], 5)          # the live run reads what --from reads
        block = json.loads(self.reg.read_text())
        block["practices"]["rows"].append({"id": "new-rule", "part": "B", "principle": "root-x", "rule": "a new rule",
                                           "sources": ["PLAN-x.md §5"], "applies": "all",
                                           "held": {"kind": "prose", "text": "prose"}, "status": "live"})
        self.reg.write_text(json.dumps(block))
        rc, r = self.ratchet()
        self.assertEqual((rc, r["red"], r["ok"]), (1, 7, False))
        rc, out = self.practices()
        self.assertEqual(rc, 1)
        self.assertIn("baseline 5 -> RISEN", out)
        rc, out = self.practices("--lower")
        self.assertEqual(rc, 1)
        self.assertIn("refused: 7 red cell(s) is above the baseline 5", out)
        self.assertEqual(json.loads(self.base.read_text())["red"], 5)

    def test_a_held_check_lowers_the_count(self):
        self.practices("--lower")
        _src(self, {"hooks-installed": "ok"})
        p = run_cli("all", self.ws, "--source", self.src, "--json")
        write(self.report, p.stdout)
        rc, r = self.ratchet()
        self.assertEqual((rc, r["red"]), (0, 3))
        rc, out = self.practices("--lower")
        self.assertIn("baseline 5 -> 3", out)

    def test_text_lists_rows_gates_and_blocked(self):
        rc, out = self.practices()
        self.assertIn("rules-classified", out)
        self.assertIn("[rules-gated]", out)
        self.assertIn("unjustified  2", out)
        self.assertIn("C1   root-y", out)

    def test_an_invalid_registry_gives_no_cells(self):
        block = json.loads(self.reg.read_text())
        block["practices"]["rows"][1]["principle"] = "nowhere"
        self.reg.write_text(json.dumps(block))
        rc, out = self.practices()
        self.assertEqual(rc, 2)
        self.assertIn("INVALID  practice 'rules-classified'", out)


class RowsView(_Workspace):
    """`checks practices --rows` (tl-564, todo's brief reads it): the rows a
    measured run prints, with no check run, no cells and no ratchet."""

    def rows_view(self, *extra):
        p = run_cli("practices", self.ws, "--rows", "--source", self.src, "--registry", self.reg, *extra)
        return p.returncode, p.stdout, p.stderr

    def marked(self):
        """Both checks the rows name, each leaving a marker when it runs."""
        self.marks = self.tmp / "marks"
        self.marks.mkdir()
        for name in ("rules-gated", "hooks-installed"):
            self.add_check(name, f"touch {self.marks / name}; exit 0")

    def test_no_run_where_a_live_run_runs(self):
        self.marked()
        rc, out, err = self.rows_view("--json")
        self.assertEqual(rc, 0, err)
        self.assertEqual(sorted(p.name for p in self.marks.iterdir()), [])     # nothing ran
        view = json.loads(out)
        self.assertEqual(sorted(view), ["blocked", "notes", "rows"])
        # the counterfactual: the same call without --rows runs both checks and adds what a run measures
        p = run_cli("practices", self.ws, "--json", "--source", self.src, "--registry", self.reg,
                    "--baseline", self.base)
        live = json.loads(p.stdout[:p.stdout.rindex("}") + 1])
        self.assertEqual(sorted(p.name for p in self.marks.iterdir()), ["hooks-installed", "rules-gated"])
        self.assertTrue({"measured", "locations", "ratchet"} <= set(live))
        self.assertTrue(any("cells" in r for r in live["rows"]))
        self.assertNotEqual(view["rows"], live["rows"])
        stripped = [{k: v for k, v in r.items() if k not in ("counts", "cells")} for r in live["rows"]]
        self.assertEqual(view["rows"], stripped)                                # the same rows, by meaning
        self.assertEqual(view["blocked"], live["blocked"])

    def test_the_rows_todo_reads(self):
        rc, out, err = self.rows_view("--json")
        rows = json.loads(out)["rows"]
        self.assertEqual([r["id"] for r in rows], [r["id"] for r in fx.ROWS])
        for r in rows:
            self.assertTrue({"id", "status"} <= set(r), r)
            self.assertNotIn("cells", r)          # ask-first carries recorded cells in the registry
            if r["status"] == "live":
                self.assertIsInstance(r["held"], dict)
                self.assertIn("applies", r)
        self.assertIn("cells", next(r for r in fx.ROWS if r["id"] == "ask-first"))

    def test_one_row_live_or_not(self):
        rc, out, _ = self.rows_view("--json", "--row", "old-rule")
        self.assertEqual((rc, [r["id"] for r in json.loads(out)["rows"]]), (0, ["old-rule"]))
        rc, _, err = self.rows_view("--row", "nowhere")
        self.assertEqual(rc, 2)
        self.assertIn("no row 'nowhere'", err)

    def test_an_ignored_input_is_refused(self):
        for extra, flag in [(("--from", self.report), "--from"), (("--lower", "--baseline", self.base), "--lower"),
                            (("--import", self.tmp / "P.md"), "--import"), (("--names", "a"), "--names")]:
            rc, out, err = self.rows_view(*extra)
            self.assertEqual((rc, out), (2, ""), extra)
            self.assertIn(f"{flag}", err)
            self.assertIn("would be ignored", err)
        self.assertFalse(self.base.exists())

    def test_text_says_not_measured(self):
        rc, out, _ = self.rows_view()
        self.assertEqual(rc, 0)
        self.assertIn("rules-classified", out)
        self.assertIn("[rules-gated]", out)
        self.assertIn("not measured: no check run", out)
        self.assertNotIn("ratchet", out)

    def test_an_invalid_registry_gives_no_rows(self):
        block = json.loads(self.reg.read_text())
        block["practices"]["rows"][1]["principle"] = "nowhere"
        self.reg.write_text(json.dumps(block))
        rc, out, err = self.rows_view("--json")
        self.assertEqual((rc, out), (2, ""))
        self.assertIn("no rows from an invalid registry", err)


@unittest.skipUnless(WORKSPACE, "this tool is not in a tools/ folder")
class RealRegistry(unittest.TestCase):
    def test_keys_are_the_row_keys(self):
        block, faults = practices.load()
        self.assertEqual(faults, [])
        self.assertEqual(list(block["keys"]), list(practices.ROW_KEYS))

    def test_validates_against_the_workspace(self):
        block, _ = practices.load()
        findings, notes = practices.validate(block, WORKSPACE)
        self.assertEqual(findings, [])
        self.assertGreater(len(practices.live(block["rows"])), 0)

    def test_rows_view_serves_every_row(self):
        """The call todo's brief makes (tl-564): every registry row, shown, no run."""
        block, _ = practices.load()
        p = run_cli("practices", "--rows", "--json")
        self.assertEqual(p.returncode, 0, p.stderr[-400:])
        self.assertEqual(json.loads(p.stdout)["rows"], [practices.shown(r) for r in block["rows"]])


if __name__ == "__main__":
    unittest.main()
