"""The contract files a repo carries (PLAN-routing-tree.md §14.8, PLAN-repo-setup.md
§7.10): services.json, cli.json, node.json. One reader for each, used by every
check that needs it: `read` parses the file, validates it against its schema
(schema/<stem>.schema.json, through checkslib/checkjson.py), then applies each
rule the schema's `x-rules` names, implemented here under the same id
(tests/test_contract_files.py holds the two sets equal, per schema).

Findings are `<file>: <rule>: <where>: <what>`, every one found, never only the
first. A file that is absent is (None, []): what absence means is each check's
call, said in its own explanation."""
import fnmatch
import json
import os
from pathlib import Path, PurePosixPath

from checkslib import checkjson, helptext

TOOL_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_DIR = TOOL_ROOT / "schema"
SERVICES, CLI, NODE = "services.json", "cli.json", "node.json"
FILES = (SERVICES, CLI, NODE)
VERIFY = "verify"                   # not a file: what `<cli> verify --json` prints (stores-exported)
SCHEMAS = FILES + (VERIFY,)
GLOB = set("*?[")


def schema_path(name):
    return SCHEMA_DIR / f"{Path(name).stem}.schema.json"


def norm(rel):
    """`./x/y` and `x/y` are one path."""
    return PurePosixPath(rel).as_posix()


def inside(rel):
    p = PurePosixPath(rel)
    return not p.is_absolute() and ".." not in p.parts and norm(rel) != "."


def _executable(repo, rel):
    p = Path(repo) / rel
    if not p.is_file():
        return f"`{rel}` does not exist"
    if not os.access(p, os.X_OK):
        return f"`{rel}` is not executable"
    return None


def _verbs(repo, rel, verbs, where):
    """Each verb `<rel> help` does not list, as findings; [] when rel cannot run (another rule says so)."""
    if not inside(rel) or _executable(repo, rel):
        return []
    have, why = helptext.listed(Path(repo) / rel, repo)
    if have is None:
        return [f"{where}: `{rel} help` {why}: no verb can be shown implemented"]
    return [f"{where}: `{rel}` does not implement `{v}` (its help lists: {', '.join(sorted(have))})"
            for v in verbs if v not in have]


def _dupes(items, where, what):
    seen, out = set(), []
    for x in items:
        if x in seen:
            out.append(f"{where}: {what} `{x}` given twice")
        seen.add(x)
    return out


def _stores(doc):
    s = doc["store"]
    return [s] if isinstance(s, str) else list(s)


# --- services.json ----------------------------------------------------------

def _one_check(doc, repo):
    n = sum(1 for s in doc["services"] if s["service"] == "check")
    return [] if n == 1 else [f"$.services: {n} `check` entries (exactly one: the command the check service runs)"]


def _run_inside(doc, repo):
    return [f"$.services[{i}].run: `{s['run']}` is not a path inside the repo"
            for i, s in enumerate(doc["services"]) if not inside(s["run"])]


def _run_executable(doc, repo):
    return [f"$.services[{i}].run: {why}" for i, s in enumerate(doc["services"])
            if inside(s["run"]) for why in [_executable(repo, s["run"])] if why]


def _services_verbs(doc, repo):
    out = []
    for i, s in enumerate(doc["services"]):
        out += _verbs(repo, s["run"], s["verbs"], f"$.services[{i}]")
    return out


def _services_unique(doc, repo):
    out = _dupes([f"{s['service']} {norm(s['run'])}" for s in doc["services"]], "$.services", "entry")
    for i, s in enumerate(doc["services"]):
        out += _dupes(s["verbs"], f"$.services[{i}].verbs", "verb")
    return out + _dupes(doc.get("tags", []), "$.tags", "tag")


def _write_declared(doc, repo):
    p = Path(repo) / CLI
    try:
        cli = json.loads(p.read_text()) if p.is_file() else None
    except ValueError:
        return []                               # accessor reports a broken cli.json
    if not isinstance(cli, dict) or not isinstance(cli.get("cli"), str) or not isinstance(cli.get("verbs"), list):
        return []
    out = []
    for i, s in enumerate(doc["services"]):
        if s["service"] == "write" and norm(s["run"]) == norm(cli["cli"]):
            out += [f"$.services[{i}]: `{v}` is not a verb {CLI} declares for `{cli['cli']}`"
                    for v in s["verbs"] if v not in cli["verbs"]]
    return out


