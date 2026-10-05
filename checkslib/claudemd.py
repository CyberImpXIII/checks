"""The one reader of a CLAUDE.md's rule sections, shared by rules-in-sync and
rules-gated so the two cannot disagree about where a section starts, where it
ends, or what counts as the same words.

A section is a `## ` heading and the lines under it, up to the next `## `
heading or the shared block's end marker (`<!-- /shared`). A heading inside a
fenced code block is not one. `shared` is True for a section between the
setup tool's `<!-- shared:` start marker and that end marker: the block every
copy carries from setup's template."""
import re
from collections import namedtuple

Section = namedtuple("Section", "heading line lines shared")

HEAD = re.compile(r"^## (.+?)\s*$")
START = re.compile(r"^<!-- shared:")
END = re.compile(r"^<!-- /shared")
FENCE = re.compile(r"^\s{0,3}(```|~~~)")


def sections(text):
    """[Section] in file order; `line` is the heading's 1-based line number."""
    out, cur, in_block, fence = [], None, False, False
    for n, line in enumerate(text.splitlines(), 1):
        if FENCE.match(line):
            fence = not fence
        if not fence and START.match(line):
            in_block, cur = True, None
            continue
        if not fence and END.match(line):
            in_block, cur = False, None
            continue
        m = None if fence else HEAD.match(line)
        if m:
            cur = Section(m.group(1), n, [], in_block)
            out.append(cur)
        elif cur is not None:
            cur.lines.append(line)
    return out


def has_block(text):
    return any(START.match(l) for l in text.splitlines())


def words(text):
    """Lowercased words: curly quotes made straight, apostrophes dropped
    ("Jacob's" -> jacobs), a link's URL dropped, every other non-letter,
    non-digit a word break. So wrapping, punctuation and markdown never matter;
    a changed word does."""
    t = text.lower().replace("’", "'").replace("‘", "'")
    t = re.sub(r"\]\([^)]*\)", " ", t)
    t = t.replace("'", "")
    return re.sub(r"[^a-z0-9]+", " ", t).split()


def contains(seq, sub):
    n = len(sub)
    return n > 0 and any(seq[i:i + n] == sub for i in range(len(seq) - n + 1))


def norm(heading):
    return re.sub(r"\s+", " ", heading.replace("’", "'")).strip().lower()


def heading_is(heading, name):
    """True when `heading` is `name`, or `name` followed by a suffix that starts
    at a word break (" — ENFORCED, not advised", ": structured"): so "Push"
    does not name "Push code changes to git", and a renamed heading does not
    keep matching."""
    h, n = norm(heading), norm(name)
    return h == n or (h.startswith(n) and not h[len(n)].isalnum())
