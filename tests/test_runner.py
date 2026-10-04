"""The runner: which checks run where, every result kept, every way a check can
break counted red, checks.json validated, and the fixtures gate itself shown
to go red for each way a fixture can be wrong."""
import json
import unittest
from unittest import mock

from tests.helpers import Case, TOOL_ROOT, repo, run_cli, write
from checkslib import decl, runner, selftest

SAY_FAIL = 'echo "{n}: finding one"; echo "{n}: finding two"; exit 2'


class Run(Case):
    def entry(self, name):
        return {e.name: e for e in decl.load(self.src)[0]}[name]

    def test_every_failing_check_is_named_not_only_the_first(self):
        for n in ("aa", "bb"):
            self.add_check(n, SAY_FAIL.format(n=n))
        self.add_check("cc", "exit 0")
        rep = runner.run_repo(repo(self.tmp / "r"), self.src)
        got = {r["check"]: (r["status"], r["lines"]) for r in rep["results"]}
        self.assertEqual(got["aa"], ("fail", ["aa: finding one", "aa: finding two"]))
        self.assertEqual(got["bb"][0], "fail")
        self.assertEqual(got["cc"], ("ok", []))
        self.assertFalse(rep["ok"])

    def test_every_broken_exit_is_error_and_red(self):
        cases = {"one": "exit 1", "silentfail": "exit 2", "silentunch": "exit 3", "crash": "kill -9 $$"}
        for n, body in cases.items():
            self.add_check(n, body)
        self.add_check("unch", 'echo "cannot here"; exit 3')
        rep = runner.run_repo(repo(self.tmp / "r"), self.src)
        got = {r["check"]: r["status"] for r in rep["results"]}
        self.assertEqual(got, {"one": "error", "silentfail": "error", "silentunch": "error", "crash": "error",
                               "unch": "unchecked"})
        self.assertFalse(rep["ok"])

    def test_unchecked_alone_is_not_red_but_is_never_ok(self):
        self.add_check("unch", 'echo "cannot here"; exit 3')
        rep = runner.run_repo(repo(self.tmp / "r"), self.src)
        self.assertTrue(rep["ok"])
        self.assertEqual(rep["results"][0]["status"], "unchecked")

    def test_timeout_is_error(self):
        self.add_check("slow", "sleep 5")
        r = runner.run_one(self.entry("slow"), self.tmp, timeout=1)
        self.assertEqual(r["status"], "error")
        self.assertIn("timed out", r["lines"][0])

    def test_refused_check_is_an_error_row_not_an_omission(self):
        self.add_check("good", "exit 0")
        self.add_check("nofixture", "exit 0", fixture=None)
        rep = runner.run_repo(repo(self.tmp / "r"), self.src)
        got = {r["check"]: r for r in rep["results"]}
        self.assertEqual(got["nofixture"]["status"], "error")
        self.assertIn("refused: no fixtures", got["nofixture"]["lines"][0])
        self.assertFalse(rep["ok"])

    def test_only_with_unknown_name_is_a_fault(self):
        self.add_check("good", "exit 0")
        rep = runner.run_repo(repo(self.tmp / "r"), self.src, only=["good", "ghost"])
        self.assertEqual([r["check"] for r in rep["results"]], ["good"])
        self.assertEqual(rep["faults"], ["no such check: ghost"])
        self.assertFalse(rep["ok"])

    def test_context_reaches_the_check(self):
        self.add_check("ctx", 'echo "ws=$CHECKS_WORKSPACE params=$CHECKS_PARAMS names=${CHECKS_ROSTER_NAMES-unset} repo=$1"; exit 2',
                       params="k")
        ws = self.tmp / "ws"
        r = repo(ws / "r", {"checks.json": json.dumps({"ctx": {"k": [1]}})})
        line = runner.run_one(self.entry("ctx"), r, ws, {"k": [1]}, ["a", "b"])["lines"][0]
        self.assertEqual(line, f'ws={ws} params={{"k": [1]}} names=a,b repo={r.resolve()}')
        # a names variable in the caller's environment never leaks in unasked
        with mock.patch.dict("os.environ", {"CHECKS_ROSTER_NAMES": "leaked"}):
            line = runner.run_one(self.entry("ctx"), r)["lines"][0]
        self.assertIn("names=unset", line)


