"""A registry with a practices block: one principle, a gate row held by one of
this tool's checks, a hook row read through hooks-installed, a prose row with a
recorded cell, an unbuilt row, a repo's own row, a superseded row, and one
blocked row. Gate paths and sources are files in the fixture's workspace; the
check names are this source's (the validator reads `checks list`)."""
import json

from checkslib.fixture import Fixture, write

KEYS = {k: "meaning" for k in ("id", "part", "principle", "rule", "sources", "applies", "held",
                               "subject", "status", "own_ids", "cells")}

ROWS = [
    {"id": "root-x", "part": "A", "rule": "make the wrong thing impossible", "sources": ["PLAN-x.md §5"],
     "applies": "all", "held": {"kind": "rollup", "text": "rollup of its rows"}, "status": "live"},
    {"id": "rules-classified", "part": "B", "principle": "root-x", "rule": "every rule is classified",
     "sources": ["PLAN-x.md §5", "gates:r#friday"], "applies": "all",
     "held": {"kind": "gate", "text": "gate tools/checks/source/rules-gated.py", "gate": "tools/checks/source/rules-gated.py",
              "check": "rules-gated"}, "subject": ["seam"], "status": "live"},
    {"id": "no-blobs", "part": "B", "principle": "root-x", "rule": "no inline blobs",
     "sources": ['CLAUDE.md "Never write an inline script blob"'], "applies": "all",
     "held": {"kind": "gate", "text": "gate tools/hooks/source/hooks/no-inline-blobs.sh",
              "gate": "tools/hooks/source/hooks/no-inline-blobs.sh", "via": "hooks-installed"},
     "subject": ["behaviour"], "status": "live"},
    {"id": "ask-first", "part": "B", "principle": "root-x", "rule": "ask before sending",
     "sources": ["memory:feedback_ask.md"], "applies": ["r"],
     "held": {"kind": "prose", "text": "prose: the send path asks", "shows": "the send path asks"},
     "status": "live", "cells": {"r": {"state": "justified", "why": "r sends nothing"}}},
    {"id": "verbs-later", "part": "B", "principle": "root-x", "rule": "a verb for every repeat",
     "sources": ["docs/verbs.txt"], "applies": "all", "held": {"kind": "unbuilt", "text": "unbuilt"},
     "status": "live"},
    {"id": "own-r", "part": "C", "rule": "r keeps its own rows", "sources": ["gates:r#friday"], "applies": ["r"],
     "held": {"kind": "prose", "text": "prose"}, "status": "live", "own_ids": ["friday"]},
    {"id": "old-rule", "rule": "the old wording", "sources": ["PLAN-x.md §5"], "status": "superseded-by rules-classified"},
]

BLOCKED = [{"id": "root-y", "conflict": "C1", "why": "whether it is a principle at all"}]


def _ws(t, rows, blocked=BLOCKED, keys=KEYS):
    ws = t / "ws"
    write(ws / "PLAN-x.md", "# PLAN x\n\n## 5. Roots\n")
    write(ws / "CLAUDE.md", "# top\n\n## Never write an inline script blob — ENFORCED\n")
    write(ws / "docs" / "verbs.txt", "verbs\n")
    write(ws / "tools" / "checks" / "source" / "rules-gated.py", "#!/usr/bin/env python3\n", 0o755)
    write(ws / "tools" / "hooks" / "source" / "hooks" / "no-inline-blobs.sh", "#!/bin/sh\n", 0o755)
    write(ws / "r" / "gates.json", json.dumps({"rules": [{"id": "friday"}]}) + "\n")
    block = {"_comment": "practice rows", "keys": keys, "rows": rows, "blocked": blocked}
    write(ws / "reg" / "gates.json", json.dumps({"_comment": "c", "rules": [], "practices": block}, indent=1) + "\n")
    return ws


def passing(t):
    ws = _ws(t, ROWS)
    return Fixture(ws / "reg", workspace=ws)


def failing(t):
    rows = [json.loads(json.dumps(r)) for r in ROWS]
    rows[1]["principle"] = "root-gone"                       # rootless
    rows[1]["held"]["check"] = "rules-gate"                  # not the check its gate is
    rows[2]["held"].pop("via")                               # a hook gate with no reader
    rows[3]["cells"]["r"] = {"state": "held"}                # a bare held, no why
    rows[4]["sources"] = ["docs/missing.txt"]                # a source that does not resolve
    rows[5]["principle"] = "root-y"                          # serves a blocked principle
    rows[6]["status"] = "superseded-by nowhere"              # successor is no row
    rows.append({"id": "root-y", "part": "A", "rule": "r", "sources": ["PLAN-x.md §5"], "applies": "all",
                 "held": {"kind": "rollup", "text": "rollup"}, "status": "live"})   # both a row and blocked
    keys = {k: v for k, v in KEYS.items() if k != "cells"}
    ws = _ws(t, rows, keys=keys)
    return Fixture(ws / "reg", workspace=ws, expect=[
        "practices: `keys` must name exactly the row keys",
        "practices: 'root-y' is both a row and blocked",
        "practice 'rules-classified': `principle` 'root-gone' is no part A row (a rootless row)",
        "practice 'rules-classified': gate tools/checks/source/rules-gated.py is check 'rules-gated': `check` must say so",
        "practice 'rules-classified': `check` 'rules-gate' is no check (checks list)",
        "practice 'no-blobs': a shared hook gate is read through `via: hooks-installed`",
        "practice 'ask-first': cell 'r': a recorded cell is {state: justified|unjustified, why}",
        "practice 'verbs-later': source does not resolve: docs/missing.txt",
        "practice 'own-r': its principle 'root-y' is blocked: block this row too",
        "practice 'old-rule': superseded by 'nowhere', which is no row",
    ])
