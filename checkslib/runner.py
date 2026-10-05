"""Select the checks that apply to a repo, run each in its own process, and
report every result (never only the first failure). `run_all` runs one
`checks run` process per repo, all of them gathered before anything is printed.

Statuses: ok, fail, unchecked (from the check's exit code, vocab.json
`results`), error (any other exit, a timeout, a refused check, a bad
checks.json). fail and error make a run red; unchecked never makes it green."""
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from checkslib import api, decl

TOOL_ROOT = Path(__file__).resolve().parent.parent
CLI = TOOL_ROOT / "checks"
DEFAULT_SOURCE = TOOL_ROOT / "source"
PARAMS_FILE = "checks.json"
TIMEOUT = 300
RED = {"fail", "error"}
STATUS = {int(code): spec["status"] for code, spec in api.RESULTS.items()}

# What counts as a repo in a workspace: the same rule `hooks copies` uses for its
# locations (tests/test_contract.py holds the two equal on a fixture workspace).
MAX_DEPTH = 4
PRUNE = {"node_modules"}


def default_workspace(tool_dir=TOOL_ROOT):
    """The workspace top when this tool sits in a `tools/` folder; else None."""
    tool_dir = Path(tool_dir).resolve()
    return tool_dir.parent.parent if tool_dir.parent.name == "tools" else None


def rel(repo, ws):
    if ws is None:
        return None
    try:
        return Path(repo).resolve().relative_to(Path(ws).resolve()).as_posix() or "."
    except ValueError:
        return None


def applies(entry, repo, ws, roles):
    kind, names = decl.scope(entry.applies_to)
    if kind == "all":
        return True
    if kind == "tools":
        return Path(repo).resolve().parent.name == "tools"
    if kind == "repos":
        return rel(repo, ws) in names
    return bool(set(names) & set(roles or ()))


def load_params(repo, entries, refused=()):
    """({check: params}, faults) from the repo's checks.json; no file, no params.
    A section for a check that does not exist, or a key the check does not
    declare, is a fault: a setting that nothing reads is a setting that does
    nothing, said out loud."""
    p = Path(repo) / PARAMS_FILE
    if not p.is_file():
        return {}, []
    try:
        data = json.loads(p.read_text())
    except ValueError as e:
        return {}, [f"{PARAMS_FILE}: does not parse ({e})"]
    if not isinstance(data, dict):
        return {}, [f"{PARAMS_FILE}: must be an object of {{check: {{param: value}}}}"]
    known = {e.name: e for e in entries}
    out, faults = {}, []
    for name, section in data.items():
        if name.startswith("_"):
            continue                                    # a _comment
        if name not in known:
            if name not in refused:
                faults.append(f"{PARAMS_FILE}: `{name}` is not a check (checks list)")
            continue
        if not isinstance(section, dict):
            faults.append(f"{PARAMS_FILE}: `{name}` must be an object of params")
            continue
        extra = sorted(set(section) - set(known[name].params))
        if extra:
            faults.append(f"{PARAMS_FILE}: `{name}` does not read {', '.join(extra)} "
                          f"(it declares: {', '.join(known[name].params) or 'none'})")
        out[name] = {k: v for k, v in section.items() if k in known[name].params}
    return out, faults


def run_one(entry, repo, ws=None, params=None, names=None, timeout=TIMEOUT, env=None):
    """`env`: extra variables over this process's own (a fixture's caller-supplied values)."""
    env = dict(os.environ, **(env or {}))
    env[api.ENV_WORKSPACE] = str(ws) if ws else ""
    env[api.ENV_PARAMS] = json.dumps(params or {})
    env.pop(api.ENV_NAMES, None)
    if names is not None:
        env[api.ENV_NAMES] = ",".join(names)
    t0 = time.monotonic()
    try:
        p = subprocess.run([str(entry.path), str(Path(repo).resolve())], capture_output=True, text=True,
                           env=env, stdin=subprocess.DEVNULL, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"check": entry.name, "status": "error", "lines": [f"timed out after {timeout}s"],
                "seconds": round(time.monotonic() - t0, 1)}
    except OSError as e:
        return {"check": entry.name, "status": "error", "lines": [f"could not start: {e}"], "seconds": 0}
    status = STATUS.get(p.returncode, "error")
    lines = [l for l in p.stdout.splitlines() if l.strip()]
    if status == "error":
        lines = [f"exit {p.returncode}"] + lines + [l for l in p.stderr.splitlines() if l.strip()][-6:]
    elif status in ("fail", "unchecked") and not lines:
        lines = [f"exit {p.returncode} with nothing said; a check must say why"]
        status = "error"
    return {"check": entry.name, "status": status, "lines": lines, "seconds": round(time.monotonic() - t0, 1)}


