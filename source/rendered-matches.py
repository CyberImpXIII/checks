#!/usr/bin/env python3
# checks: applies_to=all
# Proves: every file the repo's generator renders is exactly what it renders
# now (PLAN-repo-setup.md §7.2, §7.10). Two ways to know what is rendered:
#   1. setup, asked (remediation 2.4 part 3, Jacob's "b" of ra-2.2: the check
#      learns which files a repo renders from setup itself, never from a list of
#      its own). In a workspace that holds the setup tool (<top>/tools/setup/setup),
#      each component setup renders into repos (its fanout's own set, which
#      `setup fanout` names when refusing any other) is asked of this repo alone:
#      `setup fanout <component> --repos <repo> --dry-run --json`. Per component:
#      `unchanged` (the render is the file, byte for byte) is ok; `undeclared`
#      (the repo does not carry it) is skipped; `would-commit` (setup would render
#      files that differ or are absent) is `drift`, naming them; `failed` is
#      `drift` when setup names a drift or files it would render, and UNCHECKED
#      otherwise (setup refused for another reason: it could not judge). A repo
#      that carries none of them is n/a. setup absent, or an answer not in that
#      shape, is UNCHECKED, never ok.
#   2. node.json, where a repo has one: in a scratch copy of what a commit would
#      carry (a clone overlaid with the working tree's committable files, never
#      the repo itself), each generated file it lists is deleted, its `rebuild`
#      is run, and each must come back byte for byte. Deleting first is the
#      point: a generator that skips an existing file would otherwise pass by
#      leaving it alone. Findings: `absent` (listed, not in the tree), `rebuild`
#      (it would not start or exited non-zero), `missing` (not rendered), `drift`
#      (rendered differently; the first differing line is named). node.json is
#      validated first (schema/node.schema.json and its x-rules); one with any
#      finding is reported and not rebuilt. A folder outside git, and a run
#      nested inside a rebuild (setup runs `checks run .` as its last step), are
#      UNCHECKED. The rebuild gets 240s; one that does not finish is an error.
# A repo with a node.json is judged by it; any other repo by setup.
# To pass: never edit a rendered file by hand: change its source (the parent's
# template, the hooks tool's source, the checks tool's runner) and re-render
# (`setup <path>`, or `setup fanout <component>`), then commit the render. For
# `absent`/`missing`, list only files the rebuild renders and commit them.
# What regenerate adds at the top (unaccounted files, record safety) is
# `checks explain regenerate`.
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checkslib import api, contract, regen  # noqa: E402

SETUP_CLI = Path("tools/setup/setup")
TIMEOUT = 240
ONE_OF = re.compile(r"not a fanout component \(one of: ([^)]*)\)")


def fanout(ctx, cli, args):
    """(exit code, stdout, stderr) of `setup fanout ...` from the workspace top."""
    try:
        p = subprocess.run([str(cli), "fanout", *args, "--root", str(ctx.workspace)], capture_output=True,
                           text=True, stdin=subprocess.DEVNULL, timeout=TIMEOUT, cwd=ctx.workspace)
    except subprocess.TimeoutExpired:
        api.done(unchecked=f"`setup fanout {' '.join(args[:1])}` ran past {TIMEOUT}s: the renders went unjudged")
    return p.returncode, p.stdout, p.stderr


def components(ctx, cli):
    """The components setup renders into repos, as setup's own refusal names them."""
    _, out, err = fanout(ctx, cli, ["(list)", "--dry-run", "--json"])
    m = ONE_OF.search(err + out)
    if not m:
        api.done(unchecked=f"setup named no fanout components (its refusal of an unknown one said: "
                           f"{(err or out).strip()[-160:]!r}): the renders went unjudged")
    return [c.strip() for c in m.group(1).split(",") if c.strip()]


def judge(ctx, cli):
    findings, ok, unjudged, carried = [], [], [], []
    names = components(ctx, cli)
    for c in names:
        code, out, err = fanout(ctx, cli, [c, "--repos", str(ctx.repo), "--dry-run", "--json"])
        try:
            doc = json.loads(out)
            row = doc["repos"][0]
            status, detail = row["status"], row.get("detail") or ""
        except (ValueError, KeyError, IndexError, TypeError):
            unjudged.append(f"{c}: setup gave no report (exit {code}): {(err or out).strip()[-160:]}")
            continue
        if status == "undeclared":
            continue
        carried.append(c)
        if status == "unchanged":
            ok.append(c)
        elif status == "would-commit":
            findings.append(f"drift: {c}: setup would render {', '.join(row.get('written') or []) or detail}")
        elif status == "failed" and (" drift:" in detail or "would render" in detail):
            findings.append(f"drift: {c}: {detail[:300]}")
        else:
            unjudged.append(f"{c}: {status}: {detail[:200]}")
    if findings:
        api.done(findings)
    if unjudged:
        api.done(unchecked="setup could not judge every render here: " + "; ".join(unjudged))
    if not carried:
        api.done(na=f"setup renders none of its components ({', '.join(names)}) into {ctx.rel}")
    print(f"renders match setup's: {', '.join(ok)}")
    api.done()


def main():
    ctx = api.context()
    if os.environ.get(regen.GUARD):
        api.done(unchecked="nested inside a rebuild, which is what this check runs: not rebuilt again")
    doc, found = contract.read(ctx.repo, contract.NODE)
    if doc is not None or found:
        regen.main(("absent", "rebuild", "missing", "drift"))
    if ctx.workspace is None or ctx.rel is None:
        api.done(unchecked=f"no {contract.NODE} and no workspace top holding setup: nothing says what is "
                           f"rendered here (never a pass)")
    cli = ctx.workspace / SETUP_CLI
    if not os.access(cli, os.X_OK):
        api.done(unchecked=f"no {contract.NODE} and no setup tool at {SETUP_CLI}: nothing says what is "
                           f"rendered here (never a pass)")
    judge(ctx, cli)


main()
