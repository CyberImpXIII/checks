#!/usr/bin/env python3
# checks: applies_to=repos:tools/checks
# Proves: the practice rows (PLAN-services.md §3 A1, §4 step 7.2) in the repo's
# gates.json `practices` block are whole and true, so `checks practices` reads
# cells from rows that say what they mean:
#   - shape: the `keys` vocabulary names exactly the row keys the reader
#     (checkslib/practices.py) knows; every row has an id (unique), a rule,
#     sources (first wins) and a status (live, superseded-by <id>, retired
#     <date, why>); a live row has a part (A principle, B supporting, C a
#     repo's own), applies ("all" or repo paths) and held (gate, prose,
#     unbuilt, or rollup, which is a principle's and only a principle's);
#   - the seams between rows: a part B row's principle is a part A row (a
#     rootless row fails); a superseded row's successor is a row; a row in
#     `blocked` (left out on a decision of Jacob's, with its C<n> and why) is
#     no row, and nothing serves or is superseded by a blocked row;
#   - the seams to the workspace (only with a workspace top): every gate path
#     exists; a gate in tools/checks/source/ names that check in `check`, a
#     shared hook gate is read `via` hooks-installed, and each names a check
#     the source holds; every source resolves (a PLAN-x.md §n heading, a .md
#     and its "heading", a gates:<repo>#<id> row, a path); `memory:` sources
#     live outside the workspace and are counted, never claimed resolved;
#   - a recorded cell is {state justified|unjustified, why}, for a location
#     the row applies to; never on a principle (its cells are derived).
# Not proven: that a held gate refuses a fault (its owner's tests), or what a
# cell's state is (that is `checks practices`, which runs the gates).
# No workspace top: shape and row seams are checked, paths and sources are
# not, so the result is UNCHECKED when nothing else fails.
# To pass: fix the row the finding names in gates.json `practices` (or
# re-import PRACTICES-rows.md with `checks practices --import <file>`, which
# keeps `blocked` and recorded cells); block a row whose principle or successor
# is blocked; record a cell with its state and why, never a bare held.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checkslib import api, practices  # noqa: E402


def main():
    ctx = api.context()
    path = ctx.repo / "gates.json"
    if not path.is_file():
        api.done(["no gates.json here: the practice rows live in the registry's `practices` block"])
    block, faults = practices.load(path)
    if block is None:
        api.done(faults)
    findings, notes = practices.validate(block, ctx.workspace)
    if findings:
        api.done(findings)
    if ctx.workspace is None:
        api.done(unchecked="no workspace top: rows and their seams are whole, gate paths and sources went unchecked")
    rows = block["rows"]
    n_live = len(practices.live(rows))
    print(f"{len(rows)} practice row(s): {n_live} live, {len(rows) - n_live} superseded or retired; "
          f"{len(block.get('blocked', []))} blocked; {notes[0]}")
    api.done()


if __name__ == "__main__":
    main()
