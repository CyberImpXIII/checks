import json

from checkslib.fixture import Fixture, git_repo

TOOL = """#!/usr/bin/env bash
case "${1:-}" in
  help|"") printf 'tool.sh <verb>\\n\\n  tool.sh list    the rows\\n' ;;
  *) echo '{}' ;;
esac
"""


def passing(t):
    # The workspace top's shape: not a git repo itself, its files committed in
    # its .claude repo, which holds the cli.json (a plain repo's root cli.json
    # is tests/test_repro.py CliDeclared's case).
    top = t / "top"
    git_repo(top / ".claude", {"tool.sh": TOOL, "cli.json": json.dumps({"cli": "tool.sh", "verbs": ["list"]})})
    return Fixture(top)


def failing(t):
    return Fixture(git_repo(t / "r", {"tool.sh": TOOL, "README.md": "# r\n"}),
                   expect=["lag: no cli.json: this repo declares no CLI and no verbs"])
