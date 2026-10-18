#!/usr/bin/env python3
# checks: applies_to=roles:lag
# Proves: every store in the repo is classified, static or dynamic
# (PLAN-services.md §3 "Every store is static or dynamic", ST5), and each
# keeps what its kind promises. A store is every file cli.json's `store` or
# `renders` names (any extension) and every SQLite-named file on disk (*.db,
# *.sqlite, *.sqlite3, outside dot-folders, tests/, test/ and nested git
# repos); its kind is cli.json's `kinds` entry for its `store` entry or
# `renders` key. Findings, each prefixed `lag:` while this runs as a report:
#   - a store-shaped file cli.json does not declare, or a declared one with no kind;
#   - a dynamic store that is not a SQLite file, or whose PRAGMA user_version
#     is not its `schema_version` (unread, and not judged, while a non-empty
#     -wal sidecar exists);
#   - a static store that is writable, or whose first 2048 bytes do not name
#     its `producer`;
#   - a static store with `regen` that does not come back byte for byte when,
#     in a scratch copy of the repo (what a commit would carry, plus the
#     declared store files), it is deleted and `regen` is run (120s).
# Not seen: a JSON or TSV file a CLI writes that cli.json does not name;
# that an `immutable` store was never rewritten. The reading is
# checkslib/stores.py, shared with `checks stores` (the workspace report).
# On ok it prints every store with its kind; no store at all is ok. A
# cli.json that breaks its contract is UNCHECKED (`accessor` says how), and
# so is a regen that could not run (not a git repo, nested in a rebuild).
# Runs only under `checks all --roles lag` or `checks one stores-classified
# <repo>`, never pre-commit: it starts as the inventory (PLAN-services.md §4
# step 10.3) and becomes a gate (applies_to=all) once every repo is declared.
# To pass: name each store in cli.json's `store` (or `renders`), and give it
# a `kinds` entry: `{"kind": "dynamic", "schema_version": N, "export": "<verb>"}`
# for a service's SQLite file, `{"kind": "static", "producer": "<command>",
# "regen": ["<program>", ...]}` (or `"immutable": true`) for a process's
# output, which sits at 0444 with a header naming the producer.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checkslib import api, stores  # noqa: E402

LAG = "lag: "


def main():
    ctx = api.context()
    status, lines = stores.verdict(stores.inventory(ctx.repo, run_regen=True), prefix=LAG)
    if status == "fail":
        api.done(lines)
    if status == "unchecked":
        api.done(unchecked=lines[0])
    for l in lines:
        print(l)
    api.done()


main()
