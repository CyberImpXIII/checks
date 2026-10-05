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


def _repo(t, write_verbs):
    services = {"name": "r", "tags": ["r"],
                "services": [{"service": "check", "run": "dev.sh", "verbs": ["check"]},
                             {"service": "write", "run": "store.sh", "verbs": write_verbs}]}
    return git_repo(t / "r", {"dev.sh": DEV, "store.sh": STORE,
                              "cli.json": json.dumps({"store": "data.db", "cli": "store.sh", "verbs": ["add", "list"]}),
                              "services.json": json.dumps(services, indent=1)})


def passing(t):
    return Fixture(_repo(t, ["add", "list"]))


def failing(t):
    return Fixture(_repo(t, ["add", "purge"]),
                   expect=["services.json: verb-implemented: $.services[1]: `store.sh` does not implement `purge`",
                           "services.json: write-declared: $.services[1]: `purge` is not a verb cli.json declares"])
