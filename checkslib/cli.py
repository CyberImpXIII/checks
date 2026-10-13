"""The `checks` CLI. USAGE and COMMANDS are held equal by tests/test_meta.py."""
import argparse
import json
import os
import sys
from pathlib import Path

from checkslib import api, decl, runner, selftest, writers

USAGE = """checks <command>   the generic pre-commit gates, one source, run per repo or from the top

  checks list [--json]               each check: where it applies, the params it reads
  checks explain <name>              what a check proves and how to make it pass
  checks run [PATH] [--json]         every check that applies to the repo at PATH (default .),
                                     each result printed; exit 1 if any is fail or error
  checks one <name> [PATH] [--json]  one check on PATH, whether or not it applies there
  checks all [ROOT] [--json]         every repo under ROOT, one process each: a repo-by-check
                                     grid, then the findings of every red cell
  checks fixtures [--json]           every check against its passing and failing fixture
  checks writers [PATH] [--json]     every write site in PATH's code (default .), file:line, its
                                     primitive and what it does at mode 0444 (RESEARCH-writers.md
                                     Q4); a scan to read at each line, not a verdict; exit 0

  --root DIR         the workspace top (default: two up, when this tool sits in tools/;
                     else none, and checks that need one say UNCHECKED)
  --names a,b        roster agent names, passed by a caller that reads the roster, or
                     exported as CHECKS_ROSTER_NAMES (no-roster's second half);
                     this tool never reads one itself
  --roles a,b        run the checks declared roles:<one of these> as well
  --source DIR       another source of checks (tests use fixtures)
"""

MARK = {"ok": "ok", "fail": "FAIL", "unchecked": "unch", "error": "ERR"}
SHOW = 8


def _split(s):
    return [x for x in (s or "").replace(",", " ").split() if x] if s is not None else None


def _names(a):
    """--names, else the CHECKS_ROSTER_NAMES a calling script exported; else None
    (no-roster's names half then says UNCHECKED). Never read from a roster here."""
    if a.names is not None:
        return _split(a.names)
    env = os.environ.get(api.ENV_NAMES)
    return _split(env) if env else None


def _ws(a):
    if a.root:
        return Path(a.root).resolve()
    return runner.default_workspace()


def cmd_list(a):
    entries, refused, faults = decl.load(a.source)
    if a.json:
        print(json.dumps({"checks": [e.row() for e in entries], "refused": refused, "faults": faults}, indent=1))
    else:
        for e in entries:
            print(f"  {e.name:<16} applies_to={e.applies_to:<10} params={','.join(e.params) or '-'}")
        for n, why in sorted(refused.items()):
            print(f"  {n:<16} REFUSED: {why}")
        for f in faults:
            print(f"  FAULT  {f}")
    return 1 if refused or faults or not entries else 0


def cmd_explain(a):
    entries, refused, _ = decl.load(a.source)
    for e in entries:
        if e.name == a.name:
            print(f"{e.name}  (applies_to={e.applies_to}; params: {', '.join(e.params) or 'none'})\n")
            print(decl.explanation(e.path), end="")
            return 0
    if a.name in refused:
        print(f"{a.name}: REFUSED: {refused[a.name]}", file=sys.stderr)
        return 1
    print(f"no such check: {a.name} (checks list)", file=sys.stderr)
    return 2


def _print_repo(rep, head=True):
    if head:
        print(f"== {rep.get('rel') or rep['repo']}")
    for r in rep["results"]:
        first = r["lines"][0] if r["lines"] and r["status"] == "unchecked" else ""
        print(f"  {r['status'].upper():<10} {r['check']}{'  ' + first if first else ''}")
        if r["status"] in runner.RED or r["status"] == "ok":    # an ok check's lines are notes it chose to give
            for l in r["lines"][:SHOW]:
                print(f"               {l}")
            if len(r["lines"]) > SHOW:
                print(f"               ... and {len(r['lines']) - SHOW} more (--json for all)")
    for f in rep["faults"]:
        print(f"  FAULT      {f}")


def _summary(results):
    counts = {}
    for r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return ", ".join(f"{counts[s]} {s}" for s in ("ok", "fail", "error", "unchecked") if s in counts) or "no checks"


def _run(a, only):
    path = Path(a.path or ".")
    if not path.is_dir():
        print(f"checks: no such folder: {path}", file=sys.stderr)
        return 2
    rep = runner.run_repo(path, a.source, _ws(a), _names(a), _split(a.roles) or (), only)
    if a.json:
        print(json.dumps(rep, indent=1))
    else:
        _print_repo(rep, head=False)
        print(f"checks {'run' if only is None else 'one'} {rep['rel'] or rep['repo']}: {_summary(rep['results'])}"
              f"{', ' + str(len(rep['faults'])) + ' fault(s)' if rep['faults'] else ''}"
              f" -> {'green' if rep['ok'] else 'RED'}")
    return 0 if rep["ok"] else 1


