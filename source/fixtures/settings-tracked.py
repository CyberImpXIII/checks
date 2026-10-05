from checkslib.fixture import Fixture, git_repo, write

SETTINGS = '{\n  "hooks": {}\n}\n'


def passing(t):
    return Fixture(git_repo(t / "r", {".claude/settings.json": SETTINGS,
                                      ".gitignore": ".claude/*\n!.claude/settings.json\n"}))


def failing(t):
    r = git_repo(t / "r", {"README.md": "# r\n", ".gitignore": "*.bak\n.claude/\n"})
    write(r / ".claude/settings.json", SETTINGS)
    return Fixture(r, expect=[".claude/settings.json: exists but git does not track it",
                              ".claude/settings.json: git-ignored by .gitignore:2:.claude/"])
