"""check-partial's fixtures run THE shared runner, checkslib/parts.py, copied
into a scratch repo the way setup will render it (PLAN-small-tasks §7 step 2),
behind a dev.sh that hands it CHECK_PARTS. The failing fixture breaks that same
file with mutants, so the check is shown red on the real runner, not on a
second runner written for the test."""
from pathlib import Path

import checkslib
from checkslib.fixture import Fixture, git_repo

RUNNER = Path(checkslib.__file__).resolve().parent / "parts.py"

DEV = """#!/usr/bin/env bash
# check [--json] [--resume]: the parts CHECK_PARTS lists (else parts.json), through the shared parts.py.
here="$(cd "$(dirname "$0")" && pwd)"
[ "${1:-}" = check ] || { echo "usage: ./dev.sh check [--json] [--resume]"; exit 2; }
shift
exec python3 "$here/parts.py" run "${CHECK_PARTS:-$here/parts.json}" "$@"
"""

OWN_PARTS = '{"parts": [{"name": "dev", "run": "true", "files": ["dev.sh"], "timeout_s": 10}]}\n'

# One property of the real runner turned off each: {name: (exact text in
# parts.py, what replaces it)}. Each text must be in parts.py exactly once
# (mutate() refuses otherwise), so a refactor that moves one is loud.
MUTANTS = {
    # lost results: the progress file is written only once the run is over
    "late": ('        self.state["updated"] = now()\n',
             '        self.state["updated"] = now()\n        if self.state["state"] == "running":\n            return\n'),
    # names every part as passed before any has run
    "eager": ('    pf.start(len(parts), jobs, [p["name"] for p in parts])\n',
              '    pf.start(len(parts), jobs, [p["name"] for p in parts])\n'
              '    pf.state["passed_steps"] = [p["name"] for p in parts]\n    pf.write()\n'),
    # --resume reruns every part, changed or not
    "rerun": ('skip = {p["name"] for p in parts if not p["always"] and old.get(p["name"]) == hashes[p["name"]]}',
              "skip = set()"),
    # --resume runs no part, changed or not
    "skip": ('skip = {p["name"] for p in parts if not p["always"] and old.get(p["name"]) == hashes[p["name"]]}',
             'skip = {p["name"] for p in parts}'),
    # a skipped part is left out of the report (N of M counts only what ran)
    "drop-skipped": ('checks.append(entry(name, "ok", part["role"], skipped=True))', "pass"),
    # a part's timeout_s is ignored: a hung part holds the run
    "no-limit": ('code = p.wait(timeout=part["timeout_s"])', "code = p.wait()"),
    # the summary counts a failed part as passed: a wrong N of M
    "count": ("say(summary(n, len(parts), failed)", "say(summary(n + len(failed), len(parts), failed)"),
    # the failed list does not name the part
    "unnamed": ('failed.append(f"{name} ({fails[0]})" if fails[0].startswith(why) else f"{name} ({why}: {fails[0]})")',
                'failed.append(f"({why})")'),
    # the progress file is always the repo's own, whatever PROGRESS_FILE says
    "own-file": ('Progress(os.environ.get("PROGRESS_FILE") or os.path.join(base, ".progress", stem + ".json"), stem)',
                 'Progress(os.path.join(os.getcwd(), ".progress", "check.json"), stem)'),
}


def mutate(names=()):
    """parts.py's text with each named mutant applied."""
    text = RUNNER.read_text()
    for name in sorted(names):
        old, new = MUTANTS[name]
        n = text.count(old)
        if n != 1:
            raise ValueError(f"mutant {name}: its text is in checkslib/parts.py {n} time(s), wanted 1: re-aim it")
        text = text.replace(old, new)
    return text


def repo(t, mutants=()):
    return git_repo(t / "r", {"dev.sh": DEV, "parts.py": mutate(mutants), "parts.json": OWN_PARTS,
                              ".gitignore": ".progress/\n"})


def passing(t):
    return Fixture(repo(t))


def failing(t):
    # The three ways at once (lost results, rerunning unchanged parts, a timeout
    # ignored), so each scenario fails for its own reason; tests/test_check_partial.py
    # shows every mutant alone turning only its own scenario red.
    return Fixture(repo(t, ("late", "rerun", "no-limit")), env={"CHECKS_CHECK_PARTIAL_RUN_TIMEOUT": "8"},
                   expect=["killed: a run killed while p2 hung left no progress file",
                           "changed: after an edit to p3's file only, `--resume` ran p1, p2, p3",
                           "hung: one part past its timeout_s (2s) held the whole run"])
