"""The contract files (PLAN-routing-tree.md §14.8, PLAN-repo-setup.md §7.10):
their schemas (each x-rule implemented under its id, only enforced keywords,
nothing undeclared), each rule shown red alone, and the three checks that read
them: services-valid, accessor, registry-matches. Every check is run through
the CLI (`checks one`), the way a repo runs it."""
import copy
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
        for name in contract.FILES:
            with self.subTest(name):
                s = contract.schema(name)                      # load refuses an unenforced keyword
                self.assertLessEqual(used_keywords(s) - checkjson.ANNOTATIONS, checkjson.KEYWORDS)

    def test_x_rules_equal_the_rules_implemented_per_file(self):
        for name in contract.FILES:
            with self.subTest(name):
                self.assertEqual(set(contract.schema(name)["x-rules"]), set(contract.RULES[name]))
        self.assertEqual(set(contract.RULES), set(contract.FILES))

    def test_every_object_refuses_an_undeclared_key(self):
        """additionalProperties false at every object level: nothing undeclared."""
        def objects(node, where):
            if node.get("type") == "object":
                yield where, node
            for k, sub in (node.get("properties") or {}).items():
                yield from objects(sub, f"{where}.{k}")
            if isinstance(node.get("items"), dict):
                yield from objects(node["items"], f"{where}[]")
        for name in contract.FILES:
            for where, node in objects(contract.schema(name), name):
                with self.subTest(where):
                    self.assertIs(node.get("additionalProperties"), False)

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
CLIDOC = {"store": "app.db", "cli": "store.sh", "verbs": ["add", "list"]}
NODEDOC = {"rebuild": ["true"], "generated": ["out.txt"], "record": ["*.md"], "children": ["kid"], "registry": "reg.json"}


def _svc(d):
    d["services"].append({"service": "check", "run": "dev.sh", "verbs": ["check"]})


# (file, rule, mutate the clean doc, a finding the rule gives)
RULE_MUTANTS = [
    (contract.SERVICES, "one-check", _svc, "2 `check` entries"),
    (contract.SERVICES, "run-inside", lambda d: d["services"][1].update(run="../store.sh"), "`../store.sh` is not a path inside"),
    (contract.SERVICES, "run-executable", lambda d: d["services"][1].update(run="nope.sh"), "`nope.sh` does not exist"),
    (contract.SERVICES, "verb-implemented", lambda d: d["services"][1]["verbs"].append("purge"), "does not implement `purge`"),
    (contract.SERVICES, "unique", lambda d: d["tags"].append("t"), "tag `t` given twice"),
    (contract.SERVICES, "write-declared", lambda d: d["services"][1]["verbs"].append("drop"), "`drop` is not a verb cli.json declares"),
    (contract.CLI, "paths-inside", lambda d: d.update(store="/abs/app.db"), "`/abs/app.db` is not a path inside"),
    (contract.CLI, "cli-executable", lambda d: d.update(cli="plain.txt"), "`plain.txt` is not executable"),
    (contract.CLI, "verb-implemented", lambda d: d["verbs"].append("purge"), "does not implement `purge`"),
    (contract.CLI, "unique", lambda d: d.update(store=["app.db", "./app.db"]), "path `app.db` given twice"),
    (contract.NODE, "paths-inside", lambda d: d["generated"].append("../x"), "`../x` is not a path inside"),
    (contract.NODE, "unique", lambda d: d["record"].append("*.md"), "path `*.md` given twice"),
    (contract.NODE, "generated-exact", lambda d: d["generated"].append("gen/*.txt"), "`gen/*.txt` is a glob"),
    (contract.NODE, "disjoint", lambda d: d["generated"].append("kid/x.txt"), "`kid/x.txt` lies under a child"),
]


class Rules(Case):
    def setUp(self):
        super().setUp()
        self.r = self.tmp / "r"
        cli(self.r / "dev.sh", "check")
        cli(self.r / "store.sh", "add", "list", "drop")
        write(self.r / "plain.txt", "x\n")
        self.clean = {contract.SERVICES: SERVICES, contract.CLI: CLIDOC, contract.NODE: NODEDOC}
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

    def test_a_broken_cli_json_is_red(self):
        r = self.store(cli_doc=dict(CLIDOC, verbs=["add", "purge"]))
        res = self.one(r)
        self.assertEqual(res["status"], "fail")
        self.assertIn("cli.json: verb-implemented: $.verbs: `store.sh` does not implement `purge`", res["lines"][0])


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
