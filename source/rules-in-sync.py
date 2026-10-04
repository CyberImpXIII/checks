#!/usr/bin/env python3
# checks: applies_to=all params=file
# Proves: the repo's CLAUDE.md carries the shared rules the workspace top's
# CLAUDE.md says every copy must carry, on meaning:
#   - every section of the top's CLAUDE.md whose text says it "belongs in
#     every copy" has a heading here that starts with the same words (a
#     suffix such as " — write it when you notice it" is allowed);
#   - "Constraints that don't bend" is here once, and carries each of the top's
#     constraint bullets by meaning (Jacob, 2026-10-04). Its preamble is the
#     repo's own, and so are any further bullets of its own.
# The matching rule, exactly. Text is normalised first: lowercased, curly quotes
# made straight, markdown (** ` _ ~, a link's URL) and every other non-letter,
# non-digit dropped, apostrophes removed ("Jacob's" -> jacobs, "don't" -> dont),
# so wrapping, punctuation, dashes and bold never matter. "Content words" are
# those words minus a fixed list of fillers (a, the, to, of, or, is, ...);
# negations (never, not, no, without, dont, ...) are never fillers.
# For each bullet of the top's section, its claim is its leading bold text (its
# first sentence if it has none). Then, in this repo's section:
#   1. some bullet must contain the claim's content words, contiguous and in
#      order (words around them are allowed). None does: MISSING, naming the
#      closest bullet and the words it lacks -- or CONTRADICTED when one has
#      the claim once negations and their opposites (always, do, must, ...)
#      are set aside on both sides ("Always ..." for "Never ...");
#   2. that bullet must carry the claim's core: the further phrases CORE below
#      names for it, matched the same way. One absent: WEAKENED;
#   3. it must add no exception or hedge (HEDGES below: unless, except,
#      usually, may, where possible, ...) that the top's bullet lacks: WEAKENED.
# Everything else in a bullet (its examples, its "not in a recipe, a config")
# is the repo's own wording. CORE holds what each bullet must keep beyond its
# claim: the scope it extends to, or what to do instead. Each CORE entry is
# checked against the top's own text every run; a top bullet CORE does not
# name is still required (claim only), and a CORE entry the top no longer
# carries fails as a broken reference, so CORE cannot go stale silently.
# Not caught (said, not hidden): a contradiction written in the section's
# prose or in a separate bullet of the repo's own, without a hedge word.
# Needs the workspace top: in a lone clone it is UNCHECKED, and at the top
# itself it is UNCHECKED (that copy is the reference).
# To pass: copy the missing section from the top-level CLAUDE.md (or re-run
# the setup tool, whose shared-rules block carries them). For a constraint
# finding, put the top's bullet back with its bold claim word for word; keep
# its core phrase and add no exception to it. Your own preamble and your own
# extra bullets can stay.
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
BOLD_LEAD = re.compile(r"^\*\*(.+?)\*\*(.*)$", re.S)

# The top's bullets, by the opening words of their claim, and the core each
# must keep beyond the claim. Why these: "same for anything public or
# irreversible" widens the claim past messages; "a result to report, not an
# obstacle" says what to do instead of bypassing; "don't ask Jacob to repeat a
# secret" is a second prohibition. The rest of each top bullet is example
# ("Not in a recipe, a config, ...") or restates the claim ("Reading a mailbox
# is not permission to write to it"), and a repo may say it in its own terms.
CORE = [
    ("Never send a message", ["Same for anything public or irreversible"]),
    ("Never attempt to bypass bot detection", ["A detected wall is a result to report, not an obstacle to route around"]),
    ("Credential-shaped values are supplied at run time", []),
    ("Report key names", ["don't ask Jacob to repeat a secret back to you"]),
]
FILLER = set("a an the to of on in or and for by at as is are be been it its this that these those "
             "with from into onto here there you your we our".split())
NEGATION = set("never not no nor without dont cannot cant nothing none wont isnt arent doesnt".split())
# What a flipped negation is replaced with ("never X" -> "always X", "do X"):
# dropped along with the negations when looking for a contradicted claim.
POLARITY = NEGATION | set("always ever do does must should can".split())
HEDGES = ["unless", "except", "excepting", "exception", "exceptions", "however", "usually", "generally",
          "normally", "typically", "mostly", "ideally", "preferably", "sometimes", "occasionally",
          "optional", "optionally", "may", "if possible", "where possible", "when possible", "if needed",
          "when needed", "where needed", "if necessary", "when convenient", "if convenient", "fine to",
          "ok to", "okay to", "allowed to", "permitted", "acceptable", "try to"]


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
    """Each list item's text, its wrapped lines joined. Prose before, between or
    after the items (a preamble) is not an item."""
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


