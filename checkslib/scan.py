"""The files a scanning check reads, and how it reads one. Shared by no-roster
(roster paths and names) and accessor (a store named around its CLI), so the
scope rule and the binary/size rule are written once.

Scope: the files git would commit (ctx.tracked(); every file under the repo
outside git, .git, node_modules and __pycache__ pruned), minus the globs given.
DEFAULT_EXCLUDE is the shared baseline: docs (*.md), the installed hook copies
(.claude/), and tests (a test plants faults on purpose)."""
import fnmatch
import os
from pathlib import Path

DEFAULT_EXCLUDE = ["*.md", ".claude/*", "tests/*", "test/*"]
PRUNE = {".git", "node_modules", "__pycache__"}
MAX_BYTES = 2_000_000


def walk(root, prune=PRUNE, dot=True):
    """Every file under root (relative, posix), pruning `prune` and, unless
    dot is true, every dot-folder."""
    root = Path(root)
    out = []
    for d, dirs, names in os.walk(root):
        dirs[:] = [x for x in dirs if x not in prune and (dot or not x.startswith("."))]
        out += [Path(d, n).relative_to(root).as_posix() for n in names]
    return sorted(out)


def matches(rel, globs):
    return any(fnmatch.fnmatch(rel, g) for g in globs)


def in_scope(ctx, exclude=()):
    files = ctx.tracked()
    if files is None:
        files = walk(ctx.repo)
    globs = DEFAULT_EXCLUDE + list(exclude)
    return [f for f in sorted(files) if not matches(f, globs)]


def text(path):
    """The file's text, or None for a symlink, a missing or oversized file, or binary data."""
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    return None if b"\0" in data[:8192] else data.decode("utf-8", "replace")
