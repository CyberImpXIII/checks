"""The practice rows (PLAN-services.md §3 A1-A6, §4 step 7.2): their place in
gates.json, the one reader and validator, the import from PRACTICES-rows.md,
the cells `checks practices` prints, and the ratchet.

Where they live: gates.json's `practices` block, beside the CLAUDE.md `rules`
(A1: one registry, no second file). Its own id space: a practice id names a
practice, a `rules` id names a CLAUDE.md section's row (`gates:<repo>#<id>` in a
practice's sources points at the latter).

    "practices": {"_comment", "keys", "rows": [...], "blocked": [...]}

A row (the `keys` vocabulary in gates.json says the same, and
tests/test_practices.py holds the two equal):
    id, part (A principle | B supporting | C a repo's own), principle (B; a part C row names none),
    rule, sources (first wins), applies ("all" | [repo paths, "." the top]),
    held {kind gate|prose|unbuilt|rollup, text (the handed-over words), gate,
          check, via, shows, partial}, subject [seam, behaviour], status
    ("live" | "superseded-by <id>" | "retired <date, why>"), own_ids (C),
    cells {location: {state justified|unjustified, why}} (recorded by hand or
          by an agent's `practices:` line, A3; never by this code).
`blocked`: [{id, conflict "C<n>", why}], rows left out because the decision
they hang on is Jacob's and not made (PRACTICES-rows.md "Conflicts").

A cell is one of four (A2, Jacob 2026-10-12): `held` (a check ran here and
passed), `justified` (a recorded explanation), `unjustified` (a check failed
here, or a recorded `unjustified`), `unknown` (nothing earned an answer; A6:
never a guess). The ratchet counts unjustified + unknown cells of the live
supporting and own rows; a principle's cell is a rollup of its supporting rows
and is not counted twice. An `unbuilt` row's cells count red whatever is
recorded (A2: "red and unbuilt").

What this cannot see, said here so nothing reads stronger than it is:
  - a gate that is not one of this tool's checks (a hook, the harness's audit, another
    repo's dev.sh, setup): its cells are `unknown` unless recorded; a shared
    hook (tools/hooks/source/hooks/) is read through `hooks-installed`, which
    proves the hook runs in that repo, not that it refuses a fault;
  - `memory:` sources: they live in the user's home, outside the workspace,
    and are counted as not resolved, never as resolved.
"""
import json
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from checkslib import decl, runner

TOOL_ROOT = Path(__file__).resolve().parent.parent
REGISTRY = TOOL_ROOT / "gates.json"
BASELINE = TOOL_ROOT / "practices-baseline.json"
ID = re.compile(r"^[a-z0-9][A-Za-z0-9-]*$")
PARTS = ("A", "B", "C")
HELD = ("gate", "prose", "unbuilt", "rollup")
STATES = ("held", "justified", "unjustified", "unknown")
RECORDED = ("justified", "unjustified")
RED = ("unjustified", "unknown")
SUBJECTS = ("seam", "behaviour")
STATUS = re.compile(r"^(live|superseded-by [a-z0-9][A-Za-z0-9-]*|retired \S.*)$")
CONFLICT = re.compile(r"^C[0-9]+$")
ROW_KEYS = ("id", "part", "principle", "rule", "sources", "applies", "held", "subject", "status", "own_ids", "cells")
HELD_KEYS = ("kind", "text", "gate", "check", "via", "shows", "partial")
BLOCK_KEYS = ("_comment", "keys", "rows", "blocked")
CHECK_GATE = re.compile(r"^tools/checks/source/([a-z0-9][a-z0-9-]*)\.py$")
HOOK_GATE = re.compile(r"^tools/hooks/source/hooks/[A-Za-z0-9_.-]+$")
HOOKS_VIA = "hooks-installed"
LAG = ("lag",)                      # todo-store, a held check, is roles:lag


# ---------------------------------------------------------------- reading

def load(path=REGISTRY):
    """(block, findings). The `practices` block of a gates.json, or None with
    the reason: an unreadable registry is a finding, never an empty one."""
    try:
        doc = json.loads(Path(path).read_text())
    except (OSError, ValueError) as e:
        return None, [f"{Path(path).name}: unreadable ({e.__class__.__name__}: {str(e)[:120]})"]
    block = doc.get("practices") if isinstance(doc, dict) else None
    if not isinstance(block, dict):
        return None, [f"{Path(path).name}: no `practices` block"]
    return block, []


