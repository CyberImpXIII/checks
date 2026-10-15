#!/usr/bin/env python3
# checks: applies_to=roles:lag
# Proves: the repo keeps its work in a todo store (PLAN-architecture.md §11
# S1, "Work is invisible to the dispatcher"): a todo.json at its root, and
# that store passes its own gates, `tools/todo/todo -C <repo> --root <top>
# check`, read by checkslib/todocheck.py (the one reading, shared with
# todo-valid: a FAIL line is a finding; a broken output contract is an
# error, never a pass). Without a store, `todo ready` and `todo
# dispatchable` cannot see the repo's work, however long its TODO.md.
# Every finding starts `lag:`, one per repo: a requirement added after the
# repo was set up (§11 "Two kinds of cause": S1 is migration lag), so it runs
# only when the caller asks for lags (`checks all --roles lag`, or `checks
# one todo-store <repo>`), never in a repo's pre-commit, which it would turn
# red for a requirement its owner has not yet met. todo-valid (all) still
# gates a store that exists, pre-commit.
# A todo.json with no workspace top, or no tools/todo beside it, is
# UNCHECKED, said out loud: a store is never passed on presence alone.
# On ok it prints the store's `todo check` summary line.
# To pass: `tools/todo/todo -C <repo> init --prefix <xx>`, then bring the
# TODO.md items in (`todo import TODO.md`; PLAN-architecture.md §11 Q7) and
# fix what `todo -C <repo> check` names.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checkslib import api, todocheck  # noqa: E402

LAG = "lag:"


def main():
    ctx = api.context()
    if not (ctx.repo / todocheck.STORE).exists():
        api.done([f"{LAG} no {todocheck.STORE}: this repo's work is invisible to `todo ready` and "
                  f"`todo dispatchable` (PLAN-architecture.md §11 S1)"])
    findings, summary = todocheck.run(ctx, f"{todocheck.STORE} present, and no tools/todo beside the "
                                           f"workspace top to run `todo check` with")
    if findings:
        api.done([f"{LAG} {f}" for f in findings])
    print(summary)
    api.done()


main()
