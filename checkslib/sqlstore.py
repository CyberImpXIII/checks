"""A dynamic store in SQLite and its static exports (PLAN-services.md §3 ST1, ST2, ST6).

A COPY of tools/todo's todolib/sqlstore.py, the shared Python store helper that
setup will render into each repo (PLAN-services.md §4 step 10.2; not built when
this copy was made, 2026-10-19; copied again 2026-10-22 from todo's 47445fc).
Only this docstring differs: everything below
it is held equal to todo's file by tests/test_ledger.py (SqlstoreCopy, by
meaning: the module's code with its docstring left out). Never edit the code
here; change todo's, then copy it again, until setup's render replaces this.
In this repo the one caller is checkslib/ledger.py (the assurance ledger).

- `Db(path, migrations)` opens the file with WAL and foreign keys on, then steps
  `PRAGMA user_version` up one migration at a time, each in its own transaction:
  a migration that fails leaves the version where it was and none of its tables.
- `Db.transaction()` wraps a write: it commits on success and rolls back on error.
- `Db.export(spec)` is a table's static export: a header line naming its producer,
  the store and its user_version, the row count and a seal over the rest, then one
  record per line, sorted by the spec's key, keys sorted, so the same rows always
  give the same bytes. `write_exports` writes each at mode 0444 (a temp file, then
  a rename), and may run inside a transaction, so its COMMIT follows the exports;
  `read_export` refuses a header or seal that does not match (a hand edit);
  `export_problems` names, by code, how one export does not stand (EXPORT_CODES),
  and `verify_exports` lists every one of those lines over a set of exports.
- `Db.replace(spec, records)` swaps a table's rows inside the caller's transaction.
- `DbError` is the database's own error, for a caller that names no driver.

In this repo, only this module opens a database.
"""
import contextlib
import hashlib
import json
import os
import sqlite3
from pathlib import Path

SEAL_LEN = 16
HEADER_KEY = "export"
DbError = sqlite3.Error
# How an export can fail to stand, worst first: export_problems returns these codes.
EXPORT_CODES = {
    "missing": "the file is not there",
    "edited": "its lines do not match its seal or header: edited by hand",
    "stale": "sealed, but not what the store holds now: written from another state of it",
    "writable": "a write bit is set; an export sits at 0444",
}


class StoreError(Exception):
    """A store or an export that cannot be used as it stands; the message says why."""


class ExportSpec:
    """One table's export: the table, the file it goes to, the columns it is
    sorted by (its key), and the columns holding JSON text, which the export
    shows as JSON values and the import writes back as canonical text."""

    def __init__(self, table, file, order_by, json_columns=()):
        self.table = table
        self.file = file
        self.order_by = list(order_by)
        self.json_columns = set(json_columns)


