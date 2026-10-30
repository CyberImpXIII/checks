import json
import os

from checkslib.fixture import Fixture, git_repo, write

CLI = """#!/usr/bin/env bash
case "${1:-}" in
  add) echo add ;;
  *) printf 'todo.sh <verb>\\n\\n  add      add an item\\n' ;;
esac
"""


# A workspace with two repos. `r` names a JSON store and a SQLite store in its own
# cli.json; `tools/list` is a CLI whose store lives in every repo it runs in
# (`store_scope: workspace`), and `r` holds one of its files and the render beside
# it. The two fixtures differ only in the mode of r's own JSON store, so the mode is
# what turns the result; the SQLite store stays 0644 in both (its mode is not
# judged), and the other CLI's files sit at 0444 in both.
def _ws(t, mode):
    ws = t / "ws"
    write(ws / "CLAUDE.md", "# top\n")
    git_repo(ws / "tools" / "list", {"CLAUDE.md": "# list\n", "list.sh": CLI,
                                     "cli.json": json.dumps({"store": ["list.json"], "store_scope": "workspace",
                                                             "renders": {"LIST.md": "add"}, "cli": "list.sh",
                                                             "verbs": ["add"]})})
    r = git_repo(ws / "r", {"CLAUDE.md": "# r\n", "todo.sh": CLI, ".gitignore": "data/\n",
                            "cli.json": json.dumps({"store": ["todo.json", "data/app.db"], "cli": "todo.sh",
                                                    "verbs": ["add"]})})
    write(r / "data" / "app.db", "")
    write(r / "todo.json", "{}\n")
    os.chmod(r / "todo.json", mode)
    for rel in ("list.json", "LIST.md"):
        write(r / rel, "x\n", 0o444)
    return ws, r


def passing(t):
    ws, r = _ws(t, 0o444)
    return Fixture(r, workspace=ws)


def failing(t):
    ws, r = _ws(t, 0o644)
    return Fixture(r, workspace=ws, expect=["todo.json: writable (mode 0644)"])
