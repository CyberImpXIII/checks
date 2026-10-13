"""repro's fixtures: a CLI with a reproducible read verb (`count`: the fixture's
rows, sorted) and one that prints the time (`stamp`). Passing declares the
time volatile; failing does not, and fails for that reason alone (PLAN-
architecture.md §12 gates: "a verb that prints the time fails `checks repro`,
and the same verb with the time declared volatile passes")."""
import json

from checkslib.fixture import Fixture, git_repo, write

TOOL = """#!/usr/bin/env python3
import json, os, sys, time
verb = sys.argv[1] if len(sys.argv) > 1 else "help"
if verb == "help":
    print("tool <verb>\\n\\n  tool count   the fixture's rows, sorted\\n  tool stamp   the time, asked for")
elif verb == "count":
    rows = sorted(open(os.path.join(os.environ["TOOL_DATA"], "rows.txt")).read().split())
    print(json.dumps({"rows": rows, "n": len(rows)}))
elif verb == "stamp":
    print(json.dumps({"at": time.time_ns(), "who": "tool"}))
else:
    sys.exit(2)
"""


def _repo(t, stamp):
    doc = {"cli": "tool", "verbs": ["count", "stamp"],
           "read": {"fixture": "fx", "env": {"TOOL_DATA": "{fixture}"},
                    "verbs": {"count": {"args": ["--json"]}, "stamp": stamp}}}
    r = git_repo(t / "r", {"cli.json": json.dumps(doc), "fx/rows.txt": "b\na\nc\n"})
    write(r / "tool", TOOL, 0o755)
    return r


def passing(t):
    return Fixture(_repo(t, {"args": ["--json"], "volatile": ["at"]}))


def failing(t):
    return Fixture(_repo(t, {"args": ["--json"]}),
                   expect=["`stamp`: two runs differ after the volatile fields are removed, first at $.at"])