def run_repo(repo, source=DEFAULT_SOURCE, ws=None, names=None, roles=(), only=None):
    """Every check that applies (or exactly `only`, applicability aside), each in
    its own process, every result kept. Refused checks that would apply are
    `error` rows, not omissions."""
    repo = Path(repo).resolve()
    entries, refused, faults = decl.load(source)
    params, pfaults = load_params(repo, entries, refused)
    faults += pfaults
    results = []
    for e in entries:
        if only is not None:
            if e.name not in only:
                continue
        elif not applies(e, repo, ws, roles):
            continue
        results.append(run_one(e, repo, ws, params.get(e.name), names))
    for name, why in sorted(refused.items()):
        if only is None or name in only:
            results.append({"check": name, "status": "error", "lines": [f"refused: {why}"], "seconds": 0})
    if only is not None:
        known = {e.name for e in entries} | set(refused)
        faults += [f"no such check: {n}" for n in sorted(set(only) - known)]
    results.sort(key=lambda r: r["check"])
    ok = not faults and not any(r["status"] in RED for r in results)
    return {"repo": str(repo), "rel": rel(repo, ws), "workspace": str(ws) if ws else None,
            "results": results, "faults": faults, "ok": ok}


def discover(ws):
    """The workspace top plus every git repo under it that has a CLAUDE.md,
    to depth MAX_DEPTH, dot-folders and node_modules pruned."""
    ws = Path(ws).resolve()
    found = [ws]
    stack = [(ws, 0)]
    while stack:
        d, depth = stack.pop()
        if depth >= MAX_DEPTH:
            continue
        try:
            kids = sorted(os.scandir(d), key=lambda k: k.name)
        except OSError:
            continue
        for k in kids:
            if k.is_dir(follow_symlinks=False) and not k.name.startswith(".") and k.name not in PRUNE:
                p = Path(k.path)
                if (p / ".git").exists() and (p / "CLAUDE.md").is_file():
                    found.append(p)
                stack.append((p, depth + 1))
    return sorted(found, key=lambda p: (p != ws, rel(p, ws)))


def _run_repo_process(repo, ws, source, names, roles):
    cmd = [sys.executable, str(CLI), "run", str(repo), "--json", "--root", str(ws), "--source", str(source)]
    if names is not None:
        cmd += ["--names", ",".join(names)]
    if roles:
        cmd += ["--roles", ",".join(roles)]
    why = None
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=TIMEOUT * 4)
        try:
            rep = json.loads(p.stdout)
            if isinstance(rep, dict) and "results" in rep:
                return rep
        except ValueError:
            pass
        why = f"printed no report (exit {p.returncode}: {p.stderr.strip()[-200:]})"
    except subprocess.TimeoutExpired:
        why = "timed out"
    except OSError as e:
        why = f"could not start ({e})"
    return {"repo": str(repo), "rel": rel(repo, ws), "results": [], "faults": [f"checks run {why}"], "ok": False}


def run_all(ws, source=DEFAULT_SOURCE, names=None, roles=(), workers=8):
    repos = discover(ws)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_run_repo_process, r, ws, source, names, roles) for r in repos]
        reports = [f.result() for f in futures]     # each future already catches its own failure
    return {"root": str(Path(ws).resolve()), "repos": reports, "ok": all(r["ok"] for r in reports)}
