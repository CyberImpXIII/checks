import json
import os

from checkslib.fixture import Fixture, git_repo, write

CLI = """#!/usr/bin/env bash
case "${1:-}" in
  add) echo add ;;
  *) printf 'todo.sh <verb>\\n\\n  add      add an item\\n' ;;
esac
"""


# A JSON store and a SQLite store, both named in cli.json. The two fixtures
# differ only in the JSON store's mode, so the mode is what turns the result;
# the SQLite store stays 0644 in both (its mode is not judged).
def _repo(t, mode):
    r = git_repo(t / "r", {"todo.sh": CLI, ".gitignore": "data/\n",
                           "cli.json": json.dumps({"store": ["todo.json", "data/app.db"], "cli": "todo.sh",
                                                   "verbs": ["add"]})})
    write(r / "data" / "app.db", "")
    write(r / "todo.json", "{}\n")
    os.chmod(r / "todo.json", mode)
    return r


def passing(t):
    return Fixture(_repo(t, 0o444))


def failing(t):
    return Fixture(_repo(t, 0o644), expect=["todo.json: writable (mode 0644)"])