def live(rows):
    return [r for r in rows if isinstance(r, dict) and r.get("status") == "live"]


# ---------------------------------------------------------------- validating

def _plan_ok(ws, f, sec):
    p = ws / f
    if not p.is_file():
        return False
    return re.search(rf"^##\s+§?{re.escape(sec)}[.\s]", p.read_text(errors="replace"), re.M) is not None


def _heading_ok(ws, f, text):
    p = ws / f
    if not p.is_file():
        return False
    body = p.read_text(errors="replace")
    if f.endswith("CLAUDE.md") or f.endswith("shared-rules.md"):
        return re.search(r"^#+ " + re.escape(text), body, re.M) is not None
    return text in body


def _gate_ids(ws, repo, cache):
    if repo not in cache:
        try:
            doc = json.loads((ws / repo / "gates.json").read_text())
            cache[repo] = {r.get("id") for r in doc.get("rules", []) if isinstance(r, dict)}
        except (OSError, ValueError, AttributeError):
            cache[repo] = set()
    return cache[repo]


def resolve(src, ws, cache):
    """True, False, or None (a `memory:` source: outside the workspace, not read)."""
    s = src.replace("**(wins)**", "").strip().strip("`").strip()
    m = re.match(r"^(PLAN-[\w-]+\.md) §(\d+)", s)
    if m:
        return _plan_ok(ws, m.group(1), m.group(2))
    m = re.match(r'^([\w./-]+\.md) "([^"]+)"', s)
    if m:
        return _heading_ok(ws, m.group(1), m.group(2))
    if s.startswith("memory:"):
        return None
    m = re.match(r"^gates:([\w./-]+)#([a-z0-9-]+)$", s)
    if m:
        return m.group(2) in _gate_ids(ws, m.group(1), cache)
    if re.match(r"^[\w./-]+$", s):
        return (ws / s).exists()
    return False


