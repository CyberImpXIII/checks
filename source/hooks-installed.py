#!/usr/bin/env python3
# checks: applies_to=all
# Proves: every shared hook this repo should run is installed, either as a repo
# copy that agrees with its one source or in place at user scope.
#   In a workspace that holds the hooks tool (<top>/tools/hooks/hooks): asks
#   `hooks copies <top> --json` and reads only that report (never the user
#   settings themselves). Only THIS repo's cells count: another repo's drift is
#   that repo's red (the whole-workspace view is `checks all`, or `hooks copies`).
#   A copy reported missing or drift is COVERED when the report's `user_scope`
#   has a `kind: source` row for that file (or for the hook whose test it is)
#   with `registered: true`: the user settings run that hook from its source.
#   A support file (a lib or bin copy beside the hooks) is covered by its
#   `user_scope.support` row: `covered` true (every hook reading it runs in
#   place, beside the source's copy), false a fail naming the row's `why`
#   (a repo copy is still read), null UNCHECKED.
#   Not covered, and red: `registered: false`, no such row, or no user settings
#   file. Unknown, and UNCHECKED (never ok): `registered: null` or a
#   `user_scope.error`. A not-executable copy is red whatever user scope says.
#   A missing or drifted copy NOT covered is judged only against a committed
#   source: `hooks copies` compares with tools/hooks' working tree, so its row's
#   `source_uncommitted` true (the source is mid-edit) or null (git cannot say)
#   is UNCHECKED, never ok and never a false drift; false is a real fail. (A
#   not-executable copy matches its source, so it is red against either one.)
#   On ok it says which scope covered each hook: `repo copy: <files>` and
#   `covered by user scope: <files>`. A report not in that shape is an error.
#   Standalone (a fresh clone, or no hooks tool): there is no source to compare
#   with, so it checks only that .claude/hooks/ holds at least one hook and that
#   each is executable and parses (bash -n); each test-*.sh must parse.
# To pass: register the shared hooks at user scope (`hooks userscope`, applied
# by the setup tool), or re-install the copy from the source (setup's hooks
# component); a logic change belongs in tools/hooks/source, never in a copy.
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checkslib import api  # noqa: E402

HOOKS_CLI = Path("tools/hooks/hooks")
FAILING = {"missing", "drift", "not-executable"}
COVERABLE = {"missing", "drift"}       # a present but broken copy is a fault no user scope fixes


def broken(why):
    """`hooks copies --json` is not in the shape read here: an error, never a guess."""
    print(f"hooks copies --json did not keep the contract this check reads: {why}"[:400])
    sys.exit(1)


def is_tristate(v):
    return v is True or v is False or v is None


def user_scope(rep):
    us = rep.get("user_scope")
    if not isinstance(us, dict):
        broken("no `user_scope` object")
    for key in ("exists", "error", "hooks"):
        if key not in us:
            broken(f"`user_scope` has no `{key}`")
    if not isinstance(us["exists"], bool):
        broken("`user_scope.exists` is not true/false")
    if us["error"] is not None and not isinstance(us["error"], str):
        broken("`user_scope.error` is neither null nor text")
    if not isinstance(us["hooks"], list):
        broken("`user_scope.hooks` is not a list")
    for h in us["hooks"]:
        if not (isinstance(h, dict) and isinstance(h.get("file"), str) and isinstance(h.get("kind"), str)
                and "registered" in h and is_tristate(h["registered"])
                and isinstance(h.get("test"), (str, type(None)))):
            broken(f"a `user_scope.hooks` row is not {{file, kind, test?, registered: true|false|null}}: {h!r}")
    if not isinstance(us.get("support"), list):
        broken("`user_scope.support` is not a list")
    for s in us["support"]:
        if not (isinstance(s, dict) and isinstance(s.get("file"), str) and isinstance(s.get("kind"), str)
                and isinstance(s.get("needed_by"), list) and all(isinstance(n, str) for n in s["needed_by"])
                and "covered" in s and is_tristate(s["covered"])
                and "why" in s and isinstance(s["why"], (str, type(None)))):
            broken(f"a `user_scope.support` row is not {{file, kind, needed_by: [..], covered: true|false|null, "
                   f"why: text|null}}: {s!r}")
    return us


