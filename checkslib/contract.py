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
import re
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


def store_paths(doc):
    """The store paths cli.json names; [] when it declares no store (a CLI over no store)."""
    s = doc.get("store")
    if s is None:
        return []
    return [s] if isinstance(s, str) else list(s)


def has_store(doc):
    return "store" in doc


def exported_stores(doc):
    """The store entries the data repo should hold: every `store` entry not in
    `not_exported` (private, with a reason). [] when every entry is private."""
    private = {norm(k) for k in doc.get("not_exported") or {}}
    return [s for s in store_paths(doc) if norm(s) not in private]


def store_files(doc, files):
    """The files (repo-relative, from `files`) a valid cli.json's `store` names,
    by path or glob, whatever their extension: the one reading of `store` for
    every check (accessor, stores-readonly). [] when it declares no store."""
    globs = [norm(s) for s in store_paths(doc)]
    return sorted({p for p in files if any(fnmatch.fnmatch(p, g) for g in globs)})


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
    return out + [f"$.store: `{s}` is not a path inside the repo" for s in store_paths(doc) if not inside(s)]


def _cli_executable(doc, repo):
    why = _executable(repo, doc["cli"]) if inside(doc["cli"]) else None
    return [f"$.cli: {why}"] if why else []


def _cli_verbs(doc, repo):
    return _verbs(repo, doc["cli"], doc["verbs"], "$.verbs")


def _cli_unique(doc, repo):
    return _dupes([norm(s) for s in store_paths(doc)], "$.store", "path") + _dupes(doc["verbs"], "$.verbs", "verb")


def _not_exported(doc, repo):
    entries = {norm(s) for s in store_paths(doc)}
    return [f"$.not_exported: `{k}` is not an entry of $.store" + ("" if entries else " (no store is declared)")
            for k in sorted(doc.get("not_exported") or {}) if norm(k) not in entries]


def _cli_not_verbs(doc, repo):
    """Without not_verbs, verbs may be a subset of the help. With it, the two
    together claim to account for every command: held both ways."""
    if "not_verbs" not in doc:
        return []
    out = [f"$.not_verbs: `{v}` is also in verbs" for v in doc["not_verbs"] if v in doc["verbs"]]
    rel = doc["cli"]
    if not inside(rel) or _executable(repo, rel):
        return out
    have, why = helptext.listed(Path(repo) / rel, repo)
    if have is None:
        return out + [f"$.not_verbs: `{rel} help` {why}: the commands cannot be accounted for"]
    named = set(doc["verbs"]) | set(doc["not_verbs"])
    out += [f"$.not_verbs: `{v}` is not a command `{rel} help` lists" for v in sorted(doc["not_verbs"]) if v not in have]
    return out + [f"$.not_verbs: `{c}` (from `{rel} help`) is in neither verbs nor not_verbs" for c in sorted(have - named)]


# cli.json `read`: the read verbs `repro` runs twice (PLAN-architecture.md §12.2).
FIXTURE_MARK = "{fixture}"
ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
RUNNER_ENV_PREFIX = "CHECKS_"


def _read_verbs(doc):
    return (doc.get("read") or {}).get("verbs") or {}


def _read_declared(doc, repo):
    if "read" not in doc:
        return []
    verbs = _read_verbs(doc)
    if not verbs:
        return ["$.read.verbs: names no verb: a `read` that declares nothing runs nothing"]
    return [f"$.read.verbs.{v}: `{v}` is not a verb $.verbs lists" for v in verbs if v not in doc["verbs"]]


def _read_json(doc, repo):
    return [f"$.read.verbs.{v}.args: no `--json` (every read verb answers in JSON)"
            for v, spec in _read_verbs(doc).items() if "--json" not in spec["args"]]


def _read_fixture(doc, repo):
    if "read" not in doc:
        return []
    read, out = doc["read"], []
    fx = read.get("fixture")
    if fx is not None:
        if not inside(fx):
            out.append(f"$.read.fixture: `{fx}` is not a path inside the repo")
        elif not (Path(repo) / fx).is_dir():
            out.append(f"$.read.fixture: `{fx}` is not a folder in the repo")
    else:
        uses = [f"$.read.verbs.{v}.args" for v, spec in _read_verbs(doc).items()
                if any(FIXTURE_MARK in a for a in spec["args"])]
        uses += [f"$.read.env.{k}" for k, val in (read.get("env") or {}).items() if FIXTURE_MARK in val]
        out += [f"{where}: uses `{FIXTURE_MARK}` but $.read names no fixture" for where in uses]
    return out


def _read_env(doc, repo):
    out = []
    for k in (doc.get("read") or {}).get("env") or {}:
        if not ENV_NAME.match(k):
            out.append(f"$.read.env: `{k}` is not an environment variable name")
        elif k.upper().startswith(RUNNER_ENV_PREFIX):
            out.append(f"$.read.env: `{k}` is the checks runner's own ({RUNNER_ENV_PREFIX}*), never a CLI's")
    return out


def volatile_parts(path):
    """A volatile path's keys, or None when it is not dot-separated non-empty keys."""
    parts = path.split(".")
    return None if any(not p for p in parts) else parts


def _volatile_paths(doc, repo):
    out = []
    for v, spec in _read_verbs(doc).items():
        where = f"$.read.verbs.{v}.volatile"
        vol = spec.get("volatile", [])
        out += [f"{where}: `{p}` is not dot-separated keys" for p in vol if volatile_parts(p) is None]
        out += _dupes(vol, where, "path")
    return out


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
          "unique": _cli_unique, "not-verbs-exact": _cli_not_verbs, "not-exported-declared": _not_exported,
          "read-declared": _read_declared,
          "read-json": _read_json, "read-fixture": _read_fixture, "read-env": _read_env,
          "volatile-paths": _volatile_paths},
    NODE: {"paths-inside": _node_inside, "unique": _node_unique, "generated-exact": _generated_exact,
           "disjoint": _disjoint},
}


def schema(name):
    return checkjson.load(schema_path(name))


def cli_home(repo):
    """The folder whose cli.json declares `repo`: the repo itself, or, for a
    folder that is not a git repo (the workspace top) and has no cli.json of
    its own, its `.claude/` when that is a git repo holding one: the top's
    files are committed in its .claude repo, so its CLI is declared there.
    A git repo always declares its own at its root."""
    repo = Path(repo)
    inner = repo / ".claude"
    if (not (repo / CLI).is_file() and not (repo / ".git").exists()
            and (inner / ".git").exists() and (inner / CLI).is_file()):
        return inner
    return repo


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
