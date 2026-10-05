#!/usr/bin/env python3
# checks: applies_to=all
# Proves: every rule section of the repo's CLAUDE.md is classified, and every
# classification is true (PLAN-hard-gates.md §1, §5; Jacob's answer to §8
# decision 1: each rule is a `gate`, with the gate named, or `prose`, with a
# one-line reason no check can hold it). Rows come from two files:
#   - the registry, tools/checks/gates.json (this tool's own copy, never a
#     param): rows with `in`, a list of "shared" (the sections of setup's
#     shared-rules block, in every CLAUDE.md that carries the block's markers)
#     and repo paths relative to the workspace top ("." is the top);
#   - the repo's own gates.json, when it has one: rows without `in`, for the
#     repo's own sections (outside the shared block).
# Both ways: every `## ` heading (the shared block's against the "shared" rows;
# the rest against the rows for this repo and its own file) has a row, and
# every row that applies here names a heading that exists. A row's `section`
# matches a heading that is it, or it plus a suffix (" — ENFORCED"); its
# `rule` (a quote) must appear in that section, same words after normalising
# (the rules-in-sync reading: checkslib/claudemd.py). A `gate` row's gate and
# test exist (paths from the workspace top), the gate is executable (unless
# `template`: a file another tool installs executable), and the test names the
# gate (its file name or text holds the gate's name). A `planned` row instead
# has a `plan` pointer, "PLAN-x.md §n", whose file and §n heading exist. A
# `prose` row has a `why`. Every registry row's SHAPE is validated in every
# repo (a malformed row is red everywhere); paths and plan pointers only for
# the rows that apply here (tests/test_rules_gated.py holds every registry
# row's paths against the real workspace). On ok it prints the counts and the
# planned ids, and names a planned row whose gate and test now both exist
# (flip it to active).
# Not proven: that a gate RUNS here (wiring is hooks-installed's and setup's
# githooks'), or that its test exercises a failing input (that is the gate
# owner's suite; a static check cannot see it). No workspace top: gate paths
# and plan pointers go unchecked, so the result is UNCHECKED when nothing else
# fails.
# To pass: add a row for the new section (kind gate with its gate, or kind
# prose with why) -- in the repo's own gates.json for its own sections, in
# tools/checks/gates.json for the shared block or the top; fix a row whose
# heading or quoted rule moved; mark a gate that does not exist yet
# `"status": "planned"` with the plan section that schedules it.
import json
import os
import re
import sys
from pathlib import Path, PurePosixPath

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checkslib import api  # noqa: E402
from checkslib import claudemd  # noqa: E402

TOOL_ROOT = Path(__file__).resolve().parent.parent
REGISTRY = TOOL_ROOT / "gates.json"
ID = re.compile(r"^[a-z0-9][a-z0-9-]*$")
PLAN = re.compile(r"^(PLAN-[A-Za-z0-9_-]+\.md) §([0-9]+[a-z]?)$")
KINDS = ("gate", "prose")
HOW = ("rewrite", "block", "refuse", "check")


class Rows:
    def __init__(self, label):
        self.label = label           # how findings name the file
        self.findings = []

    def bad(self, row_id, msg):
        self.findings.append(f"{self.label} row '{row_id}': {msg}")


