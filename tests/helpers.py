"""Builders for the CLI tests: a source of checks and repos to run them on, in a
temporary folder. Test checks are small bash scripts saved as <name>.py (the
runner executes a check directly, by its shebang), so a test check needs no
import path and cannot depend on the code under test. Everything here is
spelled out by hand, never built by the code under test."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOL_ROOT = Path(__file__).resolve().parent.parent
CLI = TOOL_ROOT / "checks"
WORKSPACE = TOOL_ROOT.parent.parent if TOOL_ROOT.parent.name == "tools" else None
sys.path.insert(0, str(TOOL_ROOT))

GIT_ENV = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.invalid",
           "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}
FIXTURE = "def passing(t):\n    pass\n\n\ndef failing(t):\n    pass\n"


def write(path, text, mode=0o644):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    os.chmod(path, mode)
    return path


def check_text(body, applies_to="all", params="", proves=True):
    decl = f"# checks: applies_to={applies_to}" + (f" params={params}" if params else "")
    words = "# Proves: a test check.\n# To pass: nothing.\n" if proves else "# Says nothing useful.\n"
    return f"#!/usr/bin/env bash\n{decl}\n{words}{body}\n"


def git(path, *args):
    return subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True,
                          env=dict(os.environ, **GIT_ENV), check=True)


def repo(path, files=None, commit=True, claude_md=True):
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    if claude_md:
        write(path / "CLAUDE.md", "# r\n")
    for rel, text in (files or {}).items():
        write(path / rel, text)
    git(path, "init", "-q")
    if commit:
        git(path, "add", "-A")
        git(path, "-c", "commit.gpgsign=false", "commit", "-q", "--allow-empty", "-m", "t")
    return path


def run_cli(*args, env=None):
    return subprocess.run([sys.executable, str(CLI), *map(str, args)], capture_output=True, text=True,
                          env=dict(os.environ, **(env or {})), stdin=subprocess.DEVNULL)


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="checks-test-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.src = self.tmp / "src"
        self.src.mkdir()

    def add_check(self, name, body, applies_to="all", params="", proves=True, executable=True, fixture=FIXTURE):
        write(self.src / f"{name}.py", check_text(body, applies_to, params, proves), 0o755 if executable else 0o644)
        if fixture is not None:
            write(self.src / "fixtures" / f"{name}.py", fixture)

    def cli_json(self, *args, env=None):
        p = run_cli(*args, "--json", env=env)
        try:
            return p.returncode, json.loads(p.stdout)
        except ValueError:
            self.fail(f"no JSON from checks {' '.join(map(str, args))}: exit {p.returncode} {p.stderr[-400:]}")