def words(text):
    t = text.lower().replace("’", "'").replace("‘", "'")
    t = re.sub(r"\]\([^)]*\)", " ", t)
    t = t.replace("'", "")
    return re.sub(r"[^a-z0-9]+", " ", t).split()


def content(text):
    return [w for w in words(text) if w not in FILLER]


def contains(seq, sub):
    n = len(sub)
    return n > 0 and any(seq[i:i + n] == sub for i in range(len(seq) - n + 1))


def claim_of(bullet):
    m = BOLD_LEAD.match(bullet)
    if m:
        return m.group(1).strip()
    return re.split(r"(?<=[.!?])\s", bullet, maxsplit=1)[0]


def short(text, n=10):
    w = text.replace("**", "").split()
    return " ".join(w[:n]) + (" ..." if len(w) > n else "")


def reference(top_bullets):
    """[(claim, core phrases, top bullet)] for every bullet of the top's section,
    plus the findings that say the reference no longer agrees with CORE."""
    broken, ref, used = [], [], set()
    for b in top_bullets:
        claim = claim_of(b)
        core = []
        for i, (opening, phrases) in enumerate(CORE):
            if content(claim)[:len(content(opening))] == content(opening):
                used.add(i)
                core = phrases
                for p in phrases:
                    if not contains(content(b), content(p)):
                        broken.append(f"the top's '{CONSTRAINTS}' bullet \"{short(claim)}\" no longer says "
                                      f"\"{p}\": the reference is broken (update CORE in rules-in-sync.py)")
        ref.append((claim, core, b))
    for i, (opening, _) in enumerate(CORE):
        if i not in used:
            broken.append(f"the top's '{CONSTRAINTS}' has no bullet starting \"{opening}\": the reference is broken "
                          f"(update CORE in rules-in-sync.py)")
    return ref, broken


def compare(name, ref, mine):
    """Findings for this repo's constraint bullets against the reference."""
    out = []
    have = [(b, content(b), words(b)) for b in mine]
    for claim, core, top_b in ref:
        want = content(claim)
        matched = [h for h in have if contains(h[1], want)]
        if not matched:
            bare = [w for w in want if w not in POLARITY]
            flipped = [h for h in have if contains([w for w in h[1] if w not in POLARITY], bare)]
            if flipped:
                out.append(f"{name}: '{CONSTRAINTS}': CONTRADICTED: \"{short(claim)}\" is here with its negation "
                           f"changed: \"{short(flipped[0][0], 14)}\"")
                continue
            best = max(have, key=lambda h: len(set(want) & set(h[1])), default=None)
            lacking = [w for w in dict.fromkeys(want) if best is None or w not in best[1]]
            if best is not None and len(lacking) * 2 <= len(set(want)):
                out.append(f"{name}: '{CONSTRAINTS}': MISSING: no bullet says \"{claim}\" (closest: "
                           f"\"{short(best[0])}\", which lacks or reorders: {', '.join(lacking) or 'word order'})")
            else:
                out.append(f"{name}: '{CONSTRAINTS}': MISSING: no bullet says \"{claim}\"")
            continue
        for p in core:
            if not any(contains(h[1], content(p)) for h in matched):
                out.append(f"{name}: '{CONSTRAINTS}': WEAKENED: the bullet \"{short(claim)}\" drops \"{p}\"")
        top_w = words(top_b)
        added = [h for h in HEDGES if any(contains(m[2], h.split()) for m in matched) and not contains(top_w, h.split())]
        if added:
            out.append(f"{name}: '{CONSTRAINTS}': WEAKENED: the bullet \"{short(claim)}\" adds "
                       f"{', '.join(repr(h) for h in added)}, which the top's does not have")
    return out


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
    own = sections(mine.read_text(errors="replace"))
    ref_by = {norm(h): b for h, b in ref}
    required = [h for h, b in ref if EVERY_COPY in " ".join(b)]
    if norm(CONSTRAINTS) not in ref_by:
        api.done([f"the workspace top's CLAUDE.md has no '{CONSTRAINTS}' section: the reference is broken"])
    shared, broken = reference(bullets(ref_by[norm(CONSTRAINTS)]))
    if broken:
        api.done(broken)
    if not shared:
        api.done([f"the workspace top's '{CONSTRAINTS}' has no bullets: the reference is broken"])
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
        findings += compare(name, shared, bullets(mine_c[0]))
    api.done(findings)


main()
