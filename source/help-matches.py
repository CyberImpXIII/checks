#!/usr/bin/env python3
# checks: applies_to=all params=script,help_arg
# Proves: the repo's pre-commit script (dev.sh) documents exactly the
# subcommands its dispatching `case` implements, both directions. The help is
# read from a real run (`<script> help`), not from the source, because the
# failure this exists for was a usage() printing a hardcoded line range that
# truncated its own help while the tool kept working.
# Documented: in the help output, the lines at the indent of the first
# indented line that starts with a lowercase word (an optional `./dev.sh `
# prefix allowed; the one reader is checkslib/helptext.py). Implemented: the arms of the last top-level `case ... esac`
# block, nested cases aside, minus the help arm (the one listing -h/--help/"").
# To pass: add the missing line to usage(), or the missing arm to the case.
# A git repo with no script fails (it has no pre-commit command); a folder that
# is not a git repo and has none is UNCHECKED.
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checkslib import api, helptext  # noqa: E402

ARM = re.compile(r"^\s*([^\s()]+(?:\|[^\s()]+)*)\)")
HELP_ALIASES = {'""', "''", "-h", "--help"}


def implemented(src):
    lines = src.splitlines()
    blocks, start = [], None
    for i, line in enumerate(lines):
        if start is None and re.match(r"^case\s.*\sin\s*$", line):
            start = i
        elif start is not None and re.match(r"^esac\b", line):
            blocks.append(lines[start + 1:i])
            start = None
    if not blocks:
        return None
    out, depth = set(), 0
    for line in blocks[-1]:
        if depth == 0:
            m = ARM.match(line)
            if m:
                alts = m.group(1).split("|")
                if not set(alts) & HELP_ALIASES and alts != ["*"]:
                    out.update(a for a in alts if re.fullmatch(r"[a-z][a-z0-9-]*", a))
        depth += len(re.findall(r"(?:^|[\s;])case\s.*?\sin\b", line)) - len(re.findall(r"(?:^|[\s;])esac\b", line))
    return out


def main():
    ctx = api.context()
    script = ctx.repo / ctx.param("script", "dev.sh")
    if not script.is_file():
        if ctx.is_git():
            api.done([f"{script.name}: missing; the repo has no pre-commit command"])
        api.done(unchecked=f"{script.name}: absent, and this is not a git repo")
    impl = implemented(script.read_text(errors="replace"))
    if impl is None:
        api.done([f"{script.name}: no top-level `case ... esac` dispatch found"])
    arg = ctx.param("help_arg", "help")
    out, why = helptext.run(script, ctx.repo, arg, via_bash=True)
    if why:
        api.done([f"{script.name} {arg}: {why}"])
    doc = helptext.commands(out, script.name)
    if not doc:
        api.done([f"{script.name} {arg}: printed no subcommand lines"])
    findings = [f"implemented, not in the help: {w}" for w in sorted(impl - doc)]
    findings += [f"in the help, not implemented: {w}" for w in sorted(doc - impl)]
    api.done(findings)


main()
