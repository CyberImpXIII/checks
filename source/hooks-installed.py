#!/usr/bin/env python3
# checks: applies_to=all
# Proves: the shared hooks this repo should hold are installed and agree with
# their one source.
#   In a workspace that holds the hooks tool (<top>/tools/hooks/hooks): asks
#   `hooks copies <top> --json` and fails on any of THIS repo's files it reports
#   missing, drift (logic differs from the source) or not-executable. Only this
#   repo's cells count: another repo's drift is that repo's red, not this one's
#   (the whole-workspace view is `checks all`, or `hooks copies` from the top).
#   Standalone (a fresh clone, or no hooks tool): there is no source to compare
#   with, so it checks only that .claude/hooks/ holds at least one hook and that
#   each is executable and parses (bash -n); each test-*.sh must parse.
# To pass: re-install from the source (the setup tool's hooks component), or
# fix the copy; a logic change belongs in tools/hooks/source, never in a copy.
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checkslib import api  # noqa: E402

HOOKS_CLI = Path("tools/hooks/hooks")
FAILING = {"missing", "drift", "not-executable"}


def workspace_mode(ctx, cli):
    try:
        p = subprocess.run([str(cli), "copies", str(ctx.workspace), "--json"], capture_output=True,
                           text=True, stdin=subprocess.DEVNULL, timeout=240)
    except subprocess.TimeoutExpired:
        api.done(["hooks copies: timed out"])
    try:
        rep = json.loads(p.stdout)
        locations = rep["locations"]
    except (ValueError, KeyError, TypeError):
        api.done([f"hooks copies printed no report (exit {p.returncode}): {p.stderr.strip()[-200:]}"])
    mine = [loc for loc in locations if loc.get("path") == ctx.rel]
    if not mine:
        api.done(unchecked=f"`hooks copies` does not list {ctx.rel} as a location; its hooks went uncompared")
    files = mine[0].get("files") or []
    if not files:
        api.done(unchecked=f"`hooks copies` expects no hook in {ctx.rel}; nothing to compare")
    api.done([f"{f['file']}: {f['status']}" for f in files if f.get("status") in FAILING])


def standalone(ctx, why):
    d = ctx.repo / ".claude" / "hooks"
    hooks = sorted(p for p in d.glob("*.sh") if not p.name.startswith("test-")) if d.is_dir() else []
    if not hooks:
        api.done([f".claude/hooks/: no hooks installed ({why})"])
    findings = []
    for p in sorted(d.glob("*.sh")):
        is_test = p.name.startswith("test-")
        if not is_test and not os.access(p, os.X_OK):
            findings.append(f".claude/hooks/{p.name}: not executable")
        r = subprocess.run(["bash", "-n", str(p)], capture_output=True, text=True)
        if r.returncode:
            findings.append(f".claude/hooks/{p.name}: does not parse (bash -n)")
    api.done(findings)


def main():
    ctx = api.context()
    if ctx.workspace is None:
        standalone(ctx, "standalone: no workspace top, so no source to compare with")
    if ctx.rel is None:
        standalone(ctx, f"standalone: the repo is outside the workspace {ctx.workspace}")
    cli = ctx.workspace / HOOKS_CLI
    if not os.access(cli, os.X_OK):
        standalone(ctx, f"standalone: no hooks tool at {HOOKS_CLI}")
    workspace_mode(ctx, cli)


main()
