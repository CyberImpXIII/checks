"""The assurance ledger (PLAN-architecture.md §6a, §9 step 6): stored records of
what holds each repo, written by a command, never a summary made on request.

Its store is this repo's own SQLite file, STORE (a dynamic store,
PLAN-services.md §3 ST1: one file behind this CLI, gitignored, WAL and foreign
keys on, constraints in the schema, PRAGMA user_version stepped by MIGRATIONS
through checkslib/sqlstore.py). cli.json names it; `checks ledger` is its one
way in, and this module the only code that names its file (accessor's `impl`).

`checks ledger record [PATH]` writes one run for the repo at PATH: its commit
(HEAD, and whether the tree was dirty), the date, and these lists, each item a
row of `items`:
  gate      every check `checks run PATH` applies there, run now: its source
            file, its fixture file and the fixtures it defines (passing,
            failing), its result and first line;
  test      each check of a saved `dev.sh check --json` (--check FILE, the one
  audit     schema, refused when it does not fit), by the role its part has in
            the repo's check.parts.json (`audit` -> audit; any other role, or no
            part, -> test, with the role in its tags or `role:undeclared`);
            without --check neither list is recorded, and the run says so;
  testfile  every test-shaped file git tracks (TEST_FILE), and whether a part
            of check.parts.json names it: `run` (named), `not run` (no part
            names it, and every part is a command this reads: TRANSPARENT), or
            `unnamed` (no part names it, but some part is a command this cannot
            read, so whether it runs is not known: never `not run` on a guess);
            no parts file, or no git, and none is judged (the run says why);
  practice  each live practice row's cell here (checkslib/practices.py's
            procedure, the same `checks practices` uses, over this one
            location), with the newest justification record of (row, repo)
            taking a recorded cell's place: fresh -> justified; its file
            changed since its commit -> unjustified and `stale` (red in the
            ratchet's terms); its pointer unreadable -> unknown.
The newest KEEP runs of a repo are kept; older ones go, their items with them.

`checks ledger justify ROW [PATH]` writes a justification: the practice row and
the repo, the text, the author, the date and an evidence pointer, either a file
and line at a commit (`--file --line [--commit]`, the commit HEAD by default,
the line checked to exist in that blob) or a command and its stored output
(`--command --output FILE`). No pointer, no record: the CLI refuses it, and the
schema's CHECK refuses it again if anything else tries.

`checks ledger show [PATH] [--json]` reads the newest run and the repo's
justifications (each one's staleness read now from git); `checks ledger export
--out DIR` writes each table's static export (sqlstore: header, seal, 0444).

What this cannot see, said so nothing reads stronger than it is:
  - a part whose command is not TRANSPARENT may run any test file; its unnamed
    files are `unnamed`, and which parts were unread is in the item's detail;
  - a command pointer has no file to watch: its staleness is null, never false;
  - the date of a test or audit item is the run's (when it was recorded), not
    the --check file's own run time, which the schema does not carry.
"""
import ast
import json
import re
import sqlite3
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from checkslib import checkjson, decl, practices, runner, sqlstore

STORE_ERRORS = (sqlstore.StoreError, sqlite3.Error, OSError)

TOOL_ROOT = Path(__file__).resolve().parent.parent
STORE_REL = "state/ledger.db"           # cli.json's `store` entry; tests/test_ledger.py holds the two equal
STORE = TOOL_ROOT / STORE_REL
PRODUCER = "checks ledger export"
PARTS_FILE = "check.parts.json"
KEEP = 20
GIT_TIMEOUT = 60
MAX_OUTPUT = 65536                      # a command pointer's stored output, in bytes

LISTS = ("gate", "test", "audit", "testfile", "practice")
RESULT = ("ok", "fail", "error", "unchecked")
TESTFILE = ("run", "not run", "unnamed")

