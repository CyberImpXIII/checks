from checkslib.fixture import Fixture, git_repo

DEV = """#!/usr/bin/env bash
usage() {
  cat <<'EOF'
./dev.sh <command>

  check    every gate
  {doc}
           a continuation line, deeper, never a command
EOF
}
case "${1:-}" in
  check) echo checking ;;
  {impl}) case "$2" in --x) echo x ;; esac ;;
  ""|-h|--help|help) usage ;;
  *) usage; exit 2 ;;
esac
"""


def passing(t):
    return Fixture(git_repo(t / "r", {"dev.sh": DEV.replace("{doc}", "test     the suite").replace("{impl}", "test")}))


def failing(t):
    repo = git_repo(t / "r", {"dev.sh": DEV.replace("{doc}", "ghost    documented only").replace("{impl}", "hidden")})
    return Fixture(repo, expect=["implemented, not in the help: hidden", "in the help, not implemented: ghost"])