class Applies(Case):
    def test_selection(self):
        self.add_check("everywhere", "exit 0")
        self.add_check("toolsonly", "exit 0", applies_to="tools")
        self.add_check("toponly", "exit 0", applies_to="repos:.")
        self.add_check("named", "exit 0", applies_to="repos:a/b")
        self.add_check("roled", "exit 0", applies_to="roles:x,y")
        ws = self.tmp / "ws"
        write(ws / "CLAUDE.md", "# top\n")
        tool, ab = repo(ws / "tools" / "t"), repo(ws / "a" / "b")

        def ran(path, roles=()):
            return sorted(r["check"] for r in runner.run_repo(path, self.src, ws, roles=roles)["results"])
        self.assertEqual(ran(ws), ["everywhere", "toponly"])
        self.assertEqual(ran(tool), ["everywhere", "toolsonly"])
        self.assertEqual(ran(ab), ["everywhere", "named"])
        self.assertEqual(ran(ab, roles=["y"]), ["everywhere", "named", "roled"])
        self.assertEqual(ran(ab, roles=["z"]), ["everywhere", "named"])

    def test_default_workspace_only_from_a_tools_folder(self):
        self.assertEqual(runner.default_workspace(self.tmp / "tools" / "checks"), self.tmp.resolve())
        self.assertIsNone(runner.default_workspace(self.tmp / "elsewhere" / "checks"))


class Params(Case):
    def setUp(self):
        super().setUp()
        self.add_check("p", "exit 0", params="a,b")
        self.add_check("refusedone", "exit 0", fixture=None)

    def faults(self, data, raw=None):
        r = repo(self.tmp / "r", commit=False)
        write(r / "checks.json", raw if raw is not None else json.dumps(data))
        entries, refused, _ = decl.load(self.src)
        return runner.load_params(r, entries, refused)

    def test_good_and_comment_keys(self):
        self.assertEqual(self.faults({"_comment": "x", "p": {"a": 1}}), ({"p": {"a": 1}}, []))

    def test_each_bad_form_is_a_fault(self):
        cases = [({"ghost": {}}, "`ghost` is not a check"),
                 ({"p": {"a": 1, "z": 2}}, "`p` does not read z"),
                 ({"p": [1]}, "must be an object of params"),
                 ([1], "must be an object of {check"),
                 (None, "does not parse")]
        for data, why in cases:
            with self.subTest(why=why):
                _, faults = self.faults(data, raw="{nope" if data is None else None)
                self.assertTrue(faults and why in faults[0], faults)

    def test_section_for_a_refused_check_is_not_a_second_fault(self):
        self.assertEqual(self.faults({"refusedone": {}})[1], [])

    def test_a_param_fault_turns_the_run_red(self):
        r = repo(self.tmp / "r2", {"checks.json": json.dumps({"ghost": {}})})
        rep = runner.run_repo(r, self.src)
        self.assertFalse(rep["ok"])


class All(Case):
    def test_every_repo_reported_and_one_red_turns_all_red(self):
        self.add_check("needsfile", '[ -f "$1/ok" ] && exit 0; echo "no ok file"; exit 2')
        ws = self.tmp / "ws"
        repo(ws, {"ok": ""})
        repo(ws / "good", {"ok": ""})
        repo(ws / "bad")
        repo(ws / "nested" / "bad2")
        write(ws / ".hidden" / "CLAUDE.md", "")
        (ws / ".hidden" / ".git").mkdir()
        rep = runner.run_all(ws, self.src)
        got = {r["rel"]: r["ok"] for r in rep["repos"]}
        self.assertEqual(got, {".": True, "good": True, "bad": False, "nested/bad2": False})
        self.assertFalse(rep["ok"])

    def test_a_repo_whose_process_prints_no_report_is_a_fault(self):
        with mock.patch.object(runner, "CLI", self.tmp / "no-such-cli"):
            rep = runner._run_repo_process(self.tmp, self.tmp, self.src, None, ())
        self.assertFalse(rep["ok"])
        self.assertIn("printed no report", rep["faults"][0])


class Cli(Case):
    def test_names_from_flag_or_environment_reach_the_check(self):
        self.add_check("n", 'echo "${CHECKS_ROSTER_NAMES-unset}"; exit 2')
        r = repo(self.tmp / "r")
        lines = lambda code_rep: code_rep[1]["results"][0]["lines"][0]
        self.assertEqual(lines(self.cli_json("run", r, "--source", self.src)), "unset")
        self.assertEqual(lines(self.cli_json("run", r, "--source", self.src, "--names", "a,b")), "a,b")
        self.assertEqual(lines(self.cli_json("run", r, "--source", self.src, env={"CHECKS_ROSTER_NAMES": "c"})), "c")

    def test_exit_codes(self):
        self.add_check("good", "exit 0")
        r = repo(self.tmp / "r")
        self.assertEqual(run_cli("run", r, "--source", self.src).returncode, 0)
        self.add_check("bad", 'echo x; exit 2')
        self.assertEqual(run_cli("run", r, "--source", self.src).returncode, 1)
        self.assertEqual(run_cli("list", "--source", self.src).returncode, 0)
        self.add_check("refused", "exit 0", fixture=None)
        self.assertEqual(run_cli("list", "--source", self.src).returncode, 1)
        self.assertEqual(run_cli("bogus").returncode, 2)


