import json

from checkslib.fixture import Fixture, git_repo, write

STORE = """#!/usr/bin/env bash
DB="$(dirname "$0")/data/app.db"
case "${1:-}" in
  add|list) echo "$1 $DB" ;;
  *) printf 'store.sh <verb>\\n\\n  add      add a row\\n  list     list rows\\n' ;;
esac
"""
CALLER = "#!/usr/bin/env bash\n./store.sh list   # the store's name is not here: the CLI is the way in\n"


def _repo(t, with_cli):
    files = {"store.sh": STORE, "report.sh": CALLER, ".gitignore": "data/\n"}
    if with_cli:
        # `renders` in store-guard's shape (path -> verb): accessor accepts it;
        # a wrong one is test_contract_files' renders-declared mutant.
        files["cli.json"] = json.dumps({"store": "data/app.db", "cli": "store.sh", "verbs": ["add", "list"],
                                        "renders": {"rows.txt": "list"}})
    r = git_repo(t / "r", files)
    write(r / "data" / "app.db", "")                 # the store: ignored by git, still found on disk
    return r


def passing(t):
    return Fixture(_repo(t, True))


def failing(t):
    return Fixture(_repo(t, False), expect=["data/app.db: a store with no cli.json naming its one CLI"])
