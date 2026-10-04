from checkslib.fixture import Fixture, git_repo

# Roster-shaped strings are assembled here, so this file names none itself.
MANIFEST = "agents" + ".manifest.json"
DEFS = ".claude/" + "agents/"
NAME = "fixture-agent"


def passing(t):
    repo = git_repo(t / "tools" / "x", {
        "x.py": "def main(names):\n    return [n for n in names]\n",
        "README.md": f"The roster lives in {MANIFEST}; this tool never opens it.\n",
        f"tests/test_x.py": f"PLANTED = '{MANIFEST}'\n",
        "self.py": "PROG = 'x'\n",
    })
    return Fixture(repo, names=[NAME, "x"])


def failing(t):
    repo = git_repo(t / "tools" / "x", {
        "x.py": f"ROSTER = open('../../{MANIFEST}')\nDEFS = '{DEFS}'\nif who == \"{NAME}\":\n    pass\n",
    })
    return Fixture(repo, names=[NAME], expect=["x.py:1: names the roster's files", "x.py:2: names the roster's files",
                                               f"x.py:3: names roster agent `{NAME}`"])