def cmd_run(a):
    return _run(a, None)


def cmd_one(a):
    return _run(a, [a.name])


def cmd_all(a):
    ws = Path(a.path).resolve() if a.path else _ws(a)
    if ws is None or not ws.is_dir():
        print("checks all: no workspace top (this tool is not in a tools/ folder); pass one: checks all <root>",
              file=sys.stderr)
        return 2
    rep = runner.run_all(ws, a.source, _names(a), _split(a.roles) or ())
    if a.json:
        print(json.dumps(rep, indent=1))
        return 0 if rep["ok"] else 1
    names = sorted({r["check"] for repo in rep["repos"] for r in repo["results"]})
    width = max([len(r.get("rel") or "?") for r in rep["repos"]] + [4])
    print(" " * (width + 2) + " ".join(f"{n[:11]:<11}" for n in names))
    for repo in rep["repos"]:
        cells = {r["check"]: MARK[r["status"]] for r in repo["results"]}
        flag = "  FAULT" if repo["faults"] else ""
        print(f"  {(repo.get('rel') or '?'):<{width}}" + " ".join(f"{cells.get(n, '-'):<11}" for n in names) + flag)
    print("\n(ok | FAIL | ERR | unch = could not run here, said why | - = does not apply)")
    red = [repo for repo in rep["repos"] if not repo["ok"]]
    for repo in red:
        print()
        _print_repo({**repo, "results": [r for r in repo["results"] if r["status"] in runner.RED]})
    unch = sum(r["status"] == "unchecked" for repo in rep["repos"] for r in repo["results"])
    print(f"\nchecks all {rep['root']}: {len(rep['repos'])} location(s), {len(red)} red, "
          f"{unch} UNCHECKED cell(s) (never ok; `checks one <check> <repo>` says why)")
    return 0 if rep["ok"] else 1


def cmd_fixtures(a):
    rows = selftest.run(a.source)
    if not rows:
        rows = [{"check": "-", "fixture": "-", "ok": False, "why": "no checks in the source: nothing was shown red"}]
    bad = [r for r in rows if not r["ok"]]
    if a.json:
        print(json.dumps({"ok": not bad, "rows": rows}, indent=1))
    else:
        for r in rows:
            print(f"  {'ok  ' if r['ok'] else 'FAIL'}  {r['check']:<16} {r['fixture']:<8} {r['why']}")
        print(f"fixtures: {len(rows)} row(s), {len(bad)} failed")
    return 1 if bad else 0


def cmd_writers(a):
    path = Path(a.path or ".")
    if not path.is_dir():
        print(f"checks: no such folder: {path}", file=sys.stderr)
        return 2
    ctx = api.Ctx(path, None, {}, None)
    sites = writers.scan_repo(ctx)
    if a.json:
        print(json.dumps({"repo": str(ctx.repo), "counts": writers.counts(sites), "sites": sites}, indent=1))
        return 0
    for s in sites:
        print(f"  {s['file']}:{s['line']}  {s['primitive']}  {s['kind']} ({s['at_0444']} at 0444)  {s['code'][:100]}")
    said = ", ".join(f"{n} {k}" for k, n in writers.counts(sites).items()) or "none"
    print(f"checks writers {ctx.repo}: {len(sites)} write site(s): {said}")
    return 0


COMMANDS = {"list": cmd_list, "explain": cmd_explain, "run": cmd_run, "one": cmd_one,
            "all": cmd_all, "fixtures": cmd_fixtures, "writers": cmd_writers}


def main(argv):
    if not argv or argv[0] in ("help", "-h", "--help"):
        print(USAGE, end="")
        return 0
    if argv[0] not in COMMANDS:
        print(f"unknown command: {argv[0]}\n\n{USAGE}", end="", file=sys.stderr)
        return 2
    p = argparse.ArgumentParser(prog=f"checks {argv[0]}")
    p.add_argument("--source", type=Path, default=runner.DEFAULT_SOURCE)
    p.add_argument("--json", action="store_true")
    if argv[0] == "explain":
        p.add_argument("name")
    if argv[0] == "one":
        p.add_argument("name")
    if argv[0] == "writers":
        p.add_argument("path", nargs="?")
    if argv[0] in ("run", "one", "all"):
        p.add_argument("path", nargs="?")
        p.add_argument("--root")
        p.add_argument("--names")
        p.add_argument("--roles")
    return COMMANDS[argv[0]](p.parse_args(argv[1:]))