class Fixtures(Case):
    """`checks fixtures` must go red for each way a fixture can be wrong."""
    GOOD = ('from checkslib.fixture import Fixture, write\n\n'
            'def passing(t):\n    write(t / "r" / "ok", "")\n    return Fixture(t / "r")\n\n'
            'def failing(t):\n    (t / "r").mkdir()\n    return Fixture(t / "r", expect={expect})\n')
    BODY = '[ -f "$1/ok" ] && exit 0; echo "no ok file"; exit 2'

    def rows(self):
        return {(r["check"], r["fixture"]): r for r in selftest.run(self.src)}

    def test_good_fixture_is_green(self):
        self.add_check("c", self.BODY, fixture=self.GOOD.format(expect='["no ok file"]'))
        self.assertTrue(all(r["ok"] for r in self.rows().values()))

    def test_each_wrong_fixture_is_red(self):
        cases = {
            "noexpect": (self.BODY, self.GOOD.format(expect="[]"), "names no expected finding"),
            "wrongwhy": (self.BODY, self.GOOD.format(expect='["something else"]'), "not for the stated reason"),
            "neverred": ("exit 0", self.GOOD.format(expect='["x"]'), "came back ok, wanted fail"),
            "neverok": ('echo no; exit 2', self.GOOD.format(expect='["no"]'), "came back fail, wanted ok"),
            "raises": (self.BODY, "def passing(t):\n    raise RuntimeError('boom')\n\ndef failing(t):\n    pass\n",
                       "fixture raised RuntimeError"),
            "noload": (self.BODY, "import no_such_module_here\n\ndef passing(t):\n    pass\n\ndef failing(t):\n    pass\n",
                       "fixture file did not load"),
        }
        for n, (body, fx, _) in cases.items():
            self.add_check(n, body, fixture=fx)
        self.add_check("refused", self.BODY, fixture=None)
        rows = self.rows()
        for n, (_, _, why) in cases.items():
            with self.subTest(check=n):
                bad = [r for (c, _), r in rows.items() if c == n and not r["ok"]]
                self.assertTrue(bad, f"{n}: no red row")
                self.assertTrue(any(why in r["why"] for r in bad), [r["why"] for r in bad])
        self.assertIn("refused: no fixtures", rows[("refused", "-")]["why"])

    def test_empty_source_is_red_in_the_cli(self):
        p = run_cli("fixtures", "--source", self.src)
        self.assertEqual(p.returncode, 1)
        self.assertIn("no checks in the source", p.stdout)


