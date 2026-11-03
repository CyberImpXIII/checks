"""`checks assess <path> --subject repo|candidate` (checkslib/assess.py,
PLAN-services.md §3 X1-X2, §4 step 9.2), through the CLI:

  - each subject has a passing fixture (exit 0, every cell held or justified,
    no gap) and a failing one (exit 1, the gap named with its row);
  - repo: the cells are the ones `checks practices` earns at that location
    (one reading), rows without a subject listed as `other`, principles
    rolled up apart, a folder `checks all` does not walk refused;
  - candidate: only rows with a subject; the X1 gates: a declared verb with
    no probe is `unjustified`, a write the sandbox refused (the probe's
    non-zero exit) is `unjustified`, a seam row only justified is a gap while
    a behaviour row justified is not; no evidence is every cell unknown; a
    record never overrides a probe; evidence for another pin, naming a row
    that is no subject row, or breaking its schema is refused (exit 2) and
    no cell is read from it; --evidence changes the answer;
  - one registry: a row planted in it shows in both subjects;
  - an input a subject would ignore is refused;
  - an invalid registry gives no cells.
assess is not a cli.json read verb yet (TODO.md "checks assess"): it would
need a `read.fixture`, which the other read verbs would then run against."""
import json
import unittest

from tests.helpers import Case, TOOL_ROOT, WORKSPACE, repo, run_cli, write
from tests.test_practices import fx, _src

PIN = "fixture-pin-1"


def rows_passing():
    """root-x, a seam row held by rules-gated, a behaviour row read through
    hooks-installed, a prose row recorded justified at r: nothing red."""
    return [json.loads(json.dumps(r)) for r in fx.ROWS if r["id"] in ("root-x", "rules-classified", "no-blobs", "ask-first")]


class _Assess(Case):
    def build(self, rows, checks):
        self.ws = fx._ws(self.tmp, rows)
        repo(self.ws / "r", {"gates.json": json.dumps({"rules": [{"id": "friday"}]}) + "\n"})
        _src(self, checks)
        self.reg = self.ws / "reg" / "gates.json"

    def assess(self, path, subject, *extra):
        p = run_cli("assess", path, "--subject", subject, "--root", self.ws, "--source", self.src,
                    "--registry", self.reg, *extra)
        return p

    def json(self, path, subject, *extra):
        p = self.assess(path, subject, "--json", *extra)
        self.assertIn(p.returncode, (0, 1), p.stderr)
        return p.returncode, json.loads(p.stdout)

    def cells(self, rep):
        return {r["id"]: r["cell"]["state"] for r in rep["rows"]}


# ---------------------------------------------------------------- repo

class Repo(_Assess):
    def test_passing_fixture(self):
        self.build(rows_passing(), {"rules-gated": "ok", "hooks-installed": "ok"})
        rc, rep = self.json(self.ws / "r", "repo")
        self.assertEqual(rc, 0, rep)
        self.assertEqual((rep["subject"], rep["location"], rep["gaps"]), ("repo", "r", []))
        self.assertEqual(self.cells(rep), {"root-x": "held", "rules-classified": "held", "no-blobs": "held",
                                           "ask-first": "justified"})
        self.assertEqual(rep["groups"], {"seam": ["rules-classified"], "behaviour": ["no-blobs"],
                                         "other": ["ask-first"], "principles": ["root-x"]})
        self.assertEqual(rep["counts"], {"held": 2, "justified": 1, "unjustified": 0, "unknown": 0})

    def test_failing_fixture(self):
        self.build(fx.ROWS, {"rules-gated": "ok", "hooks-installed": "fail"})
        rc, rep = self.json(self.ws / "r", "repo")
        self.assertEqual(rc, 1)
        c = self.cells(rep)
        self.assertEqual((c["no-blobs"], c["verbs-later"], c["own-r"], c["root-x"]),
                         ("unjustified", "unknown", "unknown", "unjustified"))
        self.assertEqual(rep["gaps"], ["no-blobs", "verbs-later", "own-r"])     # principles never a gap
        self.assertNotIn("old-rule", c)                                       # not live
        p = self.assess(self.ws / "r", "repo")
        self.assertEqual(p.returncode, 1)
        self.assertRegex(p.stdout, r"no-blobs +unjustified +GAP hooks-installed FAIL")
        self.assertIn("\nseam (1 row(s); bar: held (a seam row must be gated))", p.stdout)
        self.assertIn("3 gap(s): no-blobs, verbs-later, own-r", p.stdout)

    def test_the_cells_are_checks_practices_cells(self):
        self.build(fx.ROWS, {"rules-gated": "fail", "hooks-installed": "ok"})
        _, rep = self.json(self.ws / "r", "repo")
        p = run_cli("practices", self.ws, "--json", "--source", self.src, "--registry", self.reg,
                    "--baseline", self.tmp / "b.json")
        live = json.loads(p.stdout[:p.stdout.rindex("}") + 1])
        theirs = {r["id"]: r["cells"]["r"] for r in live["rows"] if "r" in r.get("cells", {})}
        self.assertEqual({r["id"]: r["cell"] for r in rep["rows"]}, theirs)
        self.assertEqual(self.cells(rep)["rules-classified"], "unjustified")   # the input reached the cell

    def test_the_top_takes_only_its_rows(self):
        self.build(fx.ROWS, {"rules-gated": "ok", "hooks-installed": "ok"})
        _, rep = self.json(self.ws, "repo")
        self.assertEqual(rep["location"], ".")
        self.assertNotIn("ask-first", self.cells(rep))                         # applies: [r]
        self.assertNotIn("own-r", self.cells(rep))

    def test_a_folder_checks_all_does_not_walk_is_refused(self):
        self.build(fx.ROWS, {"rules-gated": "ok", "hooks-installed": "ok"})
        p = self.assess(self.ws / "docs", "repo")
        self.assertEqual((p.returncode, p.stdout), (2, ""))
        self.assertIn("docs is not a location `checks all` walks", p.stderr)


