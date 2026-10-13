#!/usr/bin/env python3
# checks: applies_to=all
# Proves: the same input gives the same answer (PLAN-architecture.md §12.2).
# Each read verb cli.json declares under `read.verbs` runs twice, as
# `<cli> <verb> <args...>`, on ONE scratch copy of `read.fixture` (that copy
# is the working directory, and its path replaces `{fixture}` in args and
# `read.env`; no fixture: the repo root, as is), with `read.env` over the
# caller's environment, minus the three the runner hands a check
# (CHECKS_WORKSPACE, CHECKS_PARAMS, CHECKS_ROSTER_NAMES). Both
# runs must print one JSON document; the verb's `volatile` paths are removed
# from each; the two are then compared with key order kept (checkslib/repro.py
# says exactly how). A finding, each verb on its own: a run that prints no
# JSON, a difference (named at its first path), different exit codes, a run
# past 60s, and a volatile path that removes nothing in either run (declared,
# yet it changes nothing). Both runs share one copy, so a read verb that
# writes its fixture and answers differently the second time is caught; and
# with a fixture, the copy is compared before and after each verb's two runs
# (checkslib/repro.py snapshot: every path, contents by sha256), so a verb
# that writes and still answers the same is a finding too, naming the paths
# added, removed or changed. Without a fixture the verbs run in the repo
# itself, which other processes write, so no tree is compared (the ok line
# says so).
# cli.json's own rules (`read` names declared verbs, each with `--json`, the
# fixture a folder in the repo, ...) are `accessor`'s findings; here a
# cli.json that breaks any is UNCHECKED, as is no cli.json (`cli-declared`
# reports that as a lag) and a cli.json with no `read` (no verb is known to
# only read). On ok it names each verb run and its exit code.
# To pass: sort what the verb prints and print no wall-clock time unless it is
# asked for; a field that must vary (a time asked for, a duration) goes in
# that verb's `volatile`; delete a volatile path that no longer matches.
import os
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checkslib import api, contract, proc, repro  # noqa: E402

RUN_TIMEOUT = 60
RUNNER_ENV = (api.ENV_WORKSPACE, api.ENV_PARAMS, api.ENV_NAMES)


def run_twice(argv, cwd, env):
    """[(exit code, stdout)] for two runs, or a finding saying why a run did not finish."""
    runs = []
    for n in (1, 2):
        try:
            code, out, _ = proc.bounded(argv, cwd, env, RUN_TIMEOUT)
        except OSError as e:
            return None, f"could not start: {e}"
        except proc.Timeout:
            return None, f"run {n} did not finish in {RUN_TIMEOUT}s"
        runs.append((code, out))
    return runs, None


def main():
    ctx = api.context()
    doc, found = contract.read(ctx.repo, contract.CLI)
    if doc is None and not found:
        api.done(unchecked=f"no {contract.CLI}: no verb declared, so none to run (`cli-declared` reports the lag)")
    if found:
        api.done(unchecked=f"{contract.CLI} breaks a rule (`accessor` says which); no verb run: {found[0][:200]}")
    read = doc.get("read")
    if not read:
        api.done(unchecked=f"{contract.CLI} declares no `read` verbs: nothing is known to only read, so nothing runs twice")
    scratch = Path(tempfile.mkdtemp(prefix="checks-repro-"))
    try:
        fixture = None
        cwd = ctx.repo
        if read.get("fixture"):
            fixture = scratch / "fixture"
            shutil.copytree(ctx.repo / read["fixture"], fixture, symlinks=True)
            cwd = fixture
        env = {k: v for k, v in os.environ.items() if k not in RUNNER_ENV}
        env.update({k: repro.substitute(v, fixture) for k, v in (read.get("env") or {}).items()})
        cli = str(ctx.repo / doc["cli"])
        findings, notes = [], []
        tree = repro.snapshot(fixture) if fixture else None
        for verb in sorted(read["verbs"]):
            spec = read["verbs"][verb]
            argv = [cli, verb] + [repro.substitute(a, fixture) for a in spec["args"]]
            runs, why = run_twice(argv, cwd, env)
            got = [f"`{verb}`: {why}"] if runs is None else repro.compare(verb, runs, spec.get("volatile", []))
            if fixture:
                after = repro.snapshot(fixture)
                changed = repro.tree_changes(tree, after)
                if changed:
                    shown = ", ".join(changed[:5]) + (f", and {len(changed) - 5} more" if len(changed) > 5 else "")
                    got.append(f"`{verb}`: a read verb changed its fixture ({len(changed)} path(s)): {shown}")
                tree = after
            findings += got
            if not got:
                notes.append(f"{verb} (exit {runs[0][0]})")
    finally:
        shutil.rmtree(scratch, ignore_errors=True)
    if not findings:
        kept = "fixture unchanged" if fixture else "no fixture: run in the repo, tree not compared"
        print(f"the same answer twice: {', '.join(notes)}; {kept}")
    api.done(findings)


main()
