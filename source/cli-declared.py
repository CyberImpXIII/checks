#!/usr/bin/env python3
# checks: applies_to=roles:lag
# Proves: the repo declares its verbs (PLAN-architecture.md §12.1: "Each
# repo's cli.json lists its verbs"; everything usable via a CLI): a cli.json
# exists at its root, fits schema/cli.schema.json and its rules (store
# optional: a CLI over no store declares its verbs too), and lists at least
# one verb (setup's skeleton `verbs: []` declares nothing). Each miss is a
# finding that starts `lag:`, one per repo: a requirement added after the repo
# was set up (PLAN-architecture.md §11 S0, "a lag is a `lag` item, one per
# requirement and repo"), so it runs only when the caller asks for lags
# (`checks all --roles lag`), never in a repo's pre-commit, which it would
# turn red for a requirement its owner has not yet met.
# On ok it names the verb count and the read verbs (`repro`'s list).
# To pass: write cli.json at the repo root: `{"cli": "<your CLI>", "verbs":
# [...]}` (plus `store` when the CLI is the way into one), every verb one
# `<cli> help` lists; add `read` for the verbs that only read, so `repro` can
# run them twice.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checkslib import api, contract  # noqa: E402

LAG = "lag:"


def main():
    ctx = api.context()
    doc, found = contract.read(ctx.repo, contract.CLI)
    if doc is None and not found:
        api.done([f"{LAG} no {contract.CLI}: this repo declares no CLI and no verbs "
                  f"(PLAN-architecture.md §12.1)"])
    if found:
        api.done([f"{LAG} {f}" for f in found])
    if not doc["verbs"]:
        api.done([f"{LAG} {contract.CLI}: declares no verbs (`verbs` is empty): nothing is usable through `{doc['cli']}`"])
    reads = sorted((doc.get("read") or {}).get("verbs") or {})
    print(f"{len(doc['verbs'])} verb(s) through `{doc['cli']}`; read verbs: {', '.join(reads) or 'none declared'}")
    api.done()


main()
