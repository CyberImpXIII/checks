#!/usr/bin/env python3
# checks: applies_to=roles:audit
# Proves: the repo's working tree holds no uncommitted work: nothing modified,
# staged, deleted or untracked-and-not-ignored (`git status --porcelain`).
# Runs only when a caller passes `--roles audit` (`checks all --roles audit`),
# never in a repo's pre-commit run: there, uncommitted work is exactly what is
# about to be committed. In an audit across the workspace, a dirty tree means
# someone is mid-task there, or left work nobody else can pick up.
# Outside a git repo (the workspace top) it is UNCHECKED, said out loud.
# To pass: commit the work (or ignore what should never be committed); if it
# is another session's, leave it and tell its owner.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checkslib import api  # noqa: E402


def main():
    ctx = api.context()
    if not ctx.is_git():
        api.done(unchecked="not a git repo: no working tree to compare with a commit")
    code, out = ctx.git("status", "--porcelain=v1", "-z", "--untracked-files=all")
    if code != 0:
        print(f"git status failed (exit {code})")
        sys.exit(1)
    entries = [e for e in out.split("\0") if e]
    findings, skip = [], False
    for e in entries:
        if skip:                    # the source path of a rename (-z prints it after the entry)
            skip = False
            continue
        xy, path = e[:2], e[3:]
        skip = "R" in xy or "C" in xy
        findings.append(f"uncommitted ({xy.strip() or '?'}): {path}")
    api.done(findings)


main()
