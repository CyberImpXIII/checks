"""Every store in a repo and its kind (PLAN-services.md §3 "Every store is static
or dynamic", ST5): the one inventory behind `stores-classified` (the check) and
`checks stores` (the workspace report), so the two cannot disagree. The
SQLite-name rule for a store on disk is also accessor's and stores-readonly's.

A row per store-shaped file:
  - every file cli.json's `store` names, whatever its extension (a JSON or TSV
    store counts once cli.json declares it);
  - every file cli.json's `renders` names (a generated file is a static store);
  - every SQLite-named file on disk (SQLITE), declared or not, outside
    dot-folders, tests/ and test/ (`on_disk`; nested git repos are pruned by
    scan.walk: each is its own row in the workspace);
  - every `store` entry or `renders` key that matches no file, with `file`
    false: declared, nothing on disk to judge.
A `~/...` entry is a folder named `~` to contract.inside, so its file is not on
disk here; the row says so in a note rather than reading the home folder.
NOT seen: a JSON or TSV file a CLI writes that cli.json does not name. Nothing
in its name tells it from config, which ST3 says is not a store.

Each row's findings (a store's kind comes from cli.json's `kinds`, keyed by
its entry):
  undeclared  store-shaped on disk, named by neither `store` nor `renders`
  no kind     declared, with no `kinds` entry
  not SQLite  dynamic, and the file does not start with SQLite's header
  version     dynamic, its PRAGMA user_version (header bytes 60-63) is not the
              declared `schema_version`; while a non-empty `-wal` sidecar
              exists the header may be stale, so the version is null (unread),
              never guessed, and nothing is judged
  writable    static, a write bit set (ST2: 0444)
  header      static, its first HEADER_BYTES bytes do not name its `producer`
              (a token match, not a parse)
  regen       static with `regen`, only when asked (the check, not the report):
              in a scratch copy of the repo (regen.scratch: what a commit would
              carry, plus every declared store file and its SQLite sidecars,
              the regen's inputs), its files deleted and `regen` run there, each
              must come back byte for byte. A regen that writes outside its
              copy is the producer's fault, and this cannot see it.
Not judged: that an `immutable` store was never rewritten, and that a static
store's header names its inputs (ST2)."""
import os
import shutil
import stat
import tempfile
from pathlib import Path

from checkslib import contract, proc, regen, scan

SQLITE = ["*.db", "*.sqlite", "*.sqlite3"]
SQLITE_SIDE = ("-wal", "-shm", "-journal")
SQLITE_MAGIC = b"SQLite format 3\x00"
NEVER_ON_DISK = ["tests/*", "test/*"]
HEADER_BYTES = 2048
REGEN_TIMEOUT = 120.0     # under the runner's 300s per check; tests/test_stores_classified.py lowers it


def in_dot_folder(rel):
    return any(part.startswith(".") for part in rel.split("/")[:-1])


def on_disk(files, extra=(), exclude=()):
    """The store-shaped files among `files`: a SQLite name (or one of `extra`'s
    globs), outside dot-folders, tests/, test/ and `exclude`."""
    return [p for p in files if scan.matches(p, SQLITE + list(extra)) and not in_dot_folder(p)
            and not scan.matches(p, NEVER_ON_DISK + list(exclude))]


def _entries(doc):
    """(where, entry) for every `store` entry and `renders` key, those with a kind first,
    so a file two entries name takes the classified one."""
    kinds = {contract.norm(k) for k in doc.get("kinds") or {}}
    out = [("store", e) for e in contract.store_paths(doc)] + [("renders", k) for k in doc.get("renders") or {}]
    return sorted(out, key=lambda we: contract.norm(we[1]) not in kinds)


def _head(path, n):
    with open(path, "rb") as f:
        return f.read(n)


