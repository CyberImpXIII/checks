"""checkslib/parts.py, the one shared suite runner (PLAN-small-tasks.md §3, §7):
every fault in a parts file refused; what a part's hash reads, each input shown
to change it (or shown not to, where the header says so); each part's result
on disk as it ends; --resume skipping only unchanged passed parts, and each
refusal to resume said; a timeout stopping the part's whole tree; a TERM
leaving the file `failed` and the rest `unchecked`; the text summary and the
--json document (validated by checkjson) green and red; the copy loading
nothing beside it; and this repo's check.parts.json held to its test modules.
The pool (PLAN-check-progress.md §10 step 1): two parts sharing a `uses` value
never overlap and a `serial` part runs alone (each beside its counterfactual,
the same parts without it overlapping); --jobs bounds the pool; a failing part
stops no other; the report is in the file's order, not the order parts end;
--jobs 1 prints what the one-at-a-time runner (1.3.0) printed; the `time:`
line's numbers move with their inputs.
check-partial (tests/test_check_partial.py) holds the same runner from outside."""
import ast
import json
import os
import re
import signal
import subprocess
import sys
import time

from tests.helpers import Case, TOOL_ROOT, write
from checkslib import checkjson, parts

PARTS = TOOL_ROOT / "checkslib" / "parts.py"
# The last one-at-a-time runner (1.3.0), what `--jobs 1` is held to.
ONE_AT_A_TIME = "c1a4a6e"
# A part that holds `lock` for 1.5s, and says `clash` when another holds it.
HOLD = "if mkdir lock 2>/dev/null; then sleep 1.5; rmdir lock; else echo clash >> clashes; sleep 1.5; fi"


def part(name, run="true", files=("a.txt",), **kw):
    return dict({"name": name, "run": run, "files": list(files), "timeout_s": 30}, **kw)