def load(path, label, registry, keys=None):
    """(rows, findings, keys). A file that is not the expected shape is one
    finding and no rows: a registry that cannot be read is red, never empty."""
    rf = Rows(label)
    try:
        doc = json.loads(path.read_text())
    except (OSError, ValueError) as e:
        return [], [f"{label}: unreadable ({e.__class__.__name__}: {str(e)[:120]})"], keys
    if not isinstance(doc, dict) or not isinstance(doc.get("rules"), list):
        return [], [f"{label}: not an object with a `rules` list"], keys
    top_keys = {"_comment", "rules"} | ({"keys"} if registry else set())
    extra = sorted(set(doc) - top_keys)
    if extra:
        rf.findings.append(f"{label}: unknown top-level key(s) {', '.join(extra)}")
    if registry:
        keys = doc.get("keys")
        if not isinstance(keys, dict) or not keys:
            return [], rf.findings + [f"{label}: no `keys` vocabulary"], keys
    rows = []
    for i, row in enumerate(doc["rules"]):
        rid = row.get("id") if isinstance(row, dict) else None
        rid = rid if isinstance(rid, str) and rid else f"#{i}"
        if not isinstance(row, dict):
            rf.bad(rid, "not an object")
            continue
        unknown = sorted(set(row) - set(keys or {}))
        if unknown:
            rf.bad(rid, f"unknown key(s) {', '.join(unknown)} (the vocabulary is the registry's `keys`)")
        if not ID.match(row.get("id") or ""):
            rf.bad(rid, "`id` missing or not lowercase-with-dashes")
        for k in ("section", "rule"):
            if not isinstance(row.get(k), str) or not row[k].strip():
                rf.bad(rid, f"`{k}` missing")
        if "note" in row and not isinstance(row["note"], str):
            rf.bad(rid, "`note` is text")
        if registry:
            where = row.get("in")
            if not isinstance(where, list) or not where or not all(isinstance(w, str) and w for w in where):
                rf.bad(rid, "`in` missing: a registry row says where it applies (\"shared\", or repo paths)")
        elif "in" in row:
            rf.bad(rid, "`in` is the registry's: a repo's own row applies to that repo only")
        kind = row.get("kind")
        if kind not in KINDS:
            rf.bad(rid, f"`kind` must be one of {', '.join(KINDS)}")
        elif kind == "prose":
            if not isinstance(row.get("why"), str) or not row["why"].strip():
                rf.bad(rid, "prose without `why` (say why no check can hold it)")
            for k in ("gate", "test", "how", "status", "plan", "template"):
                if k in row:
                    rf.bad(rid, f"prose row with `{k}`: a prose rule has no gate")
        else:
            if row.get("how") not in HOW:
                rf.bad(rid, f"`how` must be one of {', '.join(HOW)}")
            if "why" in row:
                rf.bad(rid, "gate row with `why`: `why` is for prose (use `note`)")
            status = row.get("status")
            if status not in (None, "planned"):
                rf.bad(rid, "`status` is \"planned\" or absent (active)")
            if status == "planned":
                if not isinstance(row.get("plan"), str) or not PLAN.match(row["plan"]):
                    rf.bad(rid, "planned without a `plan` pointer \"PLAN-x.md §n\"")
            else:
                if "plan" in row:
                    rf.bad(rid, "`plan` on an active row: drop it, or mark the row planned")
                for k in ("gate", "test"):
                    if not isinstance(row.get(k), str) or not row[k].strip():
                        rf.bad(rid, f"active gate without `{k}`")
            if "template" in row and not isinstance(row["template"], bool):
                rf.bad(rid, "`template` is true or false")
        rows.append(row)
    return rows, rf.findings, keys


def rel_ok(p):
    pp = PurePosixPath(p)
    return not pp.is_absolute() and ".." not in pp.parts


def names(test, gate):
    stem = PurePosixPath(gate).name.split(".")[0]
    if stem in test.name:
        return True
    try:
        return PurePosixPath(gate).name in test.read_text(errors="replace") or stem in test.read_text(errors="replace")
    except OSError:
        return False


def check_paths(row, label, ws, landed):
    """Findings for one row's gate/test/plan, against the workspace top."""
    out, rid = [], row.get("id", "?")
    if row.get("kind") != "gate":
        return out
    if row.get("status") == "planned":
        m = PLAN.match(row.get("plan") or "")
        if m:
            plan = ws / m.group(1)
            if not plan.is_file():
                out.append(f"{label} row '{rid}': plan {m.group(1)} not at the workspace top")
            else:
                head = re.compile(rf"^#{{1,6}}\s+{re.escape(m.group(2))}[.\s]", re.M)
                if not head.search(plan.read_text(errors="replace")):
                    out.append(f"{label} row '{rid}': plan {m.group(1)} has no §{m.group(2)} heading")
        g, t = row.get("gate"), row.get("test")
        if isinstance(g, str) and isinstance(t, str) and rel_ok(g) and rel_ok(t) \
                and (ws / g).is_file() and (ws / t).is_file():
            landed.append(f"landed: '{rid}' is planned but {g} and its test exist: make it active")
        return out
    g, t = row.get("gate"), row.get("test")
    if not isinstance(g, str) or not isinstance(t, str):
        return out                       # already a structure finding
    for k, p in (("gate", g), ("test", t)):
        if not rel_ok(p):
            out.append(f"{label} row '{rid}': {k} {p} must be a path from the workspace top")
    if out:
        return out
    gate, test = ws / g, ws / t
    if not gate.is_file():
        out.append(f"{label} row '{rid}': gate {g} missing")
    elif not row.get("template") and not os.access(gate, os.X_OK):
        out.append(f"{label} row '{rid}': gate {g} not executable (a template another tool installs says `template: true`)")
    if not test.is_file():
        out.append(f"{label} row '{rid}': test {t} missing")
    elif not names(test, g):
        out.append(f"{label} row '{rid}': test {t} does not name the gate {PurePosixPath(g).name}")
    return out


