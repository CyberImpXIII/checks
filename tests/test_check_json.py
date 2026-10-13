"""check-json: the schema file and its validator held to each other, one mutant
per rule (each shown red for its own reason, and each cross rule shown to be
the one that catches it), the check's UNCHECKED and error paths, and this
repo's own `./dev.sh check --json` validated through the real dev.sh."""
import copy
import json
import os
import shutil
import subprocess
import time
import unittest
from unittest import mock

from tests.helpers import Case, TOOL_ROOT, copy_committable, write
from checkslib import api, checkjson

SCHEMA = checkjson.load()

BASE = {"ok": False, "checks": [
    {"name": "suite", "status": "fail", "counts": {"failed": 1, "passed": 4},
     "failures": [{"message": "expected 2, got 3", "file": "test/x.test.js", "line": 12, "role": "code"}]},
    {"name": "tree", "status": "unchecked", "reason": "not a git repo", "counts": {"failed": 0}, "failures": []},
    {"name": "hooks", "status": "ok", "counts": {"failed": 0}, "failures": []}]}
GREEN = {"ok": True, "checks": [{"name": "suite", "status": "ok", "counts": {"failed": 0}, "failures": []}]}


def check(i):
    return lambda d: d["checks"][i]


def failure(d):
    return d["checks"][0]["failures"][0]


def setting(get, key, value):
    def f(d):
        get(d)[key] = value
    return f


def dropping(get, key):
    def f(d):
        del get(d)[key]
    return f


# (what is mutated, mutation, exit code, a substring the findings must hold)
STRUCTURE_MUTANTS = [
    ("top not an object", None, 1, "schema: $: [] is not object"),        # None: the document is []
    ("ok missing", dropping(lambda d: d, "ok"), 1, "schema: $: missing `ok`"),
    ("ok not boolean", setting(lambda d: d, "ok", "no"), 1, 'schema: $.ok: "no" is not boolean'),
    ("checks missing", dropping(lambda d: d, "checks"), 1, "schema: $: missing `checks`"),
    ("checks empty", setting(lambda d: d, "checks", []), 1, "schema: $.checks: fewer than 1 item(s)"),
    ("checks not a list", setting(lambda d: d, "checks", {}), 1, "schema: $.checks: {} is not array"),
    ("name missing", dropping(check(0), "name"), 1, "schema: $.checks[0]: missing `name`"),
    ("name empty", setting(check(0), "name", ""), 1, "schema: $.checks[0].name: shorter than 1"),
    ("status missing", dropping(check(0), "status"), 1, "schema: $.checks[0]: missing `status`"),
    ("status off the enum", setting(check(0), "status", "passed"), 1,
     'schema: $.checks[0].status: "passed" is not one of ok, fail, unchecked, error'),
    ("reason empty", setting(check(1), "reason", ""), 1, "schema: $.checks[1].reason: shorter than 1"),
    ("counts missing", dropping(check(0), "counts"), 1, "schema: $.checks[0]: missing `counts`"),
    ("counts.failed missing", dropping(lambda d: d["checks"][0]["counts"], "failed"), 1,
     "schema: $.checks[0].counts: missing `failed`"),
    ("a count negative", setting(lambda d: d["checks"][0]["counts"], "passed", -1), 1,
     "schema: $.checks[0].counts.passed: -1 is below 0"),
    ("a count boolean", setting(lambda d: d["checks"][0]["counts"], "passed", True), 1,
     "schema: $.checks[0].counts.passed: true is not integer"),
    ("a count fractional", setting(lambda d: d["checks"][0]["counts"], "passed", 1.5), 1,
     "schema: $.checks[0].counts.passed: 1.5 is not integer"),
    ("failures missing", dropping(check(2), "failures"), 1, "schema: $.checks[2]: missing `failures`"),
    ("failures not a list", setting(check(2), "failures", "none"), 1, 'schema: $.checks[2].failures: "none" is not array'),
    ("message missing", dropping(failure, "message"), 1, "schema: $.checks[0].failures[0]: missing `message`"),
    ("message empty", setting(failure, "message", ""), 1, "schema: $.checks[0].failures[0].message: shorter than 1"),
    ("role missing", dropping(failure, "role"), 1, "schema: $.checks[0].failures[0]: missing `role`"),
    ("role empty", setting(failure, "role", ""), 1, "schema: $.checks[0].failures[0].role: shorter than 1"),
    ("file missing", dropping(failure, "file"), 1, "schema: $.checks[0].failures[0]: missing `file`"),
    ("file a number", setting(failure, "file", 3), 1, "schema: $.checks[0].failures[0].file: 3 is not string or null"),
    ("file empty", setting(failure, "file", ""), 1, "schema: $.checks[0].failures[0].file: shorter than 1"),
    ("line missing", dropping(failure, "line"), 1, "schema: $.checks[0].failures[0]: missing `line`"),
    ("line zero", setting(failure, "line", 0), 1, "schema: $.checks[0].failures[0].line: 0 is below 1"),
    ("line a string", setting(failure, "line", "12"), 1, 'schema: $.checks[0].failures[0].line: "12" is not integer or null'),
]


