import json

from checkslib.fixture import Fixture, git_repo, write

RENDER = "#!/usr/bin/env bash\nset -e\ntr a-z A-Z < src.txt > out.txt\n"
NODE = {"rebuild": ["./render.sh"], "generated": ["out.txt"], "record": ["src.txt", "render.sh"]}


def _repo(t):
    return git_repo(t / "r", {"node.json": json.dumps(NODE), "render.sh": RENDER,
                              "src.txt": "one\ntwo\n", "out.txt": "ONE\nTWO\n"})


def passing(t):
    return Fixture(_repo(t))


def failing(t):
    r = _repo(t)
    write(r / "out.txt", "ONE\ntwo, edited by hand\n")      # uncommitted: a commit would carry it
    return Fixture(r, expect=["drift: out.txt: the render differs from the file (first at line 2)"])
