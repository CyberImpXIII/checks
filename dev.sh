#!/usr/bin/env bash
# The one pre-commit command for tools/checks, and the home of every check it
# repeats. The contract: `./dev.sh check` runs every gate this repo has and
# exits non-zero if any fails; `./dev.sh check --json` prints {"ok": bool, ...}.
# usage() below and the case at the bottom are held equal by tests/test_meta.py
# and by this repo's own help-matches check.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE" || exit 2

usage() {
  cat <<'EOF'
./dev.sh <command>

  check      every gate below, in order; non-zero if any fails (--json: one line)
  test       the CLI's unit tests (python3 -m unittest, tests/test_*.py)
  fixtures   every check against its own passing and failing fixture (./checks fixtures)
  run        every check that applies to this repo, on this repo (./checks run .)
  audit      this tool reads no roster (./checks one no-roster .)
EOF
}

cmd_test() { python3 -m unittest discover -s tests -t . -p 'test_*.py' 2>&1 | tail -n 25; return "${PIPESTATUS[0]}"; }
cmd_fixtures() { ./checks fixtures; }
cmd_run() { ./checks run . "$@"; }
cmd_audit() { ./checks one no-roster . "$@"; }

cmd_check() {
  local json=0 step rc=0 failed=()
  [ "${1:-}" = "--json" ] && json=1
  for step in test fixtures run audit; do
    if [ "$json" = 1 ]; then
      "cmd_$step" >/dev/null 2>&1 || { rc=1; failed+=("$step"); }
    else
      echo "== $step"
      "cmd_$step" || { rc=1; failed+=("$step"); }
    fi
  done
  if [ "$json" = 1 ]; then
    local list=""
    [ "${#failed[@]}" -gt 0 ] && list="$(printf '"%s",' "${failed[@]}")" && list="${list%,}"
    printf '{"ok": %s, "failed": [%s]}\n' "$([ "$rc" = 0 ] && echo true || echo false)" "$list"
  else
    [ "$rc" = 0 ] && echo "check: all gates green" || echo "check: FAILED: ${failed[*]}"
  fi
  return "$rc"
}

case "${1:-}" in
  check) shift; cmd_check "$@" ;;
  test) cmd_test ;;
  fixtures) cmd_fixtures ;;
  run) shift; cmd_run "$@" ;;
  audit) shift; cmd_audit "$@" ;;
  ""|-h|--help|help) usage ;;
  *) echo "unknown command: $1"; usage; exit 2 ;;
esac