# ---------------------------------------------------------------- candidate

class _CandidateCase(_Assess):
    def setUp(self):
        super().setUp()
        self.build(fx.ROWS, {"rules-gated": "ok", "hooks-installed": "ok"})
        self.c = self.tmp / "cand"
        write(self.c / "candidate.json", json.dumps({"name": "tool", "sha256": PIN, "verbs": ["build", "query"]}))
        write(self.c / "probes" / "verbs.sh", "#!/bin/sh\n", 0o755)
        write(self.c / "probes" / "write.sh", "#!/bin/sh\n", 0o755)

    def evidence(self, probes=(), records=(), pin=PIN, path=None):
        return write(path or self.c / "assess.json", json.dumps({"pin": pin, "probes": list(probes), "records": list(records)}))

    def probe(self, row, verb=None, exit=0, line="fine", probe="probes/verbs.sh"):
        e = {"row": row, "probe": probe, "exit": exit, "lines": [line]}
        if verb:
            e["verb"] = verb
        return e

    PASSING = property(lambda self: ([self.probe("rules-classified", "build"), self.probe("rules-classified", "query")],
                                     [{"row": "no-blobs", "state": "justified", "why": "it prints no shell"}]))


class Candidate(_CandidateCase):
    def test_passing_fixture(self):
        self.evidence(*self.PASSING)
        rc, rep = self.json(self.c, "candidate")
        self.assertEqual(rc, 0, rep)
        self.assertEqual(self.cells(rep), {"root-x": "held", "rules-classified": "held", "no-blobs": "justified"})
        self.assertEqual(rep["groups"], {"seam": ["rules-classified"], "behaviour": ["no-blobs"], "principles": ["root-x"]})
        self.assertEqual((rep["gaps"], rep["candidate"]["pin"], rep["candidate"]["verbs"]), ([], PIN, ["build", "query"]))
        self.assertIn("verbs build, query", rep["rows"][1]["cell"]["why"])

    def test_failing_fixture_a_declared_verb_with_no_probe(self):
        """X1 gate: a planted candidate lacking a probe for one declared verb shows that row unjustified."""
        self.evidence([self.probe("rules-classified", "build")], self.PASSING[1])
        rc, rep = self.json(self.c, "candidate")
        self.assertEqual((rc, rep["gaps"]), (1, ["rules-classified"]))
        cell = rep["rows"][1]["cell"]
        self.assertEqual(cell["state"], "unjustified")
        self.assertIn("no probe for declared verb(s) query", cell["why"])
        p = self.assess(self.c, "candidate")
        self.assertEqual(p.returncode, 1)
        self.assertRegex(p.stdout, r"rules-classified +unjustified +GAP no probe for declared verb\(s\) query")

    def test_a_write_the_sandbox_refused_is_the_gap(self):
        """X1 gate: the sandbox blocks the write; the probe's refusal is the evidence."""
        write_probe = self.probe("rules-classified", exit=1, line="sandbox: write to ../x denied", probe="probes/write.sh")
        self.evidence([write_probe], self.PASSING[1])
        rc, rep = self.json(self.c, "candidate")
        self.assertEqual((rc, rep["gaps"]), (1, ["rules-classified"]))
        self.assertEqual(rep["rows"][1]["cell"]["why"], "probe probes/write.sh exit 1: sandbox: write to ../x denied")

    def test_the_bar_is_per_subject(self):
        why = "the wrapper holds it"
        self.evidence([], [{"row": "rules-classified", "state": "justified", "why": why},
                           {"row": "no-blobs", "state": "justified", "why": why}])
        rc, rep = self.json(self.c, "candidate")
        self.assertEqual(self.cells(rep), {"root-x": "held", "rules-classified": "justified", "no-blobs": "justified"})
        self.assertEqual((rc, rep["gaps"]), (1, ["rules-classified"]))           # a seam row must be gated

    def test_no_evidence_is_every_cell_unknown(self):
        rc, rep = self.json(self.c, "candidate")
        self.assertEqual((rc, set(self.cells(rep).values()), rep["evidence"]), (1, {"unknown"}, None))
        self.assertIn("no evidence at", rep["notes"][0])
        self.assertNotIn("ask-first", self.cells(rep))                         # no subject: not a candidate's row
        self.assertNotIn("verbs-later", self.cells(rep))

    def test_a_record_never_overrides_a_probe(self):
        probes, _ = self.PASSING
        self.evidence(probes + [self.probe("no-blobs", exit=3, line="it ran a shell")],
                      [{"row": "no-blobs", "state": "justified", "why": "says so"}])
        _, rep = self.json(self.c, "candidate")
        cell = rep["rows"][2]["cell"]
        self.assertEqual((cell["state"], cell["note"]), ("unjustified", "recorded justified not used: the probe decided"))

    def test_unusable_evidence_is_refused_whole(self):
        probes, records = self.PASSING
        for label, kw, want in [
            ("another pin", dict(pin="old-pin"), "`old-pin` is not candidate.json's pin `fixture-pin-1`"),
            ("no such row", dict(records=records + [{"row": "ask-first", "state": "justified", "why": "w"}]),
             "row `ask-first` is no live practice row with a subject"),
            ("schema", dict(probes=[dict(probes[0], exit="0")]), "schema: $.probes[0].exit"),
            ("undeclared verb", dict(probes=[self.probe("rules-classified", "zap")]), "`zap` is not a verb candidate.json lists"),
        ]:
            with self.subTest(label):
                self.evidence(**dict(dict(probes=probes, records=records), **kw))
                p = self.assess(self.c, "candidate")
                self.assertEqual((p.returncode, p.stdout), (2, ""), p.stderr)
                self.assertIn("the evidence is unusable, so no cell is read from it", p.stderr)
                self.assertIn(want, p.stderr)

    def test_evidence_flag_changes_the_answer(self):
        self.evidence(*self.PASSING)
        other = self.evidence([], [], path=self.tmp / "elsewhere.json")
        rc, rep = self.json(self.c, "candidate", "--evidence", other)
        self.assertEqual((rc, rep["evidence"]), (1, str(other)))
        self.assertEqual(set(self.cells(rep).values()), {"unknown"})
        self.assertEqual(self.json(self.c, "candidate")[0], 0)                  # without it: the folder's assess.json
        p = self.assess(self.c, "candidate", "--evidence", self.tmp / "none.json")
        self.assertEqual(p.returncode, 2)
        self.assertIn("no such file", p.stderr)

    def test_not_a_candidate_folder(self):
        p = self.assess(self.tmp / "src", "candidate")
        self.assertEqual(p.returncode, 2)
        self.assertIn("no candidate.json", p.stderr)


