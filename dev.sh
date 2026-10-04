#!/usr/bin/env bash
# SETUP-STUB: installed by the setup tool. Replace this file with the repo's real
# pre-commit command; setup reports the repo as `needs owner` while this line is here.
#
# The contract: `./dev.sh check` runs every gate this repo has and exits non-zero
# if any fails; `./dev.sh check --json` prints {"ok": bool, ...} on stdout.
# This stub never fakes green: it fails until the owner fills it in.
set -uo pipefail

usage() {
  cat <<'EOF'
./dev.sh <command>

  check      every gate this repo has (run this before committing)
EOF
}

cmd_check() {
  if [ "${1:-}" = "--json" ]; then
    printf '{"ok": false, "error": "not implemented: fill in the contract"}\n'
  else
    echo "not implemented: fill in the contract (./dev.sh check is the setup stub)"
  fi
  return 1
}

case "${1:-}" in
  check) shift; cmd_check "$@" ;;
  ""|-h|--help|help) usage ;;
  *) echo "unknown command: $1"; usage; exit 2 ;;
esac