def validate(block, ws=None, source=runner.DEFAULT_SOURCE):
    """(findings, notes). Shape everywhere; paths, check names and sources
    against the workspace top when there is one (notes say what went unread)."""
    out, notes = [], []
    bad = lambda rid, msg: out.append(f"practice '{rid}': {msg}")  # noqa: E731
    extra = sorted(set(block) - set(BLOCK_KEYS))
    if extra:
        out.append(f"practices: unknown key(s) {', '.join(extra)}")
    keys = block.get("keys")
    if not isinstance(keys, dict) or set(keys) != set(ROW_KEYS):
        out.append(f"practices: `keys` must name exactly the row keys ({', '.join(ROW_KEYS)})")
    rows, blocked = block.get("rows"), block.get("blocked", [])
    if not isinstance(rows, list) or not rows:
        return out + ["practices: no `rows` list"], notes
    if not isinstance(blocked, list):
        out.append("practices: `blocked` is a list")
        blocked = []
    checks = {e.name for e in decl.load(source)[0]}
    ids = [r.get("id") for r in rows if isinstance(r, dict)]
    dup = sorted({i for i in ids if isinstance(i, str) and ids.count(i) > 1})
    if dup:
        out.append(f"practices: id(s) used more than once: {', '.join(dup)}")
    principles = {r.get("id") for r in rows if isinstance(r, dict) and r.get("part") == "A"}
    blocked_ids = set()
    for i, b in enumerate(blocked):
        bid = b.get("id") if isinstance(b, dict) else None
        if not isinstance(bid, str) or not ID.match(bid):
            out.append(f"practices: blocked #{i}: `id` missing")
            continue
        if bid in blocked_ids:
            out.append(f"practices: blocked '{bid}' listed twice")
        blocked_ids.add(bid)
        if not CONFLICT.match(str(b.get("conflict", ""))):
            out.append(f"practices: blocked '{bid}': `conflict` is C<n>, the question in PRACTICES-rows.md")
        if not isinstance(b.get("why"), str) or not b["why"].strip():
            out.append(f"practices: blocked '{bid}': no `why`")
        if bid in ids:
            out.append(f"practices: '{bid}' is both a row and blocked")
    cache, unresolved_mem, srcs = {}, 0, 0
    for i, r in enumerate(rows):
        if not isinstance(r, dict):
            out.append(f"practices: row #{i} is not an object")
            continue
        rid = r.get("id") if isinstance(r.get("id"), str) else f"#{i}"
        unknown = sorted(set(r) - set(ROW_KEYS))
        if unknown:
            bad(rid, f"unknown key(s) {', '.join(unknown)}")
        if not ID.match(r.get("id") or ""):
            bad(rid, "`id` missing or not letters, digits and dashes (starting lowercase)")
        if not isinstance(r.get("rule"), str) or not r["rule"].strip():
            bad(rid, "`rule` missing")
        sources = r.get("sources")
        if not isinstance(sources, list) or not sources or not all(isinstance(s, str) and s for s in sources):
            bad(rid, "`sources` is a non-empty list (first wins)")
            sources = []
        status = r.get("status")
        if not isinstance(status, str) or not STATUS.match(status):
            bad(rid, "`status` is live, superseded-by <id> or retired <date, why>")
        elif status.startswith("superseded-by "):
            to = status.split(" ", 1)[1]
            if to in blocked_ids:
                bad(rid, f"superseded by '{to}', which is blocked: block this row too")
            elif to not in ids:
                bad(rid, f"superseded by '{to}', which is no row")
        if ws is not None:
            for s in sources:
                srcs += 1
                ok = resolve(s, ws, cache)
                if ok is None:
                    unresolved_mem += 1
                elif not ok:
                    bad(rid, f"source does not resolve: {s[:100]}")
        if status != "live":
            for k in ("held", "applies", "cells"):
                if k in r:
                    bad(rid, f"`{k}` on a row that is not live")
            continue
        part = r.get("part")
        if part not in PARTS:
            bad(rid, "`part` is A, B or C")
        if part == "A":
            if "principle" in r:
                bad(rid, "a principle (part A) names no principle")
        elif part == "B" or "principle" in r:     # a part C row restates no workspace rule: no principle
            p = r.get("principle")
            if p in blocked_ids:
                bad(rid, f"its principle '{p}' is blocked: block this row too")
            elif p not in principles:
                bad(rid, f"`principle` '{p}' is no part A row (a rootless row)")
        if part == "C" and not (isinstance(r.get("own_ids"), list) and r["own_ids"]):
            bad(rid, "a part C row lists its repo's own row ids (`own_ids`)")
        if part != "C" and "own_ids" in r:
            bad(rid, "`own_ids` is for part C rows")
        ap = r.get("applies")
        if not (ap == "all" or (isinstance(ap, list) and ap and all(isinstance(x, str) and x for x in ap))):
            bad(rid, "`applies` is \"all\" or a list of repo paths")
        sub = r.get("subject")
        if sub is not None and not (isinstance(sub, list) and sub and all(x in SUBJECTS for x in sub)):
            bad(rid, f"`subject` is a list of {', '.join(SUBJECTS)}")
        h = r.get("held")
        if not isinstance(h, dict):
            bad(rid, "`held` missing")
            continue
        hx = sorted(set(h) - set(HELD_KEYS))
        if hx:
            bad(rid, f"`held` has unknown key(s) {', '.join(hx)}")
        kind = h.get("kind")
        if kind not in HELD:
            bad(rid, f"`held.kind` is one of {', '.join(HELD)}")
        if (kind == "rollup") != (part == "A"):
            bad(rid, "a principle's held is `rollup`, and only a principle's")
        if not isinstance(h.get("text"), str) or not h["text"].strip():
            bad(rid, "`held.text` missing (the words the row was handed over with)")
        if kind == "gate":
            g = h.get("gate")
            if not isinstance(g, str) or not g:
                bad(rid, "a gate row names its `gate`")
            else:
                m = CHECK_GATE.match(g)
                if m and h.get("check") != m.group(1):
                    bad(rid, f"gate {g} is check '{m.group(1)}': `check` must say so")
                if not m and "check" in h:
                    bad(rid, "`check` is for a gate in tools/checks/source/")
                if HOOK_GATE.match(g) and h.get("via") != HOOKS_VIA:
                    bad(rid, f"a shared hook gate is read through `via: {HOOKS_VIA}`")
                if ws is not None and not (ws / g).exists():
                    bad(rid, f"gate {g} does not exist")
            for k in ("check", "via"):
                if k in h and h[k] not in checks:
                    bad(rid, f"`{k}` '{h[k]}' is no check (checks list)")
        else:
            for k in ("gate", "check", "via", "partial"):
                if k in h:
                    bad(rid, f"`held.{k}` on a {kind} row")
        if "shows" in h and kind != "prose":
            bad(rid, "`held.shows` is a prose row's")
        if "partial" in h and h["partial"] is not True:
            bad(rid, "`held.partial` is true or absent")
        cells = r.get("cells")
        if cells is not None:
            if not isinstance(cells, dict):
                bad(rid, "`cells` is {location: {state, why}}")
                continue
            if kind == "rollup":
                bad(rid, "a principle's cells are derived, never recorded")
            for loc, c in cells.items():
                if isinstance(ap, list) and loc not in ap:
                    bad(rid, f"cell '{loc}' is outside `applies`")
                if not isinstance(c, dict) or c.get("state") not in RECORDED \
                        or not isinstance(c.get("why"), str) or not c["why"].strip():
                    bad(rid, f"cell '{loc}': a recorded cell is {{state: justified|unjustified, why}}"
                             " (a bare `held` reads as unjustified, A3)")
    if ws is None:
        notes.append("no workspace top: gate paths and sources not resolved")
    else:
        notes.append(f"{srcs} source(s) read, {unresolved_mem} `memory:` source(s) not resolved (outside the workspace)")
    return out, notes


