"""Every tool's registration (PLAN-architecture.md §6 "Every tool registered", §9
step 10.1): the one reading behind `registered` (the check) and `checks tools`
(the collected list), so the two cannot disagree. A repo registers in its own
services.json (one source per fact); the workspace list is collected from those
entries, never written by hand.

An entry: {present (a services.json file exists), name, description, stores,
shapes, services, status, findings, unchecked}; name and the rest are None when
there is no valid services.json. Its findings, every one found:
  - no services.json: the repo is not registered;
  - services.json breaks its contract (schema/services.schema.json and its
    x-rules, checkslib/contract.py: a blank or multi-line description, a
    `stores` entry cli.json does not declare, ...): each finding as given;
  - no `description`: the one line that registers the tool;
  - a store cli.json declares that `stores` does not list (the other
    direction of contract's `stores-declared`: the two lists are one fact
    written twice, so they are held equal both ways).
When cli.json cannot be read (it does not parse, or its `store` is misshapen)
and nothing else is found, the entry is unchecked: whether `stores` lists every
store is unread, never passed.
Not judged here: that a `shapes` id exists in data-bridge (its schemas live in
data-bridge's SQLite store, behind its CLI); that the description is true."""
from pathlib import Path

from checkslib import contract

PLAN = "PLAN-architecture.md §6 \"Every tool registered\""


def entry(repo):
    repo = Path(repo)
    out = {"present": (repo / contract.SERVICES).is_file(), "name": None, "description": None, "stores": None,
           "shapes": None, "services": [], "findings": [], "unchecked": None}
    doc, found = contract.read(repo, contract.SERVICES)
    if doc is None:
        out["findings"] = found or [f"no {contract.SERVICES}: this repo is not registered ({PLAN})"]
        return _status(out)
    out.update(name=doc["name"], description=doc.get("description"), stores=doc.get("stores"),
               shapes=doc.get("shapes"),
               services=[{"service": s["service"], "run": s["run"], "verbs": s["verbs"]} for s in doc["services"]])
    findings = list(found)
    if "description" not in doc:
        findings.append(f"{contract.SERVICES}: no `description`: the one line that registers this tool ({PLAN})")
    have, why = contract.cli_stores(repo)
    if have is None:
        if not findings:
            out["unchecked"] = (f"{why}: whether `stores` lists every store it declares is unread "
                                f"(accessor says how)")
    else:
        listed = {contract.norm(s) for s in doc.get("stores") or []}
        findings += [f"{contract.SERVICES}: `stores` lacks `{s}`, a store {contract.CLI} declares"
                     for s in have if s not in listed]
    out["findings"] = findings
    return _status(out)


def _status(e):
    e["status"] = "fail" if e["findings"] else ("unchecked" if e["unchecked"] else "ok")
    return e


def line(e):
    """One line of the collected list: `<name>: <description> [stores ...; reads ...; emits ...]`."""
    if e["name"] is None:
        return f"(not registered: {'its ' + contract.SERVICES + ' breaks its contract' if e['present'] else 'no ' + contract.SERVICES})"
    facts = []
    if e["stores"] is not None:
        facts.append(f"stores: {', '.join(e['stores']) or 'none'}")
    for k in ("reads", "emits"):
        if (e["shapes"] or {}).get(k):
            facts.append(f"{k}: {', '.join(e['shapes'][k])}")
    verbs = sorted({v for s in e["services"] for v in s["verbs"]})
    facts.append(f"verbs: {', '.join(verbs)}")
    return f"{e['name']}: {e['description'] or '(no description)'} [{'; '.join(facts)}]"


def counts(entries):
    c = {"locations": len(entries), "registered": 0, "no_description": 0, "no_services_json": 0,
         "unchecked": 0, "findings": sum(len(e["findings"]) for e in entries)}
    for e in entries:
        if not e["present"]:
            c["no_services_json"] += 1
        elif e["name"] is not None and e["description"] is None:
            c["no_description"] += 1
        c["registered"] += e["status"] == "ok"
        c["unchecked"] += e["status"] == "unchecked"
    return c
