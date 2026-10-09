from checkslib.fixture import Fixture, git_repo

DEV = """#!/usr/bin/env bash
# check [--json] [--resume]: the parts CHECK_PARTS lists (else parts.json), in parts.
exec python3 "$(dirname "$0")/run_parts.py" "$@"
"""

# A working parts runner, spelled out by hand. FAULTS turns one property off:
#   late     the progress file is written once, at the end (a killed run leaves none)
#   rerun    --resume runs every part, changed or not
#   no-limit a part's timeout_s is ignored (a hung part holds the run)
#   own-file the progress file is always the repo's own, whatever PROGRESS_FILE says
#   skip     --resume runs no part, changed or not
#   eager    the progress file names every part as passed before any has run
RUNNER = '''import hashlib, json, os, signal, subprocess, sys, tempfile
FAULTS = set(%(faults)r)
manifest = os.environ.get("CHECK_PARTS") or "parts.json"
progress = os.environ.get("PROGRESS_FILE") or ".progress/check.json"
if "own-file" in FAULTS:
    progress = ".progress/check.json"
base = os.path.dirname(os.path.abspath(manifest))
parts = json.load(open(manifest))["parts"]


def digest(part):
    h = hashlib.sha256()
    for f in part.get("files", []):
        try:
            h.update(open(os.path.join(base, f), "rb").read())
        except OSError:
            h.update(b"missing")
    return h.hexdigest()


def write(state):
    os.makedirs(os.path.dirname(os.path.abspath(progress)), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(progress)))
    with os.fdopen(fd, "w") as f:
        json.dump(state, f)
    os.replace(tmp, progress)


old = {}
if "--resume" in sys.argv:
    try:
        old = json.load(open(progress)).get("hashes", {})
    except (OSError, ValueError):
        old = {}
state = {"pid": os.getpid(), "state": "running", "passed_steps": [], "hashes": {}}
checks = []
if "eager" in FAULTS:
    state["passed_steps"] = [p["name"] for p in parts]
    write(state)
for part in parts:
    name, h = part["name"], digest(part)
    if ("rerun" not in FAULTS and old.get(name) == h) or ("skip" in FAULTS and "--resume" in sys.argv):
        state["passed_steps"].append(name)
        state["hashes"][name] = h
        checks.append({"name": name, "status": "ok", "counts": {"failed": 0}, "failures": []})
        continue
    p = subprocess.Popen(part["run"], shell=True, cwd=base, start_new_session=True,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        code = p.wait(timeout=None if "no-limit" in FAULTS else part.get("timeout_s", 30))
        why = "exit %%d" %% code
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        p.wait()
        code, why = -1, "timeout after %%ss" %% part.get("timeout_s")
    if code == 0:
        state["passed_steps"].append(name)
        state["hashes"][name] = h
        checks.append({"name": name, "status": "ok", "counts": {"failed": 0}, "failures": []})
    else:
        checks.append({"name": name, "status": "fail", "counts": {"failed": 1},
                       "failures": [{"message": why, "file": None, "line": None, "role": "tests"}]})
    if "late" not in FAULTS:
        write(state)
ok = all(c["status"] == "ok" for c in checks)
state["state"] = "passed" if ok else "failed"
write(state)
print(json.dumps({"ok": ok, "checks": checks}))
sys.exit(0 if ok else 1)
'''


def repo(t, faults=()):
    return git_repo(t / "r", {"dev.sh": DEV, "run_parts.py": RUNNER % {"faults": sorted(faults)},
                              ".gitignore": ".progress/\n"})


def passing(t):
    return Fixture(repo(t))


def failing(t):
    # All three faults at once, so each scenario fails for its own reason;
    # tests/test_check_partial.py shows each fault alone failing its scenario alone.
    return Fixture(repo(t, ("late", "rerun", "no-limit")), env={"CHECKS_CHECK_PARTIAL_RUN_TIMEOUT": "8"},
                   expect=["killed: a run killed while p2 hung left no progress file",
                           "changed: after an edit to p3's file only, `--resume` ran p1, p2, p3",
                           "hung: one part past its timeout_s (2s) held the whole run"])
