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

# The check's pass record (remediation 2.3, 2026-10-30; the same steps as
# tools/setup's dev.sh cmd_check). A green run of this repo's whole suite
# records the tree it ran on for the git pre-commit hook (.githooks/check-pass,
# setup's githooks component), on stderr so --json stays one document. Never
# recorded: --only, CHECK_PARTS, a tree that changed meanwhile (check-pass
# refuses), or a run in which a part said UNCHECKED (green by exit code, never a
# pass). Not recording never turns a green check red: the commit is what is
# refused.
#   pass_tree <check args>           the tree to record, taken before the first part
#   pass_record <code> <tree> <check args>   records it when code is 0; returns code
pass_tree() {
  local a top
  [ -n "${CHECK_PARTS:-}" ] && return 0
  for a in "$@"; do [ "$a" = --only ] && return 0; done
  top=$(git rev-parse --show-toplevel 2>/dev/null) || return 0
  [ -x "$top/.githooks/check-pass" ] && "$top/.githooks/check-pass" tree 2>/dev/null
  return 0
}
pass_record() {
  local code=$1 tree=$2 a resume=0 top pf state rf args
  shift 2
  { [ "$code" -eq 0 ] && [ -n "$tree" ]; } || return "$code"
  for a in "$@"; do [ "$a" = --resume ] && resume=1; done
  top=$(git rev-parse --show-toplevel)
  pf=${PROGRESS_FILE:-$top/.progress/check.json}
  state=$(jq -r 'if (.passed_steps | length) == .total and .state == "passed" then "all" else "partial" end' "$pf" 2>/dev/null)
  if [ "$state" != all ]; then
    echo "check: green, but not every part passed (one said UNCHECKED, or $pf is unreadable): the pass was not recorded" >&2
    return "$code"
  fi
  args=(--from "$tree")
  if [ $resume = 1 ]; then
    rf=$(jq -r 'if .resumed_from == null then "-" else (.resumed_from | capture("^(?<r>[0-9]+/[0-9]+) at ").r) end' "$pf" 2>/dev/null)
    [ -n "$rf" ] || { echo "check: green, but the resume point in $pf could not be read: the pass was not recorded" >&2; return "$code"; }
    [ "$rf" != - ] && args+=(--resumed-from "$rf")
  fi
  (cd "$top" && .githooks/check-pass record "${args[@]}" >&2) || echo "check: green, but the pass was not recorded (see above)" >&2
  return "$code"
}
cmd_check() {
  local tree; tree=$(pass_tree "$@")
  python3 "$HERE/checkslib/parts.py" run "${CHECK_PARTS:-$HERE/check.parts.json}" "$@"
  pass_record $? "$tree" "$@"; exit $?
}
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
