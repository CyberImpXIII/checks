from checkslib.fixture import Fixture, git_repo, write

# A stand-in for tools/todo's `todo check`, spelled out by hand: a clean store
# (every gate ok, `render` among them). tests/test_todo_valid.py breaks its
# output one way at a time; tests/test_contract.py runs the real tool.
TODO_OK = """#!/usr/bin/env bash
cat <<'OUT'
  ok    schema
  ok    render
  ok    history
todo check r: 1 open, 0 closed; 0 failed, 0 warning(s)
OUT
"""


def _ws(t, files):
    ws = t / "ws"
    write(ws / "CLAUDE.md", "# top\n")
    write(ws / "tools" / "todo" / "todo", TODO_OK, 0o755)
    return ws, git_repo(ws / "r", files)


def passing(t):
    ws, r = _ws(t, {"TODO.md": "# r TODO\n", "todo.json": "{}\n", "todo-history.json": "{}\n"})
    return Fixture(r, workspace=ws)


def failing(t):
    # The cause S1 names: a repo whose work lives in a hand-written TODO.md only.
    ws, r = _ws(t, {"TODO.md": "# r TODO\n\n## Own bugs\n\n- a bug the dispatcher cannot see\n"})
    return Fixture(r, workspace=ws, expect=["lag: no todo.json: this repo's work is invisible to `todo ready`"])
