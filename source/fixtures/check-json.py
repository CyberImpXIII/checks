from checkslib.fixture import Fixture, git_repo

# A dev.sh whose `check --json` prints {doc} and exits {code}. The two fixtures
# differ only in what it prints, so the printed document is what changes the result.
DEV = """#!/usr/bin/env bash
case "${1:-}" in
  check)
    if [ "${2:-}" = "--json" ]; then
      printf '%s\\n' '{doc}'
      exit {code}
    fi
    echo "text mode" ;;
esac
"""

# A red run in the right shape: check-json proves the shape, not a green suite.
CONFORMING = ('{"ok": false, "checks": ['
              '{"name": "suite", "status": "fail", "counts": {"failed": 1, "passed": 4},'
              ' "failures": [{"message": "expected 2, got 3", "file": "test/x.test.js", "line": 12, "role": "code"}]},'
              ' {"name": "tree", "status": "unchecked", "reason": "not a git repo", "counts": {"failed": 0},'
              ' "failures": []}]}')

# What tools/todo's `dev.sh check --json` printed on 2026-10-05: {"ok": bool, "gates": {name: bool}}.
GATES_ONLY = '{"ok": true, "gates": {"files": true, "audit": true}}'


def dev(doc, code):
    return DEV.replace("{doc}", doc).replace("{code}", str(code))


def passing(t):
    return Fixture(git_repo(t / "r", {"dev.sh": dev(CONFORMING, 1)}))


def failing(t):
    return Fixture(git_repo(t / "r", {"dev.sh": dev(GATES_ONLY, 0)}), expect=["schema: $: missing `checks`"])
