#!/usr/bin/env python3
# checks: applies_to=all
# Proves: the repo keeps a TODO.md (the shared rule "Keep an active TODO"),
# and it is not empty: it has at least one heading.
# When the repo also has a todo.json (the todo tool's store), the store's own
# gates must pass too: this runs `tools/todo/todo -C <repo> --root <top> check`
# and fails on each of its FAIL lines (its `render` gate is the one that says
# TODO.md is the render of todo.json; WARN and INFO lines are not findings).
# Its output is read as text (it has no --json): the summary line's "N failed"
# must equal the FAIL lines counted, the exit code must agree (0 iff none
# failed), and the `render` gate must have reported. Anything else is an
# error, red, never a pass (tests/test_contract.py holds this against the
# real tool). With no workspace top, or no tools/todo beside it, a repo with a
# todo.json is UNCHECKED, said out loud, rather than passed on presence alone.
# To pass: create TODO.md (the setup tool writes one with the four standard
# headings: own bugs, open decisions, unconfirmed suspicions, reported to
# other owners). With a todo.json: run `todo check` in the repo and fix what
# it names (a hand edit of TODO.md: `todo render`, see tools/todo's README).
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checkslib import api  # noqa: E402

SUMMARY = re.compile(r"^todo check \S+: .*; (\d+) failed, (\d+) warning")
LINE = re.compile(r"^\s+(ok|FAIL|WARN|INFO)\s+(\S+)(?:\s+(\S+)\s+(.*))?$")
TIMEOUT = 120


def broken(why):
    """The todo tool's output did not keep its contract: an error, never a pass."""
    print(f"todo check did not keep the contract this check reads: {why}")
    sys.exit(1)


def todo_check(ctx):
    tool = ctx.workspace / "tools" / "todo" / "todo" if ctx.workspace else None
    if tool is None or not tool.is_file():
        api.done(unchecked="TODO.md present; todo.json present too, and no tools/todo beside the workspace "
                           "top to run `todo check` with")
    try:
        p = subprocess.run([str(tool), "-C", str(ctx.repo), "--root", str(ctx.workspace), "check"],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as e:
        broken(f"could not run {tool}: {e}")
    lines = p.stdout.splitlines()
    summary = [m for m in map(SUMMARY.match, lines) if m]
    if len(summary) != 1:
        broken(f"{len(summary)} summary lines (want 1); exit {p.returncode}; {p.stderr.strip()[-200:]}")
    rows = [m for m in map(LINE.match, lines) if m]
    fails = [m for m in rows if m.group(1) == "FAIL"]
    said = int(summary[0].group(1))
    if said != len(fails):
        broken(f"the summary says {said} failed, {len(fails)} FAIL lines printed")
    if (p.returncode == 0) != (said == 0) or p.returncode not in (0, 1):
        broken(f"exit {p.returncode} with {said} failed")
    if not any(m.group(2) == "render" for m in rows):
        broken("its `render` gate (TODO.md == the render of todo.json) did not report")
    return [f"todo check: {m.group(2)} {m.group(3)}: {m.group(4)}" for m in fails]


def main():
    ctx = api.context()
    todo = ctx.repo / "TODO.md"
    if not todo.is_file():
        api.done(["TODO.md: missing"])
    if not re.search(r"^#{1,6} \S", todo.read_text(errors="replace"), re.M):
        api.done(["TODO.md: no heading; an empty TODO is not a kept one"])
    if (ctx.repo / "todo.json").exists():
        api.done(todo_check(ctx))
    api.done()


main()
