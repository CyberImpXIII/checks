"""checkslib/parts.py, the one shared suite runner (PLAN-small-tasks.md §3, §7):
every fault in a parts file refused; what a part's hash reads, each input shown
to change it (or shown not to, where the header says so); each part's result
on disk as it ends; --resume skipping only unchanged passed parts, and each
refusal to resume said; a timeout stopping the part's whole tree; a TERM
leaving the file `failed` and the rest `unchecked`; the text summary and the
--json document (validated by checkjson) green and red; the copy loading
nothing beside it; and this repo's check.parts.json held to its test modules.
check-partial (tests/test_check_partial.py) holds the same runner from outside."""
import ast
import json
import os
import signal
import subprocess
import sys
import time

from tests.helpers import Case, TOOL_ROOT, write
from checkslib import checkjson, parts

PARTS = TOOL_ROOT / "checkslib" / "parts.py"


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
        self.assertEqual(self.h(dict(p, timeout_s=99, role="x")), h3, "timeout_s and role are not")

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
        self.assertEqual((st["state"], st["passed_steps"], st["step"], st["total"], st["cmd"], st["runner"]),
                         ("passed", ["p1", "p2"], 2, 2, "parts", parts.VERSION))

    def test_red_names_each_failed_part_and_its_fail_lines(self):
        doc = {"defaults": {"role": "code"}, "parts": [
            part("p1", run="echo 'FAIL: test_one (x)'; echo 'ERROR: test_two'; exit 1"),
            part("p2"),
            part("p3", run="echo last words; exit 3")]}
        r = self.run_parts(doc)
        self.assertEqual(r.returncode, 1)
        self.assertEqual(r.stdout.splitlines()[-1],
                         "check: 1 of 3 passed; failed: p1 (exit 1: FAIL: test_one (x)); p3 (exit 3; last output: last words)")
        self.assertIn("  ERROR: test_two", r.stdout.splitlines())
        r = self.run_parts(doc, "--json")
        self.assertEqual(checkjson.validate(r.stdout, r.returncode), [])
        c = json.loads(r.stdout)["checks"]
        self.assertEqual([x["status"] for x in c], ["fail", "ok", "fail"])
        self.assertEqual([f["message"] for f in c[0]["failures"]], ["FAIL: test_one (x)", "ERROR: test_two"])
        self.assertEqual(c[0]["failures"][0]["role"], "code")
        st = self.progress()
        self.assertEqual((st["state"], st["passed_steps"], st["failed_names"]), ("failed", ["p2"], ["p1", "p3"]))

    def test_each_result_is_on_disk_before_the_next_part_runs(self):
        doc = {"parts": [part("p1"), part("p2", run='cp "$PROGRESS_FILE" seen.json')]}
        self.assertEqual(self.run_parts(doc).returncode, 0)
        seen = json.loads((self.base / "seen.json").read_text())
        self.assertEqual((seen["passed_steps"], seen["label"], seen["state"], seen["pid"] > 0),
                         (["p1"], "p2", "running", True))

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

    def test_term_stops_the_part_and_leaves_the_rest_unchecked(self):
        doc = {"parts": [part("p1"), part("p2", run="touch started; sleep 60"), part("p3")]}
        path = write(self.base / "parts.json", json.dumps(doc))
        e = dict(os.environ, PROGRESS_FILE=str(self.pf))
        p = subprocess.Popen([sys.executable, str(PARTS), "run", str(path), "--json"], stdout=subprocess.PIPE,
                             text=True, env=e, stdin=subprocess.DEVNULL)
        deadline = time.monotonic() + 30
        while not (self.base / "started").exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        p.send_signal(signal.SIGTERM)
        out, _ = p.communicate(timeout=30)
        self.assertEqual(p.returncode, 128 + signal.SIGTERM)
        self.assertEqual(checkjson.validate(out, p.returncode), [])
        self.assertEqual([(c["name"], c["status"]) for c in json.loads(out)["checks"]],
                         [("p1", "ok"), ("p2", "error"), ("p3", "unchecked")])
        st = self.progress()
        self.assertEqual((st["state"], st["passed_steps"]), ("failed", ["p1"]))

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
        self.assertEqual(self.progress()["passed_steps"], ["p1", "p2"], "a skipped part is still passed")
        (self.base / "ran").unlink()
        write(self.base / "b.txt", "changed\n")
        self.run_parts(doc, "--resume")
        self.assertEqual((self.base / "ran").read_text().split(), ["p2", "p3"], "an edit reruns the parts that read it")
        (self.base / "ran").unlink()
        self.run_parts(doc)
        self.assertEqual((self.base / "ran").read_text().split(), ["p1", "p2", "p3"], "no --resume runs everything")

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

    # ---- the file as a dependency -----------------------------------------

    def test_usage_lists_every_command_and_version_prints(self):
        documented = {line.split()[1] for line in parts.USAGE.splitlines() if line.startswith("  parts.py ")}
        self.assertEqual(documented, set(parts.COMMANDS))
        p = subprocess.run([sys.executable, str(PARTS), "version"], capture_output=True, text=True)
        self.assertEqual(p.stdout.strip(), parts.VERSION)
        p = subprocess.run([sys.executable, str(PARTS)], capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)
        self.assertIn("parts.py run <parts.json>", p.stderr)

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

    def test_the_progress_folder_is_ignored_by_git(self):
        p = subprocess.run(["git", "-C", str(TOOL_ROOT), "check-ignore", "-q", ".progress/check.json"])
        self.assertEqual(p.returncode, 0, ".progress/ must be in .gitignore")


def _not_zombie(pid):
    p = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True)
    return bool(p.stdout.strip()) and not p.stdout.strip().startswith("Z")