class RealChecks(Case):
    """A param a real check declares must change its output (the counterfactual)."""
    SRC = TOOL_ROOT / "source"

    def one(self, name, path, names=None):
        args = ["one", name, path]
        if names:
            args += ["--names", ",".join(names)]
        return self.cli_json(*args)[1]["results"][0]

    def test_no_roster_new_files_are_scanned_and_ignored_ones_are_not(self):
        r = repo(self.tmp / "tools" / "x", {".gitignore": "ignored.py\n", "a.py": "x = 1\n"})
        self.assertEqual(self.one("no-roster", r)["status"], "unchecked")
        plant = "open('" + "agents" + ".manifest.json')\n"
        write(r / "ignored.py", plant)
        self.assertEqual(self.one("no-roster", r)["status"], "unchecked")
        write(r / "new.py", plant)                       # untracked, not ignored: about to be committed
        res = self.one("no-roster", r)
        self.assertEqual(res["status"], "fail")
        self.assertIn("new.py:1", res["lines"][0])

    def test_no_roster_each_path_pattern_catches_its_own_sample(self):
        # assembled, so this file holds none of them whole
        samples = ["agents" + ".manifest.json", ".claude/" + "agents/x.md", ".claude/" + "lib/a.sh",
                   "./" + "agents" + ".sh list", "wiring" + ".json", "dispatches" + ".jsonl", "../" + ".claude"]
        for i, s in enumerate(samples):
            with self.subTest(sample=s):
                r = repo(self.tmp / f"t{i}" / "tools" / "x", {"a.py": f"X = '{s}'\n"})
                res = self.one("no-roster", r)
                self.assertEqual(res["status"], "fail")
                self.assertEqual(len(res["lines"]), 1, res["lines"])   # one pattern per sample, none overlapping

    def test_no_roster_allow_names_and_exclude_change_the_output(self):
        r = repo(self.tmp / "tools" / "x", {"a.py": "PKG = 'sib'\n", "data.json": '"' + ".claude/" + 'lib"\n'})
        res = self.one("no-roster", r, ["sib"])
        self.assertEqual(res["status"], "fail")
        self.assertEqual(len(res["lines"]), 2)
        write(r / "checks.json", json.dumps({"no-roster": {"allow_names": ["sib"], "exclude": ["data.json"]}}))
        self.assertEqual(self.one("no-roster", r, ["sib"])["status"], "ok")

    def test_no_secrets_allow_and_capture_dirs_change_the_output(self):
        fake = "AK" + "IA" + "ABCDEFGHIJKLMNOP"
        r = repo(self.tmp / "r", {".gitignore": ".env\n", "fx/k.txt": f"id = {fake}\n"})
        res = self.one("no-secrets", r)
        self.assertEqual(res["status"], "fail")
        self.assertNotIn(fake, "\n".join(res["lines"]))     # the value is never printed
        write(r / "checks.json", json.dumps({"no-secrets": {"allow": ["fx/*"]}}))
        self.assertEqual(self.one("no-secrets", r)["status"], "ok")
        write(r / "checks.json", json.dumps({"no-secrets": {"allow": ["fx/*"], "capture_dirs": ["caps"]}}))
        self.assertIn("caps: a capture folder", self.one("no-secrets", r)["lines"][0])

    def test_help_matches_script_param_changes_the_target(self):
        good = "usage() {\n  cat <<'EOF'\n  go    run\nEOF\n}\ncase \"$1\" in\n  go) : ;;\n  \"\"|help) usage ;;\nesac\n"
        bad = good.replace("go) : ;;", "go) : ;;\n  gone) : ;;")
        r = repo(self.tmp / "r", {"dev.sh": good, "other.sh": bad})
        self.assertEqual(self.one("help-matches", r)["status"], "ok")
        write(r / "checks.json", json.dumps({"help-matches": {"script": "other.sh"}}))
        self.assertEqual(self.one("help-matches", r)["status"], "fail")

    def test_help_matches_help_arg_param_changes_the_call(self):
        script = ("usage() {\n  cat <<'EOF'\n  go    run\nEOF\n}\ncase \"$1\" in\n  go) : ;;\n"
                  "  usage) usage ;;\n  *) exit 0 ;;\nesac\n")
        r = repo(self.tmp / "r", {"dev.sh": script})
        res = self.one("help-matches", r)
        self.assertEqual(res["status"], "fail")              # `help` prints nothing: no subcommand lines
        write(r / "checks.json", json.dumps({"help-matches": {"help_arg": "usage"}}))
        res = self.one("help-matches", r)
        self.assertEqual(res["status"], "fail")              # the help arm `usage` is now named, not `help`
        self.assertNotIn("printed no subcommand lines", "\n".join(res["lines"]))

    def ws_one(self, name, ws, path):
        return self.cli_json("one", name, path, "--root", ws)[1]["results"][0]

    def test_rules_in_sync_file_param_changes_the_file_read(self):
        ws = self.tmp / "ws"
        rules = "## Keep an active TODO\n\nbelongs in every copy\n\n## Constraints that don't bend\n\n- one\n"
        write(ws / "CLAUDE.md", "# top\n\n" + rules)
        r = repo(ws / "r", {"AGENTS.md": "# r\n\n" + rules})
        res = self.ws_one("rules-in-sync", ws, r)
        self.assertEqual(res["status"], "fail")
        self.assertIn("no section 'Keep an active TODO'", res["lines"][0])   # read CLAUDE.md: r's is bare
        write(r / "checks.json", json.dumps({"rules-in-sync": {"file": "AGENTS.md"}}))
        self.assertEqual(self.ws_one("rules-in-sync", ws, r)["status"], "ok")

    def test_docs_rows_header_param_changes_the_table_read(self):
        ws = self.tmp / "ws"
        write(ws / "CLAUDE.md", "| Tool | x |\n|---|---|\n| `gone/` | x |\n\n| Repo | x |\n|---|---|\n| `a/` | x |\n")
        repo(ws / "a")
        self.assertEqual(self.ws_one("docs-rows", ws, ws)["status"], "fail")
        write(ws / "checks.json", json.dumps({"docs-rows": {"header": "Repo"}}))
        self.assertEqual(self.ws_one("docs-rows", ws, ws)["status"], "ok")


if __name__ == "__main__":
    unittest.main()
