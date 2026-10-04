from checkslib.fixture import Fixture, write


def _ws(t, rows, repos):
    ws = t / "ws"
    table = "| Tool | What it's for |\n|---|---|\n" + "".join(f"| `{r}` | something |\n" for r in rows)
    write(ws / "CLAUDE.md", "# top\n\n| who | what |\n|---|---|\n| `nope/` | another table |\n\n" + table)
    write(ws / "one-file.py", "")
    for r in repos:
        (ws / r / ".git").mkdir(parents=True)
        write(ws / r / "CLAUDE.md", "# r\n")
    (ws / ".hidden" / ".git").mkdir(parents=True)        # pruned: a dot-folder is not a tool
    write(ws / ".hidden" / "CLAUDE.md", "# h\n")
    return ws


def passing(t):
    ws = _ws(t, ["a/", "deep/b/", "one-file.py"], ["a", "deep/b"])
    return Fixture(ws, workspace=ws)


def failing(t):
    ws = _ws(t, ["a/", "gone/"], ["a", "deep/b"])
    return Fixture(ws, workspace=ws, expect=["row `gone/`: no such path", "deep/b/: a repo with no row"])
