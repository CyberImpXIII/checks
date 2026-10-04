"""What a check's fixtures build: a repo (and, when the check needs one, a
workspace around it) in a temporary folder, plus what the failing fixture must
say. `checks fixtures` runs every check against both of its fixtures: the
passing one must come back `ok`, the failing one `fail` with every `expect`
substring among its findings, so it fails for the reason it was built for.

Fixtures are spelled out by hand here, never built by the code under test."""
import json
import os
import subprocess
from pathlib import Path

GIT_ENV = {"GIT_AUTHOR_NAME": "fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
           "GIT_COMMITTER_NAME": "fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid"}


class Fixture:
    def __init__(self, repo, workspace=None, names=None, expect=()):
        self.repo = Path(repo)
        self.workspace = Path(workspace) if workspace else None
        self.names = names
        self.expect = list(expect)


def write(path, text, mode=0o644):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    os.chmod(path, mode)
    return path


def params(repo, data):
    """The repo's checks.json: how a fixture sets a param, through the same file a repo would."""
    write(Path(repo) / "checks.json", json.dumps(data, indent=1) + "\n")


def git_repo(path, files=None, commit=True):
    """A git repo at path holding `files` ({relative path: text}), all committed."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    for rel, text in (files or {}).items():
        write(path / rel, text, 0o755 if rel.endswith(".sh") or rel == "dev.sh" else 0o644)
    env = dict(os.environ, **GIT_ENV)
    run = lambda *a: subprocess.run(["git", "-C", str(path), *a], capture_output=True, text=True, env=env, check=True)
    run("init", "-q")
    if commit:
        run("add", "-A")
        run("-c", "commit.gpgsign=false", "commit", "-q", "--allow-empty", "-m", "fixture")
    return path
