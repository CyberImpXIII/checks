"""stores-classified (PLAN-services.md ST5) and `checks stores`, the report over
the same inventory (checkslib/stores.py): each finding alone, from a passing
repo, turns it red with that one line (the counterfactual of every rule); the
states that must not be ok (a regen that cannot run) or not a finding (a WAL
that may hold a newer header); and the seam, the report's findings equal to
the check's, repo by repo."""
import importlib.util
import json
import os
import shutil
import sqlite3
from pathlib import Path

from tests.helpers import TOOL_ROOT, Case, run_cli, write
from checkslib import stores

_spec = importlib.util.spec_from_file_location("fx_stores_classified",
                                               TOOL_ROOT / "source" / "fixtures" / "stores-classified.py")
FX = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(FX)


class StoresClassified(Case):
    def base(self, **kinds):
        """The passing fixture, its `kinds` entries replaced by `kinds` (None removes one)."""
        r = FX.passing(self.tmp).repo
        if kinds:
            doc = json.loads((r / "cli.json").read_text())
            for k, v in kinds.items():
                doc["kinds"].pop(k, None) if v is None else doc["kinds"].__setitem__(k, v)
            write(r / "cli.json", json.dumps(doc))
        return r

    def one(self, r):
        return self.cli_json("one", "stores-classified", r)[1]["results"][0]

    def red(self, r):
        res = self.one(r)
        self.assertEqual(res["status"], "fail", res)
        return res["lines"]

    def test_passing_is_ok_and_names_each_store_with_its_kind(self):
        res = self.one(self.base())
        self.assertEqual((res["status"], res["lines"]), ("ok", [
            "TODO.md: static (renders `TODO.md`)",
            "data/app.db: dynamic (store `data/app.db`; user_version 2)"]))

    def test_each_rule_alone_turns_it_red_with_its_one_line(self):
        def stray(r):
            FX._db(r / "data" / "stray.db", 0)

        def behind(r):
            os.remove(r / "data" / "app.db")
            FX._db(r / "data" / "app.db", 1)

        def writable(r):
            os.chmod(r / "TODO.md", 0o644)

        def edited(r):            # header kept, sealed again: only the regen can tell
            os.chmod(r / "TODO.md", 0o644)
            write(r / "TODO.md", FX.RENDER + "a hand-added row\n", 0o444)

        def not_sqlite(r):
            os.remove(r / "data" / "app.db")
            write(r / "data" / "app.db", "rows as text\n")
        cases = {
            "undeclared": ({}, stray, ["lag: data/stray.db: store-shaped (a SQLite name) and named by neither "
                                       "cli.json's `store` nor `renders`"]),
            "no kind": ({"TODO.md": None}, None, ["lag: TODO.md: declared (`renders` entry `TODO.md`) with no kind "
                                                  "in cli.json's `kinds`"]),
            "version": ({}, behind, ["lag: data/app.db: dynamic, PRAGMA user_version is 1 but cli.json's "
                                     "schema_version is 2 (the file is not migrated, or cli.json is stale)"]),
            "not sqlite": ({}, not_sqlite, ["lag: data/app.db: dynamic, but not a SQLite file (ST1: a service's "
                                            "records are one SQLite file)"]),
            "writable": ({}, writable, ["lag: TODO.md: static, but writable (mode 0644); a static store sits at 0444 (ST2)"]),
            "header": ({"TODO.md": dict(FX.STATIC, producer="kb render")}, None, [
                "lag: TODO.md: static, but its first 2048 bytes do not name its producer `kb render` "
                "(ST2: a generated header, or a field)"]),
            "regen": ({}, edited, ["lag: TODO.md: static, regen `store.sh render` does not reproduce it "
                                   "(first difference at line 3)"]),
        }
        for label, (kinds, change, want) in cases.items():
            with self.subTest(label):
                shutil.rmtree(self.tmp / "r", ignore_errors=True)
                r = self.base(**kinds)
                if change:
                    change(r)
                self.assertEqual(self.red(r), want)

    def test_immutable_is_not_regenerated_and_a_render_glob_is_one_row_per_file(self):
        r = self.base(**{"TODO.md": None})
        doc = json.loads((r / "cli.json").read_text())
        doc["renders"] = {"out/*.txt": "render"}
        doc["kinds"]["out/*.txt"] = {"kind": "static", "producer": "store.sh render", "immutable": True}
        write(r / "cli.json", json.dumps(doc))
        os.remove(r / "TODO.md")
        for n in ("a", "b"):
            write(r / "out" / f"{n}.txt", "made by store.sh render\n", 0o444)
        res = self.one(r)
        self.assertEqual((res["status"], res["lines"]), ("ok", [
            "data/app.db: dynamic (store `data/app.db`; user_version 2)",
            "out/a.txt: static (renders `out/*.txt`)",
            "out/b.txt: static (renders `out/*.txt`)"]))

    def test_a_live_wal_leaves_the_version_unread_never_guessed(self):
        r = self.base()
        os.remove(r / "data" / "app.db")
        FX._db(r / "data" / "app.db", 1)                  # behind: red without a WAL (above)
        con = sqlite3.connect(r / "data" / "app.db")
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("INSERT INTO rows VALUES (1)")
        con.commit()
        try:                                              # held open: the -wal is non-empty while the check reads
            self.assertGreater((r / "data" / "app.db-wal").stat().st_size, 0)
            res = self.one(r)
        finally:
            con.close()
        self.assertEqual(res["status"], "ok", res)
        self.assertIn("data/app.db: dynamic (store `data/app.db`; user_version unread; "
                      "a non-empty -wal may hold a newer header)", res["lines"])

    def test_a_regen_that_cannot_run_is_never_ok(self):
        r = self.base()
        shutil.rmtree(r / ".git")
        res = self.one(r)
        self.assertEqual((res["status"], res["lines"]), ("unchecked", ["not a git repo: no scratch copy to run regen in"]))
        shutil.rmtree(self.tmp / "r")
        r = self.base()
        res = self.cli_json("one", "stores-classified", r, env={"CHECKS_REBUILD_ACTIVE": "1"})[1]["results"][0]
        self.assertEqual((res["status"], res["lines"]), ("unchecked", ["nested inside a rebuild: regen not run again"]))

    def test_a_regen_that_fails_or_hangs_is_a_finding_naming_how(self):
        r = self.base()
        render = 'render) rm -f TODO.md; printf'
        cli = (r / "store.sh").read_text()
        for label, body, want in (
                ("exit", cli.replace(render, 'render) echo "no store here" >&2; exit 4; printf'),
                 "static, regen `store.sh render` exited 4: no store here"),
                ("no file", cli.replace(render, 'render) rm -f TODO.md; exit 0; printf'),
                 "static, regen `store.sh render` did not render it"),
                ("hang", cli.replace(render, 'render) sleep 30; printf'),
                 "static, regen `store.sh render` did not finish in 1s")):
            with self.subTest(label):
                write(r / "store.sh", body, 0o755)
                old = stores.REGEN_TIMEOUT
                stores.REGEN_TIMEOUT = 1.0
                try:
                    rep = stores.inventory(r, run_regen=True)
                finally:
                    stores.REGEN_TIMEOUT = old
                self.assertEqual(stores.verdict(rep), ("fail", [f"TODO.md: {want}"]))

    def test_no_store_is_ok_and_a_broken_cli_json_is_unchecked(self):
        r = self.base()
        write(r / "cli.json", json.dumps({"cli": "store.sh", "verbs": ["render"]}))
        shutil.rmtree(r / "data")
        os.chmod(r / "TODO.md", 0o644)
        os.remove(r / "TODO.md")
        res = self.one(r)
        self.assertEqual((res["status"], res["lines"]),
                         ("ok", ["no store: nothing store-shaped on disk, and cli.json declares none"]))
        write(r / "cli.json", json.dumps({"cli": "store.sh", "verbs": ["render"], "kinds": {"gone.db": {"kind": "dynamic"}}}))
        res = self.one(r)
        self.assertEqual(res["status"], "unchecked")
        self.assertIn("kinds-declared", res["lines"][0])

    def test_a_home_path_is_said_not_judged(self):
        """`~/...` passes contract.inside as a folder named `~` (TODO.md): the row says
        it was not read, rather than looking in the home folder or claiming no file."""
        r = self.base()
        doc = json.loads((r / "cli.json").read_text())
        doc["store"] = ["data/app.db", "~/.app/rows.tsv"]
        doc["kinds"]["~/.app/rows.tsv"] = {"kind": "static", "producer": "p", "immutable": True}
        write(r / "cli.json", json.dumps(doc))
        res = self.one(r)
        self.assertEqual(res["status"], "ok", res)
        self.assertIn("~/.app/rows.tsv: static (store `~/.app/rows.tsv`; no file on disk; a `~` path: read as a "
                      "folder named `~` in the repo, never expanded, so not judged)", res["lines"])

    def test_the_report_finds_what_the_check_finds_repo_by_repo(self):
        """The seam: `checks stores` and stores-classified read one inventory, so a
        repo's report findings are the check's lines without the `lag: ` prefix, and
        each repo's status is the check's (regen aside: here none is declared)."""
        ws = self.tmp / "ws"
        good = FX.passing(ws / "good").repo
        bad = FX.failing(ws / "bad").repo
        for r in (good, bad):
            write(r / "CLAUDE.md", "# r\n")
            doc = json.loads((r / "cli.json").read_text())
            doc["kinds"]["TODO.md"] = {"kind": "static", "producer": "store.sh render", "immutable": True}
            write(r / "cli.json", json.dumps(doc))
        code, rep = self.cli_json("stores", ws)
        self.assertEqual(code, 0)
        got = {Path(repo["repo"]).resolve(): repo for repo in rep["repos"]}
        for r in (good, bad):
            res = self.one(r)
            mine = got[r.resolve()]
            self.assertEqual(mine["status"], res["status"])
            if res["status"] == "fail":
                self.assertEqual([f"lag: {s['path']}: {f}" for s in mine["stores"] for f in s["findings"]], res["lines"])
        self.assertEqual(got[bad.resolve()]["status"], "fail")
        self.assertEqual(rep["counts"], {"stores": 7, "dynamic": 3, "static": 2, "none": 2, "undeclared": 1,
                                         "findings": 6})

    def test_the_report_text_and_its_bad_root(self):
        ws = self.tmp / "ws"
        r = FX.passing(ws / "good").repo
        write(r / "CLAUDE.md", "# r\n")
        p = run_cli("stores", ws)          # two locations: the repo, and the top (as `checks all` walks)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("  TODO.md: static (renders `TODO.md`; regen not run (the report; "
                      "`checks one stores-classified <repo>` runs it))", p.stdout)
        self.assertIn(f"checks stores {ws.resolve()}: 2 store(s) in 1 of 2 location(s): 1 dynamic, 1 static, "
                      "0 with no kind (0 not declared in cli.json); 0 finding(s); 0 UNCHECKED location(s); regen not run",
                      p.stdout)
        p = run_cli("stores", self.tmp / "nowhere")
        self.assertEqual(p.returncode, 2)
        self.assertIn("no workspace top", p.stderr)
