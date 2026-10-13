"""stores-exported (PLAN-repo-setup.md §7.11), through the CLI: the store's own
`verify --json` decides, read by this check's own reading of the report; the
counterfactual (export, then green); every way a report can fail to be a
pass; DATA_REPO is the caller's, and a fixture's env reaches the check."""
import json
import os
import subprocess
import time

from tests.helpers import Case, repo, write
from checkslib import decl, runner
from checkslib.fixture import Fixture

VERIFY = """#!/usr/bin/env bash
case "${{1:-}}" in
  verify) {body} ;;
  export) mkdir -p "$DATA_REPO/r" && cp data/app.db "$DATA_REPO/r/rows.txt" ;;
  *) printf 'store.sh <verb>\\n\\n  export   x\\n  verify   y\\n' ;;
esac
"""
COMPARE = ('src="$DATA_REPO/r/rows.txt"; if [ ! -f "$src" ]; then s=missing; elif cmp -s "$src" data/app.db; '
           'then s=same; else s=differs; fi; printf \'{"items": [{"item": "rows", "status": "%s", "detail": "d"}]}\\n\' "$s"; '
           '[ "$s" = same ]')


class StoresExported(Case):
    def setUp(self):
        super().setUp()
        self.data = self.tmp / "data"
        self.data.mkdir()

    def store(self, body=COMPARE, verbs=("export", "verify")):
        r = repo(self.tmp / "r", {".gitignore": "data/\n"})
        write(r / "store.sh", VERIFY.format(body=body), 0o755)
        write(r / "cli.json", json.dumps({"store": "data/app.db", "cli": "store.sh", "verbs": list(verbs)}))
        write(r / "data" / "app.db", "row one\n")
        return r

    def one(self, r, env=None):
        env = {"DATA_REPO": str(self.data)} if env is None else env
        return self.cli_json("one", "stores-exported", r, env=env)[1]["results"][0]

    def say(self, doc, code=0):
        return f"printf '%s\\n' '{json.dumps(doc)}'; exit {code}"

    def test_missing_then_export_then_a_store_change_then_export(self):
        r = self.store()
        self.assertEqual(self.one(r)["lines"], ["rows: missing (d)"])
        self.cli_export(r)
        self.assertEqual(self.one(r)["status"], "ok")
        write(r / "data" / "app.db", "row one\nrow two\n")        # a write the export did not follow
        self.assertEqual(self.one(r)["lines"], ["rows: differs (d)"])
        self.cli_export(r)
        self.assertEqual(self.one(r)["status"], "ok")

    def cli_export(self, r):
        subprocess.run([str(r / "store.sh"), "export"], cwd=r, check=True, env=dict(os.environ, DATA_REPO=str(self.data)))

    def test_data_repo_unset_is_unchecked_and_not_a_folder_is_red(self):
        r = self.store()
        res = self.one(r, env={"DATA_REPO": ""})
        self.assertEqual(res["status"], "unchecked")
        self.assertIn("DATA_REPO is not set", res["lines"][0])
        res = self.one(r, env={"DATA_REPO": str(self.tmp / "nowhere")})
        self.assertEqual(res["lines"], ["DATA_REPO is set but is not a folder: the export has nowhere to be"])

    def test_no_cli_json_is_unchecked_and_no_verify_verb_is_red(self):
        res = self.one(repo(self.tmp / "plain"))
        self.assertEqual(res["status"], "unchecked")
        r = self.store(verbs=("export",))
        self.assertEqual(self.one(r)["lines"], ["cli.json: declares no `verify` verb: nothing shows the store's export is current"])
        write(r / "cli.json", json.dumps({"cli": "store.sh", "verbs": ["export"]}))   # a CLI over no store
        res = self.one(r)
        self.assertEqual(res["status"], "unchecked")
        self.assertIn("declares no `store`", res["lines"][0])

    def test_a_report_that_is_not_one_is_red(self):
        cases = [("echo all good", "printed no JSON document (exit 0)"),
                 (self.say({"items": []}), "schema: $.items: fewer than 1"),
                 (self.say({"items": [{"item": "a", "status": "fine"}]}), "$.items[0].status"),
                 (self.say({"items": [{"item": "a", "status": "same"}], "ok": True}), "unknown key `ok`"),
                 (self.say({"items": [{"item": "a", "status": "same"}, {"item": "a", "status": "same"}]}),
                  "verify: unique: $.items: item `a` given twice"),
                 (self.say({"items": [{"item": "a", "status": "same"}]}, code=3),
                  "exited 3 but reports every item `same`")]
        for body, want in cases:
            with self.subTest(want):
                res = self.one(self.store(body))
                self.assertEqual(res["status"], "fail", res)
                self.assertIn(want, "\n".join(res["lines"]))

    def test_only_unavailable_items_left_is_unchecked(self):
        r = self.store(self.say({"items": [{"item": "a", "status": "same"}, {"item": "pages", "status": "unavailable"}]}))
        res = self.one(r)
        self.assertEqual(res["status"], "unchecked")
        self.assertIn("1 item(s) could not be compared here: pages", res["lines"][0])
        r = self.store(self.say({"items": [{"item": "b", "status": "missing"}, {"item": "pages", "status": "unavailable"}]}, 1))
        self.assertEqual(self.one(r)["lines"], ["b: missing"])

    def test_a_verify_that_does_not_finish_is_an_error(self):
        r = self.store("sleep 30 & wait")
        t0 = time.monotonic()
        res = self.one(r, env={"DATA_REPO": str(self.data), "CHECKS_VERIFY_TIMEOUT": "1"})
        self.assertLess(time.monotonic() - t0, 20)
        self.assertEqual(res["status"], "error")
        self.assertIn("did not finish in 1.0s", "\n".join(res["lines"]))


class FixtureEnv(Case):
    def test_a_fixtures_env_reaches_the_check_and_without_it_the_check_does_not_pass(self):
        r = repo(self.tmp / "r", {".gitignore": "data/\n"})
        write(r / "store.sh", VERIFY.format(body=COMPARE), 0o755)
        write(r / "cli.json", json.dumps({"store": "data/app.db", "cli": "store.sh", "verbs": ["verify"]}))
        write(r / "data" / "app.db", "x\n")
        write(self.tmp / "d" / "r" / "rows.txt", "x\n")
        entry = {e.name: e for e in decl.load(runner.DEFAULT_SOURCE)[0]}["stores-exported"]
        fx = Fixture(r, env={"DATA_REPO": str(self.tmp / "d")})
        self.assertEqual(runner.run_one(entry, fx.repo, env=fx.env)["status"], "ok")
        self.assertEqual(runner.run_one(entry, fx.repo, env={"DATA_REPO": ""})["status"], "unchecked")


if __name__ == "__main__":
    import unittest
    unittest.main()