def coverage(us, f):
    """(True | False | None, why): does user scope run the shared hook copy f stands for?"""
    if not us["exists"]:
        return False, "no user settings file"
    if us["error"] is not None:
        return None, us["error"]
    support = [s for s in us["support"] if s["file"] == f]
    if support:     # a lib/bin file: hooks' own verdict, whether user scope makes the repo copy unneeded
        s = support[0]
        if s["covered"] is True:
            return True, ""
        if s["covered"] is False:
            return False, s["why"] or "support: covered false"
        return None, s["why"] or "support: covered null"
    rows = [h for h in us["hooks"] if h["kind"] == "source" and f in (h["file"], h.get("test"))]
    if not rows:
        return False, "no shared hook of that name there"
    regs = [h["registered"] for h in rows]
    if all(registered is True for registered in regs):
        return True, ""
    if any(registered is False for registered in regs):
        return False, "not registered there"
    return None, "registered: null"


def source_state(f):
    """(True | False | None): is the source this non-ok row was compared with
    committed? Read from the row's `source_uncommitted`; absent is a broken report."""
    if "source_uncommitted" not in f or not is_tristate(f["source_uncommitted"]):
        broken(f"a non-ok `locations[].files` row has no `source_uncommitted: true|false|null`: {f!r}")
    return f["source_uncommitted"]


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
    us = user_scope(rep)
    mine = [loc for loc in locations if loc.get("path") == ctx.rel]
    if not mine:
        api.done(unchecked=f"`hooks copies` does not list {ctx.rel} as a location; its hooks went uncompared")
    files = mine[0].get("files") or []
    if not files:
        api.done(unchecked=f"`hooks copies` expects no hook in {ctx.rel}; nothing to compare")
    repo_copy, covered, red, unknown, mid_edit = [], [], [], [], []
    for f in files:
        name, status = f.get("file"), f.get("status")
        if status == "ok":
            repo_copy.append(name)
        elif status in COVERABLE:
            dirty = source_state(f)
            state, why = coverage(us, name)
            if state is True:
                covered.append(name)
            elif dirty is not False:    # compared with a source mid-edit, or one git cannot place
                mid_edit.append((name, status, "source not committed" if dirty else "source_uncommitted: null"))
            elif state is False:
                red.append(f"{name}: {status}; not covered by user scope ({why})")
            else:
                unknown.append((name, status, why))
        elif status in FAILING:
            red.append(f"{name}: {status}")
    if red:     # a fail lists every copy not shown covered, the unknown ones too
        api.done(red + [f"{n}: {s}; coverage by user scope unknown ({why})" for n, s, why in unknown]
                 + [f"{n}: {s}; not judged, tools/hooks {why}" for n, s, why in mid_edit])
    if unknown or mid_edit:
        reasons = []
        if mid_edit:
            whys = sorted({why for _, _, why in mid_edit})
            reasons.append(f"compared with a tools/hooks source not known to be committed ({'; '.join(whys)}), "
                           "so missing/drift is not a verdict: " + ", ".join(n for n, _, _ in mid_edit))
        if unknown:
            whys = sorted({why for _, _, why in unknown})
            reasons.append(f"user scope could not tell ({'; '.join(whys)}): coverage unknown for "
                           + ", ".join(n for n, _, _ in unknown))
        api.done(unchecked=" | ".join(reasons))
    if repo_copy:
        print("repo copy: " + ", ".join(repo_copy))
    if covered:
        print("covered by user scope: " + ", ".join(covered))
    api.done()


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
