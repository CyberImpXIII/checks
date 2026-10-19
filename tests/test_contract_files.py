"""The contract files (PLAN-routing-tree.md §14.8, PLAN-repo-setup.md §7.10):
their schemas (each x-rule implemented under its id, only enforced keywords,
nothing undeclared), each rule shown red alone, and the three checks that read
them: services-valid, accessor, registry-matches. Every check is run through
the CLI (`checks one`), the way a repo runs it."""
import copy
import os
import json
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import Case, TOOL_ROOT, repo, write
from checkslib import checkjson, contract, helptext

HELP = """#!/usr/bin/env bash
case "${{1:-}}" in
  help|"") printf '{prog} <verb>\\n\\n{lines}' ;;
  *) echo "$1" ;;
esac
"""


def cli(path, *verbs, prog=None):
    """An executable whose `help` lists `verbs`, each as `  <verb>   text`."""
    lines = "".join(f"  {v}    does {v}\\n" for v in verbs)
    return write(path, HELP.format(prog=prog or Path(path).name, lines=lines), 0o755)


def used_keywords(node):
    used = set(node)
    for sub in (node.get("properties") or {}).values():
        used |= used_keywords(sub)
    for k in ("items", "additionalProperties"):
        if isinstance(node.get(k), dict):
            used |= used_keywords(node[k])
    return used


class Schemas(unittest.TestCase):
    def test_each_schema_loads_and_uses_only_enforced_keywords(self):
        for name in contract.SCHEMAS:
            with self.subTest(name):
                s = contract.schema(name)                      # load refuses an unenforced keyword
                self.assertLessEqual(used_keywords(s) - checkjson.ANNOTATIONS, checkjson.KEYWORDS)

    def test_x_rules_equal_the_rules_implemented_per_file(self):
        for name in contract.SCHEMAS:
            with self.subTest(name):
                self.assertEqual(set(contract.schema(name)["x-rules"]), set(contract.RULES[name]))
        self.assertEqual(set(contract.RULES), set(contract.SCHEMAS))

    def test_every_object_refuses_an_undeclared_key(self):
        """additionalProperties false at every object level: nothing undeclared."""
        def objects(node, where):
            if node.get("type") == "object":
                yield where, node
            for k, sub in (node.get("properties") or {}).items():
                yield from objects(sub, f"{where}.{k}")
            if isinstance(node.get("items"), dict):
                yield from objects(node["items"], f"{where}[]")
        # A map (name -> value) has open keys by nature; each one names the
        # x-rule that holds its keys, so no map is left unchecked.
        maps = {"cli.json.not_verbs": (contract.CLI, "not-verbs-exact"),
                "cli.json.not_exported": (contract.CLI, "not-exported-declared"),
                "cli.json.renders": (contract.CLI, "renders-declared"),
                "cli.json.kinds": (contract.CLI, "kinds-declared"),
                "cli.json.read.env": (contract.CLI, "read-env"),
                "cli.json.read.verbs": (contract.CLI, "read-declared")}
        seen = set()
        for name in contract.SCHEMAS:
            for where, node in objects(contract.schema(name), name):
                with self.subTest(where):
                    if where in maps:
                        seen.add(where)
                        self.assertIsInstance(node.get("additionalProperties"), dict)
                        self.assertIn(maps[where][1], contract.RULES[maps[where][0]])
                    else:
                        self.assertIs(node.get("additionalProperties"), False)
        self.assertEqual(seen, set(maps))

    def test_additional_properties_false_is_enforced(self):
        s = {"type": "object", "additionalProperties": False, "properties": {"a": {"type": "string"}}}
        self.assertEqual(checkjson.structure({"a": "x"}, s), [])
        self.assertEqual(checkjson.structure({"a": "x", "b": 1}, s), ["schema: $: unknown key `b`"])
        self.assertEqual(checkjson.structure({"a": "x", "b": 1}, dict(s, additionalProperties={"type": "number"})), [])

    def test_a_non_schema_additional_properties_is_refused(self):
        path = TOOL_ROOT / "tests" / "_planted_ap.json"
        try:
            path.write_text(json.dumps({"type": "object", "additionalProperties": True, "x-rules": {}}))
            with self.assertRaises(checkjson.SchemaError):
                checkjson.load(path)
        finally:
            path.unlink()


SERVICES = {"name": "r", "tags": ["t"], "services": [{"service": "check", "run": "dev.sh", "verbs": ["check"]},
                                                     {"service": "write", "run": "store.sh", "verbs": ["add"]}]}
