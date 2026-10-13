#!/usr/bin/env python3
# checks: applies_to=roles:audit params=allow
# Proves: no shell write in the repo's code loses its failure silently
# (RESEARCH-writers.md Q4 "silent" rows; Options 5). The scan is
# checkslib/writers.py, the same one `checks writers` prints: a `>`/`>>`/
# `cp`/`tee` write whose stderr goes to /dev/null and whose failure is not
# handled on its line (no `||` other than `|| true` / `|| :`, no `&&`, not an
# `if`/`while`/`until` condition). At mode 0444, or on a full disk, such a
# write fails and nothing says so: a row is lost, which is worse than an
# error. One finding per site, `file:line: <primitive>: <code>`.
# Docs, `.claude/` hook copies and tests are not scanned (scan.in_scope).
# Audit-only (roles:audit), never pre-commit: it reads a line, not the
# program, so a failure handled on a later line is a false finding until
# its file is listed in `allow` (checks.json: {"silent-writes": {"allow":
# ["path/a.sh"]}}) after a person has read it. An `allow` entry that names
# no file in the repo is a finding (stale). On ok it prints the site count
# by kind.
# To pass: handle the failure where it happens (`|| die ...`, or the shared
# tools/hooks ledger.sh, which records a failed append), or keep stderr; or,
# when the failure is handled further on, list the file in `allow`.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checkslib import api, writers  # noqa: E402


def main():
    ctx = api.context()
    allow = ctx.param("allow", [])
    if not isinstance(allow, list) or not all(isinstance(a, str) for a in allow):
        api.done([f"checks.json: silent-writes.allow must be a list of repo-relative file paths, got {allow!r}"])
    sites = writers.scan_repo(ctx)
    findings = [f"checks.json: silent-writes.allow names `{a}`, which is not a file in the repo"
                for a in allow if not (ctx.repo / a).is_file()]
    findings += [f"{s['file']}:{s['line']}: {s['primitive']}: its failure is discarded and not handled: {s['code']}"
                 for s in sites if s["kind"] == "silent" and s["file"] not in allow]
    if not findings:
        said = ", ".join(f"{n} {k}" for k, n in writers.counts(sites).items()) or "none"
        print(f"{len(sites)} write site(s), none silent outside `allow`: {said}")
    api.done(findings)


main()