TEST_FILE = re.compile(r"(^|/)(test_[^/]*\.py|[^/]*_test\.py|test-[^/]*\.sh|[^/]*\.(test|spec)\.[cm]?[jt]s)$")
NOT_TESTS = re.compile(r"(^|/)(fixtures|node_modules)/")
# A part command this module reads: what it runs is in the command itself.
_UNITTEST = re.compile(r"^python3?\s+-m\s+unittest((\s+-v)?(\s+[A-Za-z_][\w.]*)+)$")
_DIRECT = re.compile(r"^(?:(?:bash|sh|python3?|node(?:\s+--test)?)\s+)?(\S+)((?:\s+\S+)*)$")

_TAGS = "tags TEXT NOT NULL DEFAULT '[]' CHECK (json_valid(tags) AND json_type(tags) = 'array')"
MIGRATIONS = [[
    f"""CREATE TABLE justifications (
      id INTEGER PRIMARY KEY,
      row_id TEXT NOT NULL CHECK (length(row_id) > 0),
      repo TEXT NOT NULL CHECK (length(repo) > 0),
      text TEXT NOT NULL CHECK (length(trim(text)) > 0),
      file TEXT, line INTEGER, commit_sha TEXT,
      command TEXT, output TEXT,
      author TEXT NOT NULL CHECK (length(trim(author)) > 0),
      at TEXT NOT NULL CHECK (length(at) > 0),
      {_TAGS},
      CHECK ((file IS NOT NULL AND length(file) > 0 AND line IS NOT NULL AND line >= 1
              AND commit_sha IS NOT NULL AND length(commit_sha) = 40 AND command IS NULL AND output IS NULL)
          OR (command IS NOT NULL AND length(trim(command)) > 0 AND output IS NOT NULL
              AND file IS NULL AND line IS NULL AND commit_sha IS NULL)))""",
    f"""CREATE TABLE runs (
      id INTEGER PRIMARY KEY,
      repo TEXT NOT NULL CHECK (length(repo) > 0),
      commit_sha TEXT CHECK (commit_sha IS NULL OR length(commit_sha) = 40),
      dirty INTEGER CHECK (dirty IS NULL OR dirty IN (0, 1)),
      at TEXT NOT NULL CHECK (length(at) > 0),
      check_file TEXT,
      notes TEXT NOT NULL DEFAULT '{{}}' CHECK (json_valid(notes) AND json_type(notes) = 'object'),
      {_TAGS})""",
    "CREATE INDEX runs_repo ON runs (repo, id)",
    f"""CREATE TABLE items (
      id INTEGER PRIMARY KEY,
      run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
      list TEXT NOT NULL CHECK (list IN ('gate', 'test', 'audit', 'testfile', 'practice')),
      name TEXT NOT NULL CHECK (length(name) > 0),
      status TEXT NOT NULL,
      source TEXT,
      fixture TEXT,
      fixtures TEXT CHECK (fixtures IS NULL OR (json_valid(fixtures) AND json_type(fixtures) = 'array')),
      detail TEXT,
      justification_id INTEGER REFERENCES justifications(id) ON DELETE SET NULL,
      stale INTEGER CHECK (stale IS NULL OR stale IN (0, 1)),
      {_TAGS},
      UNIQUE (run_id, list, name),
      CHECK ((list IN ('gate', 'test', 'audit') AND status IN ('ok', 'fail', 'error', 'unchecked'))
          OR (list = 'testfile' AND status IN ('run', 'not run', 'unnamed'))
          OR (list = 'practice' AND status IN ('held', 'justified', 'unjustified', 'unknown'))))""",
    "CREATE INDEX items_run ON items (run_id, list)",
]]
SPECS = [sqlstore.ExportSpec("runs", "ledger-runs.jsonl", ["id"], ["tags", "notes"]),
         sqlstore.ExportSpec("items", "ledger-items.jsonl", ["id"], ["tags", "fixtures"]),
         sqlstore.ExportSpec("justifications", "ledger-justifications.jsonl", ["id"], ["tags"])]


class Refused(Exception):
    """A record the ledger will not write; the message says why."""