# The registration fields (PLAN-architecture.md §9 step 10.1); `./app.db` is cli.json's `app.db`.
SERVICES_ALL = dict(SERVICES, description="r: keeps rows", stores=["./app.db"],
                    shapes={"reads": ["row.v1"], "emits": ["note.v1"]})
CLIDOC = {"store": "app.db", "cli": "store.sh", "verbs": ["add", "list"]}
# The harness's shape (.claude/cli.json): every other command named, with why.
CLIDOC_ALL = dict(CLIDOC, _comment="prose", not_verbs={"drop": "the store's owner only"},
                  not_exported={"./app.db": "private: never exported"},
                  renders={"TODO.md": "list", "out/*.txt": "list"},
                  kinds={"./app.db": {"kind": "dynamic", "schema_version": 1, "export": "list"},
                         "TODO.md": {"kind": "static", "producer": "store.sh list", "regen": ["store.sh", "list"]},
                         "out/*.txt": {"kind": "static", "producer": "store.sh list", "immutable": True}},
                  read={"fixture": "fx", "env": {"APP_DATA": "{fixture}"},
                        "verbs": {"list": {"args": ["--json"], "volatile": ["at", "rows.*.seen"]}}})


def _read_verb(d, **spec):
    d["read"]["verbs"]["list"].update(spec)
NODEDOC = {"rebuild": ["true"], "generated": ["out.txt"], "record": ["*.md"], "children": ["kid"], "registry": "reg.json"}
VERIFYDOC = {"items": [{"item": "a", "status": "same"}, {"item": "b", "status": "differs", "detail": "line 2"}]}


def _svc(d):
    d["services"].append({"service": "check", "run": "dev.sh", "verbs": ["check"]})


# (file, rule, mutate the clean doc, a finding the rule gives)
RULE_MUTANTS = [
    (contract.SERVICES, "one-check", _svc, "2 `check` entries"),
    (contract.SERVICES, "run-inside", lambda d: d["services"][1].update(run="../store.sh"), "`../store.sh` is not a path inside"),
    (contract.SERVICES, "run-executable", lambda d: d["services"][1].update(run="nope.sh"), "`nope.sh` does not exist"),
    (contract.SERVICES, "verb-implemented", lambda d: d["services"][1]["verbs"].append("purge"), "does not implement `purge`"),
    (contract.SERVICES, "unique", lambda d: d["tags"].append("t"), "tag `t` given twice"),
    (contract.SERVICES, "unique", lambda d: d["stores"].append("app.db"), "store `app.db` given twice"),
    (contract.SERVICES, "unique", lambda d: d["shapes"]["emits"].append("note.v1"), "shape id `note.v1` given twice"),
    (contract.SERVICES, "description-one-line", lambda d: d.update(description="one\ntwo"), "more than one line"),
    (contract.SERVICES, "description-one-line", lambda d: d.update(description="   "), "$.description: blank"),
    (contract.SERVICES, "stores-declared", lambda d: d["stores"].append("cache.db"),
     "$.stores: `cache.db` is not a store cli.json declares"),
    (contract.SERVICES, "write-declared", lambda d: d["services"][1]["verbs"].append("drop"), "`drop` is not a verb cli.json declares"),
    (contract.CLI, "paths-inside", lambda d: d.update(store="/abs/app.db"), "`/abs/app.db` is not a path inside"),
    (contract.CLI, "cli-executable", lambda d: d.update(cli="plain.txt"), "`plain.txt` is not executable"),
    (contract.CLI, "verb-implemented", lambda d: d["verbs"].append("purge"), "does not implement `purge`"),
    (contract.CLI, "unique", lambda d: d.update(store=["app.db", "./app.db"]), "path `app.db` given twice"),
    (contract.CLI, "not-verbs-exact", lambda d: d["not_verbs"].pop("drop"), "`drop` (from `store.sh help`) is in neither"),
    (contract.CLI, "not-exported-declared", lambda d: d["not_exported"].update({"gone.db": "x"}),
     "$.not_exported: `gone.db` is not an entry of $.store"),
    (contract.CLI, "renders-declared", lambda d: d["renders"].update({"TODO.md": "render"}),
     "$.renders.TODO.md: `render` is not a verb $.verbs lists"),
    (contract.CLI, "renders-declared", lambda d: d["renders"].update({"../up.md": "list"}),
     "$.renders: `../up.md` is not a path inside the repo"),
    (contract.CLI, "kinds-declared", lambda d: d["kinds"].update({"gone.db": {"kind": "static", "producer": "p", "immutable": True}}),
     "$.kinds.gone.db: `gone.db` is not an entry of $.store or a key of $.renders"),
    (contract.CLI, "read-declared", lambda d: d["read"]["verbs"].update(drop={"args": ["--json"]}),
     "$.read.verbs.drop: `drop` is not a verb $.verbs lists"),
    (contract.CLI, "read-json", lambda d: _read_verb(d, args=["-q"]), "$.read.verbs.list.args: no `--json`"),
    (contract.CLI, "read-fixture", lambda d: d["read"].update(fixture="nofx"), "`nofx` is not a folder in the repo"),
    (contract.CLI, "read-env", lambda d: d["read"]["env"].update(CHECKS_PARAMS="{}"), "`CHECKS_PARAMS` is the checks runner's own"),
    (contract.CLI, "volatile-paths", lambda d: _read_verb(d, volatile=["at", "rows..seen"]), "`rows..seen` is not dot-separated keys"),
    (contract.NODE, "paths-inside", lambda d: d["generated"].append("../x"), "`../x` is not a path inside"),
    (contract.NODE, "unique", lambda d: d["record"].append("*.md"), "path `*.md` given twice"),
    (contract.NODE, "generated-exact", lambda d: d["generated"].append("gen/*.txt"), "`gen/*.txt` is a glob"),
    (contract.NODE, "disjoint", lambda d: d["generated"].append("kid/x.txt"), "`kid/x.txt` lies under a child"),
    (contract.VERIFY, "unique", lambda d: d["items"].append({"item": "a", "status": "same"}), "item `a` given twice"),
]


