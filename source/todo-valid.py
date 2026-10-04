#!/usr/bin/env python3
# checks: applies_to=all
# Proves: the repo keeps a TODO.md (the shared rule "Keep an active TODO"),
# and it is not empty: it has at least one heading.
# When the repo also has a todo.json (the todo tool's store), TODO.md must be
# its render. That comparison belongs to `todo check`, which is not wired in
# here yet, so a repo with a todo.json is UNCHECKED, said out loud, rather than
# passed on presence alone.
# To pass: create TODO.md (the setup tool writes one with the four standard
# headings: own bugs, open decisions, unconfirmed suspicions, reported to
# other owners).
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checkslib import api  # noqa: E402


def main():
    ctx = api.context()
    todo = ctx.repo / "TODO.md"
    if not todo.is_file():
        api.done(["TODO.md: missing"])
    if not re.search(r"^#{1,6} \S", todo.read_text(errors="replace"), re.M):
        api.done(["TODO.md: no heading; an empty TODO is not a kept one"])
    if (ctx.repo / "todo.json").exists():
        api.done(unchecked="TODO.md present; todo.json present too, and rendered == store needs "
                           "`todo check`, which this check does not call yet")
    api.done()


main()