# --- cli.json -----------------------------------------------------------------

def _cli_inside(doc, repo):
    out = [f"$.cli: `{doc['cli']}` is not a path inside the repo"] if not inside(doc["cli"]) else []
    return out + [f"$.store: `{s}` is not a path inside the repo" for s in _stores(doc) if not inside(s)]


def _cli_executable(doc, repo):
    why = _executable(repo, doc["cli"]) if inside(doc["cli"]) else None
    return [f"$.cli: {why}"] if why else []


def _cli_verbs(doc, repo):
    return _verbs(repo, doc["cli"], doc["verbs"], "$.verbs")


def _cli_unique(doc, repo):
    return _dupes([norm(s) for s in _stores(doc)], "$.store", "path") + _dupes(doc["verbs"], "$.verbs", "verb")


# --- node.json ----------------------------------------------------------------

LISTS = ("generated", "record", "children")


def _node_inside(doc, repo):
    out = [f"$.{k}: `{p}` is not a path inside the repo" for k in LISTS for p in doc.get(k, []) if not inside(p)]
    if "registry" in doc and not inside(doc["registry"]):
        out.append(f"$.registry: `{doc['registry']}` is not a path inside the repo")
    return out


def _node_unique(doc, repo):
    out = []
    for k in LISTS:
        out += _dupes([norm(p) for p in doc.get(k, [])], f"$.{k}", "path")
    return out


def _generated_exact(doc, repo):
    return [f"$.generated: `{p}` is a glob; list each generated file" for p in doc["generated"] if GLOB & set(p)]


def under(rel, prefixes):
    rel = norm(rel)
    return any(rel == norm(c) or rel.startswith(norm(c) + "/") for c in prefixes)


def is_record(rel, record):
    return any(fnmatch.fnmatchcase(norm(rel), norm(g)) for g in record)


def _disjoint(doc, repo):
    out = [f"$.generated: `{p}` is also a record file" for p in doc["generated"] if is_record(p, doc["record"])]
    return out + [f"$.generated: `{p}` lies under a child" for p in doc["generated"]
                  if under(p, doc.get("children", []))]


# --- verify --json ------------------------------------------------------------

def _verify_unique(doc, repo):
    return _dupes([i["item"] for i in doc["items"]], "$.items", "item")


RULES = {
    VERIFY: {"unique": _verify_unique},
    SERVICES: {"one-check": _one_check, "run-inside": _run_inside, "run-executable": _run_executable,
               "verb-implemented": _services_verbs, "unique": _services_unique, "write-declared": _write_declared},
    CLI: {"paths-inside": _cli_inside, "cli-executable": _cli_executable, "verb-implemented": _cli_verbs,
          "unique": _cli_unique},
    NODE: {"paths-inside": _node_inside, "unique": _node_unique, "generated-exact": _generated_exact,
           "disjoint": _disjoint},
}


def schema(name):
    return checkjson.load(schema_path(name))


def read(repo, name):
    """(doc, findings). doc is None when the file is absent (no findings), or
    when it does not parse or does not fit its schema (the findings say how);
    a doc that fits the schema comes back with any rule findings beside it."""
    p = Path(repo) / name
    if not p.is_file():
        return None, []
    try:
        doc = json.loads(p.read_text())
    except ValueError as e:
        return None, [f"{name}: does not parse ({e})"]
    return validate(doc, name, repo)


def validate(doc, name, repo):
    """(doc, findings) for a parsed document: None and the structural findings
    when it does not fit schema/<name>.schema.json, else doc and its rule findings."""
    found = [f"{name}: {f}" for f in checkjson.structure(doc, schema(name))]
    if found:
        return None, found
    for rule, fn in RULES[name].items():
        found += [f"{name}: {rule}: {x}" for x in fn(doc, Path(repo))]
    return doc, found