class Rules(Case):
    def setUp(self):
        super().setUp()
        self.r = self.tmp / "r"
        cli(self.r / "dev.sh", "check")
        cli(self.r / "store.sh", "add", "list", "drop")
        (self.r / "fx").mkdir()
        write(self.r / "plain.txt", "x\n")
        self.clean = {contract.SERVICES: SERVICES_ALL, contract.CLI: CLIDOC_ALL, contract.NODE: NODEDOC, contract.VERIFY: VERIFYDOC}
        for name, doc in self.clean.items():
            write(self.r / name, json.dumps(doc))

    def read(self, name, doc):
        write(self.r / name, json.dumps(doc))
        helptext._CACHE.clear()
        return contract.read(self.r, name)

    def test_the_clean_documents_have_no_finding(self):
        for name, doc in self.clean.items():
            with self.subTest(name):
                got, found = self.read(name, doc)
                self.assertEqual((got, found), (doc, []))

    def test_each_rule_mutant_is_red_and_only_its_rule_catches_it(self):
        self.assertEqual({(f, r) for f, r, *_ in RULE_MUTANTS}, {(f, r) for f in contract.RULES for r in contract.RULES[f]})
        for name, rule, fn, want in RULE_MUTANTS:
            with self.subTest(name=name, rule=rule):
                doc = copy.deepcopy(self.clean[name])
                fn(doc)
                _, found = self.read(name, doc)
                self.assertTrue(any(f.startswith(f"{name}: {rule}: ") and want in f for f in found), found)
                without = {name: {k: v for k, v in contract.RULES[name].items() if k != rule}}
                with mock.patch.dict(contract.RULES, without):
                    _, found = self.read(name, doc)
                self.assertFalse([f for f in found if want in f], found)
                write(self.r / name, json.dumps(self.clean[name]))

    def test_renders_is_the_object_store_guard_reads(self):
        """tools/hooks' store-guard reads `renders` as {path: verb} (hooks
        6eb9c65) and skips any other shape, letting every write pass: the
        schema takes hooks' own example and refuses a list or an empty verb."""
        cli = contract.schema(contract.CLI)
        ok = {"cli": "g.sh", "verbs": ["render"], "renders": {"TODO.md": "render"}}
        self.assertEqual(checkjson.structure(ok, cli), [])
        for bad in (["TODO.md"], {"TODO.md": ""}, {"TODO.md": ["render"]}):
            with self.subTest(renders=bad):
                self.assertTrue(checkjson.structure(dict(ok, renders=bad), cli))

    def test_not_verbs_each_way_it_can_be_wrong(self):
        name = contract.CLI
        cases = {
            "ghost": (dict(CLIDOC_ALL, not_verbs={"drop": "x", "purge": "x"}), "`purge` is not a command `store.sh help` lists"),
            "overlap": (dict(CLIDOC_ALL, not_verbs={"drop": "x", "add": "x"}), "`add` is also in verbs"),
        }
        for label, (doc, want) in cases.items():
            with self.subTest(label):
                _, found = self.read(name, doc)
                self.assertEqual([f for f in found if f.startswith(f"{name}: not-verbs-exact: ")],
                                 [f"{name}: not-verbs-exact: $.not_verbs: {want}"], found)
        # without not_verbs, verbs may be a subset of the help: `drop` unnamed is fine
        self.assertEqual(self.read(name, CLIDOC), (CLIDOC, []))

    def test_read_each_way_it_can_be_wrong(self):
        """The branches the one mutant per rule leaves unshown."""
        name = contract.CLI
        no_fx = copy.deepcopy(CLIDOC_ALL)
        del no_fx["read"]["fixture"]
        no_fx["read"]["verbs"]["list"]["args"] = ["--json", "--dir", "{fixture}"]
        cases = {
            "placeholder without a fixture": (no_fx, "read-fixture", [
                "$.read.verbs.list.args: uses `{fixture}` but $.read names no fixture",
                "$.read.env.APP_DATA: uses `{fixture}` but $.read names no fixture"]),
            "fixture outside": (dict(CLIDOC_ALL, read=dict(CLIDOC_ALL["read"], fixture="../fx")), "read-fixture",
                                ["$.read.fixture: `../fx` is not a path inside the repo"]),
            "no verb": (dict(CLIDOC_ALL, read={"verbs": {}}), "read-declared",
                        ["$.read.verbs: names no verb: a `read` that declares nothing runs nothing"]),
            "env name": (dict(CLIDOC_ALL, read=dict(CLIDOC_ALL["read"], env={"BAD-NAME": "x"})), "read-env",
                         ["$.read.env: `BAD-NAME` is not an environment variable name"]),
            "volatile twice": (dict(CLIDOC_ALL, read=dict(CLIDOC_ALL["read"], verbs={"list": {"args": ["--json"], "volatile": ["at", "at"]}})),
                               "volatile-paths", ["$.read.verbs.list.volatile: path `at` given twice"]),
        }
        for label, (doc, rule, want) in cases.items():
            with self.subTest(label):
                _, found = self.read(name, doc)
                self.assertEqual([f for f in found if f.startswith(f"{name}: {rule}: ")],
                                 [f"{name}: {rule}: {w}" for w in want], found)

    def test_kinds_each_way_it_can_be_wrong(self):
        """kinds-declared's branches beyond the one mutant: each alone, each with its own line."""
        name = contract.CLI
        dyn, sta = CLIDOC_ALL["kinds"]["./app.db"], CLIDOC_ALL["kinds"]["TODO.md"]

        def kinds(**over):
            return dict(CLIDOC_ALL, kinds=dict(CLIDOC_ALL["kinds"], **over))
        cases = {
            "dynamic without its fields": (kinds(**{"./app.db": {"kind": "dynamic"}}), [
                "$.kinds../app.db: a dynamic store names its `schema_version`",
                "$.kinds../app.db: a dynamic store names its `export`"]),
            "export not a verb": (kinds(**{"./app.db": dict(dyn, export="dump")}),
                                  ["$.kinds../app.db.export: `dump` is not a verb $.verbs lists"]),
            "dynamic with a static field": (kinds(**{"./app.db": dict(dyn, producer="p")}),
                                            ["$.kinds../app.db: `producer` belongs to a static store, not a dynamic one"]),
            "static with a dynamic field": (kinds(**{"TODO.md": dict(sta, schema_version=1)}),
                                            ["$.kinds.TODO.md: `schema_version` belongs to a dynamic store, not a static one"]),
            "static without a producer": (kinds(**{"TODO.md": {"kind": "static", "immutable": True}}),
                                          ["$.kinds.TODO.md: a static store names its `producer`"]),
            "static with both": (kinds(**{"TODO.md": dict(sta, immutable=True)}),
                                 ["$.kinds.TODO.md: a static store has exactly one of `regen` (the command) or `immutable: true`"]),
            "static with neither": (kinds(**{"TODO.md": {"kind": "static", "producer": "p"}}),
                                    ["$.kinds.TODO.md: a static store has exactly one of `regen` (the command) or `immutable: true`"]),
            "regen outside": (kinds(**{"TODO.md": dict(sta, regen=["/bin/sh", "-c", "x"])}),
                              ["$.kinds.TODO.md.regen: `/bin/sh` is not a path inside the repo (the copy's own program runs)"]),
        }
        for label, (doc, want) in cases.items():
            with self.subTest(label):
                _, found = self.read(name, doc)
                self.assertEqual([f for f in found if f.startswith(f"{name}: kinds-declared: ")],
                                 [f"{name}: kinds-declared: {w}" for w in want], found)

    def test_kinds_shape_is_held_by_the_schema(self):
        for kinds, want in (({"TODO.md": {}}, "$.kinds.TODO.md: missing `kind`"),
                            ({"TODO.md": {"kind": "cached"}}, "is not one of dynamic, static"),
                            ({"TODO.md": {"kind": "static", "producer": "p", "immutable": False}}, "is not one of True"),
                            ({"./app.db": {"kind": "dynamic", "schema_version": "1", "export": "list"}}, "is not integer"),
                            ({"TODO.md": {"kind": "static", "producer": "p", "regen": []}}, "fewer than 1 item"),
                            ({"TODO.md": {"kind": "static", "producr": "p"}}, "unknown key `producr`")):
            with self.subTest(want):
                got, found = self.read(contract.CLI, dict(CLIDOC_ALL, kinds=kinds))
                self.assertIsNone(got)
                self.assertIn(want, "\n".join(found))

    def test_read_shape_is_held_by_the_schema(self):
        for read, want in (({"verbs": {"list": {}}}, "$.read.verbs.list: missing `args`"),
                           ({"verbs": {"list": {"args": ["--json"], "volatle": []}}}, "unknown key `volatle`"),
                           ({"fixture": "fx"}, "$.read: missing `verbs`"),
                           ({"verbs": {}, "env": {"A": 1}}, "$.read.env.A: 1 is not string")):
            with self.subTest(want):
                got, found = self.read(contract.CLI, dict(CLIDOC_ALL, read=read))
                self.assertIsNone(got)
                self.assertIn(want, "\n".join(found))

    def test_store_is_optional_and_cli_is_not(self):
        """PLAN-architecture.md §12.1: every repo declares its verbs, store or none."""
        bare = {"cli": "store.sh", "verbs": ["add"]}
        self.assertEqual(self.read(contract.CLI, bare), (bare, []))
        got, found = self.read(contract.CLI, {"verbs": ["add"]})
        self.assertIsNone(got)
        self.assertIn("$: missing `cli`", "\n".join(found))
        self.assertEqual(contract.store_files(bare, ["app.db"]), [])

    def test_not_verbs_shape_is_held_by_the_schema(self):
        # the counterfactual: the keys added for .claude/cli.json do not open the
        # schema; a misspelt key and a reason that is not a string stay red
        for doc, want in ((dict(CLIDOC_ALL, not_verbz={}), "unknown key `not_verbz`"),
                          (dict(CLIDOC_ALL, not_verbs={"drop": ""}), "$.not_verbs.drop: shorter than 1"),
                          (dict(CLIDOC_ALL, not_verbs=["drop"]), "$.not_verbs: [\"drop\"] is not object")):
            with self.subTest(want):
                got, found = self.read(contract.CLI, doc)
                self.assertIsNone(got)
                self.assertIn(want, "\n".join(found))

    def test_absent_broken_and_misshapen(self):
        (self.r / contract.CLI).unlink()
        self.assertEqual(contract.read(self.r, contract.CLI), (None, []))
        write(self.r / contract.CLI, "{nope")
        doc, found = contract.read(self.r, contract.CLI)
        self.assertIsNone(doc)
        self.assertIn("cli.json: does not parse", found[0])
        doc, found = self.read(contract.SERVICES, dict(SERVICES, owner="x", services=[]))
        self.assertIsNone(doc)
        self.assertEqual(len(found), 2, found)                 # every structural finding, not only the first
        self.assertIn("unknown key `owner`", "\n".join(found))


