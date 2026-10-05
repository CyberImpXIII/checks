import json

from checkslib.fixture import Fixture, git_repo, write

STORE = """#!/usr/bin/env bash
case "${1:-}" in
  verify)
    src="$DATA_REPO/r/rows.txt"
    if [ ! -f "$src" ]; then s=missing; elif cmp -s "$src" data/app.db; then s=same; else s=differs; fi
    printf '{"items": [{"item": "rows", "status": "%s"}]}\\n' "$s"
    [ "$s" = same ] ;;
  export) mkdir -p "$DATA_REPO/r" && cp data/app.db "$DATA_REPO/r/rows.txt" ;;
  *) printf 'store.sh <verb>\\n\\n  export   write the store to the data repo\\n  verify   compare the two\\n' ;;
esac
"""


def _repo(t, exported):
    r = git_repo(t / "r", {"store.sh": STORE, ".gitignore": "data/\n",
                           "cli.json": json.dumps({"store": "data/app.db", "cli": "store.sh",
                                                   "verbs": ["export", "verify"]})})
    write(r / "store.sh", STORE, 0o755)
    write(r / "data" / "app.db", "row one\nrow two\n")
    write(t / "data" / "r" / "rows.txt", exported)
    return Fixture(r, env={"DATA_REPO": str(t / "data")})


def passing(t):
    return _repo(t, "row one\nrow two\n")


def failing(t):
    fx = _repo(t, "row one\n")                       # a row written to the store, never exported
    fx.expect = ["rows: differs"]
    return fx
