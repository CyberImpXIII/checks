"""The one reading of a repo's todo store through its own gate, `tools/todo/todo
-C <repo> --root <top> check`, shared by todo-valid (all) and todo-store
(roles:lag) so the two never read it two ways.

Its output is read as text (it has no --json): the summary line's "N failed"
must equal the FAIL lines counted, the exit code must agree (0 iff none
failed), and the `render` gate (TODO.md == the render of todo.json) must have
reported. Anything else is an error, red, never a pass: `broken` exits 1,
which the runner reads as `error`. WARN and INFO lines are not findings.
tests/test_todo_valid.py holds each broken contract against stand-in tools;
tests/test_contract.py holds the reading against the real tool."""
import re
import subprocess
import sys

from checkslib import api

SUMMARY = re.compile(r"^todo check \S+: .*; (\d+) failed, (\d+) warning")
LINE = re.compile(r"^\s+(ok|FAIL|WARN|INFO)\s+(\S+)(?:\s+(\S+)\s+(.*))?$")
TIMEOUT = 120
STORE = "todo.json"


def broken(why):
    """The todo tool's output did not keep its contract: an error, never a pass."""
    print(f"todo check did not keep the contract this check reads: {why}")
    sys.exit(1)


def tool(ctx):
    """tools/todo/todo beside the workspace top, or None (no top, or no tool there)."""
    t = ctx.workspace / "tools" / "todo" / "todo" if ctx.workspace else None
    return t if t is not None and t.is_file() else None


def run(ctx, missing_tool):
    """Run `todo check` on ctx.repo; return (findings, summary line).
    No tool to run it with: UNCHECKED with `missing_tool` as the reason
    (exits), so a store is never passed on presence alone."""
    t = tool(ctx)
    if t is None:
        api.done(unchecked=missing_tool)
    try:
        p = subprocess.run([str(t), "-C", str(ctx.repo), "--root", str(ctx.workspace), "check"],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as e:
        broken(f"could not run {t}: {e}")
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
    return [f"todo check: {m.group(2)} {m.group(3)}: {m.group(4)}" for m in fails], summary[0].string.strip()
