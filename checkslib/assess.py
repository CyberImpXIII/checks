"""`checks assess <path> --subject repo|candidate` (PLAN-services.md §3 X1-X2,
§4 step 9.2): one assessor, one registry, for our own repos and for an outside
tool the bench holds. It prints the four-state cell (checkslib/practices.py's
STATES: held, justified, unjustified, unknown) of every live practice row that
applies to the subject, the `seam` rows and the `behaviour` rows apart.

  repo       the rows whose `applies` takes the repo's location; each cell is
             earned exactly as `checks practices` earns it there (the checks
             the rows name run on that repo now, practices.run_location and
             practices.cells: one reading, so the two cannot disagree). Rows
             with no `subject` are listed too, as `other`. A gap: a red cell
             (unjustified or unknown, A2).
  candidate  the rows that carry a `subject` (X1); `applies` is about our
             repos and is not read. Each cell comes from the evidence the
             bench wrote (assess.json in the candidate's folder, or
             --evidence; schema/assess.schema.json, read by checkslib/contract.py):
             a probe entry decides (exit 0 held, else unjustified; a row whose
             entries name verbs needs one for every verb candidate.json
             declares, or it is unjustified); a record (justified|unjustified,
             why) is used only where no probe decided; nothing is unknown.
             No assess.json is every cell unknown, never an error. A gap
             (X1, X3): a `seam` row that is not held; a `behaviour` row that is
             neither held nor justified (a row with both subjects meets the
             seam bar).

Principles (part A) are rolled up from the supporting rows listed here
(practices.rollup), shown apart, and never counted as gaps: the gaps, like
the ratchet, are the supporting and own rows.

What this cannot see, said so nothing reads stronger than it is:
  - a candidate's probes are not run here: their recorded exits are the
    bench's run, bound to the pin, and a probe that passes while testing
    nothing reads `held`;
  - a probe path is checked to be a file inside the folder, through symlinks;
  - a repo cell held by a gate this tool does not run (a hook beyond
    hooks-installed, another repo's dev.sh) is `unknown` unless recorded,
    as in `checks practices`; the ledger's justifications are not read
    (neither does `checks practices`)."""
import json
from pathlib import Path

from checkslib import contract, practices, runner

SUBJECTS = ("repo", "candidate")
GROUPS = ("seam", "behaviour", "other", "principles")


def _group(row):
    if row.get("part") == "A":
        return ["principles"]
    sub = row.get("subject") or []
    return [g for g in practices.SUBJECTS if g in sub] or ["other"]


def gap(row, cell, subject):
    """True when the cell falls short of the bar its row meets for this subject."""
    if row.get("part") == "A":
        return False
    if subject == "repo":
        return cell["state"] in practices.RED
    if "seam" in (row.get("subject") or []):
        return cell["state"] != "held"
    return cell["state"] not in ("held", "justified")


def _report(subject, rows, cells, head, notes):
    """The one shape both subjects print: rows in registry order, each with its cell."""
    out, groups = [], {g: [] for g in GROUPS}
    for r in rows:
        c = cells[r["id"]]
        item = dict(practices.shown(r), subject=r.get("subject") or [], cell=c, gap=gap(r, c, subject))
        out.append(item)
        for g in _group(r):
            groups[g].append(r["id"])
    if subject == "candidate":
        groups.pop("other")
    counted = [i for i in out if i.get("part") != "A"]
    counts = {s: sum(1 for i in counted if i["cell"]["state"] == s) for s in practices.STATES}
    return dict(head, subject=subject, rows=out, groups=groups, counts=counts,
                gaps=[i["id"] for i in out if i["gap"]], notes=notes)


# ---------------------------------------------------------------- repo

def assess_repo(rows, repo, ws, source=runner.DEFAULT_SOURCE, names=None):
    """(report, None) or (None, why). `rows`: a validated registry's rows."""
    repo = Path(repo).resolve()
    loc = runner.rel(repo, ws)
    if loc is None:
        return None, f"{repo} is not under the workspace top {ws}"
    walked = [runner.rel(r, ws) for r in runner.discover(ws)]
    if loc not in walked:
        return None, f"{loc} is not a location `checks all` walks (a git repo with a CLAUDE.md, or the top)"
    results = {loc: practices.run_location(rows, repo, ws, [loc], source, names)}
    table = practices.cells(rows, [loc], results)
    here = [r for r in practices.live(rows) if loc in table.get(r["id"], {})]
    cells = {r["id"]: table[r["id"]][loc] for r in here}
    return _report("repo", here, cells, {"path": str(repo), "location": loc},
                   [f"cells earned as `checks practices` earns them at {loc}: its checks ran now"]), None