class HelpText(unittest.TestCase):
    def test_commands_take_the_program_name_as_a_prefix(self):
        text = "usage\n\n  store.sh add    a row\n  ./store.sh list  rows\n  drop   gone\n      deeper  never\n"
        self.assertEqual(helptext.commands(text, "store.sh"), {"add", "list", "drop"})
        self.assertEqual(helptext.commands("  ./dev.sh check  x\n  test  y\n"), {"check", "test"})

    def test_a_help_with_no_command_lines_says_so(self):
        with self.subTest("nothing listed"):
            import tempfile
            d = Path(tempfile.mkdtemp())
            p = write(d / "quiet.sh", "#!/usr/bin/env bash\necho usage only\n", 0o755)
            self.assertEqual(helptext.listed(p, d), (None, "printed no command lines"))


class ServicesValid(Case):
    def one(self, r):
        return self.cli_json("one", "services-valid", r)[1]["results"][0]

    def test_no_services_json_is_unchecked_never_ok(self):
        res = self.one(repo(self.tmp / "r"))
        self.assertEqual(res["status"], "unchecked")
        self.assertIn("no services.json", res["lines"][0])

    def test_a_verb_the_cli_lacks_is_red_and_adding_it_is_green(self):
        r = repo(self.tmp / "r")
        cli(r / "dev.sh", "check")
        cli(r / "store.sh", "add")
        write(r / "services.json", json.dumps(dict(SERVICES, services=SERVICES["services"][:1] +
                                                   [{"service": "write", "run": "store.sh", "verbs": ["add", "list"]}])))
        res = self.one(r)
        self.assertEqual(res["status"], "fail")
        self.assertEqual(len(res["lines"]), 1, res["lines"])
        self.assertIn("`store.sh` does not implement `list` (its help lists: add)", res["lines"][0])
        cli(r / "store.sh", "add", "list")                    # the counterfactual: implement it
        self.assertEqual(self.one(r)["status"], "ok")

    def test_a_help_that_lists_nothing_is_red(self):
        r = repo(self.tmp / "r")
        write(r / "dev.sh", "#!/usr/bin/env bash\necho fine\n", 0o755)
        write(r / "services.json", json.dumps({"name": "r", "services": [SERVICES["services"][0]]}))
        res = self.one(r)
        self.assertEqual(res["status"], "fail")
        self.assertIn("`dev.sh help` printed no command lines", res["lines"][0])


