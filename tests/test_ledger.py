"""The assurance ledger (checkslib/ledger.py, `checks ledger`; PLAN-architecture.md
§6a, §9 step 6), on a fixture workspace (source/fixtures/practices-valid.py's)
holding one git repo `r`, a test source and a temporary store:

  - the store is the one cli.json declares (dynamic, at the schema's version),
    services.json lists it, git ignores it, and only checkslib/sqlstore.py
    opens a SQLite file; that module is todo's, code for code (SqlstoreCopy);
  - no pointer, no record: `justify` refuses (nothing written), and the
    schema's CHECK refuses the same row inserted around it;
  - a justification turns a practice cell justified, and the same record goes
    `stale` (unjustified, red) once its file changes after its commit; without
    it the cell is unknown (the counterfactual of both);
  - each test file is run / not run / unnamed by the parts that name it, and a
    command this cannot read never yields `not run`;
  - a `--check` document that breaks the one schema is refused, writing nothing;
    one that fits files each check under test or audit by its part's role;
  - gates carry their source and fixtures; the newest KEEP runs are kept; an
    export is the same bytes twice;
  - the CLI: exit 0 recorded, 2 refused or nothing recorded."""
import ast
import json
import sqlite3
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from checkslib import ledger, sqlstore
from tests.helpers import TOOL_ROOT, WORKSPACE, Case, git, repo, run_cli, write
from tests.test_practices import _src, fx

TODO_SQLSTORE = WORKSPACE / "tools" / "todo" / "todolib" / "sqlstore.py" if WORKSPACE else None
CHECK_OK = {"ok": False, "checks": [
    {"name": "test.a", "status": "ok", "counts": {"failed": 0}, "failures": []},
    {"name": "audit", "status": "fail", "counts": {"failed": 1},
     "failures": [{"message": "a stray file", "file": None, "line": None, "role": "audit"}]},
    {"name": "loose", "status": "unchecked", "reason": "no tool here", "counts": {"failed": 0}, "failures": []}]}


def _code(path):
    """A module's code with its docstring left out, as an AST dump (meaning, not bytes)."""
    tree = ast.parse(Path(path).read_text())
    body = tree.body
    if body and isinstance(body[0], ast.Expr) and isinstance(getattr(body[0], "value", None), ast.Constant) \
            and isinstance(body[0].value.value, str):
        body = body[1:]
    return [ast.dump(n) for n in body]


@unittest.skipUnless(TODO_SQLSTORE and TODO_SQLSTORE.is_file(), "no tools/todo/todolib/sqlstore.py to compare")
class SqlstoreCopy(unittest.TestCase):
    def test_the_copy_is_todos_code(self):
        self.assertEqual(_code(TOOL_ROOT / "checkslib" / "sqlstore.py"), _code(TODO_SQLSTORE),
                         "checkslib/sqlstore.py drifted from tools/todo/todolib/sqlstore.py: copy todo's again")

    def test_the_comparison_sees_a_change(self):
        self.assertNotEqual(_code(TOOL_ROOT / "checkslib" / "ledger.py"), _code(TODO_SQLSTORE))


class StoreDeclared(unittest.TestCase):
    def test_cli_json_services_json_gitignore(self):
        cli = json.loads((TOOL_ROOT / "cli.json").read_text())
        store = cli["store"] if isinstance(cli["store"], list) else [cli["store"]]
        self.assertEqual(store, [ledger.STORE_REL])
        self.assertEqual(cli["kinds"][ledger.STORE_REL],
                         {"kind": "dynamic", "schema_version": len(ledger.MIGRATIONS), "export": "ledger"})
        self.assertIn("ledger", cli["verbs"])
        self.assertIn(ledger.STORE_REL, json.loads((TOOL_ROOT / "services.json").read_text())["stores"])
        self.assertEqual(json.loads((TOOL_ROOT / "checks.json").read_text())["accessor"]["impl"],
                         ["checkslib/ledger.py"])
        for f in (ledger.STORE_REL, ledger.STORE_REL + "-wal", ledger.STORE_REL + "-shm"):
            p = subprocess.run(["git", "-C", str(TOOL_ROOT), "check-ignore", "-q", "--no-index", f])
            self.assertEqual(p.returncode, 0, f"{f} is not ignored")

    def test_only_sqlstore_opens_a_database(self):
        openers = []
        for f in sorted(list((TOOL_ROOT / "checkslib").glob("*.py")) + list((TOOL_ROOT / "source").glob("*.py"))):
            for n in ast.walk(ast.parse(f.read_text())):
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "connect" \
                        and isinstance(n.func.value, ast.Name) and n.func.value.id == "sqlite3":
                    openers.append(f.relative_to(TOOL_ROOT).as_posix())
        self.assertEqual(openers, ["checkslib/sqlstore.py"])