# ---------------------------------------------------------------- importing

def _cells(line):
    parts = re.split(r"(?<!\\)\|", line)[1:-1]
    return [p.strip().replace("\\|", "|") for p in parts]


def _sources(text):
    out = []
    for s in text.split("; "):
        s = s.replace("**(wins)**", "").strip().strip("`").strip()
        if s:
            out.append(s)
    return out


def _held(text):
    t = text.strip()
    if t.startswith("rollup"):
        return {"kind": "rollup", "text": t}
    if t.startswith("gate "):
        m = re.match(r"^gate ([\w./-]+)(.*)$", t)
        if not m:
            raise ValueError(f"held names no gate path: {t[:80]}")
        h = {"kind": "gate", "text": t, "gate": m.group(1)}
        c = CHECK_GATE.match(m.group(1))
        if c:
            h["check"] = c.group(1)
        if HOOK_GATE.match(m.group(1)):
            h["via"] = HOOKS_VIA
        if re.search(r"\b(unbuilt|prose)\b", m.group(2)):
            h["partial"] = True
        return h
    if t.startswith("prose"):
        h = {"kind": "prose", "text": t}
        if t.startswith("prose: "):
            h["shows"] = t[len("prose: "):]
        return h
    if t.startswith("unbuilt"):
        return {"kind": "unbuilt", "text": t}
    raise ValueError(f"held is not gate|prose|unbuilt|rollup: {t[:80]}")