def _ok_suite(d):
    d["checks"][0].update(status="ok", counts={"failed": 0}, failures=[])


def _hooks_with_failure(d):
    d["checks"][2].update(counts={"failed": 1}, failures=[dict(BASE["checks"][0]["failures"][0])])


# (rule, mutation, exit code, substring): one or more per x-rule; one-document is text-level, below.
RULE_MUTANTS = [
    ("exit-agrees", lambda d: None, 0, "exit-agrees: exit 0 but ok is false"),
    ("exit-agrees", lambda d: d.update(checks=GREEN["checks"]) or d.update(ok=True), 1, "exit-agrees: exit 1 but ok is true"),
    ("verdict", setting(lambda d: d, "ok", True), 0, "verdict: ok is true but suite is fail/error"),
    ("verdict", _ok_suite, 1, "verdict: ok is false but no check is fail or error"),
    ("counted", setting(lambda d: d["checks"][0]["counts"], "failed", 2), 1,
     "counted: $.checks[0] (suite): counts.failed is 2, failures has 1"),
    ("status-failures", _hooks_with_failure, 1, "status-failures: $.checks[2] (hooks): ok with 1 failure(s)"),
    ("status-failures", lambda d: d["checks"][0].update(counts={"failed": 0}, failures=[]), 1,
     "status-failures: $.checks[0] (suite): fail with no failure saying what"),
    ("unchecked-reason", dropping(check(1), "reason"), 1, "unchecked-reason: $.checks[1] (tree): unchecked with no `reason`"),
    ("unique-names", setting(check(2), "name", "suite"), 1, "unique-names: $.checks[2]: `suite` given twice"),
    ("line-needs-file", setting(failure, "file", None), 1, "line-needs-file: $.checks[0].failures[0]: line 12 with no file"),
]


def mutated(fn):
    d = copy.deepcopy(BASE)
    if fn is None:
        return []
    fn(d)
    return d


class SchemaFile(unittest.TestCase):
    def test_status_enum_is_vocab_statuses_plus_error(self):
        enum = SCHEMA["properties"]["checks"]["items"]["properties"]["status"]["enum"]
        self.assertEqual(set(enum), {s["status"] for s in api.RESULTS.values()} | {"error"})

    def test_x_rules_equal_the_rules_implemented(self):
        self.assertEqual(set(SCHEMA["x-rules"]), set(checkjson.RULES))
        self.assertEqual({r for r, *_ in RULE_MUTANTS} | {"one-document"}, set(checkjson.RULES))

    def test_every_keyword_enforced_is_used_and_every_one_used_is_enforced(self):
        used = set()

        def walk(node):
            used.update(node)
            for sub in (node.get("properties") or {}).values():
                walk(sub)
            for k in ("items", "additionalProperties"):
                if isinstance(node.get(k), dict):
                    walk(node[k])
        walk(SCHEMA)
        self.assertEqual(used - checkjson.ANNOTATIONS, checkjson.KEYWORDS)

    def test_an_unenforced_keyword_or_type_is_refused(self):
        for planted in ({"pattern": "^x"}, {"type": "date"}):
            s = copy.deepcopy(SCHEMA)
            s["properties"]["checks"]["items"]["properties"]["name"].update(planted)
            path = TOOL_ROOT / "tests" / f"_planted_{os.getpid()}.json"
            try:
                path.write_text(json.dumps(s))
                with self.assertRaises(checkjson.SchemaError):
                    checkjson.load(path)
            finally:
                path.unlink()


