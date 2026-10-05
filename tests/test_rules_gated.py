"""rules-gated: every CLAUDE.md rule section is classified, gate or prose
(PLAN-hard-gates.md §5). The registry is this tool's own gates.json, never a
param, so its logic is tested on a COPY of the tool (checkslib, vocab.json,
the check and a planted gates.json) run by hand, the way api.py says a check
runs. A repo's own gates.json is tested through `checks one`.

Held here: a changed gates.json changes the result (a removed row names its
heading, an added row names itself, a changed quote is named); the shared
block and an `in` repo path select rows; a malformed registry is red; a
planned row whose gate and test exist is reported `landed`; no workspace is
UNCHECKED; the registry's `keys` vocabulary equals what the check reads; and
every row of the real registry holds against the real workspace."""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path

from tests.helpers import TOOL_ROOT, WORKSPACE, Case, write

MD = """# r

## Never push on a Friday — ENFORCED

**No push on a Friday.** The guard blocks it.

## Prefer short names

Short names read better.
"""
ROWS = [
    {"id": "friday", "section": "Never push on a Friday", "rule": "No push on a Friday",
     "kind": "gate", "how": "block", "gate": "gates/guard.sh", "test": "gates/test-guard.sh"},
    {"id": "short-names", "section": "Prefer short names", "rule": "Short names read better",
     "kind": "prose", "why": "taste"},
]
SHARED_MD = """# s

<!-- shared:rules@0 -->
## Shared rules

**Do not edit it here.**

## Keep it small

**Small files only.**
<!-- /shared -->

## Local thing

Local words.
"""


