from checkslib.fixture import Fixture, git_repo, write


def passing(t):
    return Fixture(git_repo(t / "r", {"README.md": "# r\n", ".gitignore": "out/\n", "out/ignored.txt": "x\n"}))


def failing(t):
    r = git_repo(t / "r", {"README.md": "# r\n"})
    write(r / "README.md", "# r, edited\n")
    write(r / "new.txt", "not yet added\n")
    return Fixture(r, expect=["uncommitted (M): README.md", "uncommitted (??): new.txt"])