def _judge(repo, row, spec):
    """The row's facts and findings, from the file on disk; nothing is written."""
    p = Path(repo) / row["path"]
    if row["declared"] is None:
        return ["store-shaped (a SQLite name) and named by neither cli.json's `store` nor `renders`"]
    if spec is None:
        return [f"declared (`{row['declared']}` entry `{row['entry']}`) with no kind in cli.json's `kinds`"]
    if not row["file"]:
        return []
    try:
        head = _head(p, max(HEADER_BYTES, 100))
        mode = stat.S_IMODE(os.stat(p).st_mode)
    except OSError as e:
        return [f"could not be read ({e.strerror})"]
    out = []
    if spec["kind"] == "dynamic":
        if not head.startswith(SQLITE_MAGIC):
            return ["dynamic, but not a SQLite file (ST1: a service's records are one SQLite file)"]
        wal = Path(f"{p}-wal")
        if wal.is_file() and wal.stat().st_size > 0:
            row["user_version"] = None
            row["notes"].append("a non-empty -wal may hold a newer header")
        else:
            row["user_version"] = int.from_bytes(head[60:64], "big") if len(head) >= 64 else None
            if row["user_version"] != spec["schema_version"]:
                out.append(f"dynamic, PRAGMA user_version is {row['user_version']} but cli.json's schema_version "
                           f"is {spec['schema_version']} (the file is not migrated, or cli.json is stale)")
        return out
    if mode & 0o222:
        out.append(f"static, but writable (mode {mode:04o}); a static store sits at 0444 (ST2)")
    if spec["producer"] not in head[:HEADER_BYTES].decode("utf-8", "replace"):
        out.append(f"static, but its first {HEADER_BYTES} bytes do not name its producer `{spec['producer']}` "
                   "(ST2: a generated header, or a field)")
    return out


def _copy_inputs(repo, doc, files, work):
    """Every declared store file (and its SQLite sidecars) into the copy: a
    regen's inputs, which a clone lacks when they are git-ignored."""
    for rel in contract.store_files(doc, files):
        for side in ("",) + SQLITE_SIDE:
            src = Path(repo) / (rel + side)
            if src.is_file() and not src.is_symlink():
                (work / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, work / (rel + side))


