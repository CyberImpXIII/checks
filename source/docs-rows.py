#!/usr/bin/env python3
# checks: applies_to=repos:. params=header
# Proves: the workspace top's CLAUDE.md tool table (the first table whose
# header row's first cell is `header`, default "Tool") has a row per repo
# folder and a folder per row:
#   - every git repo under the top that has a CLAUDE.md (the same set
#     `checks all` walks: depth 4, dot-folders and node_modules pruned) is the
#     first-cell path of some row;
#   - every row's first-cell path (the first `backticked` path in the cell)
#     exists; a row may name a file as well as a folder.
# Runs at the workspace top only. Without a workspace: UNCHECKED.
# To pass: add a row for the new tool (top-level prose is the dispatcher's
# edit), or delete the row of a folder that is gone.
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checkslib import api, runner  # noqa: E402

CELL_PATH = re.compile(r"`([^`]+)`")


def table(text, header):
    """[first cell] of each body row of the first table whose header's first cell is `header`."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if line.lstrip().startswith("|") and cells and cells[0] == header:
            rows = []
            for row in lines[i + 2:]:
                if not row.lstrip().startswith("|"):
                    break
                rows.append(row.strip().strip("|").split("|")[0].strip())
            return rows
    return None


def main():
    ctx = api.context()
    if ctx.workspace is None:
        api.done(unchecked="no workspace top: the tool table lives there")
    header = ctx.param("header", "Tool")
    md = ctx.workspace / "CLAUDE.md"
    if not md.is_file():
        api.done(["CLAUDE.md: missing at the workspace top"])
    rows = table(md.read_text(errors="replace"), header)
    if rows is None:
        api.done([f"CLAUDE.md: no table whose header starts with `{header}`"])
    if not rows:
        api.done([f"CLAUDE.md: the `{header}` table has no rows"])
    findings, named = [], set()
    for cell in rows:
        m = CELL_PATH.search(cell)
        if not m:
            findings.append(f"row `{cell[:40]}`: no `path` in its first cell")
            continue
        p = m.group(1).rstrip("/")
        named.add(p)
        if not (ctx.workspace / p).exists():
            findings.append(f"row `{m.group(1)}`: no such path")
    for repo in runner.discover(ctx.workspace)[1:]:
        r = repo.relative_to(ctx.workspace).as_posix()
        if r not in named:
            findings.append(f"{r}/: a repo with no row in the `{header}` table")
    api.done(findings)


main()