def open_db(path=None):
    path = Path(path) if path else STORE
    path.parent.mkdir(parents=True, exist_ok=True)
    return sqlstore.Db(path, MIGRATIONS)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def git(repo, *args):
    """(exit code, stdout) of one git command in repo; (None, why) when git cannot start."""
    try:
        p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True,
                           stdin=subprocess.DEVNULL, timeout=GIT_TIMEOUT)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, str(e)
    return p.returncode, p.stdout


def repo_key(repo, ws):
    """The repo as the ledger names it: its path from the workspace top ('.' the
    top), or its absolute path when it is not under one."""
    return runner.rel(repo, ws) or str(Path(repo).resolve())


def repo_path(key, ws):
    p = Path(key)
    return p if p.is_absolute() else (Path(ws) / key if ws else None)


def head(repo):
    """(commit, dirty): HEAD's sha and whether the tree holds uncommitted work;
    (None, None) outside git or with no commit."""
    code, out = git(repo, "rev-parse", "--verify", "HEAD^{commit}")
    if code != 0:
        return None, None
    code2, st = git(repo, "status", "--porcelain")
    return out.strip(), (None if code2 != 0 else int(bool(st.strip())))


def _shown(path, ws):
    path = Path(path).resolve()
    if ws:
        try:
            return path.relative_to(Path(ws).resolve()).as_posix()
        except ValueError:
            pass
    return str(path)


def _first(lines):
    lines = [l for l in (lines or []) if l]
    if not lines:
        return None
    return lines[0][:300] + (f" (+{len(lines) - 1} more)" if len(lines) > 1 else "")


# ------------------------------------------------------------------ the lists