def _regen(repo, doc, files, entry, spec, matched):
    """{path: [findings]} for one regenerable entry. Raises regen.Broken when no copy can be made."""
    shown = " ".join(spec["regen"])
    tmp = Path(tempfile.mkdtemp(prefix="checks-stores-"))
    try:
        work = tmp / "copy"
        regen.scratch(repo, work)
        _copy_inputs(repo, doc, files, work)
        for p in matched:
            if (work / p).is_file() or (work / p).is_symlink():
                (work / p).unlink()
        argv = [str(work / spec["regen"][0])] + spec["regen"][1:]
        env = {k: v for k, v in os.environ.items() if not k.startswith("CHECKS_")}
        env[regen.GUARD] = "1"
        try:
            code, _, err = proc.bounded(argv, work, env, REGEN_TIMEOUT)
        except OSError as e:
            return {p: [f"static, regen `{shown}` could not start ({e.strerror})"] for p in matched}
        except proc.Timeout:
            return {p: [f"static, regen `{shown}` did not finish in {REGEN_TIMEOUT:g}s"] for p in matched}
        if code != 0:
            tail = ([l for l in (err or "").splitlines() if l.strip()][-1:] or ["(nothing on stderr)"])[0][:200]
            return {p: [f"static, regen `{shown}` exited {code}: {tail}"] for p in matched}
        out = {}
        for p in matched:
            mine = work / p
            if not mine.is_file():
                out[p] = [f"static, regen `{shown}` did not render it"]
            elif mine.read_bytes() != (Path(repo) / p).read_bytes():
                line = regen._first_difference(mine.read_bytes(), (Path(repo) / p).read_bytes())
                out[p] = [f"static, regen `{shown}` does not reproduce it (first difference at line {line})"]
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def inventory(repo, run_regen=False):
    """{"rows": [...], "unchecked": why or None, "regen_unchecked": why or None}.
    A row: {path, entry, declared ("store" | "renders" | None), kind (None: no
    kind declared), file, user_version (dynamic SQLite only), notes, findings}.
    `unchecked`: cli.json breaks its contract, so nothing is judged (accessor
    says how). `regen_unchecked`: a regen was due and could not run here."""
    repo = Path(repo)
    files = scan.walk(repo)
    doc, found = contract.read(repo, contract.CLI)
    if found:
        return {"rows": [], "unchecked": f"{contract.CLI} does not keep its contract (`accessor` says how); "
                                         f"no store judged: {found[0][:200]}", "regen_unchecked": None}
    doc = doc or {}
    kinds = {contract.norm(k): v for k, v in (doc.get("kinds") or {}).items()}
    rows = {}
    for where, entry in _entries(doc):
        matched = contract.entry_files(entry, files)
        for p in matched or [contract.norm(entry)]:
            rows.setdefault(p, {"path": p, "entry": entry, "declared": where, "file": bool(matched)})
    for p in on_disk(files):
        rows.setdefault(p, {"path": p, "entry": None, "declared": None, "file": True})
    for row in rows.values():
        spec = kinds.get(contract.norm(row["entry"])) if row["entry"] is not None else None
        row["kind"] = spec["kind"] if spec else None
        row["notes"] = []
        if row["path"].split("/")[0] == "~":   # contract.inside passes it as a folder named `~` (TODO.md)
            row["notes"].append("a `~` path: read as a folder named `~` in the repo, never expanded, so not judged")
        row["findings"] = _judge(repo, row, spec)
    regen_unchecked = None
    due = [(e, kinds[contract.norm(e)]) for _, e in _entries(doc)
           if kinds.get(contract.norm(e), {}).get("regen")]
    for entry, spec in due:
        matched = [p for p, r in rows.items() if r["entry"] == entry and r["file"]]
        if not matched:
            continue
        if not run_regen:
            for p in matched:
                rows[p]["notes"].append("regen not run (the report; `checks one stores-classified <repo>` runs it)")
            continue
        if os.environ.get(regen.GUARD):
            regen_unchecked = "nested inside a rebuild: regen not run again"
            continue
        if not (repo / ".git").exists():
            regen_unchecked = "not a git repo: no scratch copy to run regen in"
            continue
        try:
            for p, fs in _regen(repo, doc, files, entry, spec, matched).items():
                rows[p]["findings"] += fs
        except regen.Broken as e:
            regen_unchecked = f"regen `{' '.join(spec['regen'])}` not run: {e}"
    return {"rows": [rows[p] for p in sorted(rows)], "unchecked": None, "regen_unchecked": regen_unchecked}


def line(row):
    """One inventory line: `<path>: <kind or none> (<where it is declared>[; facts])`."""
    where = f"{row['declared']} `{row['entry']}`" if row["declared"] else "not declared"
    facts = [] if row["file"] else ["no file on disk"]
    if "user_version" in row:
        facts.append(f"user_version {row['user_version'] if row['user_version'] is not None else 'unread'}")
    return f"{row['path']}: {row['kind'] or 'none'} ({'; '.join([where] + facts + row['notes'])})"


def verdict(rep, prefix=""):
    """(status, lines) for one repo's inventory: the check's result, and the
    report's per-repo status. Findings first; then a regen that could not run
    (unchecked, never ok); else ok with one line per store."""
    if rep["unchecked"]:
        return "unchecked", [rep["unchecked"]]
    findings = [f"{prefix}{r['path']}: {f}" for r in rep["rows"] for f in r["findings"]]
    if findings:
        return "fail", findings
    if rep["regen_unchecked"]:
        return "unchecked", [rep["regen_unchecked"]]
    if not rep["rows"]:
        return "ok", ["no store: nothing store-shaped on disk, and cli.json declares none"]
    return "ok", [line(r) for r in rep["rows"]]


def counts(rows):
    c = {"stores": len(rows), "dynamic": 0, "static": 0, "none": 0, "undeclared": 0,
         "findings": sum(len(r["findings"]) for r in rows)}
    for r in rows:
        c[r["kind"] or "none"] += 1
        c["undeclared"] += r["declared"] is None
    return c
