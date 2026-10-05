"""A repo with no shared block: its own sections are classified by its own
gates.json (so the registry's rows do not apply to it, and the fixture does
not depend on them). Gate and test paths are from the fixture's workspace top."""
import json

from checkslib.fixture import Fixture, write

MD = """# r

## Never push on a Friday — ENFORCED

**No push on a Friday.** The guard blocks it.

## Prefer short names

Short names read better.

## Back up nightly

**The store is backed up every night.**
"""

ROWS = [
    {"id": "friday", "section": "Never push on a Friday", "rule": "No push on a Friday",
     "kind": "gate", "how": "block", "gate": "gates/guard.sh", "test": "gates/test-guard.sh"},
    {"id": "short-names", "section": "Prefer short names", "rule": "Short names read better",
     "kind": "prose", "why": "taste, not a behaviour"},
    {"id": "backup", "section": "Back up nightly", "rule": "backed up every night",
     "kind": "gate", "how": "check", "status": "planned", "plan": "PLAN-x.md §2"},
]


def _ws(t, md, rows, guard_mode=0o755):
    ws = t / "ws"
    write(ws / "gates" / "guard.sh", "#!/bin/sh\nexit 2\n", guard_mode)
    write(ws / "gates" / "test-guard.sh", "#!/bin/sh\n# runs guard.sh on a Friday push and wants exit 2\n", 0o755)
    write(ws / "PLAN-x.md", "# PLAN x\n\n## 2. Backups\n")
    write(ws / "r" / "CLAUDE.md", md)
    write(ws / "r" / "gates.json", json.dumps({"rules": rows}, indent=1) + "\n")
    return ws


def passing(t):
    ws = _ws(t, MD, ROWS)
    return Fixture(ws / "r", workspace=ws)


def failing(t):
    md = MD.replace("**No push on a Friday.**", "**No pushes on Fridays.**") + "\n## Unclassified rule\n\nAlways.\n"
    rows = [dict(r) for r in ROWS]
    rows[1].pop("why")
    rows[2]["plan"] = "PLAN-x.md §9"
    rows.append({"id": "gone", "section": "Removed section", "rule": "anything", "kind": "prose", "why": "w"})
    ws = _ws(t, md, rows, guard_mode=0o644)
    return Fixture(ws / "r", workspace=ws, expect=[
        "section 'Unclassified rule' (this repo's own sections) has no row",
        "gates.json row 'gone': no section 'Removed section' in CLAUDE.md",
        "gates.json row 'friday': rule not in section 'Never push on a Friday — ENFORCED': \"No push on a Friday\"",
        "gates.json row 'friday': gate gates/guard.sh not executable",
        "gates.json row 'short-names': prose without `why`",
        "gates.json row 'backup': plan PLAN-x.md has no §9 heading",
    ])