def parse_md(text):
    """Every row of a PRACTICES-rows.md, in file order, as registry rows; raises
    ValueError on a row it cannot read (never a half-read row)."""
    rows, sec, principle, said = [], "", None, {}
    for n, line in enumerate(text.splitlines(), 1):
        if line.startswith("## "):
            sec, principle = line, None
        m = re.match(r"^Counts: (\d+) principles,.* (\d+) Part C rows", line)
        if m:
            said["A"], said["C"] = int(m.group(1)), int(m.group(2))
        m = re.match(r"^### Serving `([^`]+)` \((\d+) rows?\)", line)
        if m:
            principle = m.group(1)
            said[principle] = int(m.group(2))
        m = re.match(r"^\| `([^`]+)` \|", line)
        if not m:
            continue
        rid = m.group(1)
        if not ID.match(rid):
            raise ValueError(f"line {n}: row id '{rid}' is not letters, digits and dashes")
        c = _cells(line)
        try:
            if sec.startswith("## Superseded"):
                _, rule, src, status = c[:4]
                rows.append({"id": rid, "rule": rule, "sources": _sources(src), "status": status})
                continue
            if sec.startswith("## Part A"):
                _, rule, src, ap, held, status = c[:6]
                r = {"id": rid, "part": "A", "rule": rule, "sources": _sources(src)}
                sub, own = "-", None
            elif sec.startswith("## Part B"):
                _, rule, src, ap, held, sub, status = c[:7]
                r = {"id": rid, "part": "B", "principle": principle, "rule": rule, "sources": _sources(src)}
                own = None
            elif sec.startswith("## Part C"):
                _, rule, src, ap, held, status, own = c[:7]
                r = {"id": rid, "part": "C", "rule": rule, "sources": _sources(src)}   # the file names no principle
                sub = "-"
            else:
                continue
        except ValueError:
            raise ValueError(f"line {n}: row '{rid}' has too few columns")
        r["applies"] = "all" if ap.strip() == "all" else [x.strip() for x in ap.split(",") if x.strip()]
        try:
            r["held"] = _held(held)
        except ValueError as e:
            raise ValueError(f"line {n}: row '{rid}': {e}")
        if sub.strip() not in ("-", ""):
            r["subject"] = [x.strip() for x in sub.split(",")]
        r["status"] = status.strip()
        if own:
            r["own_ids"] = [x.strip() for x in own.split(",") if x.strip()]
        rows.append(r)
    # The file states its own counts: a row the reader missed is a mismatch, never a silent drop.
    got = {}
    for r in rows:
        k = r.get("principle") if r.get("part") == "B" else r.get("part")
        if k:
            got[k] = got.get(k, 0) + 1
    for k, n in sorted(said.items()):
        if got.get(k, 0) != n:
            raise ValueError(f"the file says {n} row(s) for {k}, and {got.get(k, 0)} were read")
    if not said:
        raise ValueError("no counts line and no `### Serving` headings: not a PRACTICES-rows.md")
    return rows


MARK = ',\n  "practices": '


def dump_block(block):
    """The block as gates.json carries it: one row per line, so a diff names the row."""
    j = lambda v: json.dumps(v, ensure_ascii=False)  # noqa: E731
    head = [f'   {j(k)}: {j(block[k])}' for k in BLOCK_KEYS if k in block and k not in ("rows", "blocked")]
    lists = []
    for k in ("rows", "blocked"):
        if k in block:
            items = ",\n".join(f"    {j(x)}" for x in block[k])
            lists.append(f'   {j(k)}: [\n{items}\n   ]')
    return "{\n" + ",\n".join(head + lists) + "\n  }"


def splice(text, block):
    """(new text, None) with the `practices` block, the file's last key, replaced
    and every other byte kept (the `rules` stay as their authors laid them out);
    (None, why) when the file is not laid out that way or the result differs
    from the intent."""
    old = json.loads(text)
    at = text.rfind(MARK)
    if at < 0 or list(old)[-1] != "practices":
        return None, "gates.json does not end with its `practices` block (a line `  \"practices\": {`)"
    new = text[:at] + MARK + dump_block(block) + "\n}\n"
    try:
        doc = json.loads(new)
    except ValueError as e:
        return None, f"the spliced gates.json does not parse ({e})"
    if doc.get("practices") != block or {k: v for k, v in doc.items() if k != "practices"} != \
            {k: v for k, v in old.items() if k != "practices"}:
        return None, "the spliced gates.json changes more than the practices block"
    return new, None


def import_md(md_path, registry=REGISTRY):
    """Replace the registry's practice rows with the file's, leaving out the
    rows `blocked` names and keeping every recorded cell. Returns (summary,
    problems); writes nothing when there is a problem."""
    doc = json.loads(Path(registry).read_text())
    block = doc.get("practices")
    if not isinstance(block, dict):
        return None, ["the registry has no `practices` block to import into (its keys and `blocked` list)"]
    try:
        parsed = parse_md(Path(md_path).read_text())
    except (OSError, ValueError) as e:
        return None, [f"{md_path}: {e}"]
    blocked = {b["id"] for b in block.get("blocked", []) if isinstance(b, dict) and "id" in b}
    seen = {r["id"] for r in parsed}
    problems = [f"blocked '{b}' is no row in {Path(md_path).name}" for b in sorted(blocked - seen)]
    old_cells = {r["id"]: r["cells"] for r in block.get("rows", []) if isinstance(r, dict) and r.get("cells")}
    rows = []
    for r in parsed:
        if r["id"] in blocked:
            continue
        if r["id"] in old_cells:
            r["cells"] = old_cells[r["id"]]
        rows.append(r)
    lost = sorted(set(old_cells) - {r["id"] for r in rows})
    problems += [f"row '{i}' carries recorded cells and is no longer imported" for i in lost]
    if problems:
        return None, problems
    block["rows"] = rows
    text, why = splice(Path(registry).read_text(), block)
    if text is None:
        return None, [why]
    Path(registry).write_text(text)
    return {"rows": len(rows), "blocked": len(blocked), "file": str(md_path),
            "live": len(live(rows)), "not_live": len(rows) - len(live(rows))}, []


