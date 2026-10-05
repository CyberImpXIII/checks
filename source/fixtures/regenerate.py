import json

from checkslib.fixture import Fixture, git_repo, write

RENDER = "#!/usr/bin/env bash\nset -e\ntr a-z A-Z < src.txt > out.txt\n"
NODE = {"rebuild": ["./render.sh"], "generated": ["out.txt"], "record": ["src.txt", "render.sh", "*.md", ".gitignore"],
        "children": ["child"]}


def _top(t):
    ws = git_repo(t / "ws", {"node.json": json.dumps(NODE), "render.sh": RENDER, "README.md": "# top\n",
                             "src.txt": "one\n", "out.txt": "ONE\n", ".gitignore": "state/\n"})
    write(ws / "state" / "cache.txt", "instance state: ignored, so never unaccounted\n")
    git_repo(ws / "child", {"anything.txt": "the child accounts for itself\n"})
    return ws


def passing(t):
    ws = _top(t)
    return Fixture(ws, workspace=ws)


def failing(t):
    ws = _top(t)
    write(ws / "stray.txt", "a file no list names\n")
    return Fixture(ws, workspace=ws, expect=["unaccounted: stray.txt: named by neither generated nor record"])
