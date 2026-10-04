from checkslib.fixture import Fixture, write


def passing(t):
    write(t / "r" / "TODO.md", "# r TODO\n\n## Own bugs\n")
    return Fixture(t / "r")


def failing(t):
    (t / "r").mkdir()
    write(t / "r" / "todo.md.bak", "# not the file\n")
    return Fixture(t / "r", expect=["TODO.md: missing"])
