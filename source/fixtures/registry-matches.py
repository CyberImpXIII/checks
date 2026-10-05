import json

from checkslib.fixture import Fixture, git_repo, write

TOP = {"name": "top", "services": [{"service": "check", "run": "dev.sh", "verbs": ["check"]}]}
CHILD = {"name": "child", "services": [{"service": "check", "run": "dev.sh", "verbs": ["check"]}], "tags": ["c"]}
NODE = {"rebuild": ["true"], "generated": ["registry.json"], "record": ["services.json", "node.json"],
        "children": ["child"], "registry": "registry.json"}


def _node(t, rows):
    r = git_repo(t / "r", {"node.json": json.dumps(NODE), "services.json": json.dumps(TOP),
                           "registry.json": json.dumps({"roles": "not read", "services": rows}, indent=1)})
    write(r / "child" / "services.json", json.dumps(CHILD))
    return r


def passing(t):
    return Fixture(_node(t, {".": TOP, "./child": CHILD}))


def failing(t):
    return Fixture(_node(t, {".": TOP, "child": CHILD, "ghost": CHILD}),
                   expect=["registry.json: row `ghost`: no matching services.json"])
