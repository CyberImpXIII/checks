#!/usr/bin/env python3
# checks: applies_to=all
# Proves: every store the repo's cli.json names that its CLI writes whole (a
# JSON or other plain file) sits read-only on disk -- no write bit for anyone
# (mode 0444 or tighter) -- so a stray Edit, `>>` or `cp` fails loudly instead
# of landing around the CLI (PLAN-services.md §3, "Every data store is gated
# and read-only", rules 2 and 5). The CLI makes the file writable for its own
# write and sets it back.
#   A SQLite store (*.db, *.sqlite, *.sqlite3 and their -wal/-shm/-journal
#   files) stays writable while its CLI runs (WAL, several writers), so its
#   mode is not judged: the store hook and `accessor` hold rule 2 for it.
#   Mode is a signal, not the seal: `sed -i` and `mv` replace a 0444 file
#   (the planner's probe, same section). This check proves the mode only.
# No cli.json is UNCHECKED (no store declared, so none to judge); so is a
# cli.json with no `store`, a cli.json that does not keep its contract (`accessor` reports how), a store
# that matches no file, and a repo whose every store is SQLite. Never ok
# without at least one store judged.
# To pass: `chmod a-w <store>`, and make the CLI restore that mode after each
# write (chmod u+w, write, chmod a-w); a file the CLI does not write whole
# does not belong in cli.json's `store`.
import os
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checkslib import api, contract, scan  # noqa: E402

SQLITE = ["*.db", "*.sqlite", "*.sqlite3"]
SQLITE_SIDE = [g + s for g in SQLITE for s in ("-wal", "-shm", "-journal")]


def main():
    ctx = api.context()
    doc, found = contract.read(ctx.repo, contract.CLI)
    if doc is None:
        if found:
            api.done(unchecked=f"{contract.CLI} does not keep its contract (`accessor` says how); "
                               "no store judged: " + found[0][:200])
        api.done(unchecked=f"no {contract.CLI}: no store declared here, so none to judge")
    if found:
        api.done(unchecked=f"{contract.CLI} breaks a rule (`accessor` says which); no store judged: {found[0][:200]}")
    if not contract.has_store(doc):
        api.done(unchecked=f"{contract.CLI} declares no `store` (a CLI over no store): none to judge")
    files =contract.store_files(doc, scan.walk(ctx.repo))
    if not files:
        api.done(unchecked=f"{contract.CLI}'s store matches no file on disk: no store to judge")
    judged = [p for p in files if not scan.matches(Path(p).name, SQLITE + SQLITE_SIDE)]
    if not judged:
        api.done(unchecked="every store is SQLite (kept writable for its WAL): its mode is not judged; "
                           "the store hook and `accessor` hold it")
    findings = []
    for rel in judged:
        mode = stat.S_IMODE(os.stat(ctx.repo / rel).st_mode)
        if mode & 0o222:
            findings.append(f"{rel}: writable (mode {mode:04o}); a store its CLI writes whole sits at 0444")
    if not findings:
        print("read-only: " + ", ".join(judged))
    api.done(findings)


main()
