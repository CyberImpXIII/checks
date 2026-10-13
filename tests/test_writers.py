"""`checks writers` and `silent-writes` (RESEARCH-writers.md Q4, could-not-settle 1):
each primitive classified as Q1 measured it, the lines that look like writes
but are not, a write site added to a repo changing the report, and the
`allow` param shown to change the check's result both ways."""
import json
import unittest

from tests.helpers import Case, repo, run_cli, write
from checkslib import writers


def kinds(rel, text):
    return [(s["line"], s["primitive"], s["kind"]) for s in writers.sites_in(rel, text)]


class Classify(unittest.TestCase):
    def test_python(self):
        src = ("import os\nos.replace(tmp, p)\np.write_text(t)\nopen(p, 'a').write(x)\nopen(p).read()\n"
               "open(p, encoding='utf-8')\nsqlite3.connect(db)\nos.chmod(p, 0o444)\n# open(p, 'w') in a comment\n")
        self.assertEqual(kinds("a.py", src), [(2, "os.replace", "rename"), (3, "write_text", "in-place"),
                                              (4, "open(w|a|x)", "in-place"), (7, "sqlite3.connect", "sqlite"),
                                              (8, "chmod", "chmod")])

    def test_js(self):
        src = "fs.writeFileSync(p, s)\nfs.renameSync(t, p)\n// fs.writeFileSync(p)\nconst db = new DatabaseSync(p)\n"
        self.assertEqual(kinds("a.js", src), [(1, "writeFileSync", "in-place"), (2, "renameSync", "rename"),
                                              (4, "DatabaseSync", "sqlite")])

    def test_shell_and_what_is_not_a_write(self):
        src = ("#!/usr/bin/env bash\n"
               'echo x > "$f"\n'                                  # 2 in-place
               'jq . a > "$tmp" && mv "$tmp" a\n'                 # 3 rename (Q1: tmp && mv)
               "echo 'a > b' \"c > d\"\n"                        # quoted: no write
               "return $((fails > 0))\n"                          # arithmetic: no write
               "cmd >/dev/null 2>&1\n"                            # /dev/null: no write
               '{ echo x >> "$l"; } 2>/dev/null || true\n'        # 7 silent
               'echo x >> "$l" 2>/dev/null || die "lost"\n'      # 8 handled
               'if { echo x >> "$l"; } 2>/dev/null; then :; fi\n'  # 9 handled by if
               "crontab - < f\n"                                  # 10 crontab
               "echo x | tee -a log\n")                           # 11 tee
        self.assertEqual(kinds("x", src), [(2, ">", "in-place"), (3, "mv", "rename"), (7, ">>", "silent"),
                                           (8, ">>", "in-place"), (9, ">>", "in-place"), (10, "crontab -", "crontab"),
                                           (11, "tee", "in-place")])
        self.assertEqual(kinds("x.txt", 'echo x > "$f"\n'), [], "no shebang, no known extension: not code")


class Writers(Case):
    def test_a_write_site_added_changes_the_report(self):
        r = repo(self.tmp / "r", {"a.py": "print('hi')\n", "tests/t.py": "open(p, 'w')\n", "README.md": "open(p, 'w')\n"})
        code, doc = self.cli_json("writers", r)
        self.assertEqual((code, doc["sites"], doc["counts"]), (0, [], {}))
        write(r / "a.py", "print('hi')\nPath(p).write_text(s)\n")
        doc = self.cli_json("writers", r)[1]
        self.assertEqual([(s["file"], s["line"], s["kind"], s["at_0444"]) for s in doc["sites"]],
                         [("a.py", 2, "in-place", "loud")])
        self.assertEqual(doc["counts"], {"in-place": 1})
        p = run_cli("writers", str(r))
        self.assertIn("a.py:2  write_text  in-place (loud at 0444)", p.stdout)
        self.assertEqual(p.stdout.splitlines()[-1], f"checks writers {r.resolve()}: 1 write site(s): 1 in-place")


class SilentWrites(Case):
    LOG = '#!/bin/sh\n{ echo x >> "$l"; } 2>/dev/null || true\n'

    def one(self, r, *more):
        return self.cli_json("one", "silent-writes", r, *more)[1]["results"][0]

    def test_allow_turns_the_result_and_a_stale_entry_is_red(self):
        r = repo(self.tmp / "r", {"log.sh": self.LOG})
        res = self.one(r)
        self.assertEqual(res["status"], "fail")
        self.assertTrue(res["lines"][0].startswith("log.sh:2: >>: its failure is discarded"), res["lines"])
        write(r / "checks.json", json.dumps({"silent-writes": {"allow": ["log.sh"]}}))
        res = self.one(r)
        self.assertEqual((res["status"], res["lines"]), ("ok", ["1 write site(s), none silent outside `allow`: 1 silent"]))
        write(r / "checks.json", json.dumps({"silent-writes": {"allow": ["log.sh", "gone.sh"]}}))
        res = self.one(r)
        self.assertEqual(res["lines"], ["checks.json: silent-writes.allow names `gone.sh`, which is not a file in the repo"])
        write(r / "checks.json", json.dumps({"silent-writes": {"allow": "log.sh"}}))
        self.assertIn("must be a list", self.one(r)["lines"][0])

    def test_it_runs_only_when_audits_are_asked_for(self):
        r = repo(self.tmp / "r", {"log.sh": self.LOG})
        names = lambda *a: {x["check"] for x in self.cli_json("run", r, *a)[1]["results"]}  # noqa: E731
        self.assertNotIn("silent-writes", names())
        self.assertIn("silent-writes", names("--roles", "audit"))


if __name__ == "__main__":
    unittest.main()
