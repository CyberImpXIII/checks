#!/usr/bin/env python3
# checks: applies_to=all
# Proves: every store a CLI writes whole (a JSON or other plain file), and every
# file it renders, sits read-only on disk -- no write bit for anyone (mode 0444
# or tighter) -- so a stray Edit, `>>`, `cp` or `git stash` fails loudly or is
# seen, instead of landing around the CLI (PLAN-services.md §3, "Every data
# store is gated and read-only", rules 2 and 5; INCIDENTS.md I-3: a stash
# rewrote 13 such files at 0644, and only the repos whose own cli.json named
# them saw it). The CLI makes the file writable for its own write and sets it
# back. The files judged here are those named by:
#   - this repo's own cli.json `store` and `renders`;
#   - every other workspace repo's cli.json whose `store_scope` is `workspace`
#     (its CLI keeps its store in each repo it runs in, as tools/todo does):
#     its `store` entries here, and its `renders` here when one of those
#     stores is here. The workspace's repos are the ones `checks all` walks.
#   A file two CLIs both claim is a finding.
#   A SQLite store (*.db, *.sqlite, *.sqlite3 and their -wal/-shm/-journal
#   files) stays writable while its CLI runs (WAL, several writers), so its
#   mode is not judged: the store hook and `accessor` hold rule 2 for it.
#   Mode is a signal, not the seal: `sed -i` and `mv` replace a 0444 file
#   (the planner's probe, same section). This check proves the mode only.
# n/a: no store or render is declared for this repo by any CLI, or every
# store is SQLite. UNCHECKED: this repo's cli.json does not keep its contract
# (`accessor` reports how), its store matches no file, or there is no
# workspace top around the repo, so other CLIs' stores here cannot be known
# (its own are still judged, and a writable one is still a finding). Never
# plain ok without at least one file judged.
# To pass: `chmod a-w <file>`, and make the CLI restore that mode after each
# write (chmod u+w, write, chmod a-w); a file the CLI does not write whole
# does not belong in cli.json's `store`.
import os
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checkslib import api, contract, runner, scan, stores  # noqa: E402

SQLITE = stores.SQLITE
SQLITE_SIDE = [g + s for g in SQLITE for s in stores.SQLITE_SIDE]
WORKSPACE = "workspace"


def renders(doc, files):
    return sorted({p for k in (doc.get("renders") or {}) for p in contract.entry_files(k, files)})


def foreign(ctx, files):
    """({file: [cli dir, ...]}, None) for other workspace CLIs whose store lives in
    every repo; (None, why) when there is no workspace top around this repo."""
    if ctx.workspace is None or ctx.rel is None:
        return None, "no workspace top around this repo: other CLIs' stores here cannot be known"
    claims = {}
    for other in runner.discover(ctx.workspace):
        if other.resolve() == ctx.repo:
            continue
        doc, found = contract.read(other, contract.CLI)
        if doc is None or found or doc.get("store_scope") != WORKSPACE:
            continue                    # a broken cli.json is its own repo's finding (accessor)
        held = contract.store_files(doc, files)
        who = runner.rel(other, ctx.workspace)
        for p in held + (renders(doc, files) if held else []):
            claims.setdefault(p, []).append(who)
    return claims, None


def main():
    ctx = api.context()
    files = scan.walk(ctx.repo)
    doc, found = contract.read(ctx.repo, contract.CLI)
    if found:
        what = "does not keep its contract (`accessor` says how)" if doc is None else "breaks a rule (`accessor` says which)"
        api.done(unchecked=f"{contract.CLI} {what}; no store judged: {found[0][:200]}")
    own = []
    if doc is not None:
        own = contract.store_files(doc, files)
        if contract.has_store(doc) and not own:
            api.done(unchecked=f"{contract.CLI}'s store matches no file on disk: no store to judge")
        own += renders(doc, files)
    claims, blind = foreign(ctx, files)
    claims = claims or {}
    findings = [f"{p}: claimed by two CLIs (this repo's and {', '.join(claims[p])}'s): one store has one CLI"
                for p in sorted(set(own) & set(claims))]
    files_judged = sorted(set(own) | set(claims))
    judged = [p for p in files_judged if not scan.matches(Path(p).name, SQLITE + SQLITE_SIDE)]
    for rel in judged:
        mode = stat.S_IMODE(os.stat(ctx.repo / rel).st_mode)
        if mode & 0o222:
            who = f" ({', '.join(claims[rel])}'s)" if rel in claims and rel not in own else ""
            findings.append(f"{rel}{who}: writable (mode {mode:04o}); a store its CLI writes whole sits at 0444")
    if findings:
        api.done(findings)
    if blind:
        api.done(unchecked=f"{blind}" + (f"; this repo's own are read-only: {', '.join(judged)}" if judged else ""))
    if not files_judged:
        api.done(na="no store or render is declared here by any CLI: none to judge")
    if not judged:
        api.done(na="every store is SQLite (kept writable for its WAL): its mode is not judged; "
                    "the store hook and `accessor` hold it")
    print("read-only: " + ", ".join(f"{p} ({', '.join(claims[p])})" if p in claims else p for p in judged))
    api.done()


main()