class Accessor(Case):
    def one(self, r):
        return self.cli_json("one", "accessor", r)[1]["results"][0]

    def store(self, files=None, cli_doc=CLIDOC):
        r = repo(self.tmp / "r", dict({".gitignore": "*.db\n"}, **(files or {})))
        cli(r / "store.sh", "add", "list")
        write(r / "app.db", "")
        if cli_doc is not None:
            write(r / "cli.json", json.dumps(cli_doc))
        return r

    def test_no_store_and_no_cli_json_is_ok(self):
        self.assertEqual(self.one(repo(self.tmp / "r", {"a.py": "x = 1\n"}))["status"], "ok")

    def test_a_store_with_no_cli_json_is_red_unless_it_is_under_tests(self):
        r = repo(self.tmp / "r")
        write(r / "tests" / "fixture.db", "")
        write(r / ".cache" / "x.sqlite", "")
        self.assertEqual(self.one(r)["status"], "ok")
        write(r / "data" / "x.sqlite3", "")
        res = self.one(r)
        self.assertEqual((res["status"], res["lines"]), ("fail", ["data/x.sqlite3: a store with no cli.json naming its one CLI"]))

    def test_the_stores_param_adds_a_shape(self):
        r = repo(self.tmp / "r")
        write(r / "log.jsonl", "")
        self.assertEqual(self.one(r)["status"], "ok")
        write(r / "checks.json", json.dumps({"accessor": {"stores": ["*.jsonl"]}}))
        self.assertIn("log.jsonl: a store with no cli.json", self.one(r)["lines"][0])

    def test_a_second_store_cli_json_does_not_name_is_red(self):
        r = self.store()
        write(r / "other.db", "")
        res = self.one(r)
        self.assertEqual(res["lines"], ["other.db: a store cli.json does not name (one gated CLI per store)"])

    def test_a_read_around_the_cli_is_red_with_its_line_and_impl_exempts_it(self):
        r = self.store({"lib/db.py": "import x\nDB = 'app.db'\n", "notes.md": "app.db lives here\n",
                        "near.py": "a = 'myapp.db'\nb = 'app.dbx'\nc = 'app.db.bak'\n"})
        res = self.one(r)
        self.assertEqual((res["status"], res["lines"]),
                         ("fail", ["lib/db.py:2: names the store `app.db` around its CLI `store.sh`"]))
        write(r / "checks.json", json.dumps({"accessor": {"impl": ["lib/*"]}}))
        self.assertEqual(self.one(r)["status"], "ok")
        write(r / "checks.json", json.dumps({"accessor": {"exclude": ["lib/db.py"]}}))
        self.assertEqual(self.one(r)["status"], "ok")

    def test_the_cli_itself_may_name_the_store(self):
        r = self.store()
        write(r / "store.sh", (r / "store.sh").read_text() + "# opens app.db\n", 0o755)
        self.assertEqual(self.one(r)["status"], "ok")

    def test_a_store_list_and_a_glob(self):
        r = self.store({"x.py": "open('data/b.db')\n"}, cli_doc=dict(CLIDOC, store=["app.db", "data/*.db"]))
        write(r / "data" / "b.db", "")
        res = self.one(r)
        self.assertEqual(res["lines"], ["x.py:1: names the store `b.db` around its CLI `store.sh`"])

    def test_a_store_glob_matching_nothing_is_unchecked(self):
        r = repo(self.tmp / "r")
        cli(r / "store.sh", "add", "list")
        write(r / "cli.json", json.dumps(dict(CLIDOC, store="data/*.db")))
        res = self.one(r)
        self.assertEqual(res["status"], "unchecked")

    def test_a_json_store_counts_once_cli_json_declares_it(self):
        """PLAN-services.md §3 rule 1: no `stores` param, the declaration is enough."""
        r = repo(self.tmp / "r", {"todo.json": "{}\n", "report.sh": "jq . todo.json\n"})
        cli(r / "store.sh", "add", "list")
        self.assertEqual(self.one(r)["status"], "ok", "an undeclared *.json is not a store")
        write(r / "cli.json", json.dumps(dict(CLIDOC, store="todo.json")))
        res = self.one(r)
        self.assertEqual((res["status"], res["lines"]),
                         ("fail", ["report.sh:1: names the store `todo.json` around its CLI `store.sh`"]))

    def test_a_nested_repo_is_judged_in_its_own_row_not_the_parent(self):
        """The top's four 2026-10-09 findings were stores inside nested repos."""
        top = self.tmp / "top"
        write(top / "CLAUDE.md", "# top\n")                   # not a git repo, as the workspace top
        repo(top / "kid")
        write(top / "kid" / "data" / "k.db", "")
        self.assertEqual(self.one(top)["status"], "ok")
        self.assertEqual(self.one(top / "kid")["status"], "fail", "the kid still answers for its store")
        write(top / "plain" / "data" / "p.db", "")              # the counterfactual: not a repo, so the top's
        res = self.one(top)
        self.assertEqual(res["lines"], ["plain/data/p.db: a store with no cli.json naming its one CLI"])

    def test_a_cli_json_with_no_store_is_ok_until_a_store_appears(self):
        r = repo(self.tmp / "r", {"x.py": "open('app.db')\n"})
        cli(r / "store.sh", "add", "list")
        write(r / "cli.json", json.dumps({"cli": "store.sh", "verbs": ["add"]}))
        res = self.one(r)
        self.assertEqual((res["status"], res["lines"]), ("ok", []))
        write(r / "app.db", "")                                 # the counterfactual: a store it does not name
        res = self.one(r)
        self.assertEqual((res["status"], res["lines"]), ("fail", ["app.db: a store cli.json does not name (one gated CLI per store)"]))

    def test_a_broken_cli_json_is_red(self):
        r = self.store(cli_doc=dict(CLIDOC, verbs=["add", "purge"]))
        res = self.one(r)
        self.assertEqual(res["status"], "fail")
        self.assertIn("cli.json: verb-implemented: $.verbs: `store.sh` does not implement `purge`", res["lines"][0])