class Ledger(Case):
    def setUp(self):
        super().setUp()
        self.ws = fx._ws(self.tmp, fx.ROWS)
        write(self.ws / "CLAUDE.md", "# top\n\n## Never write an inline script blob — ENFORCED\n")
        self.parts = [{"name": "test.a", "run": "python3 -m unittest tests.test_a"},
                      {"name": "audit", "run": "python3 tests/test_audit.py", "role": "audit"}]
        self.r = repo(self.ws / "r", {
            "gates.json": json.dumps({"rules": [{"id": "friday"}]}) + "\n",
            "notes.txt": "one\ntwo\nthree\n",
            "tests/test_a.py": "", "tests/test_b.py": "", "tests/test_audit.py": "",
            "source/fixtures/test_skip.py": "",
            "check.parts.json": json.dumps({"parts": self.parts})})
        _src(self, {"rules-gated": "ok", "hooks-installed": "fail"})
        self.reg = self.ws / "reg" / "gates.json"
        self.dbp = self.tmp / "state" / "ledger.db"
        self.db = ledger.open_db(self.dbp)
        self.addCleanup(self.db.close)

    def record(self, check=None):
        return ledger.record(self.r, self.ws, self.db, check, None, self.src, None, self.reg)

    def items(self, lst):
        return {i["name"]: i for i in ledger.show(self.db, self.r, self.ws)["lists"][lst]}

    def justify(self, row="own-r", **pointer):
        return ledger.justify(self.db, row, self.r, self.ws, "r keeps its rows in gates.json", "test-agent",
                              registry=self.reg, **pointer)

    def count(self, table):
        return self.db.conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]

    def set_parts(self, parts):
        write(self.r / "check.parts.json", json.dumps({"parts": parts}))
        git(self.r, "add", "-A")
        git(self.r, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "parts")

    # ---------------------------------------------------------- no pointer
    def test_no_pointer_no_record(self):
        with self.assertRaisesRegex(ledger.Refused, "no pointer, no record"):
            self.justify()
        with self.assertRaisesRegex(ledger.Refused, "not both"):
            self.justify(file="notes.txt", line=1, command="ls", output="x")
        with self.assertRaisesRegex(ledger.Refused, "line 9 is not one"):
            self.justify(file="notes.txt", line=9)
        with self.assertRaisesRegex(ledger.Refused, "not in r at"):
            self.justify(file="absent.txt", line=1)
        with self.assertRaisesRegex(ledger.Refused, "no practice row `nowhere`"):
            self.justify(row="nowhere", file="notes.txt", line=1)
        self.assertEqual(self.count("justifications"), 0)
        self.assertIsInstance(self.justify(file="notes.txt", line=3), int)     # the counterfactual: with one, a record
        self.assertEqual(self.count("justifications"), 1)

    def test_the_schema_refuses_it_too(self):
        cols = "(row_id, repo, text, author, at, file, line, commit_sha, command, output)"
        sql = f"INSERT INTO justifications {cols} VALUES ('own-r', 'r', 'why', 'me', 'now', ?, ?, ?, ?, ?)"
        for vals in [(None, None, None, None, None),                   # no pointer
                     ("f", 1, "a" * 40, "ls", "out"),                   # both
                     ("f", 1, "abc", None, None),                       # not a full commit
                     ("f", 0, "a" * 40, None, None),                    # no line 0
                     (None, None, None, "ls", None)]:                   # a command with no output
            with self.subTest(vals=vals), self.assertRaises(sqlite3.IntegrityError):
                with self.db.transaction() as c:
                    c.execute(sql, vals)
        with self.db.transaction() as c:                               # each pointer alone is a record
            c.execute(sql, ("f", 1, "a" * 40, None, None))
            c.execute(sql, (None, None, None, "ls", "out"))
        self.assertEqual(self.count("justifications"), 2)

    # ---------------------------------------------------------- stale
    def test_a_justification_goes_stale_when_its_file_changes(self):
        self.record()
        self.assertEqual(self.items("practice")["own-r"]["status"], "unknown")       # without it: unknown
        jid = self.justify(file="notes.txt", line=2)
        self.record()
        cell = self.items("practice")["own-r"]
        self.assertEqual((cell["status"], cell["stale"], cell["justification_id"]), ("justified", 0, jid))
        self.assertEqual(ledger.show(self.db, self.r, self.ws)["justifications"][0]["stale"], False)
        write(self.r / "notes.txt", "one\nTWO\nthree\n")                               # uncommitted counts
        self.record()
        cell = self.items("practice")["own-r"]
        self.assertEqual((cell["status"], cell["stale"]), ("unjustified", 1))
        self.assertIn("stale: notes.txt changed since", cell["detail"])
        js = ledger.show(self.db, self.r, self.ws)["justifications"]
        self.assertEqual((js[0]["stale"], js[0]["id"]), (True, jid))
        git(self.r, "add", "-A")
        git(self.r, "-c", "commit.gpgsign=false", "commit", "-q", "-m", "edit")       # committed: still changed
        self.record()
        self.assertEqual(self.items("practice")["own-r"]["status"], "unjustified")

    def test_a_check_decided_row_keeps_its_result(self):
        self.justify(row="rules-classified", file="notes.txt", line=1)
        self.record()
        self.assertEqual(self.items("practice")["rules-classified"]["status"], "held")   # rules-gated ok, not the record

    def test_a_command_pointer_is_never_stale(self):
        self.justify(command="grep -c friday gates.json", output="1\n")
        self.record()
        cell = self.items("practice")["own-r"]
        self.assertEqual((cell["status"], cell["stale"]), ("justified", None))
        self.assertEqual(ledger.show(self.db, self.r, self.ws)["justifications"][0]["stale"], None)

    # ---------------------------------------------------------- test files
    def test_test_files_run_not_run_unnamed(self):
        self.record()
        tf = {n: i["status"] for n, i in self.items("testfile").items()}
        self.assertEqual(tf, {"tests/test_a.py": "run", "tests/test_audit.py": "run", "tests/test_b.py": "not run"})
        self.set_parts(self.parts + [{"name": "lint", "run": "./dev.sh lint"}])       # a command not read
        self.record()
        tf = {n: (i["status"], i["detail"]) for n, i in self.items("testfile").items()}
        self.assertEqual(tf["tests/test_b.py"][0], "unnamed")
        self.assertIn("cannot read: lint", tf["tests/test_b.py"][1])
        self.assertEqual(tf["tests/test_a.py"][0], "run")

    def test_a_discovery_or_a_package_is_not_read(self):
        tracked = {"tests/__init__.py", "tests/test_a.py", "tests/test_b.py"}
        self.assertIsNone(ledger._transparent("python3 -m unittest discover -s tests", tracked))
        self.assertIsNone(ledger._transparent("python3 -m unittest tests", tracked))
        self.assertEqual(ledger._transparent("python3 -m unittest tests.test_a.Case.test_x", tracked),
                         {"tests/test_a.py"})
        self.assertEqual(ledger._transparent("bash tests/test_b.py", tracked), {"tests/test_b.py"})
        self.assertIsNone(ledger._transparent("bash tests/test_b.py && rm -rf x", tracked))

    def test_no_parts_file_judges_none(self):
        (self.r / "check.parts.json").unlink()
        _, items, notes = self.record()
        self.assertEqual([i for i in items if i["list"] == "testfile"], [])
        self.assertIn("no check.parts.json", notes["testfile"])

    # ---------------------------------------------------------- --check
    def test_a_check_document_that_breaks_the_schema_is_refused(self):
        bad = json.loads(json.dumps(CHECK_OK))
        bad["checks"][1]["counts"]["failed"] = 0                                    # counts disagree with failures
        with self.assertRaisesRegex(ledger.Refused, "does not fit schema/check-json"):
            self.record(json.dumps(bad))
        with self.assertRaisesRegex(ledger.Refused, "not one JSON document"):
            self.record("ok\n")
        self.assertEqual((self.count("runs"), self.count("items")), (0, 0))

    def test_tests_and_audits_by_role(self):
        _, _, notes = self.record(json.dumps(CHECK_OK))
        self.assertNotIn("tests", notes)
        t, a = self.items("test"), self.items("audit")
        self.assertEqual({n: (i["status"], i["tags"]) for n, i in t.items()},
                         {"test.a": ("ok", ["role:undeclared"]), "loose": ("unchecked", ["role:undeclared"])})
        self.assertEqual((a["audit"]["status"], a["audit"]["detail"], a["audit"]["tags"]),
                         ("fail", "a stray file", ["role:audit"]))
        _, _, notes = self.record()
        self.assertIn("tests", notes)
        self.assertEqual(self.items("test"), {})

    # ---------------------------------------------------------- gates, keep, export
    def test_gates_carry_source_and_fixtures(self):
        self.record()
        g = self.items("gate")
        self.assertEqual(g["rules-gated"]["status"], "ok")
        self.assertEqual(g["hooks-installed"]["status"], "fail")
        self.assertEqual(g["rules-gated"]["fixtures"], ["failing", "passing"])
        self.assertTrue(g["rules-gated"]["source"].endswith("src/rules-gated.py"))
        self.assertTrue(g["rules-gated"]["fixture"].endswith("src/fixtures/rules-gated.py"))
        run = ledger.show(self.db, self.r, self.ws)["run"]
        self.assertEqual((run["repo"], run["commit_sha"], run["dirty"]),
                         ("r", git(self.r, "rev-parse", "HEAD").stdout.strip(), 0))

    def test_the_newest_runs_are_kept(self):
        with mock.patch.object(ledger, "KEEP", 2):
            ids = [self.record()[0] for _ in range(3)]
        runs = [r[0] for r in self.db.conn.execute("SELECT id FROM runs ORDER BY id")]
        self.assertEqual(runs, ids[1:])
        self.assertEqual(self.db.conn.execute("SELECT count(*) FROM items WHERE run_id = ?", (ids[0],)).fetchone()[0], 0)

    def test_export_is_the_same_bytes_twice(self):
        self.justify(file="notes.txt", line=1)
        self.record(json.dumps(CHECK_OK))
        a, b = self.tmp / "a", self.tmp / "b"
        ledger.export(self.db, a)
        ledger.export(self.db, b)
        for spec in ledger.SPECS:
            self.assertEqual((a / spec.file).read_bytes(), (b / spec.file).read_bytes())
            self.assertEqual((a / spec.file).stat().st_mode & 0o777, 0o444)
            header, rows = sqlstore.read_export(a / spec.file, spec)
            self.assertEqual(header["rows"], self.count(spec.table))
        self.assertEqual(self.db.verify_exports(a, ledger.SPECS, ledger.PRODUCER), [])

    # ---------------------------------------------------------- the CLI
    def cli(self, *args):
        p = run_cli("ledger", *args, "--db", self.tmp / "cli.db", "--root", self.ws, "--source", self.src)
        return p.returncode, p.stdout + p.stderr

    def test_cli_exit_codes(self):
        rc, out = self.cli("show", self.r)
        self.assertEqual(rc, 2, out)
        self.assertIn("no run recorded", out)
        rc, out = self.cli("justify", "own-r", self.r, "--text", "t", "--author", "a", "--registry", self.reg)
        self.assertEqual(rc, 2, out)
        self.assertIn("REFUSED: no pointer, no record", out)
        bad = write(self.tmp / "bad.json", '{"ok": true}')
        rc, out = self.cli("record", self.r, "--check", bad, "--registry", self.reg)
        self.assertEqual(rc, 2, out)
        good = write(self.tmp / "good.json", json.dumps(CHECK_OK))
        rc, out = self.cli("record", self.r, "--check", good, "--registry", self.reg)
        self.assertEqual(rc, 0, out)
        self.assertIn("checks ledger record r: run 1:", out)
        rc, out = self.cli("show", self.r, "--json")
        self.assertEqual(rc, 0, out)
        rep = json.loads(out)
        self.assertEqual((rep["run"]["id"], rep["lists"]["audit"][0]["name"]), (1, "audit"))
        rc, out = self.cli("export", "--out", self.tmp / "ex")
        self.assertEqual(rc, 0, out)
        self.assertEqual(sorted(p.name for p in (self.tmp / "ex").iterdir()), sorted(s.file for s in ledger.SPECS))


if __name__ == "__main__":
    unittest.main()