# ---------------------------------------------------------------- candidate

def _probe_cell(entries, verbs):
    failed = [e for e in entries if e["exit"] != 0]
    named = sorted({e["verb"] for e in entries if "verb" in e})
    missing = [v for v in (verbs or []) if v not in named] if named else []
    first = lambda e: (e["lines"] or [""])[0][:160]  # noqa: E731
    if failed:
        e = failed[0]
        more = f" (+{len(failed) - 1} more failed)" if len(failed) > 1 else ""
        return {"state": "unjustified", "why": f"probe {e['probe']}" + (f" [{e['verb']}]" if "verb" in e else "")
                + f" exit {e['exit']}: {first(e)}{more}"}
    if missing:
        return {"state": "unjustified", "why": f"no probe for declared verb(s) {', '.join(missing)} "
                f"(probed: {', '.join(named)})"}
    e = entries[0]
    return {"state": "held", "why": f"{len(entries)} probe run(s) exit 0" + (f", verbs {', '.join(named)}" if named else "")
            + f"; {e['probe']}: {first(e)}"}


def read_evidence(folder, evidence=None):
    """(doc, path, findings): the evidence and where it was read; doc None and
    no findings when there is none; doc None with findings when it is unusable."""
    path = Path(evidence) if evidence else Path(folder) / contract.ASSESS
    if not path.is_file():
        if evidence:
            return None, path, [f"--evidence {evidence}: no such file"]
        return None, path, []
    try:
        doc = json.loads(path.read_text())
    except ValueError as e:
        return None, path, [f"{path.name}: does not parse ({e})"]
    doc, found = contract.validate(doc, contract.ASSESS, folder)
    return (None if found else doc), path, found


def assess_candidate(rows, folder, evidence=None):
    """(report, None) or (None, why with every finding)."""
    folder = Path(folder).resolve()
    manifest, why = contract.candidate_manifest(folder)
    if manifest is None:
        return None, f"{why}: not a candidate's folder (the bench's candidates/<c>/)"
    pin, verbs = contract.candidate_pin(manifest), contract.candidate_verbs(manifest)
    doc, path, found = read_evidence(folder, evidence)
    rows = practices.live(rows)
    subject_rows = [r for r in rows if r.get("subject") and r.get("part") != "A"]
    ids = {r["id"] for r in subject_rows}
    if doc is not None:
        found += [f"{path.name}: row `{e['row']}` is no live practice row with a subject"
                  for e in doc["probes"] + doc["records"] if e["row"] not in ids]
    if found:
        return None, "the evidence is unusable, so no cell is read from it:\n  " + "\n  ".join(found)
    cells, notes = {}, []
    probes = doc["probes"] if doc else []
    records = {r["row"]: r for r in doc["records"]} if doc else {}
    for r in subject_rows:
        mine = [e for e in probes if e["row"] == r["id"]]
        rec = records.get(r["id"])
        if mine:
            c = _probe_cell(mine, verbs)
            if rec:
                c["note"] = f"recorded {rec['state']} not used: the probe decided"
        elif rec:
            c = {"state": rec["state"], "why": rec["why"], "recorded": True}
        else:
            c = {"state": "unknown", "why": "no probe output and no recorded explanation"}
        cells[r["id"]] = c
    principles = []
    for p in rows:
        if p.get("part") != "A":
            continue
        here = [(r["id"], cells[r["id"]]) for r in subject_rows if r.get("principle") == p["id"]]
        if here:
            cells[p["id"]] = practices.rollup(here)
            principles.append(p)
    order = {r["id"]: i for i, r in enumerate(rows)}
    shown = sorted(subject_rows + principles, key=lambda r: order[r["id"]])
    if doc is None:
        notes.append(f"no evidence at {path}: every cell unknown (the bench's `./dev.sh assess` writes it)")
    else:
        notes.append(f"evidence {path}: {len(probes)} probe entr(ies), {len(records)} record(s), pin {pin[:16]}")
    head = {"path": str(folder), "candidate": {"name": manifest.get("name"), "pin": pin, "verbs": verbs},
            "evidence": str(path) if doc is not None else None}
    return _report("candidate", shown, cells, head, notes), None
