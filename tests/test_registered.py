"""registered (PLAN-architecture.md §6 "Every tool registered", §9 step 10.1)
and `checks tools`, the collected list over the same reading
(checkslib/registry.py): each rule alone, from the passing fixture, turns it
red with its one line and undoing it turns it green (the counterfactual of
every rule); the states that must not be ok (a cli.json that cannot be read);
that it runs only when lags are asked for; services-valid gating `stores`
pre-commit; and the seam, the list's findings equal to the check's, repo by repo."""
import importlib.util
import json
from pathlib import Path

from tests.helpers import TOOL_ROOT, Case, run_cli, write

_spec = importlib.util.spec_from_file_location("fx_registered", TOOL_ROOT / "source" / "fixtures" / "registered.py")
FX = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(FX)

LINE = "r: r: keeps rows and notes [stores: ./data.db, notes.json; reads: row.v1; emits: note.v1; verbs: check]"


class Registered(Case):
    def base(self, **change):
        """The passing fixture's repo, its services.json fields changed (None removes one)."""
        r = FX.passing(self.tmp).repo
        if change:
            self.edit(r, **change)
        return r

    def edit(self, r, **change):
        doc = json.loads((r / "services.json").read_text())
        for k, v in change.items():
            doc.pop(k, None) if v is None else doc.__setitem__(k, v)
        write(r / "services.json", json.dumps(doc))

    def one(self, r, check="registered"):
        return self.cli_json("one", check, r)[1]["results"][0]

    def red(self, r):
        res = self.one(r)
        self.assertEqual(res["status"], "fail", res)
        self.assertTrue(all(l.startswith("lag: ") for l in res["lines"]), res["lines"])
        return res["lines"]

    def test_passing_is_ok_and_prints_its_line_in_the_list(self):
        res = self.one(self.base())
        self.assertEqual((res["status"], res["lines"]), ("ok", [LINE]))

    def test_no_services_json_is_red(self):
        r = self.base()
        (r / "services.json").unlink()
        self.assertEqual(self.red(r), ["lag: no services.json: this repo is not registered "
                                       "(PLAN-architecture.md §6 \"Every tool registered\")"])

    def test_each_rule_alone_is_red_and_undoing_it_is_green(self):
        cases = [
            ("no description", {"description": None}, "lag: services.json: no `description`: the one line"),
            ("a store cli.json does not declare", {"stores": ["data.db", "notes.json", "cache.db"]},
             "lag: services.json: stores-declared: $.stores: `cache.db` is not a store cli.json declares"),
            ("a declared store not listed", {"stores": ["data.db"]},
             "lag: services.json: `stores` lacks `notes.json`, a store cli.json declares"),
            ("no stores at all while cli.json declares two", {"stores": None},
             "lag: services.json: `stores` lacks `data.db`, a store cli.json declares"),
            ("a description over two lines", {"description": "one\ntwo"},
             "lag: services.json: description-one-line: $.description: more than one line"),
        ]
        for what, change, want in cases:
            with self.subTest(what):
                r = self.base(**change)
                lines = self.red(r)
                self.assertTrue(lines[0].startswith(want), lines)
                if what != "no stores at all while cli.json declares two":
                    self.assertEqual(len(lines), 1, lines)
                self.edit(r, **PASSING_FIELDS)               # undo: back to the passing entry
                self.assertEqual(self.one(r)["status"], "ok")

    def test_no_store_anywhere_needs_no_stores(self):
        r = self.base(stores=None)
        write(r / "cli.json", json.dumps({"cli": "store.sh", "verbs": ["add", "list"]}))
        self.assertEqual(self.one(r)["status"], "ok")
        (r / "cli.json").unlink()
        self.assertEqual(self.one(r)["status"], "ok")
        self.edit(r, stores=["data.db"])                 # owning a store nothing declares
        self.assertIn("(it declares none)", self.red(r)[0])

    def test_an_unreadable_cli_json_is_unchecked_never_ok(self):
        r = self.base(stores=[])
        write(r / "cli.json", "{nope")
        res = self.one(r)
        self.assertEqual(res["status"], "unchecked", res)
        self.assertIn("cli.json does not parse: whether `stores` lists every store it declares is unread", res["lines"][0])
        self.edit(r, stores=["data.db"])                 # an entry it cannot show declared is a finding
        self.assertIn("cli.json does not parse, so no entry can be shown declared", self.red(r)[0])

    def test_runs_only_when_lags_are_asked_for(self):
        r = self.base(description=None)
        _, rep = self.cli_json("run", r)
        self.assertNotIn("registered", [x["check"] for x in rep["results"]])
        _, rep = self.cli_json("run", r, "--roles", "lag")
        self.assertEqual([x["status"] for x in rep["results"] if x["check"] == "registered"], ["fail"])

    def test_services_valid_gates_stores_pre_commit_and_ignores_a_missing_description(self):
        r = self.base(description=None)
        self.assertEqual(self.one(r, "services-valid")["status"], "ok")
        self.edit(r, stores=["data.db", "notes.json", "cache.db"])
        res = self.one(r, "services-valid")
        self.assertEqual(res["status"], "fail")
        self.assertEqual(res["lines"], ["services.json: stores-declared: $.stores: `cache.db` is not a store cli.json declares"])

    def test_shapes_takes_only_reads_and_emits(self):
        r = self.base(shapes={"reads": ["a"], "writes": ["b"]})
        res = self.one(r, "services-valid")
        self.assertEqual(res["status"], "fail")
        self.assertIn("unknown key `writes`", res["lines"][0])


