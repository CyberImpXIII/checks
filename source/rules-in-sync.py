#!/usr/bin/env python3
# checks: applies_to=all params=file
# Proves: the repo's CLAUDE.md carries the shared rules the workspace top's
# CLAUDE.md says every copy must carry, on meaning:
#   - "Constraints that don't bend" is present and verbatim, word for word (how
#     its lines wrap aside: a rewrap is the same text), because the delegation layer
#     copies that section into agent definitions word for word;
#   - every section of the top's CLAUDE.md whose text says it "belongs in
#     every copy" has a heading here that starts with the same words (a
#     suffix such as " — write it when you notice it" is allowed).
# The list of required sections is read from the top's text each run, so it
# cannot go stale. Needs the workspace top: in a lone clone it is UNCHECKED,
# and at the top itself it is UNCHECKED (that copy is the reference).
# To pass: copy the missing section from the top-level CLAUDE.md (or re-run
# the setup tool, whose shared-rules block carries them), keeping the
# constraints section word for word.
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checkslib import api  # noqa: E402

CONSTRAINTS = "Constraints that don't bend"
EVERY_COPY = "belongs in every copy"
HEAD = re.compile(r"^## (.+?)\s*$")
END = re.compile(r"^(## |<!-- /shared)")


def sections(text):
    """[(heading, body lines)] for every `## ` heading, the body ending at the next
    heading or the shared block's end marker."""
    out, cur = [], None
    for line in text.splitlines():
        m = HEAD.match(line)
        if m:
            cur = (m.group(1), [])
            out.append(cur)
        elif cur is not None and END.match(line):
            cur = None
        elif cur is not None:
            cur[1].append(line)
    return out


def norm(heading):
    return re.sub(r"\s+", " ", heading.replace("’", "'")).strip().lower()


def body(lines):
    return " ".join(lines).split()


def main():
    ctx = api.context()
    name = ctx.param("file", "CLAUDE.md")
    if ctx.workspace is None:
        api.done(unchecked="no workspace top: nothing to compare with (lone clone)")
    top = ctx.workspace / "CLAUDE.md"
    if not top.is_file():
        api.done(unchecked=f"the workspace top has no CLAUDE.md to compare with ({top})")
    mine = ctx.repo / name
    if mine.resolve() == top.resolve():
        api.done(unchecked="this is the reference copy (the workspace top)")
    if not mine.is_file():
        api.done([f"{name}: missing"])
    ref = sections(top.read_text(errors="replace"))
    own = sections(mine.read_text(errors="replace"))
    ref_by = {norm(h): b for h, b in ref}
    required = [h for h, b in ref if EVERY_COPY in " ".join(b)]
    if norm(CONSTRAINTS) not in ref_by:
        api.done([f"the workspace top's CLAUDE.md has no '{CONSTRAINTS}' section: the reference is broken"])
    findings = []
    own_heads = [norm(h) for h, _ in own]
    for h in required:
        if not any(o.startswith(norm(h)) for o in own_heads):
            findings.append(f"{name}: no section '{h}' (the top says it belongs in every copy)")
    mine_c = [b for h, b in own if norm(h) == norm(CONSTRAINTS)]
    if not mine_c:
        findings.append(f"{name}: no section '{CONSTRAINTS}'")
    elif len(mine_c) > 1:
        findings.append(f"{name}: '{CONSTRAINTS}' appears {len(mine_c)} times")
    else:
        want, have = body(ref_by[norm(CONSTRAINTS)]), body(mine_c[0])
        if want != have:
            first = next((i for i, (a, b) in enumerate(zip(want, have)) if a != b), min(len(want), len(have)))
            near = " ".join(have[first:first + 6]) or "(the end)"
            findings.append(f"{name}: '{CONSTRAINTS}' differs from the top's at word {first + 1}, near \"{near}\" "
                            f"({len(have)} words here, {len(want)} there)")
    api.done(findings)


main()
