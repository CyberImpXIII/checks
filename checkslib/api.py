"""What a check imports: its context (the repo path, the workspace top if there
is one, its params, the roster names a caller passed) and the one way to end
(`done`), which maps a result onto the exit codes in vocab.json.

The runner hands these over in the environment, so a check also runs by hand:
    CHECKS_WORKSPACE=/path/to/top source/<name>.py /path/to/repo
A check reads a param only through `ctx.param("key", default)`, which is how
tests/test_meta.py holds what a check reads equal to what it declares."""
import json
import os
import subprocess
import sys
from pathlib import Path

TOOL_ROOT = Path(__file__).resolve().parent.parent
RESULTS = json.loads((TOOL_ROOT / "vocab.json").read_text())["results"]
CODE = {spec["status"]: int(code) for code, spec in RESULTS.items()}

ENV_WORKSPACE = "CHECKS_WORKSPACE"
ENV_PARAMS = "CHECKS_PARAMS"
ENV_NAMES = "CHECKS_ROSTER_NAMES"


class Ctx:
    def __init__(self, repo, workspace, params, names):
        self.repo = Path(repo).resolve()
        self.workspace = Path(workspace).resolve() if workspace else None
        self._params = params
        self.names = names              # None: no caller passed any (not: the roster is empty)

    @property
    def rel(self):
        """The repo's path relative to the workspace top ('.' for the top), or None."""
        if self.workspace is None:
            return None
        try:
            return self.repo.relative_to(self.workspace).as_posix() or "."
        except ValueError:
            return None

    def param(self, key, default):
        return self._params.get(key, default)

    def is_git(self):
        return (self.repo / ".git").exists()

    def git(self, *args):
        p = subprocess.run(["git", "-C", str(self.repo), *args], capture_output=True, text=True)
        return p.returncode, p.stdout

    def tracked(self):
        """Paths git would commit (relative): tracked ones plus untracked ones
        that are not ignored, because a pre-commit check that skipped new files
        would pass the very commit that adds a fault. None outside a git repo."""
        if not self.is_git():
            return None
        code, out = self.git("ls-files", "-z", "--cached", "--others", "--exclude-standard")
        return [p for p in out.split("\0") if p] if code == 0 else None


def context(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print(f"usage: {Path(sys.argv[0]).name} <repo path>", file=sys.stderr)
        sys.exit(64)
    repo = Path(argv[0])
    if not repo.is_dir():
        print(f"no such folder: {repo}", file=sys.stderr)
        sys.exit(64)
    try:
        params = json.loads(os.environ.get(ENV_PARAMS) or "{}")
    except ValueError:
        print(f"{ENV_PARAMS} is not JSON", file=sys.stderr)
        sys.exit(64)
    raw = os.environ.get(ENV_NAMES)
    names = None if raw is None else [n for n in raw.replace(",", " ").split() if n]
    return Ctx(repo, os.environ.get(ENV_WORKSPACE) or None, params, names)


def done(findings=(), unchecked=None):
    """Exit with the result: findings -> fail; else unchecked (a reason) -> unchecked; else ok."""
    findings = list(findings)
    if findings:
        for f in findings:
            print(f)
        sys.exit(CODE["fail"])
    if unchecked:
        print(unchecked)
        sys.exit(CODE["unchecked"])
    sys.exit(CODE["ok"])
