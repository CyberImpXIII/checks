import json

from checkslib.fixture import Fixture, git_repo

TOOL = """#!/usr/bin/env bash
case "${1:-}" in
  help|"") printf 'tool.sh <verb>\\n\\n  tool.sh list    the rows\\n' ;;
  *) echo '{}' ;;
esac
"""


def passing(t):
    return Fixture(git_repo(t / "r", {"tool.sh": TOOL,
                                      "cli.json": json.dumps({"cli": "tool.sh", "verbs": ["list"]})}))


def failing(t):
    return Fixture(git_repo(t / "r", {"tool.sh": TOOL, "README.md": "# r\n"}),
                   expect=["lag: no cli.json: this repo declares no CLI and no verbs"])
