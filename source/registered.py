#!/usr/bin/env python3
# checks: applies_to=roles:lag
# Proves: the repo is registered as a tool (PLAN-architecture.md §6 "Every
# tool registered", §9 step 10.1) in its own services.json: the file exists
# and keeps its contract (schema/services.schema.json and every x-rule, the
# same reading services-valid uses: a blank or multi-line `description`, or a
# `stores` entry cli.json's `store` does not declare, is a finding); it has a
# `description`, the one line that registers it; and its `stores` lists every
# store cli.json declares (the two lists are one fact written twice, held
# equal both ways). The reading is checkslib/registry.py, shared with `checks
# tools`, the collected list.
# Every finding starts `lag:`, one per repo: a requirement added after the
# repos were set up, so it runs only when the caller asks for lags (`checks
# all --roles lag`, or `checks one registered <repo>`), never in a repo's
# pre-commit, which it would turn red for a description its owner has not
# yet written (step 10.3 drafts them). services-valid (all) still gates a
# services.json pre-commit, the `stores` it declares included.
# A cli.json that cannot be read, with nothing else found, is UNCHECKED: the
# stores half is unread, never passed. Not judged: that a `shapes` id exists
# in data-bridge, or that the description is true.
# On ok it prints the entry's line in the collected list.
# To pass: add `"description": "<one line: what this tool is for>"` to
# services.json, and `"stores": [...]` naming every store cli.json's `store`
# names (`[]` when it owns none); `shapes: {reads, emits}` where it has any.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checkslib import api, registry  # noqa: E402

LAG = "lag:"


def main():
    e = registry.entry(api.context().repo)
    if e["findings"]:
        api.done([f"{LAG} {f}" for f in e["findings"]])
    if e["unchecked"]:
        api.done(unchecked=e["unchecked"])
    print(registry.line(e))
    api.done()


main()