class StoresReadonly(Case):
    """PLAN-services.md §3 rule 2/5: a store its CLI writes whole sits at 0444;
    SQLite is not judged by mode. Each case changes one input."""

    def one(self, r):
        return self.cli_json("one", "stores-readonly", r)[1]["results"][0]

    def store(self, stores, files):
        r = repo(self.tmp / "r")
        cli(r / "store.sh", "add", "list")
        write(r / "cli.json", json.dumps(dict(CLIDOC, store=stores)))
        for rel, mode in files.items():
            write(r / rel, "x\n", mode)
        return r

    def test_mode_turns_the_result(self):
        r = self.store("todo.json", {"todo.json": 0o444})
        res = self.one(r)
        self.assertEqual((res["status"], res["lines"]), ("ok", ["read-only: todo.json"]))
        for mode in (0o644, 0o464, 0o446):                      # owner, group, other write bit: each red
            os.chmod(r / "todo.json", mode)
            with self.subTest(mode=oct(mode)):
                res = self.one(r)
                self.assertEqual((res["status"], res["lines"]),
                                 ("fail", [f"todo.json: writable (mode {mode:04o}); a store its CLI writes whole sits at 0444"]))

    def test_every_matched_file_of_a_glob_is_judged(self):
        res = self.one(self.store(["state/*"], {"state/a.json": 0o444, "state/b.tsv": 0o600}))
        self.assertEqual(res["lines"], ["state/b.tsv: writable (mode 0600); a store its CLI writes whole sits at 0444"])

    def test_sqlite_and_its_side_files_are_not_judged(self):
        res = self.one(self.store(["app.db", "app.db-wal", "x.sqlite3-journal"],
                                  {"app.db": 0o644, "app.db-wal": 0o644, "x.sqlite3-journal": 0o644}))
        self.assertEqual(res["status"], "unchecked", res["lines"])
        self.assertIn("every store is SQLite", res["lines"][0])
        res = self.one(self.store(["app.db", "t.json"], {"app.db": 0o644, "t.json": 0o444}))
        self.assertEqual((res["status"], res["lines"]), ("ok", ["read-only: t.json"]))

    def test_nothing_to_judge_is_unchecked_never_ok(self):
        self.assertEqual(self.one(repo(self.tmp / "none"))["status"], "unchecked")
        r = repo(self.tmp / "nostore")
        cli(r / "store.sh", "add")
        write(r / "cli.json", json.dumps({"cli": "store.sh", "verbs": ["add"]}))
        write(r / "todo.json", "{}\n", 0o644)
        res = self.one(r)
        self.assertEqual(res["status"], "unchecked")
        self.assertIn("declares no `store`", res["lines"][0])
        res = self.one(self.store("missing.json", {}))
        self.assertEqual(res["status"], "unchecked")
        self.assertIn("matches no file", res["lines"][0])

    def test_a_broken_cli_json_is_unchecked_and_left_to_accessor(self):
        r = self.store("todo.json", {"todo.json": 0o644})
        write(r / "cli.json", json.dumps(dict(CLIDOC, store="todo.json", verbs=["purge"])))
        res = self.one(r)
        self.assertEqual(res["status"], "unchecked", res["lines"])
        self.assertIn("`accessor` says which", res["lines"][0])
        write(r / "cli.json", "{not json")
        self.assertEqual(self.one(r)["status"], "unchecked")