PASSING_FIELDS = {"description": "r: keeps rows and notes", "stores": ["./data.db", "notes.json"],
                     "shapes": {"reads": ["row.v1"], "emits": ["note.v1"]}}


class Tools(Case):
    def ws(self):
        ws = self.tmp / "ws"
        good = FX.passing(ws / "good").repo
        bad = FX.failing(ws / "bad").repo
        none = FX.passing(ws / "none").repo
        (none / "services.json").unlink()
        for r in (good, bad, none):
            write(r / "CLAUDE.md", "# r\n")
        return ws, good, bad, none

    def test_the_list_finds_what_the_check_finds_repo_by_repo(self):
        """The seam: `checks tools` and registered read one entry, so a repo's
        findings in the list are the check's lines without `lag: `, and each
        repo's status is the check's."""
        ws, good, bad, none = self.ws()
        code, rep = self.cli_json("tools", ws)
        self.assertEqual(code, 0)
        got = {Path(t["repo"]).resolve(): t for t in rep["tools"]}
        for r in (good, bad, none):
            res = self.cli_json("one", "registered", r)[1]["results"][0]
            mine = got[r.resolve()]
            self.assertEqual(mine["status"], res["status"])
            self.assertEqual([f"lag: {f}" for f in mine["findings"]], res["lines"] if res["status"] == "fail" else [])
        self.assertEqual(got[good.resolve()]["description"], "r: keeps rows and notes")
        self.assertEqual([got[r.resolve()]["status"] for r in (good, bad, none)], ["ok", "fail", "fail"])
        # four locations: the three repos and the top (as `checks all` walks), which has no services.json
        self.assertEqual(rep["counts"], {"locations": 4, "registered": 1, "no_description": 1, "no_services_json": 2,
                                         "unchecked": 0, "findings": 5})

    def test_the_list_text_and_its_bad_root(self):
        ws, *_ = self.ws()
        p = run_cli("tools", ws)
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn(LINE, p.stdout)
        self.assertIn("r: (no description) [stores: data.db, cache.db; verbs: check]", p.stdout)
        self.assertIn("(not registered: no services.json)", p.stdout)
        self.assertIn(f"checks tools {ws.resolve()}: 4 location(s), 1 registered; 2 with no services.json, "
                      "1 with no description; 5 finding(s); 0 UNCHECKED", p.stdout)
        p = run_cli("tools", self.tmp / "nowhere")
        self.assertEqual(p.returncode, 2)
        self.assertIn("no workspace top", p.stderr)
