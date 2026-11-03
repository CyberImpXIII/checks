#!/usr/bin/env python3
# checks: applies_to=repos:.
# Proves: the workspace top holds no RESEARCH-*.md. A research document is a
# tools/research render (`research ask` / `answer` / `render` write
# tools/research/docs/RESEARCH-<topic>.md); the hand-written ones that predate
# the service are kept, with their banners, in tools/research/archive/
# (PLAN-O10-import.md §3; Jacob, 2026-11-02, ra-12.2). Only the top's own
# files are read: a render or an archived original under tools/research is
# where it belongs.
# Runs at the workspace top only. Without a workspace: UNCHECKED.
# To pass: record the questions through `research ask` and `answer`, then move
# the hand-written file into tools/research/archive/ with its banner.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checkslib import api  # noqa: E402


def main():
    ctx = api.context()
    if ctx.workspace is None:
        api.done(unchecked="no workspace top: the hand-written research documents lived there")
    api.done([f"{p.name}: a research document at the top; record it through `research ask` and "
              f"`answer` (rendered to tools/research/docs/), and keep the original in tools/research/archive/"
              for p in sorted(ctx.workspace.glob("RESEARCH-*.md")) if p.is_file()])


main()
