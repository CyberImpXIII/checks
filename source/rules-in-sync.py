#!/usr/bin/env python3
# checks: applies_to=all params=file
# Proves: the repo's CLAUDE.md carries the shared rules the workspace top's
# CLAUDE.md says every copy must carry:
#   - every section of the top's CLAUDE.md whose text says it "belongs in
#     every copy" has a heading here that starts with the same words (a
#     suffix such as " — write it when you notice it" is allowed);
#   - each rule sentence of the top's "Constraints that don't bend" is present
#     in this copy. A rule sentence is the bold lead of each bullet there (its
#     first sentence if it has no bold lead): today, never send on Jacob's
#     behalf, never bypass bot detection, credentials at run time only, key
#     names never values. They are read from the top each run, so a fifth
#     bullet there is required here at once.
# The matching rule, exactly (Jacob, 2026-10-04, decision 12 revised: "a check
# is supposed to be a guardrail for the guardrail"): the sentence's words must
# appear in this file, in order and next to each other, after both sides are
# normalised: lowercased, curly quotes made straight, apostrophes dropped
# ("Jacob's" -> jacobs), markdown (** ` _ ~, a link's URL) and every other
# non-letter, non-digit made a word break. So wrapping, punctuation, dashes and
# bold never matter; a changed word does. Every other line is ignored: the
# section's preamble, a bullet's explanation, the repo's own extra bullets,
# even where the section sits. Wording drift around the sentences is not this
# check's business (an audit on demand, if anyone wants one).
# Needs the workspace top: in a lone clone it is UNCHECKED, and at the top
# itself it is UNCHECKED (that copy is the reference).
# To pass: copy the missing section from the top-level CLAUDE.md (or re-run
# the setup tool, whose shared-rules block carries them); for a missing rule
# sentence, put the top's bold lead back, word for word, under your
# "Constraints that don't bend". Your own preamble, explanations and extra
# bullets can stay.
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checkslib import api  # noqa: E402

CONSTRAINTS = "Constraints that don't bend"
EVERY_COPY = "belongs in every copy"
HEAD = re.compile(r"^## (.+?)\s*$")
END = re.compile(r"^(## |<!-- /shared)")
BULLET = re.compile(r"^\s{0,3}[-*+]\s+")
BOLD_LEAD = re.compile(r"^\*\*(.+?)\*\*")


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


def bullets(lines):
    """Each list item's text, its wrapped lines joined; prose around the items is not one."""
    out, cur, blank = [], None, False
    for line in lines:
        if BULLET.match(line):
            cur = [BULLET.sub("", line, count=1)]
            out.append(cur)
        elif not line.strip():
            pass
        elif cur is not None and (line[:1].isspace() or not blank):
            cur.append(line.strip())
        else:
            cur = None
        blank = not line.strip()
    return [" ".join(b).strip() for b in out]


def rule_sentence(bullet):
    m = BOLD_LEAD.match(bullet)
    if m:
        return m.group(1).strip()
    return re.split(r"(?<=[.!?])\s", bullet, maxsplit=1)[0]


def words(text):
    t = text.lower().replace("’", "'").replace("‘", "'")
    t = re.sub(r"\]\([^)]*\)", " ", t)
    t = t.replace("'", "")
    return re.sub(r"[^a-z0-9]+", " ", t).split()


def contains(seq, sub):
    n = len(sub)
    return n > 0 and any(seq[i:i + n] == sub for i in range(len(seq) - n + 1))


def norm(heading):
    return re.sub(r"\s+", " ", heading.replace("’", "'")).strip().lower()


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
    text = mine.read_text(errors="replace")
    own = sections(text)
    ref_by = {norm(h): b for h, b in ref}
    if norm(CONSTRAINTS) not in ref_by:
        api.done([f"the workspace top's CLAUDE.md has no '{CONSTRAINTS}' section: the reference is broken"])
    rules = [rule_sentence(b) for b in bullets(ref_by[norm(CONSTRAINTS)])]
    rules = [r for r in rules if words(r)]
    if not rules:
        api.done([f"the workspace top's '{CONSTRAINTS}' has no rule sentences: the reference is broken"])
    findings = []
    own_heads = [norm(h) for h, _ in own]
    for h in (h for h, b in ref if EVERY_COPY in " ".join(b)):
        if not any(o.startswith(norm(h)) for o in own_heads):
            findings.append(f"{name}: no section '{h}' (the top says it belongs in every copy)")
    have = words(text)
    for r in rules:
        if not contains(have, words(r)):
            findings.append(f"{name}: rule sentence missing (from the top's '{CONSTRAINTS}'): \"{r}\"")
    api.done(findings)


main()