class Parts(Case):
    def setUp(self):
        super().setUp()
        self.base = self.tmp / "suite"
        write(self.base / "a.txt", "a\n")
        write(self.base / "b.txt", "b\n")
        self.pf = self.tmp / "progress" / "check.json"

    def run_parts(self, doc, *flags, env=None, timeout=120):
        path = write(self.base / "parts.json", json.dumps(doc) if not isinstance(doc, str) else doc)
        e = {k: v for k, v in os.environ.items() if k not in ("PROGRESS_FILE", "PARTS_MAX_AGE", "PARTS_RUNTIME")}
        e["PROGRESS_FILE"] = str(self.pf)
        e.update(env or {})
        return subprocess.run([sys.executable, str(PARTS), "run", str(path), *flags], capture_output=True, text=True,
                              env=e, stdin=subprocess.DEVNULL, timeout=timeout)

    def progress(self):
        return json.loads(self.pf.read_text())

    def faults(self, doc):
        return parts.check(doc, str(self.base))[1]

    # ---- the parts file ----------------------------------------------------

    def test_a_good_file_has_no_fault_and_merges_defaults(self):
        doc = {"defaults": {"files": ["b.txt"], "except": ["x/"], "timeout_s": 5, "role": "code"},
               "parts": [part("p1", timeout_s=9), {"name": "p2", "run": "true", "always": "reads the world"}]}
        got, faults = parts.check(doc, str(self.base))
        self.assertEqual(faults, [])
        self.assertEqual((got[0]["files"], got[0]["except"], got[0]["timeout_s"], got[0]["role"]),
                         (["b.txt", "a.txt"], ["x/"], 9, "code"))
        self.assertEqual((got[1]["files"], got[1]["timeout_s"], got[1]["always"]), (["b.txt"], 5, "reads the world"))

    def test_each_fault_is_refused_by_itself(self):
        cases = {
            "unknown top-level key `part`": {"part": [], "parts": [part("p")]},
            "defaults: unknown key `run`": {"defaults": {"run": "x"}, "parts": [part("p")]},
            "`parts` is not a non-empty list": {"parts": []},
            "is not [A-Za-z0-9._-]+": {"parts": [part("a b")]},
            "the name is used twice": {"parts": [part("p"), part("p")]},
            "part p: unknown key `timeout`": {"parts": [dict(part("p"), timeout=3)]},
            "part p: `run` is not a non-empty command": {"parts": [part("p", run=" ")]},
            "part p: no `timeout_s` above 0": {"parts": [dict(part("p"), timeout_s=0)]},
            "starts with ~": {"parts": [part("p", files=["~/x"])]},
            "no `files` and no `always`": {"parts": [part("p", files=[])]},
            "part p: `always` must say why": {"parts": [part("p", always="")]},
            "part p: `files` names nope.txt, which does not exist": {"parts": [part("p", files=["nope.txt"])]},
            "defaults: `timeout_s` is not a number above 0": {"defaults": {"timeout_s": True}, "parts": [part("p")]},
            "part p: `files` is not a list of non-empty strings": {"parts": [dict(part("p", always="x"), files="a.txt")]},
            "part p: `uses` is not a list of non-empty strings": {"parts": [part("p", uses="serial")]},
            "part p: `uses` value 'Serial' is not browser, serial or store:<name>": {"parts": [part("p", uses=["Serial"])]},
            "part p: `uses` value 'store:' is not": {"parts": [part("p", uses=["store:"])]},
            "defaults: unknown key `uses`": {"defaults": {"uses": ["serial"]}, "parts": [part("p")]},
        }
        for want, doc in cases.items():
            with self.subTest(fault=want):
                got = self.faults(doc)
                self.assertEqual(len(got), 1, got)
                self.assertIn(want, got[0])

    def test_validate_and_a_refused_run(self):
        bad = write(self.base / "bad.json", json.dumps({"parts": [part("p", files=["nope.txt"])]}))
        p = subprocess.run([sys.executable, str(PARTS), "validate", str(bad)], capture_output=True, text=True)
        self.assertEqual((p.returncode, p.stdout.count("\n")), (1, 1), p.stdout)
        r = self.run_parts({"parts": [part("p", files=["nope.txt"])]}, "--json")
        self.assertEqual(r.returncode, 2)
        self.assertEqual(checkjson.validate(r.stdout, r.returncode), [])
        doc = json.loads(r.stdout)
        self.assertEqual((doc["ok"], doc["checks"][0]["name"], doc["checks"][0]["status"]), (False, "parts-file", "error"))
        self.assertFalse(self.pf.exists(), "a refused file runs nothing and writes nothing")
        r = self.run_parts("{not json", "--json")
        self.assertEqual((r.returncode, json.loads(r.stdout)["ok"]), (2, False))
        r = self.run_parts({"parts": [part("p")]}, "--bogus")
        self.assertEqual(r.returncode, 2)
        self.assertIn("unknown option --bogus", r.stderr)

    # ---- the hash ------------------------------------------------------------

    def h(self, p, **kw):
        merged = parts.check({"parts": [p]}, str(self.base))
        self.assertEqual(merged[1], [])
        return parts.part_hash(str(self.base), merged[0][0], **kw)

    def test_each_input_changes_the_hash(self):
        write(self.base / "d" / "x.txt", "x\n")
        write(self.base / "d" / "skip" / "y.txt", "y\n")
        write(self.base / "d" / "s.sh", "echo\n")
        p = part("p", files=["d"], **{"except": ["d/skip"], "shape": ["d/*.sh"]})
        h0 = self.h(p)
        self.assertEqual(self.h(p), h0, "the same tree hashes the same")
        write(self.base / "d" / "skip" / "y.txt", "changed\n")
        self.assertEqual(self.h(p), h0, "an `except` file is not read")
        write(self.base / "d" / "s.sh", "echo changed\n")
        self.assertEqual(self.h(p), h0, "a `shape` file's content is not read")
        os.chmod(self.base / "d" / "s.sh", 0o755)
        h1 = self.h(p)
        self.assertNotEqual(h1, h0, "a `shape` file's executable bit is")
        write(self.base / "d" / "x.txt", "changed\n")
        h2 = self.h(p)
        self.assertNotEqual(h2, h1, "a content file's content is")
        write(self.base / "d" / "new.txt", "new\n")
        h3 = self.h(p)
        self.assertNotEqual(h3, h2, "a new file is")
        self.assertNotEqual(self.h(dict(p, run="false")), h3, "the definition is")
        os.environ["PARTS_RUNTIME"] = "other"
        try:
            self.assertNotEqual(self.h(p), h3, "the runtime is")
        finally:
            del os.environ["PARTS_RUNTIME"]
        self.assertEqual(self.h(p), h3)
        self.assertEqual(self.h(dict(p, timeout_s=99, role="x", uses=["serial"])), h3, "timeout_s, role and uses are not")

    def test_a_named_file_counts_by_content_whatever_shape_says(self):
        write(self.base / "s.sh", "1\n")
        p = part("p", files=["s.sh"], shape=["*.sh"])
        h0 = self.h(p)
        write(self.base / "s.sh", "2\n")
        self.assertNotEqual(self.h(p), h0)

    def test_a_folder_in_git_reads_tracked_and_untracked_but_not_ignored(self):
        subprocess.run(["git", "init", "-q", str(self.base)], check=True)
        write(self.base / ".gitignore", "junk/\n")
        p = part("p", files=["."])
        h0 = self.h(p)
        write(self.base / "junk" / "x", "1\n")
        self.assertEqual(self.h(p), h0, "an ignored file is not read")
        write(self.base / "new.txt", "1\n")
        self.assertNotEqual(self.h(p), h0, "an untracked file is")

    def test_the_progress_file_and_logs_are_in_no_hash(self):
        prog = parts.Progress(str(self.base / ".progress" / "check.json"), "check")
        p = part("p", files=["."])
        h0 = self.h(p, ignored=prog.ignored)
        write(self.base / ".progress" / "check.json", "{}")
        write(self.base / ".progress" / ".check.json.abc123", "{}")
        write(self.base / ".progress" / "check.json.logs" / "p.log", "out")
        self.assertEqual(self.h(p, ignored=prog.ignored), h0)
        write(self.base / ".progress" / "other.json", "{}")
        self.assertNotEqual(self.h(p, ignored=prog.ignored), h0, "only the run's own files are ignored")

    def test_files_lists_what_the_hash_reads(self):
        write(self.base / "d" / "x.txt", "x\n")
        write(self.base / "d" / "s.sh", "x\n")
        path = write(self.base / "parts.json", json.dumps({"parts": [
            part("p", files=["d", "a.txt"], shape=["*.sh"], always="because")]}))
        p = subprocess.run([sys.executable, str(PARTS), "files", str(path), "p"], capture_output=True, text=True)
        self.assertEqual(p.stdout.splitlines(), ["content a.txt", "shape d/s.sh", "content d/x.txt", "always: because"])
        p = subprocess.run([sys.executable, str(PARTS), "files", str(path), "q"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)

    # ---- a run -------------------------------------------------------------

    def test_green_text_and_json(self):
        doc = {"parts": [part("p1"), part("p2", files=["b.txt"])]}
        r = self.run_parts(doc)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        lines = r.stdout.splitlines()
        self.assertTrue(lines[0].startswith("ok    p1 ("), lines)
        self.assertEqual(lines[-1], "check: 2 of 2 passed")
        r = self.run_parts(doc, "--json")
        self.assertEqual(checkjson.validate(r.stdout, r.returncode), [])
        self.assertEqual([(c["name"], c["status"]) for c in json.loads(r.stdout)["checks"]], [("p1", "ok"), ("p2", "ok")])
        st = self.progress()
        self.assertEqual((st["state"], sorted(st["passed_steps"]), st["step"], st["total"], st["cmd"], st["runner"]),
                         ("passed", ["p1", "p2"], 2, 2, "parts", parts.VERSION))
        self.assertEqual((st["jobs"], st["running"], sorted(st["times"])), (parts.default_jobs(), [], ["p1", "p2"]))
        self.assertTrue(all(t["start"] <= t["end"] for t in st["times"].values()), st["times"])

    def test_red_names_each_failed_part_and_its_fail_lines(self):
        doc = {"defaults": {"role": "code"}, "parts": [
            part("p1", run="echo 'FAIL: test_one (x)'; echo 'ERROR: test_two'; exit 1"),
            part("p2"),
            part("p3", run="echo last words; exit 4")]}
        r = self.run_parts(doc)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stdout.splitlines()[-1],
                         "check: 1 of 3 passed; failed: p1 (exit 1: FAIL: test_one (x)); p3 (exit 4; last output: last words)")
        self.assertIn("  ERROR: test_two", r.stdout.splitlines())
        r = self.run_parts(doc, "--json")
        self.assertEqual(checkjson.validate(r.stdout, r.returncode), [])
        c = json.loads(r.stdout)["checks"]
        self.assertEqual([x["status"] for x in c], ["fail", "ok", "fail"])
        self.assertEqual([f["message"] for f in c[0]["failures"]], ["FAIL: test_one (x)", "ERROR: test_two"])
        self.assertEqual(c[0]["failures"][0]["role"], "code")
        st = self.progress()
        self.assertEqual((st["state"], st["passed_steps"], sorted(st["failed_names"])), ("failed", ["p2"], ["p1", "p3"]))

    def test_exit_3_is_unchecked_and_any_other_exit_is_a_fail(self):
        """The exit code alone turns the status: 3 unchecked (green run), 4 fail (red)."""
        def doc(code):
            return {"parts": [part("p1"), part("p2", run=f"echo 'no sibling repo here'; exit {code}")]}
        r = self.run_parts(doc(3))
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("UNCHK p2 (exit 3, ", r.stdout)
        self.assertEqual(r.stdout.splitlines()[-1], "check: 1 of 2 passed; unchecked: p2 (no sibling repo here)")
        st = self.progress()
        self.assertEqual((st["state"], st["passed_steps"], st["failed_names"], st["step"]), ("passed", ["p1"], [], 2))
        self.assertNotIn("p2", st["hashes"], "an unchecked part is never kept for --resume")
        r = self.run_parts(doc(3), "--json")
        self.assertEqual((r.returncode, checkjson.validate(r.stdout, r.returncode)), (0, []))
        p2 = json.loads(r.stdout)["checks"][1]
        self.assertEqual((p2["status"], p2["reason"], p2["failures"]), ("unchecked", "exit 3: no sibling repo here", []))
        r = self.run_parts(doc(4), "--json")
        self.assertEqual(r.returncode, 1)
        self.assertEqual(json.loads(r.stdout)["checks"][1]["status"], "fail")
        r = self.run_parts(doc(3), "--resume")
        self.assertIn("re-running 1 of 2: p2", r.stdout.splitlines()[0])

    def test_a_fail_line_naming_a_real_file_fills_file_and_line_else_null(self):
        (self.base / "src").mkdir()
        write(self.base / "src" / "x.py", "a\nb\n")
        lines = ["FAIL src/x.py:2 the second row is wrong",       # a file inside: filled
                 "ERROR: src/x.py:12: past its end, still the file",
                 "FAIL src/gone.py:3 not there",                  # no such file: null
                 "FAIL 2026-10-12T10:30 at a time",               # a time, not a place: null
                 "FAIL ../outside.py:1 outside the repo",          # outside: null
                 "FAIL: test_one (tests.x)"]                      # no location: null
        write(self.base.parent / "outside.py", "x\n")
        run = "; ".join(f"echo '{l}'" for l in lines) + "; exit 1"
        r = self.run_parts({"parts": [part("p1", run=run)]}, "--json")
        self.assertEqual(checkjson.validate(r.stdout, r.returncode), [])
        got = [(f["file"], f["line"]) for f in json.loads(r.stdout)["checks"][0]["failures"]]
        self.assertEqual(got, [("src/x.py", 2), ("src/x.py", 12), (None, None), (None, None), (None, None), (None, None)])

    def test_each_result_is_on_disk_before_the_next_part_runs(self):
        doc = {"parts": [part("p1"), part("p2", run='cp "$PROGRESS_FILE" seen.json')]}
        self.assertEqual(self.run_parts(doc, "--jobs", "1").returncode, 0)
        seen = json.loads((self.base / "seen.json").read_text())
        self.assertEqual((seen["passed_steps"], seen["label"], seen["state"], seen["pid"] > 0, seen["running"]),
                         (["p1"], "p2", "running", True, ["p2"]))

    def test_in_a_pool_each_result_is_on_disk_as_it_ends_not_at_the_end(self):
        """p2 runs beside p1 and waits (20s at most) to see p1's pass in the
        progress file while it still runs itself."""
        wait = ('n=0; while [ $n -lt 200 ]; do grep -q \'"passed_steps": \\["p1"\\]\' "$PROGRESS_FILE" && '
                '{ cp "$PROGRESS_FILE" seen.json; exit 0; }; sleep 0.1; n=$((n+1)); done; exit 1')
        doc = {"parts": [part("p1"), part("p2", run=wait)]}
        r = self.run_parts(doc, "--jobs", "2")
        self.assertEqual(r.returncode, 0, r.stdout)
        seen = json.loads((self.base / "seen.json").read_text())
        self.assertEqual((seen["state"], seen["running"], "end" in seen["times"]["p1"], "end" in seen["times"]["p2"]),
                         ("running", ["p2"], True, False))

    def test_a_progress_file_that_cannot_be_written_is_said_once_and_changes_nothing(self):
        r = self.run_parts({"parts": [part("p1"), part("p2")]}, env={"PROGRESS_FILE": "/dev/null/x/check.json"})
        self.assertEqual(r.returncode, 0)
        self.assertEqual(r.stderr.count("cannot write the progress file"), 1, r.stderr)

    def test_a_timeout_stops_the_whole_tree_and_the_next_part_runs(self):
        doc = {"parts": [part("p1", run="(sleep 60 & echo $! > kid.pid; wait) ; echo never", timeout_s=1),
                         part("p2", run="touch p2.ran")]}
        t0 = time.monotonic()
        r = self.run_parts(doc, "--json")
        self.assertLess(time.monotonic() - t0, 30)
        c = json.loads(r.stdout)["checks"]
        self.assertEqual([(x["name"], x["status"]) for x in c], [("p1", "error"), ("p2", "ok")])
        self.assertEqual(c[0]["failures"][0]["message"], "timeout after 1s; no output")
        self.assertTrue((self.base / "p2.ran").exists())
        kid = int((self.base / "kid.pid").read_text())
        time.sleep(0.2)
        self.assertFalse(parts.alive(kid) and _not_zombie(kid), f"the part's child {kid} outlived the timeout")
        r = self.run_parts(doc)
        self.assertEqual(r.stdout.splitlines()[-1], "check: 1 of 2 passed; failed: p1 (timeout after 1s; no output)")

    def terminated(self, doc, started, *flags):
        """The run's (exit, stdout) after a TERM sent once every file in
        `started` exists (30s at most, else the test fails naming them)."""
        path = write(self.base / "parts.json", json.dumps(doc))
        e = dict(os.environ, PROGRESS_FILE=str(self.pf))
        p = subprocess.Popen([sys.executable, str(PARTS), "run", str(path), *flags], stdout=subprocess.PIPE,
                             text=True, env=e, stdin=subprocess.DEVNULL)
        deadline = time.monotonic() + 30
        while not all((self.base / s).exists() for s in started) and time.monotonic() < deadline:
            time.sleep(0.05)
        missing = [s for s in started if not (self.base / s).exists()]
        p.send_signal(signal.SIGTERM)
        out, _ = p.communicate(timeout=60)
        self.assertEqual(missing, [], f"waited 30s for {started}; the run said: {out}")
        return p.returncode, out

    def test_term_stops_the_part_and_leaves_the_rest_unchecked(self):
        doc = {"parts": [part("p1"), part("p2", run="touch started; sleep 60"), part("p3")]}
        code, out = self.terminated(doc, ["started"], "--json", "--jobs", "1")
        self.assertEqual(code, 128 + signal.SIGTERM)
        self.assertEqual(checkjson.validate(out, code), [])
        self.assertEqual([(c["name"], c["status"]) for c in json.loads(out)["checks"]],
                         [("p1", "ok"), ("p2", "error"), ("p3", "unchecked")])
        st = self.progress()
        self.assertEqual((st["state"], st["passed_steps"]), ("failed", ["p1"]))

    def test_term_stops_every_running_part_and_kills_their_trees(self):
        """In a pool, TERM stops all the running parts (each an error, its
        child dead) and leaves the one never started unchecked."""
        hang = "sleep 60 & echo $! > {0}.pid; touch {0}.started; wait"
        doc = {"parts": [part("p1", run=hang.format("p1")), part("p2", run=hang.format("p2")),
                         part("p3", uses=["serial"])]}
        code, out = self.terminated(doc, ["p1.started", "p2.started"], "--jobs", "4")
        self.assertEqual(code, 128 + signal.SIGTERM, out)
        lines = out.splitlines()
        self.assertEqual(lines[:2], ["ERROR p1 (stopped by signal 15)", "ERROR p2 (stopped by signal 15)"], out)
        self.assertEqual(lines[-1], "check: 0 of 3 passed; failed: p1 (stopped by signal 15); "
                                    "p2 (stopped by signal 15); not run: 1", out)
        time.sleep(0.2)
        for n in ("p1", "p2"):
            kid = int((self.base / f"{n}.pid").read_text())
            self.assertFalse(parts.alive(kid) and _not_zombie(kid), f"{n}'s child {kid} outlived the TERM")
        st = self.progress()
        self.assertEqual((st["state"], st["passed_steps"], st["running"], sorted(st["failed_names"])),
                         ("failed", [], [], ["p1", "p2"]))

    # ---- the pool ----------------------------------------------------------

    def overlap(self, doc, *flags):
        """Whether p1 and p2 ran at once: by the start and end times in the
        progress file, and by the `lock` folder HOLD takes (a second witness)."""
        (self.base / "clashes").unlink(missing_ok=True)
        r = self.run_parts(doc, *flags)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        t = self.progress()["times"]
        by_times = t["p1"]["start"] < t["p2"]["end"] and t["p2"]["start"] < t["p1"]["end"]
        by_lock = (self.base / "clashes").exists()
        self.assertEqual(by_times, by_lock, (t, r.stdout))
        return by_times

    def test_parts_sharing_a_uses_value_never_overlap(self):
        def doc(u1, u2):
            return {"parts": [part("p1", run=HOLD, uses=u1), part("p2", run=HOLD, uses=u2)]}
        self.assertTrue(self.overlap(doc([], []), "--jobs", "2"), "the counterfactual: without uses they overlap")
        self.assertTrue(self.overlap(doc(["store:a"], ["store:b"]), "--jobs", "2"), "different values may overlap")
        self.assertFalse(self.overlap(doc(["store:a"], ["browser", "store:a"]), "--jobs", "2"))
        self.assertFalse(self.overlap(doc(["browser"], ["browser"]), "--jobs", "2"))
        self.assertFalse(self.overlap(doc(["serial"], []), "--jobs", "2"), "a serial part runs alone")
        self.assertFalse(self.overlap(doc([], ["serial"]), "--jobs", "2"))
        self.assertFalse(self.overlap(doc([], []), "--jobs", "1"), "--jobs 1 is one at a time")

    def test_a_serial_part_waits_for_those_before_it_and_holds_those_after(self):
        doc = {"parts": [part("p1", run="sleep 0.5"), part("p2", run="sleep 0.5", uses=["serial"]),
                         part("p3", run="sleep 0.5"), part("p4", run="sleep 0.5")]}
        self.assertEqual(self.run_parts(doc, "--jobs", "4").returncode, 0)
        t = self.progress()["times"]
        self.assertGreaterEqual(t["p2"]["start"], t["p1"]["end"], t)
        self.assertGreaterEqual(min(t["p3"]["start"], t["p4"]["start"]), t["p2"]["end"], t)
        self.assertLess(t["p3"]["start"], t["p4"]["end"], "after the serial part, the pool fills again")

    def test_a_part_that_conflicts_lets_a_later_part_start_first(self):
        """p2 shares p1's store, so it waits; p3 shares nothing and starts
        beside p1 -- yet the report keeps p1, p2, p3."""
        doc = {"parts": [part("p1", run="sleep 1", uses=["store:s"]), part("p2", run="true", uses=["store:s"]),
                         part("p3", run="true")]}
        r = self.run_parts(doc, "--jobs", "2")
        t = self.progress()["times"]
        self.assertLess(t["p3"]["start"], t["p2"]["start"], t)
        self.assertEqual([line.split()[1] for line in r.stdout.splitlines()[:3]], ["p1", "p2", "p3"], r.stdout)

    def test_the_report_is_in_the_files_order_not_the_order_parts_end(self):
        doc = {"parts": [part("p1", run="sleep 1.5"), part("p2"), part("p3", run="sleep 0.5")]}
        r = self.run_parts(doc, "--jobs", "3")
        t = self.progress()["times"]
        self.assertLess(t["p2"]["end"], t["p3"]["end"], t)
        self.assertLess(t["p3"]["end"], t["p1"]["end"], "the counterfactual: they ended p2, p3, p1")
        self.assertEqual([line[:8] for line in r.stdout.splitlines()[:3]], ["ok    p1", "ok    p2", "ok    p3"], r.stdout)
        r = self.run_parts(doc, "--jobs", "3", "--json")
        self.assertEqual([c["name"] for c in json.loads(r.stdout)["checks"]], ["p1", "p2", "p3"])

    def test_a_failing_part_stops_no_other(self):
        doc = {"parts": [part("p1", run="exit 1"), part("p2", run="sleep 0.5; touch p2.ran"),
                         part("p3", run="touch p3.ran"), part("p4", run="exit 4", uses=["serial"]),
                         part("p5", run="touch p5.ran")]}
        r = self.run_parts(doc, "--jobs", "2", "--json")
        self.assertEqual(r.returncode, 1)
        self.assertEqual([c["status"] for c in json.loads(r.stdout)["checks"]], ["fail", "ok", "ok", "fail", "ok"])
        self.assertEqual(sorted(p.name for p in self.base.glob("*.ran")), ["p2.ran", "p3.ran", "p5.ran"])

    def mixed(self):
        """A red suite of every kind of result, for comparing two runners' words."""
        return {"defaults": {"role": "code"}, "parts": [
            part("p1"), part("p2", run="echo 'FAIL: test_x (y)'; echo two; exit 1"),
            part("p3", run="echo 'no sibling'; exit 3"), part("p4", run="sleep 0.3", uses=["serial"]),
            part("p5", run="echo last words; exit 4", files=["b.txt"]), part("p6", run="sleep 5", timeout_s=1)]}

    @staticmethod
    def words(out):
        """The run's words, its seconds and its `time:` line left out."""
        return [re.sub(r"\b\d+s\b", "Ns", line) for line in out.splitlines() if not line.startswith("time: ")]

    def test_jobs_1_says_what_a_pool_says(self):
        one, many = self.run_parts(self.mixed(), "--jobs", "1"), self.run_parts(self.mixed(), "--jobs", "6")
        self.assertEqual((one.returncode, self.words(one.stdout)), (many.returncode, self.words(many.stdout)))
        self.assertIn("check: 2 of 6 passed; failed: p2 ", one.stdout)
        one, many = (self.run_parts(self.mixed(), "--jobs", j, "--json") for j in ("1", "6"))
        self.assertEqual(json.loads(one.stdout), json.loads(many.stdout))

    def test_jobs_1_says_what_the_one_at_a_time_runner_said(self):
        """1.3.0 ran parts one at a time; --jobs 1 prints the same lines, the
        `time:` line apart, for a suite of every kind of result, and resumes."""
        p = subprocess.run(["git", "-C", str(TOOL_ROOT), "show", f"{ONE_AT_A_TIME}:checkslib/parts.py"],
                           capture_output=True, text=True)
        if p.returncode:
            self.skipTest(f"the 1.3.0 runner ({ONE_AT_A_TIME}) is not in this clone: {p.stderr.strip()}")
        old = write(self.tmp / "old" / "parts.py", p.stdout)
        doc = self.mixed()
        for p in doc["parts"]:
            p.pop("uses", None)         # 1.3.0 refuses the key it never knew
        path = write(self.base / "parts.json", json.dumps(doc))

        def by(runner, *flags):
            e = dict(os.environ, PROGRESS_FILE=str(self.pf))
            r = subprocess.run([sys.executable, str(runner), "run", str(path), *flags], capture_output=True,
                               text=True, env=e, stdin=subprocess.DEVNULL, timeout=120)
            return r.returncode, self.words(r.stdout), r.stdout.count("\ntime: ")

        was, now = by(old), by(PARTS, "--jobs", "1")
        self.assertEqual((was[2], now[2]), (0, 1), "only the new runner says a time line")
        self.assertEqual(was[:2], now[:2])
        self.assertEqual(by(old, "--resume")[:2], by(PARTS, "--resume", "--jobs", "1")[:2])
        self.assertEqual(by(old, "--json")[:2], by(PARTS, "--json", "--jobs", "1")[:2])

    def test_the_time_line_moves_with_its_inputs(self):
        line = re.compile(r"time: ([\d.]+)s wall, ([\d.]+)s summed over (\d+) part\(s\) run \(--jobs (\d+)\), "
                          r"(\d+)% of it in serial parts\Z")

        def said(doc, jobs):
            out = self.run_parts(doc, "--jobs", jobs).stdout.splitlines()
            m = line.match(out[-2])
            self.assertIsNotNone(m, out)
            return float(m[1]), float(m[2]), int(m[3]), int(m[4]), int(m[5])

        def doc(u1):
            return {"parts": [part("p1", run="sleep 1", uses=u1), part("p2", run="sleep 1")]}
        wall, summed, ran, jobs, share = said(doc([]), "2")
        self.assertEqual((ran, jobs, share), (2, 2, 0))
        self.assertGreaterEqual(summed, 2.0)
        self.assertLess(wall, 1.9, "two parts at once: the wall is less than the sum")
        wall, summed, ran, jobs, share = said(doc(["serial"]), "2")
        self.assertGreaterEqual(wall, 2.0, "a serial part runs alone")
        self.assertTrue(40 <= share <= 60, share)
        self.assertEqual(said(doc([]), "1")[3], 1)
        st = self.progress()
        self.assertTrue(st["wall_s"] >= 2.0 and st["parts_s"] >= 2.0 and st["serial_s"] == 0, st)
        self.run_parts({"parts": [part("p1")]})
        r = self.run_parts({"parts": [part("p1")]}, "--resume", "--jobs", "3")
        self.assertIn("time: ", r.stdout)
        self.assertIn("no part ran (--jobs 3)", r.stdout.splitlines()[-2])

    # ---- resume ------------------------------------------------------------

    def test_resume_runs_only_what_changed_or_did_not_pass(self):
        doc = {"parts": [part("p1", run="echo p1 >> ran"), part("p2", run="echo p2 >> ran", files=["b.txt"]),
                         part("p3", run="echo p3 >> ran; exit 1", files=["b.txt"])]}
        self.run_parts(doc)
        (self.base / "ran").unlink()
        r = self.run_parts(doc, "--resume")
        self.assertEqual((self.base / "ran").read_text().split(), ["p3"], "unchanged passed parts are skipped")
        self.assertTrue(r.stdout.startswith("resume: re-running 1 of 3: p3"), r.stdout)
        self.assertIn("skip  p1", r.stdout)
        self.assertEqual(r.stdout.splitlines()[-1], "check: 2 of 3 passed; failed: p3 (exit 1; no output)")
        r = self.run_parts(doc, "--resume", "--json")
        c = json.loads(r.stdout)["checks"]
        self.assertEqual([(x["name"], x["status"], x["counts"].get("skipped")) for x in c],
                         [("p1", "ok", 1), ("p2", "ok", 1), ("p3", "fail", None)])
        self.assertEqual(checkjson.validate(r.stdout, r.returncode), [])
        self.assertEqual(sorted(self.progress()["passed_steps"]), ["p1", "p2"], "a skipped part is still passed")
        (self.base / "ran").unlink()
        write(self.base / "b.txt", "changed\n")
        self.run_parts(doc, "--resume")
        self.assertEqual(sorted((self.base / "ran").read_text().split()), ["p2", "p3"], "an edit reruns the parts that read it")
        (self.base / "ran").unlink()
        self.run_parts(doc)
        self.assertEqual(sorted((self.base / "ran").read_text().split()), ["p1", "p2", "p3"], "no --resume runs everything")

    def test_an_always_part_is_never_skipped(self):
        doc = {"parts": [part("p1", run="echo p1 >> ran"), part("p2", run="echo p2 >> ran", files=[], always="why")]}
        self.run_parts(doc)
        (self.base / "ran").unlink()
        self.run_parts(doc, "--resume")
        self.assertEqual((self.base / "ran").read_text().split(), ["p2"])

    def test_each_refusal_to_resume_runs_everything_and_says_why(self):
        doc = {"parts": [part("p1", run="echo p1 >> ran")]}

        def resumed(env=None):
            (self.base / "ran").unlink(missing_ok=True)
            r = self.run_parts(doc, "--resume", env=env)
            return not (self.base / "ran").exists(), r.stdout.splitlines()[0]

        self.assertEqual(resumed(), (False, f"full run: no progress file ({self.pf})"))
        self.assertTrue(resumed()[0], "the counterfactual: a fresh file resumes")
        self.assertEqual(resumed({"PARTS_MAX_AGE": "-1"})[0], False)
        st = self.progress()
        write(self.pf, json.dumps(dict(st, state="running", pid=os.getpid())))
        self.assertEqual(resumed(), (False, f"full run: a run is writing the progress file now (pid {os.getpid()})"))
        write(self.pf, json.dumps(dict(st, passed_steps=[])))
        self.assertEqual(resumed(), (False, "full run: no part passed in the progress file"))
        write(self.pf, "{garbage")
        self.assertEqual(resumed(), (False, f"full run: progress file unreadable ({self.pf})"))
        self.run_parts(doc)
        self.assertEqual(resumed({"PARTS_RUNTIME": "another python"})[0], False, "a new runtime reruns everything")

    # ---- --only ------------------------------------------------------------

    def test_only_runs_the_named_part_alone_and_writes_its_result(self):
        doc = {"parts": [part("p1", run="echo p1 >> ran"), part("p2", run="echo p2 >> ran", files=["b.txt"]),
                         part("p3", run="echo p3 >> ran; exit 1", files=["b.txt"]),
                         part("p4", run="echo p4 >> ran", files=[], always="why")]}
        self.run_parts(doc)
        (self.base / "ran").unlink()
        r = self.run_parts(doc, "--only", "p3")
        self.assertEqual((self.base / "ran").read_text().split(), ["p3"], "only the named part runs")
        self.assertEqual(r.returncode, 1)
        out = r.stdout.splitlines()
        self.assertTrue(out[0].startswith("only: running 1 of 4: p3; keeping 2 other part(s) that passed at "), out)
        self.assertEqual(out[-1], "check: 0 of 1 passed; failed: p3 (exit 1; no output); not run: 3 (--only)")
        st = self.progress()
        self.assertEqual((st["only"], st["kept"], st["total"], st["state"], st["failed_names"]),
                         (["p3"], ["p1", "p2"], 1, "failed", ["p3"]), "the always part p4 is never kept")
        self.assertEqual((sorted(st["passed_steps"]), sorted(st["hashes"])), (["p1", "p2"], ["p1", "p2"]))
        # fixed: --only records the pass, and a later --resume skips all but the always part
        doc["parts"][2]["run"] = "echo p3 >> ran"
        (self.base / "ran").unlink()
        r = self.run_parts(doc, "--only", "p3", "--json")
        self.assertEqual(r.returncode, 0)
        self.assertEqual(checkjson.validate(r.stdout, r.returncode), [])
        self.assertEqual([(c["name"], c["status"]) for c in json.loads(r.stdout)["checks"]],
                         [("p1", "unchecked"), ("p2", "unchecked"), ("p3", "ok"), ("p4", "unchecked")])
        self.assertEqual(sorted(self.progress()["passed_steps"]), ["p1", "p2", "p3"])
        (self.base / "ran").unlink()
        r = self.run_parts(doc, "--resume")
        self.assertEqual((self.base / "ran").read_text().split(), ["p4"], r.stdout)
        self.assertEqual(r.stdout.splitlines()[-1], "check: 4 of 4 passed")

    def test_only_keeps_no_pass_whose_files_changed_or_from_an_unresumable_file(self):
        doc = {"parts": [part("p1"), part("p2", files=["b.txt"]), part("p3")]}
        self.run_parts(doc)
        write(self.base / "b.txt", "changed\n")
        self.run_parts(doc, "--only", "p3")
        self.assertEqual(self.progress()["kept"], ["p1"], "p2's file changed since it passed")
        r = self.run_parts(doc, "--only", "p3", env={"PARTS_MAX_AGE": "-1"})
        self.assertIn("keeping none (progress file expired", r.stdout.splitlines()[0])
        self.assertEqual(self.progress()["passed_steps"], ["p3"])
        self.run_parts(doc)
        self.assertEqual((self.progress()["only"], self.progress()["kept"]), (None, None), "a full run sets neither")

    def test_only_refusals(self):
        doc = {"parts": [part("p1")]}
        for flags, said in [(("--only", "nope"), "--only nope: no part of that name"),
                            (("--only",), "--only needs a part name"),
                            (("--only", "p1", "--resume"), "--only and --resume together"),
                            (("--bogus",), "unknown option --bogus"),
                            (("--jobs", "0"), "--jobs needs a whole number above 0, not '0'"),
                            (("--jobs", "two"), "--jobs needs a whole number above 0, not 'two'"),
                            (("--jobs", "-1"), "--jobs needs a whole number above 0, not '-1'"),
                            (("--jobs",), "--jobs needs a whole number above 0, not ''"),
                            (("--jobs", "2", "--jobs", "2"), "--jobs given twice")]:
            r = self.run_parts(doc, *flags)
            self.assertEqual(r.returncode, 2, flags)
            self.assertIn(said, r.stderr, flags)
            r = self.run_parts(doc, *flags, "--json")
            self.assertEqual((r.returncode, checkjson.validate(r.stdout, r.returncode)), (2, []), flags)

    # ---- the file as a dependency -----------------------------------------

    def test_usage_lists_every_command_and_version_prints(self):
        documented = {line.split()[1] for line in parts.USAGE.splitlines() if line.startswith("  parts.py ")}
        self.assertEqual(documented, set(parts.COMMANDS))
        p = subprocess.run([sys.executable, str(PARTS), "version"], capture_output=True, text=True)
        self.assertEqual(p.stdout.strip(), parts.VERSION)
        p = subprocess.run([sys.executable, str(PARTS)], capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)
        self.assertIn("parts.py run <parts.json>", p.stderr)

    def test_usage_json_is_what_run_accepts(self):
        """`usage --json` is the consumers' interface (tools/todo's IterateRule
        reads it): every option it lists, run accepts, with its value; an
        exclusive pair is refused together; a word it does not list is refused;
        the help text's run line is the one built from the same table."""
        p = subprocess.run([sys.executable, str(PARTS), "usage", "--json"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        doc = json.loads(p.stdout)
        self.assertEqual((doc["version"], doc["commands"]), (parts.VERSION, sorted(parts.COMMANDS)))
        run = doc["run"]
        self.assertEqual([o["flag"] for o in run["options"]], ["--resume", "--only", "--jobs", "--json"])
        self.assertIn(f"  {run['usage']}\n", parts.__doc__, "the docstring's run line is the built one")
        self.assertEqual(run["usage"], "parts.py run <parts.json> [--resume | --only <name>...] [--jobs <n>] [--json]")
        for o in run["options"]:
            words = [o["flag"]] + (["1"] if o["value"] else [])
            with self.subTest(flag=o["flag"]):
                self.assertIsNone(parts.options(words * (2 if o["repeatable"] else 1))[2])
                if o["value"]:
                    self.assertIsNotNone(parts.options([o["flag"]])[2], "a valued flag needs its value")
        for a, b in run["exclusive"]:
            words = [w for f in (a, b) for w in ([f] + (["1"] if parts.RUN_OPTIONS[f] else []))]
            self.assertIsNotNone(parts.options(words)[2], (a, b))
        self.assertIn("unknown option --quick", parts.options(["--quick"])[2])
        p = subprocess.run([sys.executable, str(PARTS), "usage"], capture_output=True, text=True)
        self.assertEqual((p.returncode, p.stdout.strip()), (0, parts.USAGE.strip()))
        p = subprocess.run([sys.executable, str(PARTS), "usage", "--bogus"], capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)

    def test_usage_json_follows_the_table(self):
        """Counterfactual: a flag added to the table appears in the usage line
        and the document and is accepted, so neither is a hand-kept copy."""
        saved = dict(parts.RUN_OPTIONS)
        try:
            parts.RUN_OPTIONS["--quick"] = None
            self.assertTrue(parts.run_usage().endswith("[--json] [--quick]"), parts.run_usage())
            self.assertIn("--quick", [o["flag"] for o in parts.usage_doc()["run"]["options"]])
            self.assertIsNone(parts.options(["--quick"])[2])
        finally:
            parts.RUN_OPTIONS.clear()
            parts.RUN_OPTIONS.update(saved)

    def test_it_loads_only_the_standard_library(self):
        tree = ast.parse(PARTS.read_text())
        mods = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        mods |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        self.assertTrue(mods)
        self.assertEqual(mods - set(sys.stdlib_module_names), set())
        self.assertFalse([n for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.level], "no relative import")

    def test_a_lone_copy_runs(self):
        lone = write(self.tmp / "lone" / "parts.py", PARTS.read_text())
        path = write(self.base / "parts.json", json.dumps({"parts": [part("p1")]}))
        p = subprocess.run([sys.executable, "-I", str(lone), "run", str(path)], capture_output=True, text=True,
                           cwd=self.tmp / "lone", env=dict(os.environ, PROGRESS_FILE=str(self.pf)))
        self.assertEqual((p.returncode, p.stdout.splitlines()[-1]), (0, "check: 1 of 1 passed"), p.stderr)


class ThisRepo(Case):
    """check.parts.json: valid, one part per test module, each running exactly it."""

    def test_check_parts_is_valid_and_covers_every_test_module(self):
        base, got = parts.load(str(TOOL_ROOT / "check.parts.json"))
        modules = sorted(p.stem for p in (TOOL_ROOT / "tests").glob("test_*.py"))
        tests = {p["name"]: p for p in got if p["name"].startswith("test.")}
        self.assertEqual(sorted(tests), sorted(f"test.{m[len('test_'):]}" for m in modules))
        for name, p in tests.items():
            m = "test_" + name[len("test."):]
            with self.subTest(part=name):
                self.assertEqual(p["run"], f"python3 -m unittest tests.{m}")
                self.assertIn(f"tests/{m}.py", p["files"])
                self.assertEqual(p["role"], "code")

    def test_dev_sh_test_with_names_runs_just_those_parts(self):
        """`./dev.sh test <part>...` (PLAN-small-tasks §3.5) is the runner's --only:
        handed a three-part suite through CHECK_PARTS, it runs the two named and
        records them in the progress file."""
        base = self.tmp / "suite"
        write(base / "a.txt", "a\n")
        doc = {"parts": [part(n, run=f"echo {n} >> ran") for n in ("p1", "p2", "p3")]}
        pf = self.tmp / "progress" / "check.json"
        env = dict(os.environ, CHECK_PARTS=str(write(base / "parts.json", json.dumps(doc))), PROGRESS_FILE=str(pf))
        p = subprocess.run([str(TOOL_ROOT / "dev.sh"), "test", "p3", "p1"], capture_output=True, text=True,
                           env=env, stdin=subprocess.DEVNULL, timeout=120)
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertEqual(sorted((base / "ran").read_text().split()), ["p1", "p3"])
        self.assertEqual(p.stdout.splitlines()[-1], "check: 2 of 2 passed; not run: 1 (--only)")
        st = json.loads(pf.read_text())
        self.assertEqual((st["only"], sorted(st["passed_steps"])), (["p1", "p3"], ["p1", "p3"]))

    def test_the_progress_folder_is_ignored_by_git(self):
        p = subprocess.run(["git", "-C", str(TOOL_ROOT), "check-ignore", "-q", ".progress/check.json"])
        self.assertEqual(p.returncode, 0, ".progress/ must be in .gitignore")


def _not_zombie(pid):
    p = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True)
    return bool(p.stdout.strip()) and not p.stdout.strip().startswith("Z")