class Validate(unittest.TestCase):
    def test_conforming_documents_pass_green_and_red(self):
        self.assertEqual(checkjson.validate(json.dumps(GREEN), 0), [])
        self.assertEqual(checkjson.validate(json.dumps(BASE), 1), [])
        self.assertEqual(checkjson.validate("\n  " + json.dumps(BASE, indent=1) + "\n\n", 1), [])

    def test_one_document(self):
        for text, want in (("", "one-document: printed nothing on stdout (exit 1)"),
                           ("all gates green\n", "one-document: stdout is not one JSON document"),
                           (json.dumps(BASE) + "\ncheck: done", "one-document: stdout is not one JSON document (Extra data"),
                           (json.dumps(BASE) + "\n" + json.dumps(BASE), "one-document: stdout is not one JSON document (Extra data"),
                           ("== test\n" + json.dumps(BASE), "it starts: == test")):
            with self.subTest(text=text[:20]):
                got = checkjson.validate(text, 1)
                self.assertEqual(len(got), 1, got)
                self.assertIn(want, got[0])

    def test_each_structure_mutant_is_red_for_its_reason(self):
        for what, fn, code, want in STRUCTURE_MUTANTS:
            with self.subTest(what):
                got = checkjson.validate(json.dumps(mutated(fn)), code)
                self.assertIn(want, "\n".join(got))

    def test_each_rule_mutant_is_red_and_only_its_rule_catches_it(self):
        for rule, fn, code, want in RULE_MUTANTS:
            with self.subTest(rule=rule, want=want):
                text = json.dumps(mutated(fn))
                self.assertEqual(checkjson.validate(json.dumps(BASE), 1), [])       # the base is clean
                got = checkjson.validate(text, code)
                self.assertIn(want, "\n".join(got))
                without = dict(checkjson.RULES, **{rule: None})
                with mock.patch.object(checkjson, "RULES", without):
                    self.assertFalse([g for g in checkjson.validate(text, code) if g.startswith(rule + ":")])

    def test_exit_agrees_is_said_even_when_the_structure_is_broken(self):
        got = checkjson.validate(json.dumps({"ok": False, "gates": {}}), 0)
        self.assertEqual(got, ["schema: $: missing `checks`", "exit-agrees: exit 0 but ok is false"])

    def test_every_structural_finding_is_listed_not_only_the_first(self):
        d = mutated(dropping(failure, "role"))
        d["checks"][2]["status"] = "green"
        got = checkjson.validate(json.dumps(d), 1)
        self.assertEqual(len(got), 2, got)


DEV = """#!/usr/bin/env bash
case "${{1:-}}" in
  check) [ "${{2:-}}" = "--json" ] && {{ {body} }} ;;
esac
"""


