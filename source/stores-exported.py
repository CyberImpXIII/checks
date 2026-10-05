#!/usr/bin/env python3
# checks: applies_to=all
# Proves: the repo's store and its exported form in the data repo agree
# (PLAN-repo-setup.md §7.11): the database is the one source, the data repo
# its serialised form, and a store changed without its export is red here.
# It runs the store's own `verify` (the CLI cli.json names; never a read of
# the store or the data repo by this tool) as `<cli> verify --json`, with
# DATA_REPO passed through from the caller's environment, and reads the
# report: it must be one JSON document fitting schema/verify.schema.json (an
# item list; an empty one is never a pass) with no item twice. Each item
# `differs` or `missing` is a finding (its `detail` with it), and so is a
# non-zero exit beside a report where every item is `same` (a verify that
# died mid-way must not read as a pass). Only `unavailable` items left is
# UNCHECKED, naming them.
# No cli.json is UNCHECKED (no store declared here); a cli.json with any
# finding is reported as accessor would, not run. A cli.json that declares no
# `verify` verb is a finding: nothing shows the export current. DATA_REPO
# unset is UNCHECKED, never an empty pass: the caller supplies it (from the
# instance's .claude/local.env), as roster names arrive via `--names`; this
# tool reads no instance file. Set but not a folder is a finding. The verify
# gets 240s; one that does not finish is an error.
# To pass: `differs`/`missing`: run the store's `export` (the write service
# runs it after every sanctioned write) and commit the data repo's change;
# add `verify` to the CLI, its help and cli.json's verbs, printing the report.
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checkslib import api, contract, proc  # noqa: E402

DATA = "DATA_REPO"
TIMEOUT = float(os.environ.get("CHECKS_VERIFY_TIMEOUT") or 240)
RED = ("differs", "missing")


def main():
    ctx = api.context()
    doc, found = contract.read(ctx.repo, contract.CLI)
    if doc is None and not found:
        api.done(unchecked=f"no {contract.CLI}: no store is declared here, so no export to verify")
    if found:
        api.done(found)
    if "verify" not in doc["verbs"]:
        api.done([f"{contract.CLI}: declares no `verify` verb: nothing shows the store's export is current"])
    data = os.environ.get(DATA)
    if not data:
        api.done(unchecked=f"{DATA} is not set: no data repo to verify the export against "
                           f"(the caller supplies it; this tool reads no instance file)")
    if not Path(data).is_dir():
        api.done([f"{DATA} is set but is not a folder: the export has nowhere to be"])
    cmd = f"{doc['cli']} verify --json"
    try:
        code, out, err = proc.bounded([str(ctx.repo / doc["cli"]), "verify", "--json"], ctx.repo,
                                      dict(os.environ, **{DATA: data}), TIMEOUT)
    except OSError as e:
        api.done([f"`{cmd}` could not start: {e}"])
    except proc.Timeout:
        print(f"`{cmd}` did not finish in {TIMEOUT}s")
        sys.exit(1)
    try:
        report = json.loads(out)
    except ValueError:
        tail = [l for l in (err or "").splitlines() if l.strip()][-1:] or ["(nothing on stderr)"]
        api.done([f"`{cmd}` printed no JSON document (exit {code}): {tail[0][:200]}"])
    report, found = contract.validate(report, contract.VERIFY, ctx.repo)
    if found:
        api.done([f"`{cmd}`: {f}" for f in found])
    items = report["items"]
    findings = [f"{i['item']}: {i['status']}" + (f" ({i['detail']})" if i.get("detail") else "")
                for i in items if i["status"] in RED]
    away = [i["item"] for i in items if i["status"] == "unavailable"]
    if code != 0 and not findings and not away:
        findings.append(f"`{cmd}` exited {code} but reports every item `same`: a verify that failed is not a pass")
    if findings:
        api.done(findings)
    if away:
        api.done(unchecked=f"{len(away)} item(s) could not be compared here: {', '.join(away[:5])}")
    api.done([])


main()
