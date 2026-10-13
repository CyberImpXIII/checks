#!/usr/bin/env python3
# checks: applies_to=tools params=exclude,allow_names
# Proves: a tool under tools/ reads no roster (PLAN-tools-folder.md §1, the
# membership rule for tools/), in two halves:
#   1. paths: no file in scope names the delegation layer's roster files: the
#      agents manifest, the agent definitions folder, its library folder, its
#      CLI, the wiring file, the dispatch ledger, or a reach up into a parent's
#      dot-claude folder;
#   2. names: no file in scope names a roster agent as a quoted literal ("x"
#      or 'x') or as `--agent x`. The names are NOT stored here (a copy goes
#      stale, and holding them would be reading the roster): a caller that
#      reads the roster passes them (`checks run --names a,b`). Without them
#      the second half does not run, and the result is UNCHECKED, not ok.
#      The repo's own folder name is never a finding (a tool may name itself).
# Scope: the files git would commit (every file outside a git repo), minus *.md, the
# installed hook copies (.claude/), tests/ and test/ (a test plants faults),
# the todo store at the repo root (todo.json, todo-history.json: the prose
# TODO.md is rendered from, notes and reports that name the roster's files as
# their subject, written by the todo CLI and not editable by hand; the same
# file name anywhere else is scanned), and the globs in the `exclude` param (for data that legitimately names a
# path, such as an install destination). `allow_names` lists agent names this
# repo may use with another meaning (a sibling folder or package of the same
# name); the paths half still runs on every file.
# To pass: take what the code needs as an argument from its caller instead of
# reading it; or, for data that only names a path, add an `exclude` glob; for a
# name that means something else here, add it to `allow_names`.
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checkslib import api, scan  # noqa: E402

# Written so that no pattern matches its own source text.
PATHS = [
    re.compile(r"agents\.manifest"),
    re.compile(r"\.claude/(?:agents|lib)\b"),
    re.compile(r"\bagents\.sh\b"),
    re.compile(r"\bwiring\.json\b"),
    re.compile(r"\bdispatches\.jsonl\b"),
    re.compile(r"\.\./+\.claude\b"),
]
# The todo store (tools/todo): prose like TODO.md, rendered into it. Root only.
TODO_STORE = ["todo.json", "todo-history.json"]


def main():
    ctx = api.context()
    files = scan.in_scope(ctx, TODO_STORE + list(ctx.param("exclude", [])))
    names = None
    if ctx.names is not None:
        allowed = {ctx.repo.name, *ctx.param("allow_names", [])}
        names = [n for n in ctx.names if n not in allowed]
    name_rx = None
    if names:
        alt = "|".join(map(re.escape, sorted(names, key=len, reverse=True)))
        name_rx = re.compile(rf"""(["'])({alt})\1|--agent[ =]({alt})\b""")
    findings, scanned = [], 0
    for rel in files:
        t = scan.text(ctx.repo / rel)
        if t is None:
            continue
        scanned += 1
        for n, line in enumerate(t.splitlines(), 1):
            for rx in PATHS:
                if rx.search(line):
                    findings.append(f"{rel}:{n}: names the roster's files ({rx.pattern})")
            if name_rx:
                for m in name_rx.finditer(line):
                    findings.append(f"{rel}:{n}: names roster agent `{m.group(2) or m.group(3)}`")
    if not scanned:
        api.done(unchecked="nothing in scope to scan (every file excluded, or none tracked)")
    if findings:
        api.done(findings)
    if names is None:
        api.done(unchecked=f"paths half clean ({scanned} files); names half not run: no roster names "
                           f"passed (--names), and this tool reads no roster itself")
    api.done()


main()