class OneRegistry(_CandidateCase):
    def test_a_planted_row_shows_in_both_subjects(self):
        block = json.loads(self.reg.read_text())
        block["practices"]["rows"].append({"id": "planted", "part": "B", "principle": "root-x", "rule": "a new rule",
                                           "sources": ["PLAN-x.md §5"], "applies": "all", "subject": ["behaviour"],
                                           "held": {"kind": "prose", "text": "prose"}, "status": "live"})
        self.reg.write_text(json.dumps(block))
        _, cand = self.json(self.c, "candidate")
        _, rep = self.json(self.ws / "r", "repo")
        for r in (cand, rep):
            self.assertIn("planted", r["groups"]["behaviour"])
            self.assertEqual(self.cells(r)["planted"], "unknown")

    def test_an_ignored_input_is_refused(self):
        for path, subject, extra, flag in [(self.c, "candidate", ("--names", "a"), "--names"),
                                           (self.ws / "r", "repo", ("--evidence", self.c / "assess.json"), "--evidence")]:
            p = self.assess(path, subject, *extra)
            self.assertEqual((p.returncode, p.stdout), (2, ""), extra)
            self.assertIn(f"{flag} would be ignored", p.stderr)

    def test_an_invalid_registry_gives_no_cells(self):
        block = json.loads(self.reg.read_text())
        block["practices"]["rows"][1]["principle"] = "nowhere"
        self.reg.write_text(json.dumps(block))
        p = self.assess(self.c, "candidate")
        self.assertEqual((p.returncode, p.stdout), (2, ""))
        self.assertIn("no cells from an invalid registry", p.stderr)


@unittest.skipUnless(WORKSPACE, "this tool is not in a tools/ folder")
class RealRegistry(Case):
    def test_a_candidate_gets_every_subject_row_of_the_real_registry(self):
        """The default registry (gates.json here) is the one read: every live
        part-B/C row with a subject, and no other, is a candidate row."""
        block = json.loads((TOOL_ROOT / "gates.json").read_text())["practices"]
        want = [r["id"] for r in block["rows"] if r.get("subject") and r.get("part") != "A"
                and r.get("status") == "live"]
        self.assertTrue(want)
        c = self.tmp / "cand"
        write(c / "candidate.json", json.dumps({"name": "t", "sha256": PIN, "verbs": ["v"]}))
        p = run_cli("assess", c, "--subject", "candidate", "--json")
        self.assertEqual(p.returncode, 1, p.stderr)
        rep = json.loads(p.stdout)
        self.assertEqual([r["id"] for r in rep["rows"] if r["part"] != "A"], want)
        self.assertEqual(rep["gaps"], want)


if __name__ == "__main__":
    unittest.main()
