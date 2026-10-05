#!/usr/bin/env python3
# checks: applies_to=all
# Proves: the repo's `.claude/settings.json`, when it exists, is tracked by git
# (`git ls-files` lists it: committed, or staged for the commit being made) and
# no ignore rule matches it (`git check-ignore --no-index`: .gitignore,
# .git/info/exclude or the global excludes file), so the hook registrations it
# holds travel with a clone (PLAN-repo-setup.md §7.9). A repo with no
# settings.json passes: there is nothing to track. Outside a git repo (the
# workspace top) it is UNCHECKED, said out loud.
# To pass: `git add .claude/settings.json` unchanged and commit it; delete the
# ignore rule the finding names (it names file:line and the pattern). The
# file's contents stay Jacob's: this check never asks for an edit to them.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checkslib import api  # noqa: E402

REL = ".claude/settings.json"


def main():
    ctx = api.context()
    if not ctx.is_git():
        api.done(unchecked="not a git repo: nothing can track .claude/settings.json here")
    if not (ctx.repo / REL).is_file():
        api.done()
    findings = []
    code, out = ctx.git("ls-files", "-z", "--cached", "--", REL)
    if code != 0:
        print(f"git ls-files failed (exit {code})")
        sys.exit(1)
    if REL not in out.split("\0"):
        findings.append(f"{REL}: exists but git does not track it (git add it, unchanged)")
    # The verdict comes from -q alone: with -v, check-ignore also prints (and
    # exits 0 on) a matching negation (`!pattern`), which un-ignores the path.
    code, _ = ctx.git("check-ignore", "-q", "--no-index", "--", REL)
    if code == 0:
        _, why = ctx.git("check-ignore", "-v", "--no-index", "--", REL)
        source = why.split("\t", 1)[0].strip() or "an ignore rule"
        findings.append(f"{REL}: git-ignored by {source}")
    elif code != 1:
        print(f"git check-ignore failed (exit {code})")
        sys.exit(1)
    api.done(findings)


main()