def gate_items(repo, ws, source=runner.DEFAULT_SOURCE, names=None):
    """Every check `checks run` applies to repo, run now, as items."""
    entries = {e.name: e for e in decl.load(source)[0]}
    rep = runner.run_repo(repo, source, ws, names)
    out = []
    for r in rep["results"]:
        e = entries.get(r["check"])
        fixtures = None
        if e and e.fixture.is_file():
            try:
                tree = ast.parse(e.fixture.read_text())
                fixtures = sorted({n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
                                  & {"passing", "failing"})
            except (OSError, SyntaxError):
                fixtures = None
        out.append({"list": "gate", "name": r["check"], "status": r["status"],
                    "source": _shown(e.path, ws) if e else None,
                    "fixture": _shown(e.fixture, ws) if e and e.fixture.is_file() else None,
                    "fixtures": fixtures, "detail": _first(r["lines"]),
                    "tags": [f"applies_to:{e.applies_to}"] if e else ["refused"]})
    for f in rep["faults"]:
        out.append({"list": "gate", "name": f"fault: {f}"[:200], "status": "error", "detail": f, "tags": ["fault"]})
    return out


def read_parts(repo):
    """(parts, why): the repo's check.parts.json parts as {name: {run, role}},
    or (None, why) when there is none or it does not read."""
    p = Path(repo) / PARTS_FILE
    if not p.is_file():
        return None, f"no {PARTS_FILE}: which tests `dev.sh check` runs is not declared"
    try:
        doc = json.loads(p.read_text())
        role = (doc.get("defaults") or {}).get("role")
        return {x["name"]: {"run": x["run"], "role": x.get("role", role)} for x in doc["parts"]}, None
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
        return None, f"{PARTS_FILE} does not read ({e.__class__.__name__}: {e})"


def check_items(text, parts):
    """The tests and audits of a saved `dev.sh check --json`; Refused when it
    does not fit the one schema (schema/check-json.schema.json)."""
    try:
        doc = json.loads(text)
    except ValueError as e:
        raise Refused(f"--check: not one JSON document ({e})")
    code = 0 if isinstance(doc, dict) and doc.get("ok") is True else 1   # exit-agrees holds by construction
    bad = checkjson.validate(text, code)
    if bad:
        raise Refused("--check does not fit schema/check-json.schema.json: " + "; ".join(bad[:5]))
    out = []
    for c in doc["checks"]:
        part = (parts or {}).get(c["name"])
        role = part["role"] if part else None
        why = c.get("reason") or (c["failures"][0]["message"] if c["failures"] else None)
        out.append({"list": "audit" if role == "audit" else "test", "name": c["name"], "status": c["status"],
                    "source": part["run"] if part else None, "detail": why[:300] if why else None,
                    "tags": [f"role:{role}" if role else "role:undeclared"]})
    return out


def _transparent(run, tracked):
    """The test files `run` runs, when what it runs is in the command itself;
    None when it is a command this cannot read (a script, a discovery run)."""
    run = run.strip()
    m = _UNITTEST.match(run)
    if m:
        mods = [w for w in m.group(1).split() if w != "-v"]
        if "discover" in mods:
            return None                 # a discovery run: what it finds is not in the command
        dotted = {f[:-3].replace("/", "."): f for f in tracked
                  if f.endswith(".py") and not f.endswith("__init__.py")}   # a package runs what it holds
        files = set()
        for mod in mods:
            hit = [f for d, f in dotted.items() if mod == d or mod.startswith(d + ".")]
            if not hit:
                return None             # a package or a name this cannot map to one file: not read
            files.update(hit)
        return files
    m = _DIRECT.match(run)
    if m:
        args = [m.group(1)] + m.group(2).split()
        files = {a[2:] if a.startswith("./") else a for a in args}
        named = {f for f in files if f in tracked and TEST_FILE.search(f)}
        if named and named == {f for f in files if not f.startswith("-")}:
            return named
    return None


def testfile_items(repo, parts):
    """(items, why): each test-shaped file git tracks, run / not run / unnamed;
    ([], why) when none can be judged."""
    if parts is None:
        return [], "no parts file read"
    code, out = git(repo, "ls-files")
    if code != 0:
        return [], "not a git repo: no tracked files to judge"
    tracked = set(out.splitlines())
    tests = sorted(f for f in tracked if TEST_FILE.search(f) and not NOT_TESTS.search(f))
    named, unread = {}, []
    for name, part in parts.items():
        got = _transparent(part["run"], tracked)
        if got is None:
            unread.append(name)
            got = {f for f in tests if f in part["run"] or (f.endswith(".py") and f[:-3].replace("/", ".") in part["run"])}
        for f in got:
            named.setdefault(f, []).append(name)
    items = []
    for f in tests:
        if f in named:
            items.append({"list": "testfile", "name": f, "status": "run", "source": f,
                          "detail": "named by " + ", ".join(sorted(named[f]))})
        elif unread:
            items.append({"list": "testfile", "name": f, "status": "unnamed", "source": f,
                          "detail": "no part names it; parts whose command this cannot read: " + ", ".join(sorted(unread))})
        else:
            items.append({"list": "testfile", "name": f, "status": "not run", "source": f,
                          "detail": "no part of " + PARTS_FILE + " names it, and every part was read"})
    return items, None


def stale(j, ws):
    """(stale, why) of one justification record now: True when its file changed
    since its commit (working tree included), False when not, None when it
    cannot be said (a command pointer; a repo or commit that is gone)."""
    if j["file"] is None:
        return None, "a command pointer: no file to watch"
    repo = repo_path(j["repo"], ws)
    if repo is None or not repo.is_dir():
        return None, f"repo {j['repo']} is not here"
    code, _ = git(repo, "diff", "--quiet", j["commit_sha"], "--", j["file"])
    if code == 0:
        code_u, untracked = git(repo, "ls-files", "--others", "--exclude-standard", "--", j["file"])
        if code_u == 0 and untracked.strip():
            return True, f"{j['file']} is untracked here"
        return False, f"{j['file']} unchanged since {j['commit_sha'][:12]}"
    if code == 1:
        return True, f"{j['file']} changed since {j['commit_sha'][:12]}"
    return None, f"git diff against {j['commit_sha'][:12]} failed (exit {code}): commit gone?"


def latest_justifications(db, repo):
    rows = db.conn.execute("SELECT * FROM justifications WHERE repo = ? ORDER BY id", (repo,)).fetchall()
    out = {}
    for r in rows:
        out[r["row_id"]] = dict(r)
    return out


def override(j, ws):
    """The practice cell a justification record gives (practices.cells' `overrides`)."""
    s, why = stale(j, ws)
    head_ = f"justification {j['id']} by {j['author']}"
    if s is True:
        return {"state": "unjustified", "why": f"stale: {why} ({head_}: {j['text'][:200]})",
                "stale": True, "justification": j["id"]}
    if s is None and j["file"] is not None:
        return {"state": "unknown", "why": f"{head_}: its pointer cannot be read: {why}",
                "stale": None, "justification": j["id"]}
    return {"state": "justified", "why": f"{head_}: {j['text'][:200]}", "stale": None if s is None else False,
            "justification": j["id"]}


def practice_items(db, repo, ws, source=runner.DEFAULT_SOURCE, names=None, registry=None):
    """(items, why): each live practice row's cell at repo; ([], why) when none
    can be computed (no workspace top, a registry that does not read or is invalid)."""
    loc = runner.rel(repo, ws)
    if loc is None:
        return [], "no workspace top: practice rows apply to locations under one"
    block, faults = practices.load(registry or practices.REGISTRY)
    if block is None:
        return [], f"practice registry: {faults[0]}"
    findings, _ = practices.validate(block, ws, source)
    if findings:
        return [], f"practice registry invalid ({len(findings)} finding(s), checks one practices-valid)"
    rows = block["rows"]
    results = {loc: practices.run_location(rows, repo, ws, [loc], source, names)}
    overrides = {(rid, loc): override(j, ws) for rid, j in latest_justifications(db, loc).items()}
    table = practices.cells(rows, [loc], results, overrides)
    items = []
    for rid in sorted(table):
        c = table[rid].get(loc)
        if c is None:
            continue
        tags = ["derived"] if c.get("derived") else []
        tags += ["recorded"] if c.get("recorded") else []
        tags += ["unbuilt"] if c.get("unbuilt") else []
        items.append({"list": "practice", "name": rid, "status": c["state"], "detail": c["why"][:500],
                      "justification_id": c.get("justification"),
                      "stale": None if c.get("stale") is None else int(c["stale"]), "tags": tags})
    return items, None


# ------------------------------------------------------------------ the verbs

def record(repo, ws, db, check_text=None, check_file=None, source=runner.DEFAULT_SOURCE, names=None,
           registry=None):
    """One run of repo into db; returns (run id, items, notes). Refused before
    anything is written when --check does not fit the schema."""
    repo = Path(repo).resolve()
    if not repo.is_dir():
        raise Refused(f"no such folder: {repo}")
    parts, parts_why = read_parts(repo)
    notes = {}
    items = []
    if check_text is not None:
        items += check_items(check_text, parts)
    else:
        notes["tests"] = "no --check: tests and audits not recorded in this run"
    items += gate_items(repo, ws, source, names)
    tf, why = testfile_items(repo, parts)
    items += tf
    if why:
        notes["testfile"] = parts_why or why
    pi, why = practice_items(db, repo, ws, source, names, registry)
    items += pi
    if why:
        notes["practice"] = why
    sha, dirty = head(repo)
    key = repo_key(repo, ws)
    with db.transaction() as c:
        cur = c.execute("INSERT INTO runs (repo, commit_sha, dirty, at, check_file, notes, tags) VALUES (?,?,?,?,?,?,?)",
                        (key, sha, dirty, now(), str(check_file) if check_file else None,
                         sqlstore.canonical(notes), "[]"))
        run_id = cur.lastrowid
        for it in items:
            c.execute("INSERT INTO items (run_id, list, name, status, source, fixture, fixtures, detail, "
                      "justification_id, stale, tags) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                      (run_id, it["list"], it["name"], it["status"], it.get("source"), it.get("fixture"),
                       None if it.get("fixtures") is None else sqlstore.canonical(it["fixtures"]),
                       it.get("detail"), it.get("justification_id"), it.get("stale"),
                       sqlstore.canonical(it.get("tags") or [])))
        c.execute("DELETE FROM runs WHERE repo = ? AND id NOT IN "
                  "(SELECT id FROM runs WHERE repo = ? ORDER BY id DESC LIMIT ?)", (key, key, KEEP))
    return run_id, items, notes


