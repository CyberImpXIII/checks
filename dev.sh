#!/usr/bin/env bash
# The one pre-commit command for tools/checks, and the home of every check it
# repeats. The contract: `./dev.sh check` runs every gate this repo has, in
# parts, and exits non-zero if any fails; `--json` prints the one schema
# (schema/check-json.schema.json). The parts are check.parts.json, run by the
# shared runner checkslib/parts.py (PLAN-small-tasks §7): each part has its
# own timeout, each result is written to .progress/check.json as it ends, and
# `--resume` re-runs only the parts whose files changed since they passed.
# CHECK_PARTS=<file> runs that file's parts instead (check-partial hands it a
# suite of its own). tests/test_parts.py holds check.parts.json to the test
# modules and to the steps below.
# usage() below and the case at the bottom are held equal by tests/test_meta.py
# and by this repo's own help-matches check.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$HERE" || exit 2

usage() {
  cat <<'EOF'
./dev.sh <command>

  check      every part of check.parts.json (a part per test module, then fixtures, run, audit), each with its own timeout; ends "check: N of M passed; failed: ..."; non-zero if any fails (--json: schema/check-json.schema.json; --resume: only the parts whose files changed since they passed; --only <part>: just that part; CHECK_PARTS=<file>: that file's parts instead)
  test       the CLI's unit tests, all at once (python3 -m unittest, tests/test_*.py); `test <part>...`: just those parts of check.parts.json (check --only <part>...), results in the progress file, so a later check --resume skips them while their files are unchanged
  fixtures   every check against its own passing and failing fixture (./checks fixtures)
  run        every check that applies to this repo, on this repo (./checks run .)
  audit      this tool reads no roster (./checks one no-roster .)
EOF
}

cmd_check() { exec python3 "$HERE/checkslib/parts.py" run "${CHECK_PARTS:-$HERE/check.parts.json}" "$@"; }
cmd_test() {
  if [ "$#" -gt 0 ]; then
    local only=() p
    for p in "$@"; do only+=(--only "$p"); done
    cmd_check "${only[@]}"
  fi
  python3 -m unittest discover -s tests -t . -p 'test_*.py' 2>&1 | tail -n 25; return "${PIPESTATUS[0]}"
}
cmd_fixtures() { ./checks fixtures; }
cmd_run() { ./checks run . "$@"; }
cmd_audit() { ./checks one no-roster . "$@"; }

case "${1:-}" in
  check) shift; cmd_check "$@" ;;
  test) shift; cmd_test "$@" ;;
  fixtures) cmd_fixtures ;;
  run) shift; cmd_run "$@" ;;
  audit) shift; cmd_audit "$@" ;;
  ""|-h|--help|help) usage ;;
  *) echo "unknown command: $1"; usage; exit 2 ;;
esac
