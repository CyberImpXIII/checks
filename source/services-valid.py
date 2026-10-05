#!/usr/bin/env python3
# checks: applies_to=all
# Proves: the repo's services.json, its declaration ahead of time of what the
# node's server may do with it (PLAN-routing-tree.md §14.8), is valid: it fits
# schema/services.schema.json (no key the schema does not name: nothing
# undeclared), and every x-rule holds: exactly one `check` entry; every `run`
# is a path inside the repo, exists and is executable; every verb is one
# `<run> help` lists (read from a real run of it, checkslib/helptext.py); no
# entry, verb or tag twice; and a `write` entry over the CLI that cli.json
# names passes only verbs cli.json declares. Every finding is listed.
# No services.json is UNCHECKED: the contract is unmet, never a pass (setup
# installs the skeleton). That the node's registry agrees with this file is
# registry-matches, at the node.
# To pass: fix the entry the finding names: declare only verbs the program's
# help lists (or add the verb to the program and its help); point `run` at an
# executable inside the repo; keep one `check` entry.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checkslib import api, contract  # noqa: E402


def main():
    ctx = api.context()
    doc, found = contract.read(ctx.repo, contract.SERVICES)
    if doc is None and not found:
        api.done(unchecked=f"no {contract.SERVICES}: nothing is declared for the server to run here "
                           f"(the contract is unmet, never a pass)")
    api.done(found)


main()