# ---------------------------------------------------------------- cells

def check_of(row):
    h = row.get("held") or {}
    return h.get("check") or h.get("via") if h.get("kind") == "gate" else None


def where(row, locs):
    return list(locs) if row.get("applies") == "all" else list(row.get("applies") or [])


def _cell(row, loc, locs, results, over=None):
    """`over`: a cell the ledger built from a justification record (justified,
    or unjustified and `stale`), used where a recorded cell would be, and over it."""
    h = row.get("held") or {}
    kind = h.get("kind")
    rec = over or (row.get("cells") or {}).get(loc)
    decided = False
    if kind == "gate":
        name = check_of(row)
        if loc not in locs:
            state, why = "unknown", f"{loc} is not a location `checks all` walks: nothing ran there"
        elif not name:
            state, why = "unknown", f"held by {h.get('gate')}, which its owner runs, not checks practices"
        else:
            r = (results.get(loc) or {}).get(name)
            st = r.get("status") if r else None
            first = (r.get("lines") or [""])[0] if r else ""
            more = f" (+{len(r['lines']) - 1} more)" if r and len(r.get("lines") or []) > 1 else ""
            if st == "ok" and h.get("partial"):
                state, why = "unknown", f"{name} ok here, but the row is only partly held by it: {h.get('text')}"
            elif st == "ok":
                state, why, decided = "held", f"{name} ok" + (f": {first}" if first else ""), True
            elif st == "fail":
                state, why, decided = "unjustified", f"{name} FAIL: {first}{more}", True
            elif st in ("unchecked", "error"):
                state, why = "unknown", f"{name} {st.upper()}: {first}"
            elif st == "not-run":
                state, why = "unknown", f"{name} does not run here: {first}"
            else:
                state, why = "unknown", f"{name} has no result here"
    elif kind == "prose":
        shows = h.get("shows")
        state, why = "unknown", "prose: no explanation recorded" + (f" (it must show: {shows})" if shows else "")
    else:
        state, why = "unknown", f"unbuilt: {h.get('text')}"
    cell = {"state": state, "why": why}
    if kind == "unbuilt":
        cell["unbuilt"] = True
    if rec:
        if decided or kind == "unbuilt":
            cell["note"] = f"recorded {rec['state']} not used: " + ("the check decided" if decided else "the row is unbuilt")
        else:
            cell = dict(over, recorded=True) if over else {"state": rec["state"], "why": rec["why"], "recorded": True}
    return cell


def cells(rows, locs, results, overrides=None):
    """{row id: {location: cell}} for every live row, principles rolled up from
    their supporting rows. `results`: {location: {check: {status, lines}}}.
    `overrides`: {(row id, location): cell} from the ledger's justification
    records (checkslib/ledger.py), taking a recorded cell's place."""
    out = {}
    overrides = overrides or {}
    rows = live(rows)
    for r in rows:
        if r.get("part") != "A":
            out[r["id"]] = {loc: _cell(r, loc, locs, results, overrides.get((r["id"], loc)))
                            for loc in where(r, locs)}
    for p in rows:
        if p.get("part") != "A":
            continue
        out[p["id"]] = {}
        sup = [r for r in rows if r.get("principle") == p["id"]]
        for loc in where(p, locs):
            here = [(r["id"], out[r["id"]][loc]) for r in sup if loc in out[r["id"]]]
            bad = [i for i, c in here if c["state"] == "unjustified"]
            unk = [i for i, c in here if c["state"] == "unknown"]
            if not here:
                c = {"state": "unknown", "why": "no supporting row applies here"}
            elif bad:
                c = {"state": "unjustified", "why": f"{len(bad)} of {len(here)} supporting rows unjustified: {', '.join(bad)}"}
            elif unk:
                c = {"state": "unknown", "why": f"{len(unk)} of {len(here)} supporting rows unknown"}
            else:
                c = {"state": "held", "why": f"all {len(here)} supporting rows hold"}
            c["derived"] = True
            out[p["id"]][loc] = c
    return out