def justify(db, row_id, repo, ws, text, author, file=None, line=None, commit=None, command=None,
            output=None, registry=None):
    """Write one justification; its id. Refused (nothing written) without an
    evidence pointer, or with one that does not resolve."""
    repo = Path(repo).resolve()
    if not repo.is_dir():
        raise Refused(f"no such folder: {repo}")
    block, faults = practices.load(registry or practices.REGISTRY)
    if block is None:
        raise Refused(f"practice registry: {faults[0]}")
    if row_id not in {r.get("id") for r in block["rows"]}:
        raise Refused(f"no practice row `{row_id}` (checks practices)")
    if not (text or "").strip():
        raise Refused("no text: a justification says why")
    if not (author or "").strip():
        raise Refused("no author: the session or agent that writes it is named")
    by_file = file is not None or line is not None or commit is not None
    by_command = command is not None or output is not None
    if not by_file and not by_command:
        raise Refused("no pointer, no record: give --file and --line (at --commit), or --command and --output")
    if by_file and by_command:
        raise Refused("one pointer: a file and line at a commit, or a command and its output, not both")
    key = repo_key(repo, ws)
    if by_file:
        if not file or not line:
            raise Refused("a file pointer needs --file and --line")
        code, sha = git(repo, "rev-parse", "--verify", f"{commit or 'HEAD'}^{{commit}}")
        if code != 0:
            raise Refused(f"commit {commit or 'HEAD'} does not resolve in {key}")
        sha = sha.strip()
        code, blob = git(repo, "show", f"{sha}:{file}")
        if code != 0:
            raise Refused(f"{file} is not in {key} at {sha[:12]}")
        n = len(blob.splitlines())
        if not 1 <= int(line) <= n:
            raise Refused(f"{file} has {n} line(s) at {sha[:12]}; line {line} is not one")
        vals = (file, int(line), sha, None, None)
    else:
        if not (command or "").strip() or output is None:
            raise Refused("a command pointer needs --command and --output (its stored output)")
        if len(output.encode()) > MAX_OUTPUT:
            raise Refused(f"the stored output is {len(output.encode())} bytes; at most {MAX_OUTPUT} (keep the part that shows it)")
        vals = (None, None, None, command, output)
    with db.transaction() as c:
        cur = c.execute("INSERT INTO justifications (row_id, repo, text, file, line, commit_sha, command, output, "
                        "author, at, tags) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                        (row_id, key, text.strip(), *vals, author.strip(), now(), "[]"))
        return cur.lastrowid


def show(db, repo, ws):
    """The newest run of repo, its items by list, and the repo's justifications
    with their staleness read now; None when no run is recorded."""
    key = repo_key(repo, ws)
    run = db.conn.execute("SELECT * FROM runs WHERE repo = ? ORDER BY id DESC LIMIT 1", (key,)).fetchone()
    js = [dict(r) for r in db.conn.execute("SELECT * FROM justifications WHERE repo = ? ORDER BY id", (key,))]
    for j in js:
        j["stale"], j["stale_why"] = stale(j, ws)
    if run is None:
        return {"repo": key, "run": None, "lists": {}, "justifications": js}
    run = dict(run)
    run["notes"] = json.loads(run["notes"])
    run["tags"] = json.loads(run["tags"])
    lists = {l: [] for l in LISTS}
    for r in db.conn.execute("SELECT * FROM items WHERE run_id = ? ORDER BY list, name", (run["id"],)):
        it = dict(r)
        it["tags"] = json.loads(it["tags"])
        it["fixtures"] = None if it["fixtures"] is None else json.loads(it["fixtures"])
        del it["run_id"]
        lists[it["list"]].append(it)
    return {"repo": key, "run": run, "lists": lists, "justifications": js}


def counts(items):
    c = {}
    for it in items:
        c[it["status"]] = c.get(it["status"], 0) + 1
    return c


def export(db, folder):
    Path(folder).mkdir(parents=True, exist_ok=True)
    return db.write_exports(folder, SPECS, PRODUCER)
