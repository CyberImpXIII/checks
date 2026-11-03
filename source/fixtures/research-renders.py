from checkslib.fixture import Fixture, write


def _ws(t, top):
    ws = t / "ws"
    write(ws / "CLAUDE.md", "# top\n")
    write(ws / "tools" / "research" / "docs" / "RESEARCH-x.md", "# rendered\n")
    write(ws / "tools" / "research" / "archive" / "RESEARCH-y.md", "> Archived\n# y\n")
    write(ws / "PLAN-research.md", "not a research document\n")
    for name in top:
        write(ws / name, "# hand-written\n")
    return ws


def passing(t):
    ws = _ws(t, [])
    return Fixture(ws, workspace=ws)


def failing(t):
    ws = _ws(t, ["RESEARCH-z.md"])
    return Fixture(ws, workspace=ws, expect=["RESEARCH-z.md: a research document at the top"])