def red(rows, table):
    """The ratchet's count: unjustified + unknown cells of live non-principle rows."""
    return sum(1 for r in live(rows) if r.get("part") != "A"
               for c in table.get(r["id"], {}).values() if c["state"] in RED)


def counts(table_row):
    c = {s: 0 for s in STATES}
    for cell in table_row.values():
        c[cell["state"]] += 1
    return c


# ---------------------------------------------------------------- results

def from_report(report):
    """(locations, results) from a saved `checks all --json` report."""
    locs, results = [], {}
    for repo in report.get("repos", []):
        loc = repo.get("rel")
        if not loc:
            continue
        locs.append(loc)
        results[loc] = {r["check"]: r for r in repo.get("results", []) if isinstance(r, dict) and "check" in r}
    return locs, results


def run_live(rows, ws, source=runner.DEFAULT_SOURCE, names=None, workers=8):
    """(locations, results): every location `checks all` walks, and there the
    checks the live rows name, each where its applies_to (roles:lag included)
    selects it; a named check that does not apply there is `not-run`, said."""
    ws = Path(ws).resolve()
    entries = {e.name: e for e in decl.load(source)[0]}
    repos = runner.discover(ws)
    locs = [runner.rel(r, ws) for r in repos]

    def one(repo):
        return runner.rel(repo, ws), run_location(rows, repo, ws, locs, source, names, entries)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = dict(pool.map(one, repos))
    return locs, results


def run_location(rows, repo, ws, locs, source=runner.DEFAULT_SOURCE, names=None, entries=None):
    """{check: result} at one location: the checks the live rows name there,
    each where its applies_to (roles:lag included) selects it; a named check
    that does not apply there is `not-run`, said. run_live's per-location step,
    and the ledger's (checkslib/ledger.py), so both read one location alike."""
    if entries is None:
        entries = {e.name: e for e in decl.load(source)[0]}
    loc = runner.rel(repo, ws)
    wanted = {check_of(r) for r in live(rows) if check_of(r) and loc in where(r, locs)}
    runs, skip = [], {}
    for n in sorted(wanted):
        e = entries.get(n)
        if e is None:
            skip[n] = {"check": n, "status": "error", "lines": ["no such check in the source"]}
        elif runner.applies(e, repo, ws, LAG):
            runs.append(n)
        else:
            skip[n] = {"check": n, "status": "not-run", "lines": [f"applies_to={e.applies_to}"]}
    got = runner.run_repo(repo, source, ws, names, LAG, runs)["results"] if runs else []
    return dict(skip, **{r["check"]: r for r in got})


# ---------------------------------------------------------------- ratchet

def read_baseline(path=BASELINE):
    """The baseline count, or None with why."""
    try:
        n = json.loads(Path(path).read_text()).get("red")
    except (OSError, ValueError, AttributeError) as e:
        return None, f"{Path(path).name}: unreadable ({e.__class__.__name__})"
    if not isinstance(n, int) or isinstance(n, bool) or n < 0:
        return None, f"{Path(path).name}: `red` is not a count"
    return n, None


def lower_baseline(n, path=BASELINE, how=""):
    """Write n as the baseline only if it is lower than the one there (or none
    is there). Returns (written, why)."""
    old, _ = read_baseline(path)
    if old is not None and n > old:
        return False, f"refused: {n} red cell(s) is above the baseline {old}; the count only falls"
    if old is not None and n == old:
        return False, f"unchanged: {n} is the baseline already"
    Path(path).write_text(json.dumps({
        "_comment": "The practices ratchet (PLAN-services.md §3 A2): the count of red cells (unjustified + "
                    "unknown, principles aside) that `checks practices` may report. It only falls: "
                    "`checks practices --lower` rewrites it, and refuses a higher count.",
        "red": n, "measured": how}, indent=1) + "\n")
    return True, f"baseline {old if old is not None else 'none'} -> {n}"
