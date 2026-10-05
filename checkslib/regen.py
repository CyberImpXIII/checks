"""The one rebuild engine behind `rendered-matches` and `regenerate`
(PLAN-repo-setup.md §7.10): in a scratch copy of what the repo would commit,
delete every file node.json lists as generated, run its `rebuild`, and compare.

The scratch copy is a `git clone` of the repo overlaid with the working tree's
committable files (tracked, plus untracked and not ignored; a file deleted in
the tree is deleted there too). So it holds exactly what a commit would carry,
never ignored instance state: a fresh clone of the commit about to be made.
The rebuild runs there, never in the repo itself. A rebuild that writes outside
its working folder is the generator's fault, and this engine cannot see it.

Findings, each a category the checks choose from (CATEGORIES):
  absent      a generated file listed in node.json is not in the tree
  rebuild     the rebuild could not start, or exited non-zero
  missing     the rebuild did not render a generated file
  drift       the render differs from the file in the tree (first line named)
  record      the rebuild deleted or changed a record file
  unaccounted a committable file (before or after the rebuild) named by neither
              list, not node.json itself, not under a child

The comparison is this engine's own, from bytes and git: it never trusts the
generator's report of what it did. The rebuild runs with CHECKS_REBUILD_ACTIVE
set; a check started inside it (setup runs `checks run .` as its last step)
says UNCHECKED instead of rebuilding again, so the two cannot recurse."""
import os
import shutil
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

from checkslib import api, contract

CATEGORIES = ("absent", "rebuild", "missing", "drift", "record", "unaccounted")
GUARD = "CHECKS_REBUILD_ACTIVE"
ORIGIN = "CHECKS_ORIGIN"
# Under the runner's 300s, so this says why rather than being killed. The
# environment override exists for the tests' timeout case.
TIMEOUT = float(os.environ.get("CHECKS_REBUILD_TIMEOUT") or 240)


class Broken(Exception):
    """The engine could not do its job (git failed, the rebuild timed out): an error, not a finding."""


def _git(repo, *args):
    p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if p.returncode != 0:
        raise Broken(f"git {' '.join(args[:2])} failed in {repo} (exit {p.returncode}): {p.stderr.strip()[-200:]}")
    return p.stdout


