import json

from checkslib.fixture import Fixture, git_repo

DEV = """#!/usr/bin/env bash
case "${1:-}" in
  check) echo ok ;;
  *) printf './dev.sh <command>\\n\\n  check    every gate\\n' ;;
esac
"""
STORE = """#!/usr/bin/env bash
case "${1:-}" in
  add|list) echo "$1" ;;
  *) printf 'store.sh <verb>\\n\\n  add      add a row\\n  list     list rows\\n' ;;
esac
"""
CLI = json.dumps({"store": ["data.db", "notes.json"], "cli": "store.sh", "verbs": ["add", "list"]})


def _repo(t, **fields):
    services = dict({"name": "r", "services": [{"service": "check", "run": "dev.sh", "verbs": ["check"]}]}, **fields)
    return git_repo(t / "r", {"dev.sh": DEV, "store.sh": STORE, "cli.json": CLI,
                              "services.json": json.dumps(services, indent=1)})


def passing(t):
    return Fixture(_repo(t, description="r: keeps rows and notes", stores=["./data.db", "notes.json"],
                         shapes={"reads": ["row.v1"], "emits": ["note.v1"]}))


def failing(t):
    # No description; `stores` names one store cli.json does not declare and
    # leaves out one it does: each rule's finding, every one listed.
    return Fixture(_repo(t, stores=["data.db", "cache.db"]),
                   expect=["lag: services.json: no `description`",
                           "lag: services.json: stores-declared: $.stores: `cache.db` is not a store cli.json declares",
                           "lag: services.json: `stores` lacks `notes.json`, a store cli.json declares"])