def load_check():
    spec = importlib.util.spec_from_file_location("rules_gated", TOOL_ROOT / "source" / "rules-gated.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class OwnGatesJson(Case):
    """A repo's own gates.json, through the real runner."""

    def ws(self, md=MD, rows=ROWS):
        ws = self.tmp / "ws"
        write(ws / "gates" / "guard.sh", "#!/bin/sh\nexit 2\n", 0o755)
        write(ws / "gates" / "test-guard.sh", "#!/bin/sh\n# runs guard.sh\n", 0o755)
        write(ws / "PLAN-x.md", "# x\n\n## 2. Two\n")
        write(ws / "r" / "CLAUDE.md", md)
        write(ws / "r" / "gates.json", json.dumps({"rules": rows}))
        return ws

    def run_one(self, ws):
        code, doc = self.cli_json("one", "rules-gated", ws / "r", "--root", ws)
        return doc["results"][0]

    def test_ok_prints_the_counts(self):
        res = self.run_one(self.ws())
        self.assertEqual(res["status"], "ok", res)
        self.assertEqual(res["lines"][0], "rows here: 2 (1 gated, 0 planned, 1 prose); planned: none")

    def test_removed_row_names_its_heading(self):
        res = self.run_one(self.ws(rows=ROWS[:1]))
        self.assertEqual(res["status"], "fail")
        self.assertEqual(res["lines"], ["CLAUDE.md:7: section 'Prefer short names' (this repo's own sections) has no row "
                                        "(classify it: kind gate with its gate, or kind prose with why)"])

    def test_added_row_without_heading_names_the_row(self):
        rows = ROWS + [{"id": "extra", "section": "Nowhere", "rule": "x", "kind": "prose", "why": "w"}]
        res = self.run_one(self.ws(rows=rows))
        self.assertEqual(res["lines"], ["gates.json row 'extra': no section 'Nowhere' in CLAUDE.md (this repo's own sections)"])

    def test_changed_quote_is_named(self):
        rows = [dict(ROWS[0], rule="No push on a Monday"), ROWS[1]]
        res = self.run_one(self.ws(rows=rows))
        self.assertEqual(len(res["lines"]), 1, res)
        self.assertIn("row 'friday': rule not in section", res["lines"][0])

    def test_heading_prefix_must_end_at_a_word(self):
        rows = [dict(ROWS[0], section="Never push on a Fri"), ROWS[1]]
        res = self.run_one(self.ws(rows=rows))
        self.assertEqual(res["status"], "fail")
        self.assertIn("no section 'Never push on a Fri'", "\n".join(res["lines"]))

    def test_planned_row_then_landed(self):
        md = MD + "\n## Back up nightly\n\n**Backed up every night.**\n"
        planned = {"id": "backup", "section": "Back up nightly", "rule": "Backed up every night", "kind": "gate",
                   "how": "check", "status": "planned", "plan": "PLAN-x.md §2",
                   "gate": "gates/backup.sh", "test": "gates/test-backup.sh"}
        ws = self.ws(md=md, rows=ROWS + [planned])
        res = self.run_one(ws)
        self.assertEqual(res["lines"], ["rows here: 3 (1 gated, 1 planned, 1 prose); planned: backup"])
        write(ws / "gates" / "backup.sh", "#!/bin/sh\n", 0o755)
        write(ws / "gates" / "test-backup.sh", "#!/bin/sh\n", 0o755)
        res = self.run_one(ws)
        self.assertEqual(res["status"], "ok")
        self.assertIn("landed: 'backup' is planned but gates/backup.sh and its test exist: make it active", res["lines"])

    def test_template_gate_need_not_be_executable(self):
        ws = self.ws(rows=[dict(ROWS[0], template=True), ROWS[1]])
        os.chmod(ws / "gates" / "guard.sh", 0o644)
        self.assertEqual(self.run_one(ws)["status"], "ok")
        write(ws / "r" / "gates.json", json.dumps({"rules": ROWS}))        # the same, without `template`
        self.assertEqual(self.run_one(ws)["lines"], [
            "gates.json row 'friday': gate gates/guard.sh not executable "
            "(a template another tool installs says `template: true`)"])

    def test_test_must_name_the_gate(self):
        ws = self.ws(rows=[dict(ROWS[0], test="gates/t.sh"), ROWS[1]])
        write(ws / "gates" / "t.sh", "#!/bin/sh\n# tests something else\n", 0o755)
        res = self.run_one(ws)
        self.assertEqual(res["lines"], ["gates.json row 'friday': test gates/t.sh does not name the gate guard.sh"])

    def test_own_row_may_not_carry_in(self):
        res = self.run_one(self.ws(rows=[dict(ROWS[0], **{"in": ["."]}), ROWS[1]]))
        self.assertIn("`in` is the registry's", "\n".join(res["lines"]))


class RegistryCopy(Case):
    """The registry's logic, on a copy of the tool with a planted registry."""

    KEYS = {k: "k" for k in ("id", "section", "rule", "in", "kind", "how", "gate", "test", "template",
                             "status", "plan", "why", "note")}

    def tool(self, rules, keys=None):
        tool = self.tmp / "tool"
        shutil.copytree(TOOL_ROOT / "checkslib", tool / "checkslib", ignore=shutil.ignore_patterns("__pycache__"))
        shutil.copy(TOOL_ROOT / "vocab.json", tool / "vocab.json")
        write(tool / "source" / "rules-gated.py", (TOOL_ROOT / "source" / "rules-gated.py").read_text(), 0o755)
        write(tool / "gates.json", json.dumps({"keys": self.KEYS if keys is None else keys, "rules": rules}))
        return tool

    def run_copy(self, tool, repo, ws):
        env = {k: v for k, v in os.environ.items() if not k.startswith("CHECKS_")}
        if ws is not None:
            env["CHECKS_WORKSPACE"] = str(ws)
        p = subprocess.run([sys.executable, str(tool / "source" / "rules-gated.py"), str(repo)],
                           capture_output=True, text=True, env=env)
        return p.returncode, p.stdout.splitlines()

    def shared_rules(self):
        return [{"id": "s-head", "section": "Shared rules", "rule": "Do not edit it here", "in": ["shared"],
                 "kind": "prose", "why": "w"},
                {"id": "s-small", "section": "Keep it small", "rule": "Small files only", "in": ["shared"],
                 "kind": "prose", "why": "w"},
                {"id": "local", "section": "Local thing", "rule": "Local words", "in": ["a"],
                 "kind": "prose", "why": "w"}]

    def test_shared_block_and_in_path_select_rows(self):
        ws = self.tmp / "ws"
        write(ws / "a" / "CLAUDE.md", SHARED_MD)
        write(ws / "b" / "CLAUDE.md", SHARED_MD)
        tool = self.tool(self.shared_rules())
        code, out = self.run_copy(tool, ws / "a", ws)
        self.assertEqual((code, out), (0, ["rows here: 3 (0 gated, 0 planned, 3 prose); planned: none"]))
        # b carries the same block, but row `local` is a's: b's own section has no row
        code, out = self.run_copy(tool, ws / "b", ws)
        self.assertEqual(code, 2)
        self.assertEqual(out, ["CLAUDE.md:13: section 'Local thing' (this repo's own sections) has no row "
                               "(classify it: kind gate with its gate, or kind prose with why)"])

    def test_a_shared_heading_without_a_row_is_named(self):
        ws = self.tmp / "ws"
        write(ws / "a" / "CLAUDE.md", SHARED_MD)
        code, out = self.run_copy(self.tool(self.shared_rules()[1:]), ws / "a", ws)
        self.assertEqual(code, 2)
        self.assertEqual(out, ["CLAUDE.md:4: section 'Shared rules' (the shared block) has no row "
                               "(classify it: kind gate with its gate, or kind prose with why)"])

    def test_registry_without_in_or_keys_is_red(self):
        ws = self.tmp / "ws"
        write(ws / "a" / "CLAUDE.md", SHARED_MD)
        rules = self.shared_rules()
        rules[0] = {k: v for k, v in rules[0].items() if k != "in"}
        code, out = self.run_copy(self.tool(rules), ws / "a", ws)
        self.assertEqual(code, 2)
        self.assertIn("tools/checks/gates.json row 's-head': `in` missing", "\n".join(out))
        shutil.rmtree(self.tmp / "tool")
        code, out = self.run_copy(self.tool(self.shared_rules(), keys={}), ws / "a", ws)
        self.assertEqual(code, 2)             # no rows read: the finding, then every heading unclassified
        self.assertEqual(out[0], "tools/checks/gates.json: no `keys` vocabulary")

    def test_unknown_key_and_bad_shapes_are_named(self):
        ws = self.tmp / "ws"
        write(ws / "a" / "CLAUDE.md", SHARED_MD)
        rules = self.shared_rules()
        rules[2] = dict(rules[2], colour="red")
        rules.append({"id": "g", "section": "Local thing", "rule": "Local words", "in": ["a"], "kind": "gate",
                      "how": "hope", "status": "planned"})
        code, out = self.run_copy(self.tool(rules), ws / "a", ws)
        text = "\n".join(out)
        self.assertEqual(code, 2)
        for want in ("row 'local': unknown key(s) colour", "row 'g': `how` must be one of",
                     "row 'g': planned without a `plan` pointer"):
            self.assertIn(want, text)

    def test_duplicate_id_across_registry_and_own_file(self):
        ws = self.tmp / "ws"
        write(ws / "a" / "CLAUDE.md", SHARED_MD)
        write(ws / "a" / "gates.json", json.dumps({"rules": [{"id": "s-small", "section": "Local thing",
                                                              "rule": "Local words", "kind": "prose", "why": "w"}]}))
        rules = self.shared_rules()[:2]
        code, out = self.run_copy(self.tool(rules), ws / "a", ws)
        self.assertEqual((code, out), (2, ["row id 's-small' used more than once (registry and repo rows share one id space)"]))

    def test_no_workspace_is_unchecked(self):
        ws = self.tmp / "ws"
        write(ws / "a" / "CLAUDE.md", SHARED_MD)
        tool = self.tool(self.shared_rules()[:2])
        # without a workspace no repo path applies; an unclassified section is still a finding
        code, out = self.run_copy(tool, ws / "a", None)
        self.assertEqual(code, 2, out)
        write(ws / "a" / "gates.json", json.dumps({"rules": [{"id": "l", "section": "Local thing",
                                                              "rule": "Local words", "kind": "prose", "why": "w"}]}))
        code, out = self.run_copy(tool, ws / "a", None)
        self.assertEqual(code, 3, out)
        self.assertEqual(out, ["no workspace top: sections are classified, but gate paths and plan pointers went unchecked"])


class RealRegistry(Case):
    def test_keys_vocabulary_equals_what_the_check_reads(self):
        reg = json.loads((TOOL_ROOT / "gates.json").read_text())
        src = (TOOL_ROOT / "source" / "rules-gated.py").read_text()
        for k in reg["keys"]:
            self.assertTrue(f'"{k}"' in src, f"key {k} in gates.json is read by no code")
        used = {k for rule in reg["rules"] for k in rule}
        self.assertEqual(used - set(reg["keys"]), set())

    @unittest.skipIf(WORKSPACE is None, "this tool is not inside a workspace")
    def test_every_registry_row_holds_against_the_workspace(self):
        mod = load_check()
        rows, findings, _ = mod.load(TOOL_ROOT / "gates.json", "tools/checks/gates.json", registry=True)
        self.assertEqual(findings, [])
        landed = []
        for r in rows:
            findings += mod.check_paths(r, "tools/checks/gates.json", WORKSPACE, landed)
        self.assertEqual(findings, [])

    @unittest.skipIf(WORKSPACE is None, "this tool is not inside a workspace")
    def test_the_top_and_this_repo_are_classified(self):
        for repo in (WORKSPACE, TOOL_ROOT):
            code, doc = self.cli_json("one", "rules-gated", repo, "--root", WORKSPACE)
            res = doc["results"][0]
            self.assertEqual(res["status"], "ok", (repo, res))


if __name__ == "__main__":
    unittest.main()