def committable(repo):
    """What a commit in `repo` would carry and exists on disk: tracked plus untracked-not-ignored."""
    out = _git(repo, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    return sorted({p for p in out.split("\0") if p and (Path(repo, p).exists() or Path(repo, p).is_symlink())})


def _copy(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.is_symlink() or dst.exists():
        dst.unlink()
    if src.is_symlink():
        os.symlink(os.readlink(src), dst)
    else:
        shutil.copy2(src, dst)


def scratch(repo, dest):
    """dest: a clone of repo holding exactly repo's committable files. Returns that file list."""
    clone = subprocess.run(["git", "clone", "-q", "--no-hardlinks", str(repo), str(dest)],
                           capture_output=True, text=True, stdin=subprocess.DEVNULL)
    if clone.returncode != 0:
        raise Broken(f"git clone failed (exit {clone.returncode}): {clone.stderr.strip()[-200:]}")
    view = committable(repo)
    keep = set(view)
    for p in _git(dest, "ls-files", "-z").split("\0"):
        if p and p not in keep and (dest / p).exists():
            (dest / p).unlink()
    for p in view:
        src = Path(repo) / p
        if src.is_dir() and not src.is_symlink():
            continue                # a nested repo (`child/`): listed, so it can be accounted for; never copied
        _copy(src, dest / p)
    return view


def _first_difference(a, b):
    la, lb = a.split(b"\n"), b.split(b"\n")
    for i, (x, y) in enumerate(zip(la, lb), 1):
        if x != y:
            return i
    return min(len(la), len(lb)) + 1


def _rebuild(doc, repo, work):
    argv = [a.replace("{origin}", str(repo)) for a in doc["rebuild"]]
    env = {k: v for k, v in os.environ.items() if not k.startswith("CHECKS_")}
    env[GUARD] = "1"
    env[ORIGIN] = str(repo)
    try:
        p = subprocess.Popen(argv, cwd=work, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, start_new_session=True)
    except OSError as e:
        return [f"rebuild: could not start `{' '.join(doc['rebuild'])}`: {e}"]
    try:
        _, err = p.communicate(timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)        # the generator's whole process tree
        p.communicate()
        raise Broken(f"rebuild `{' '.join(doc['rebuild'])}` did not finish in {TIMEOUT}s")
    if p.returncode != 0:
        tail = [l for l in (err or "").splitlines() if l.strip()][-1:] or ["(nothing on stderr)"]
        return [f"rebuild: `{' '.join(doc['rebuild'])}` exited {p.returncode}: {tail[0][:200]}"]
    return []


def _digest(path):
    return path.read_bytes() if path.is_file() and not path.is_symlink() else os.readlink(path)


def run(repo, doc):
    """{category: [finding, ...]} for every category, for the node.json `doc` of `repo`."""
    repo = Path(repo).resolve()
    out = {c: [] for c in CATEGORIES}
    tmp = Path(tempfile.mkdtemp(prefix="checks-rebuild-"))
    try:
        work = tmp / repo.name
        view = scratch(repo, work)
        have = set(view)
        generated = [contract.norm(g) for g in doc["generated"]]
        record, children = doc["record"], doc.get("children", [])
        out["absent"] = [f"absent: {g}: listed as generated, but the tree to be committed has no such file"
                         for g in generated if g not in have]
        kept = {p: _digest(work / p) for p in view if contract.is_record(p, record) and p not in generated
                and ((work / p).is_file() or (work / p).is_symlink())}
        for g in generated:
            if (work / g).exists() or (work / g).is_symlink():
                (work / g).unlink()
        out["rebuild"] = _rebuild(doc, repo, work)
        for g in generated:
            mine = work / g
            if not mine.is_file():
                out["missing"].append(f"missing: {g}: the rebuild did not render it")
            elif g in have and mine.read_bytes() != (repo / g).read_bytes():
                line = _first_difference(mine.read_bytes(), (repo / g).read_bytes())
                out["drift"].append(f"drift: {g}: the render differs from the file (first at line {line})")
        for p, before in kept.items():
            if not ((work / p).exists() or (work / p).is_symlink()):
                out["record"].append(f"record: {p}: deleted by the rebuild")
            elif _digest(work / p) != before:
                out["record"].append(f"record: {p}: changed by the rebuild")
        after = set(committable(work))
        for p in sorted(have | after):
            if p in generated or p == contract.NODE or contract.is_record(p, record) or contract.under(p, children):
                continue
            how = "" if p in have else " (written by the rebuild)"
            out["unaccounted"].append(f"unaccounted: {p}: named by neither generated nor record{how}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return out


def main(categories):
    """The whole of `rendered-matches` and `regenerate`, which differ only in
    the categories they report. A node.json with any finding is reported and
    NOT rebuilt: its paths decide what is deleted, so a path outside the repo
    must never reach the engine."""
    ctx = api.context()
    if os.environ.get(GUARD):
        api.done(unchecked="nested inside a rebuild, which is what this check runs: not rebuilt again")
    doc, found = contract.read(ctx.repo, contract.NODE)
    if doc is None and not found:
        api.done(unchecked=f"no {contract.NODE}: nothing declares the generated files or how to render them "
                           f"(the contract is unmet, never a pass)")
    if found:
        api.done(found)
    if not ctx.is_git():
        api.done(unchecked="not a git repo: what a commit would carry cannot be copied out to rebuild")
    try:
        res = run(ctx.repo, doc)
    except Broken as e:
        print(e)
        sys.exit(1)
    api.done([f for c in categories for f in res[c]])
