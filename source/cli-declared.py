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
# The workspace top is not a git repo; its files are committed in its .claude
# repo, so a folder that is not a git repo, with no cli.json of its own and a
# .claude/ git repo holding one, is declared by .claude/cli.json
# (contract.cli_home; the ok line says so).
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
    home = contract.cli_home(ctx.repo)
    where = "" if home == ctx.repo else f"{home.name}/"
    doc, found = contract.read(home, contract.CLI)
    if doc is None and not found:
        api.done([f"{LAG} no {contract.CLI}: this repo declares no CLI and no verbs "
                  f"(PLAN-architecture.md §12.1)"])
    if found:
        api.done([f"{LAG} {where}{f}" for f in found])
    if not doc["verbs"]:
        api.done([f"{LAG} {where}{contract.CLI}: declares no verbs (`verbs` is empty): "
                  f"nothing is usable through `{doc['cli']}`"])
    reads = sorted((doc.get("read") or {}).get("verbs") or {})
    said = f"; declared in {where}{contract.CLI} (not a git repo: its .claude repo holds it)" if where else ""
    print(f"{len(doc['verbs'])} verb(s) through `{doc['cli']}`; read verbs: {', '.join(reads) or 'none declared'}{said}")
    api.done()


main()