class TheCheck(Case):
    def one(self, repo, env=None):
        rep = self.cli_json("one", "check-json", repo, env=env)[1]
        return rep["results"][0]

    def dev(self, body, mode=0o755):
        r = self.tmp / "r"
        write(r / "dev.sh", DEV.format(body=body), mode)
        return r

    def test_conforming_output_is_ok_and_its_edit_is_red(self):
        r = self.dev(f"printf '%s\\n' '{json.dumps(BASE)}'; exit 1;")
        self.assertEqual(self.one(r)["status"], "ok")
        self.dev(f"printf '%s\\n' '{json.dumps(BASE)}'; exit 0;")
        res = self.one(r)
        self.assertEqual((res["status"], res["lines"]), ("fail", ["exit-agrees: exit 0 but ok is false"]))

    def test_no_dev_sh_and_no_json_are_unchecked_never_ok(self):
        (self.tmp / "r").mkdir()
        res = self.one(self.tmp / "r")
        self.assertEqual(res["status"], "unchecked")
        self.assertIn("no dev.sh", res["lines"][0])
        r = self.dev("echo all green;")
        write(r / "dev.sh", (r / "dev.sh").read_text().replace('"--json"', '"-j"'), 0o755)
        res = self.one(r)
        self.assertEqual(res["status"], "unchecked")
        self.assertIn("has no --json", res["lines"][0])

    def test_not_executable_is_red(self):
        r = self.dev("echo '{}';", mode=0o644)
        res = self.one(r)
        self.assertEqual((res["status"], res["lines"]), ("fail", ["dev.sh: not executable (it is run directly, as ./dev.sh)"]))

    def test_the_guard_is_passed_down_and_a_nested_run_is_unchecked(self):
        """The suite sees the guard (so a check-json inside it stops), and a
        check-json started with the guard set does not run the suite at all."""
        green = json.dumps(GREEN)
        r = self.dev(f'[ -n "$CHECKS_CHECK_JSON_ACTIVE" ] && printf "%s\\n" \'{green}\' || echo unguarded; '
                     f'touch "$(dirname "$0")/ran";')
        self.assertEqual(self.one(r)["status"], "ok")
        (r / "ran").unlink()
        res = self.one(r, env={"CHECKS_CHECK_JSON_ACTIVE": "1"})
        self.assertEqual(res["status"], "unchecked")
        self.assertIn("nested", res["lines"][0])
        self.assertFalse((r / "ran").exists())

    def test_a_run_that_does_not_finish_is_an_error_and_is_killed(self):
        r = self.dev("sleep 30 & wait;")
        t0 = time.monotonic()
        res = self.one(r, env={"CHECKS_CHECK_JSON_TIMEOUT": "1"})
        self.assertLess(time.monotonic() - t0, 20)
        self.assertEqual(res["status"], "error")
        self.assertIn("did not finish in 1.0s", "\n".join(res["lines"]))

    def test_runs_only_under_the_audit_role(self):
        r = self.dev(f"printf '%s\\n' '{json.dumps(GREEN)}';")
        names = lambda *a: {x["check"]: x["status"] for x in self.cli_json("run", r, *a)[1]["results"]}
        self.assertNotIn("check-json", names())
        self.assertEqual(names("--roles", "audit")["check-json"], "ok")


class OwnDevJson(Case):
    def test_the_real_dev_sh_check_json_conforms_when_red(self):
        """A copy of this tool whose check.parts.json is one failing unit test and
        the roster audit: the real dev.sh runs both through the shared runner;
        the document validates, says the test part failed with role code and
        its FAIL line, the audit ok, and exits 1. (tests/test_parts.py holds
        the runner's documents green and red on hand-made suites.)"""
        dst = self.tmp / "tools" / "checks"
        copy_committable(TOOL_ROOT, dst)
        shutil.rmtree(dst / "tests")
        write(dst / "tests" / "__init__.py", "")
        write(dst / "tests" / "test_stub.py",
              "import unittest\n\n\nclass Stub(unittest.TestCase):\n    def test_red(self):\n        self.fail('planted')\n")
        write(dst / "check.parts.json", json.dumps({"parts": [
            {"name": "test.stub", "run": "python3 -m unittest tests.test_stub", "files": ["tests"],
             "timeout_s": 60, "role": "code"},
            {"name": "audit", "run": "./dev.sh audit", "files": ["."], "timeout_s": 120, "role": "audit"}]}))
        env = {k: v for k, v in os.environ.items() if k not in ("CHECKS_CHECK_JSON_ACTIVE", "CHECK_PARTS", "PROGRESS_FILE")}
        p = subprocess.run([str(dst / "dev.sh"), "check", "--json"], capture_output=True, text=True,
                           env=env, stdin=subprocess.DEVNULL, timeout=280)
        self.assertEqual(checkjson.validate(p.stdout, p.returncode), [], p.stdout + p.stderr[-400:])
        doc = json.loads(p.stdout)
        self.assertEqual([(c["name"], c["status"]) for c in doc["checks"]], [("test.stub", "fail"), ("audit", "ok")])
        self.assertEqual(doc["checks"][0]["failures"][0]["role"], "code")
        self.assertIn("FAIL: test_red", doc["checks"][0]["failures"][0]["message"])
        self.assertEqual(p.returncode, 1)
        self.assertTrue((dst / ".progress" / "check.json").is_file())


if __name__ == "__main__":
    unittest.main()