def canonical(value):
    """One spelling for one value: keys sorted, no spaces, unicode kept."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _seal(header, body):
    unsealed = {k: v for k, v in header.items() if k != "seal"}
    return hashlib.sha256((canonical(unsealed) + "\n" + body).encode()).hexdigest()[:SEAL_LEN]


def write_file(path, text, readonly=True):
    """A temp file beside path, then a rename: a reader never sees half a file,
    and a 0444 target is replaced as easily as a writable one."""
    path = Path(path)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    tmp.write_text(text)
    os.chmod(tmp, 0o444 if readonly else 0o644)
    os.replace(tmp, path)


class Db:
    def __init__(self, path, migrations):
        self.path = Path(path)
        self.migrations = list(migrations)
        self.conn = sqlite3.connect(str(self.path), isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        try:
            mode = self.conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            if str(mode).lower() != "wal":
                raise StoreError(f"{self.path}: journal_mode is {mode}, not wal")
            self.conn.execute("PRAGMA foreign_keys=ON")
            self.migrate()
        except BaseException:
            self.conn.close()
            raise

    def close(self):
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    @property
    def version(self):
        return self.conn.execute("PRAGMA user_version").fetchone()[0]

    def migrate(self):
        """Step user_version up to len(migrations), one migration per transaction."""
        have = self.version
        if have > len(self.migrations):
            raise StoreError(f"{self.path}: user_version {have} is newer than this code knows ({len(self.migrations)})")
        for n in range(have, len(self.migrations)):
            with self.transaction():
                for statement in self.migrations[n]:
                    self.conn.execute(statement)
                self.conn.execute(f"PRAGMA user_version = {n + 1}")

    @contextlib.contextmanager
    def transaction(self):
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            yield self.conn
        except BaseException:
            self.conn.execute("ROLLBACK")
            raise
        self.conn.execute("COMMIT")

    def rows(self, spec):
        """The table's rows as dicts, sorted by its key, JSON columns decoded."""
        order = ", ".join(spec.order_by)
        out = []
        for row in self.conn.execute(f"SELECT * FROM {spec.table} ORDER BY {order}"):
            rec = dict(row)
            for col in spec.json_columns:
                if rec.get(col) is not None:
                    rec[col] = json.loads(rec[col])
            out.append(rec)
        return out

    def insert(self, spec, records):
        """Rows into the table (inside the caller's transaction), JSON columns
        written as canonical text."""
        for rec in records:
            rec = {k: (canonical(v) if k in spec.json_columns and v is not None else v) for k, v in rec.items()}
            cols = sorted(rec)
            self.conn.execute(f"INSERT INTO {spec.table} ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})",
                              [rec[c] for c in cols])

    def replace(self, spec, records):
        """The table's rows become records (inside the caller's transaction)."""
        self.conn.execute(f"DELETE FROM {spec.table}")
        self.insert(spec, records)

    # -- the static exports ---------------------------------------------------
    def export(self, spec, producer):
        rows = self.rows(spec)
        body = "".join(canonical(r) + "\n" for r in rows)
        header = {HEADER_KEY: spec.table, "producer": producer, "store": self.path.name,
                  "user_version": self.version, "rows": len(rows)}
        header["seal"] = _seal(header, body)
        return canonical(header) + "\n" + body

    def write_exports(self, folder, specs, producer):
        """Every spec's export into folder, each at 0444. Returns {file: bytes}."""
        out = {}
        for spec in specs:
            text = self.export(spec, producer)
            write_file(Path(folder) / spec.file, text)
            out[spec.file] = len(text.encode())
        return out

    def import_exports(self, folder, specs):
        """A fresh store's rows from the exports in folder, in one transaction.
        Refuses an export whose header or seal does not match, or one written at
        another user_version than this store's."""
        parsed = [(spec, read_export((Path(folder) / spec.file), spec)) for spec in specs]
        with self.transaction():
            for spec, (header, rows) in parsed:
                if header["user_version"] != self.version:
                    raise StoreError(f"{spec.file}: written at user_version {header['user_version']}, "
                                     f"the store is at {self.version}")
                self.insert(spec, rows)

    def export_problems(self, folder, spec, producer):
        """[(code, line)] for one export that does not stand as the store would
        write it, codes from EXPORT_CODES; [] when it stands."""
        path = Path(folder) / spec.file
        if not path.is_file():
            return [("missing", f"{spec.file}: missing")]
        problems = []
        mode = path.stat().st_mode & 0o777
        if mode != 0o444:
            problems.append(("writable", f"{spec.file}: writable (mode {mode:04o}); an export sits at 0444"))
        try:
            read_export(path, spec)
        except StoreError as e:
            return problems + [("edited", str(e))]
        if path.read_text() != self.export(spec, producer):
            problems.append(("stale", f"{spec.file}: differs from the store {self.path.name}"))
        return problems

    def verify_exports(self, folder, specs, producer):
        """One line per export that does not stand as the store would write it:
        missing, writable, edited by hand (its seal), or different from the store."""
        return [line for spec in specs for _, line in self.export_problems(folder, spec, producer)]


def read_export(path, spec):
    """(header, rows) of one export file; StoreError when its header is not this
    spec's or its seal does not match the lines below it."""
    path = Path(path)
    if not path.is_file():
        raise StoreError(f"{spec.file}: missing")
    return parse_export(path.read_text(), spec)


def parse_export(text, spec, sealed=True):
    """(header, rows) of an export's text. sealed=False reads the rows of a
    version whose seal no longer matters (an old commit's, for an audit)."""
    head, _, body = text.partition("\n")
    try:
        header = json.loads(head)
        rows = [json.loads(line) for line in body.splitlines()]
    except ValueError as e:
        raise StoreError(f"{spec.file}: does not parse: {e}")
    if not isinstance(header, dict) or header.get(HEADER_KEY) != spec.table:
        raise StoreError(f"{spec.file}: its first line is not the header of an export of {spec.table}")
    if not sealed:
        return header, rows
    if header.get("seal") != _seal(header, body):
        raise StoreError(f"{spec.file}: its seal does not match its lines: edited by hand")
    if header.get("rows") != len(rows):
        raise StoreError(f"{spec.file}: its header says {header.get('rows')} rows, it holds {len(rows)}")
    return header, rows