class RegistryMatches(Case):
    TOP = {"name": "top", "services": [{"service": "check", "run": "dev.sh", "verbs": ["check"]}]}
    KID = {"name": "kid", "services": [{"service": "check", "run": "dev.sh", "verbs": ["check"]}]}

    def one(self, r):
        return self.cli_json("one", "registry-matches", r)[1]["results"][0]

    def node(self, rows, node=None):
        r = self.tmp / "r"
        write(r / "node.json", json.dumps(node or {"rebuild": ["true"], "generated": [], "record": [],
                                                   "children": ["kid"], "registry": "reg.json"}))
        write(r / "services.json", json.dumps(self.TOP))
        write(r / "kid" / "services.json", json.dumps(self.KID))
        if rows is not None:
            write(r / "reg.json", json.dumps({"services": rows}))
        return r

    def test_equal_rows_pass(self):
        self.assertEqual(self.one(self.node({".": self.TOP, "kid": self.KID}))["status"], "ok")

    def test_every_mismatch_is_listed(self):
        res = self.one(self.node({".": dict(self.TOP, tags=["x"]), "gone": self.KID}))
        self.assertEqual(res["status"], "fail")
        self.assertEqual(res["lines"], ["reg.json: row `gone`: no matching services.json (not the node or a child that has one)",
                                        "reg.json: row `.` differs from services.json at: tags",
                                        "kid/services.json: no row in reg.json"])

    def test_unchecked_and_broken_registries(self):
        r = self.tmp / "plain"
        r.mkdir()
        self.assertEqual(self.one(r)["status"], "unchecked")
        r = self.node(None, {"rebuild": ["true"], "generated": [], "record": []})
        self.assertEqual(self.one(r)["status"], "unchecked")
        r = self.node(None, {"rebuild": ["true"], "generated": [], "record": [], "children": ["kid"]})
        self.assertIn("names children but no `registry`", self.one(r)["lines"][0])
        r = self.node(None)
        self.assertEqual(self.one(r)["lines"], ["reg.json: the registry node.json names does not exist"])
        write(r / "reg.json", json.dumps({"roles": {}}))
        self.assertIn("no `services` object", self.one(r)["lines"][0])

    def test_a_node_json_outside_the_repo_is_not_followed(self):
        r = self.node({".": self.TOP}, {"rebuild": ["true"], "generated": [], "record": [], "registry": "../reg.json"})
        res = self.one(r)
        self.assertEqual(res["lines"], ["node.json: paths-inside: $.registry: `../reg.json` is not a path inside the repo"])


if __name__ == "__main__":
    unittest.main()