def match_rows(rows, secs, scope, findings, text_of):
    """Both ways between rows ([(label, row)]) and the headings of one scope."""
    for s in secs:
        if not any(claudemd.heading_is(s.heading, r.get("section", "")) for _, r in rows):
            findings.append(f"CLAUDE.md:{s.line}: section '{s.heading}' ({scope}) has no row "
                            f"(classify it: kind gate with its gate, or kind prose with why)")
    for label, r in rows:
        hit = [s for s in secs if claudemd.heading_is(s.heading, r.get("section", ""))]
        rid = r.get("id", "?")
        if not hit:
            findings.append(f"{label} row '{rid}': no section '{r.get('section')}' in CLAUDE.md ({scope})")
            continue
        quote = claudemd.words(r.get("rule") or "")
        if quote and not any(claudemd.contains(claudemd.words(text_of(s)), quote) for s in hit):
            findings.append(f"{label} row '{rid}': rule not in section '{hit[0].heading}': \"{r.get('rule')}\"")


def main():
    ctx = api.context()
    ws = ctx.workspace
    reg_label = "tools/checks/gates.json"
    reg, findings, keys = load(REGISTRY, reg_label, registry=True)
    own_path = ctx.repo / "gates.json"
    own, own_label = [], "gates.json"
    if own_path.is_file() and own_path.resolve() != REGISTRY.resolve():
        own, f, _ = load(own_path, own_label, registry=False, keys=keys)
        findings += f
    ids = [r.get("id") for r in reg + own if isinstance(r.get("id"), str)]
    for d in sorted({i for i in ids if ids.count(i) > 1}):
        findings.append(f"row id '{d}' used more than once (registry and repo rows share one id space)")

    md = ctx.repo / "CLAUDE.md"
    if not md.is_file():
        api.done(findings, unchecked="no CLAUDE.md here: no rules to classify")
    text = md.read_text(errors="replace")
    secs = claudemd.sections(text)
    text_of = lambda s: s.heading + "\n" + "\n".join(s.lines)  # noqa: E731
    shared = [s for s in secs if s.shared]
    mine = [s for s in secs if not s.shared]
    # A block with no "shared" rows is still the block: its headings must be classified.
    rel = ctx.rel
    block = [(reg_label, r) for r in reg if "shared" in (r.get("in") or [])] if claudemd.has_block(text) else []
    here = [(reg_label, r) for r in reg if rel is not None and rel in (r.get("in") or [])] \
        + [(own_label, r) for r in own]
    if claudemd.has_block(text):
        match_rows(block, shared, "the shared block", findings, text_of)
    match_rows(here, mine, "this repo's own sections", findings, text_of)

    # one entry per row: a row `in` both "shared" and this repo is checked and counted once
    applied_pairs = list({id(r): (label, r) for label, r in block + here}.values())
    landed = []
    if ws is not None:
        for label, r in applied_pairs:
            findings += check_paths(r, label, ws, landed)
    if findings:
        api.done(findings)
    if ws is None:
        api.done(unchecked="no workspace top: sections are classified, but gate paths and plan pointers went unchecked")
    applied = [r for _, r in applied_pairs]
    if not secs:
        api.done(unchecked="CLAUDE.md has no `## ` sections: nothing to classify")
    planned = [r.get("id") for r in applied if r.get("status") == "planned"]
    prose = sum(1 for r in applied if r.get("kind") == "prose")
    print(f"rows here: {len(applied)} ({len(applied) - len(planned) - prose} gated, {len(planned)} planned, "
          f"{prose} prose); planned: {', '.join(planned) or 'none'}")
    for line in landed:
        print(line)
    api.done()


if __name__ == "__main__":       # imported by tests/test_rules_gated.py to hold every registry row
    main()
