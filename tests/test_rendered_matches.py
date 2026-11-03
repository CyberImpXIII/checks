"""rendered-matches asks setup (remediation 2.4 part 3; Jacob's "b" of ra-2.2): with no
node.json, the components setup renders into repos (named by its fanout's refusal of
any other) are asked of this repo alone, `setup fanout <c> --repos <repo> --dry-run
--json`. unchanged is ok, undeclared skipped, would-commit and a named drift are red,
any other answer is UNCHECKED, none carried is n/a; no setup tool is UNCHECKED. A
fake setup in a fake workspace answers from a file, so every branch is shown."""
import json

from tests.helpers import Case, repo, write

FAKE = r"""#!/usr/bin/env bash
# a stand-in for tools/setup/setup: `fanout <component> ...` answers from answers.json beside it
here=$(cd "$(dirname "$0")" && pwd)
echo "$*" >> "$here/calls"
[ "$1" = fanout ] || exit 64
c=$2
if ! jq -e --arg c "$c" 'has($c)' "$here/answers.json" >/dev/null; then
  echo "setup fanout: fanout $c: not a fanout component (one of: $(jq -r 'keys_unsorted | join(", ")' "$here/answers.json"))" >&2
  exit 2
fi
a=$(jq -c --arg c "$c" '.[$c]' "$here/answers.json")
case "$a" in
  \"refuse:*) jq -r --arg c "$c" '.[$c] | ltrimstr("refuse:")' "$here/answers.json" >&2; exit 2 ;;
  \"*) jq -r --arg c "$c" '.[$c]' "$here/answers.json" ;;
  *) jq -c --arg c "$c" '{component: $c, dry_run: true, repos: [.[$c]]}' "$here/answers.json" ;;
esac
"""


def row(status, detail="", written=()):
    return {"path": "r", "status": status, "detail": detail, "written": list(written), "commit": None}


class AsksSetup(Case):
    def ws(self, answers, tool=True):
        ws = self.tmp / "ws"
        r = repo(ws / "r")
        if tool:
            write(ws / "tools" / "setup" / "setup", FAKE, 0o755)
            write(ws / "tools" / "setup" / "answers.json", json.dumps(answers))
        return ws, r

    def one(self, ws, r):
        return self.cli_json("one", "rendered-matches", r, "--root", ws)[1]["results"][0]

    def test_every_carried_render_unchanged_is_ok_and_says_which(self):
        ws, r = self.ws({"rules": row("unchanged"), "parts": row("unchanged"), "mutate": row("undeclared")})
        res = self.one(ws, r)
        self.assertEqual(res["status"], "ok", res)
        self.assertEqual(res["lines"], ["renders match setup's: rules, parts"])
        calls = (ws / "tools" / "setup" / "calls").read_text()
        self.assertIn(f"fanout parts --repos {r.resolve()} --dry-run --json --root {ws.resolve()}", calls)

    def test_a_render_setup_would_write_is_drift_naming_its_files(self):
        ws, r = self.ws({"rules": row("unchanged"), "parts": row("would-commit", "1 file(s) would be rendered",
                                                                   ["devtools/parts.py"])})
        res = self.one(ws, r)
        self.assertEqual(res["status"], "fail", res)
        self.assertEqual(res["lines"], ["drift: parts: setup would render devtools/parts.py"])

    def test_a_failed_render_is_drift_only_when_setup_names_a_drift(self):
        ws, r = self.ws({"parts": row("failed", "parts drift: devtools/parts.py: its meaning differs; nothing written")})
        res = self.one(ws, r)
        self.assertEqual(res["status"], "fail", res)
        self.assertTrue(res["lines"][0].startswith("drift: parts: parts drift: devtools/parts.py"), res)
        ws2 = self.tmp / "ws2"
        ws2, r2 = ws2, repo(ws2 / "r")
        write(ws2 / "tools" / "setup" / "setup", FAKE, 0o755)
        write(ws2 / "tools" / "setup" / "answers.json", json.dumps({"parts": row("failed", "the source moved during the run")}))
        res = self.one(ws2, r2)
        self.assertEqual(res["status"], "unchecked", res)
        self.assertIn("parts: failed: the source moved", res["lines"][0])

    def test_a_component_rendered_from_the_names_record_is_named_not_judged(self):
        """setup refuses to fan out siblings without --names (PLAN-O18); this check never reads
        the names record, so it names the component and judges the rest."""
        ws, r = self.ws({"rules": row("unchanged"), "parts": row("unchanged"),
                         "siblings": "refuse:setup fanout: fanout siblings: --names FILE is required (the sibling "
                                     "table is rendered from the names record, never looked for)"})
        res = self.one(ws, r)
        self.assertEqual(res["status"], "ok", res)
        self.assertEqual(res["lines"], ["renders match setup's: rules, parts; not judged here: siblings (rendered "
                                        "from the names record, which setup is handed and this check never reads)"])
        ws2 = self.tmp / "ws2"
        ws2, r2 = ws2, repo(ws2 / "r")
        write(ws2 / "tools" / "setup" / "setup", FAKE, 0o755)
        write(ws2 / "tools" / "setup" / "answers.json", json.dumps({"parts": "refuse:setup fanout: something else"}))
        self.assertEqual(self.one(ws2, r2)["status"], "unchecked")

    def test_a_repo_carrying_none_is_na(self):
        ws, r = self.ws({"rules": row("undeclared"), "parts": row("undeclared")})
        res = self.one(ws, r)
        self.assertEqual((res["status"], res.get("na")), ("ok", True), res)
        self.assertIn("setup renders none of its components (rules, parts)", res["lines"][0])

    def test_no_setup_tool_or_an_unreadable_answer_is_unchecked_never_ok(self):
        ws, r = self.ws({}, tool=False)
        res = self.one(ws, r)
        self.assertEqual(res["status"], "unchecked", res)
        self.assertIn("no setup tool at tools/setup/setup", res["lines"][0])
        ws2 = self.tmp / "ws2"
        r2 = repo(ws2 / "r")
        write(ws2 / "tools" / "setup" / "setup", FAKE, 0o755)
        write(ws2 / "tools" / "setup" / "answers.json", json.dumps({"parts": "not json at all"}))
        res = self.one(ws2, r2)
        self.assertEqual(res["status"], "unchecked", res)
        self.assertIn("parts: setup gave no report", res["lines"][0])
        ws3 = self.tmp / "ws3"
        r3 = repo(ws3 / "r")
        write(ws3 / "tools" / "setup" / "setup", "#!/usr/bin/env bash\necho nothing >&2\nexit 2\n", 0o755)
        res = self.one(ws3, r3)
        self.assertEqual(res["status"], "unchecked", res)
        self.assertIn("setup named no fanout components", res["lines"][0])

    def test_a_node_json_is_judged_by_its_rebuild_and_setup_is_not_asked(self):
        ws, r = self.ws({"parts": row("would-commit", "", ["x"])})
        write(r / "node.json", json.dumps({"rebuild": ["true"], "generated": [], "record": ["CLAUDE.md"]}))
        res = self.one(ws, r)
        self.assertEqual(res["status"], "ok", res)
        self.assertFalse((ws / "tools" / "setup" / "calls").exists())
