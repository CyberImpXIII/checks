#!/usr/bin/env python3
# checks: applies_to=all
# Proves: the repo keeps a TODO.md (the shared rule "Keep an active TODO"),
# and it is not empty: it has at least one heading.
# When the repo also has a todo.json (the todo tool's store), the store's own
# gates must pass too: this runs `tools/todo/todo -C <repo> --root <top> check`
# and fails on each of its FAIL lines (its `render` gate is the one that says
# TODO.md is the render of todo.json; WARN and INFO lines are not findings).
# The reading of that output is checkslib/todocheck.py, shared with
# todo-store: a broken contract (summary count, exit code, a silent `render`
# gate) is an error, red, never a pass (tests/test_contract.py holds this
# against the real tool). With no workspace top, or no tools/todo beside it,
# a repo with a todo.json is UNCHECKED, said out loud, rather than passed on
# presence alone. A repo WITHOUT a todo.json passes here: that it lacks one
# is `todo-store`'s lag finding (roles:lag), not a pre-commit fault.
# To pass: create TODO.md (the setup tool writes one with the four standard
# headings: own bugs, open decisions, unconfirmed suspicions, reported to
# other owners). With a todo.json: run `todo check` in the repo and fix what
# it names (a hand edit of TODO.md: `todo render`, see tools/todo's README).
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checkslib import api, todocheck  # noqa: E402


def main():
    ctx = api.context()
    todo = ctx.repo / "TODO.md"
    if not todo.is_file():
        api.done(["TODO.md: missing"])
    if not re.search(r"^#{1,6} \S", todo.read_text(errors="replace"), re.M):
        api.done(["TODO.md: no heading; an empty TODO is not a kept one"])
    if (ctx.repo / todocheck.STORE).exists():
        findings, _ = todocheck.run(ctx, "TODO.md present; todo.json present too, and no tools/todo beside "
                                         "the workspace top to run `todo check` with")
        api.done(findings)
    api.done()


main()
