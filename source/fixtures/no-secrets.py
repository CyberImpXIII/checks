from checkslib.fixture import Fixture, git, git_repo, params, write

# A credential SHAPE, built here so that no shaped value sits in this file.
FAKE_GITHUB = "gh" + "p_" + "A1b2" * 9


def passing(t):
    repo = git_repo(t / "r", {".gitignore": ".env\ndata/.captures/\n", "app.py": "TOKEN = os.environ['TOKEN']\n",
                              ".env.example": "TOKEN=\n", "fixtures/fake.txt": f"t = {FAKE_GITHUB}\n"}, commit=False)
    params(repo, {"no-secrets": {"capture_dirs": ["data/.captures"], "allow": ["fixtures/*"]}})
    git_repo(repo)
    # a staged copy that differs from the working tree, clean in both: still ok
    write(repo / "app.py", "TOKEN = os.environ['TOKEN']  # staged\n")
    git(repo, "add", "app.py")
    write(repo / "app.py", "TOKEN = os.environ['TOKEN']  # edited after staging\n")
    return Fixture(repo)


def failing(t):
    repo = git_repo(t / "r", {".env": "TOKEN=\n", "app.py": f"TOKEN = '{FAKE_GITHUB}'\n",
                              "cfg.py": "TOKEN = None\n"}, commit=False)
    params(repo, {"no-secrets": {"capture_dirs": ["data/.captures"]}})
    git_repo(repo)
    # staged with a secret, then cleaned in the working tree only: the commit would carry it
    write(repo / "cfg.py", f"TOKEN = '{FAKE_GITHUB}'\n")
    git(repo, "add", "cfg.py")
    write(repo / "cfg.py", "TOKEN = None\n")
    return Fixture(repo, expect=[".env: a .env file that git would commit", "app.py:1: holds a GitHub token shape (value not shown)",
                                 "cfg.py:1: holds a GitHub token shape in the staged copy (value not shown)",
                                 ".env: not git-ignored", "data/.captures: a capture folder that is not git-ignored"])
