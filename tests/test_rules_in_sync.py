"""rules-in-sync's constraint matching, both ways: the fixture's good copy (own
preamble, own extra bullets, own examples) passes; each fault planted alone in
it fails with exactly one finding that names it; the failing fixture's planted
faults are counted one for one; a top that no longer agrees with CORE fails as
a broken reference; and the real workspace top agrees with CORE."""
import importlib.util
import unittest

from tests.helpers import Case, TOOL_ROOT, WORKSPACE, write

_spec = importlib.util.spec_from_file_location("fx_rules", TOOL_ROOT / "source" / "fixtures" / "rules-in-sync.py")
fx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fx)

# (what is planted, old text in fx.GOOD, new text, the one finding it must raise)
PLANTS = [
    ("claim reworded", "**Never send a message, email or reply on Jacob’s behalf",
     "**Never send a message or reply on Jacob’s behalf", "MISSING: no bullet says \"Never send a message"),
    ("claim deleted", "- Never attempt to bypass bot detection. A detected wall is a result to\n  report -- not an obstacle to route around.\n",
     "", "MISSING: no bullet says \"Never attempt to bypass bot detection.\""),
    ("core dropped", "Same for anything public or irreversible: making this repo public.",
     "Making this repo public.", "drops \"Same for anything public or irreversible\""),
    ("second core dropped", "and don't ask Jacob to repeat a\n  secret back to you.", "and that is all.",
     "drops \"don't ask Jacob to repeat a secret back to you\""),
    ("hedge added", "Not in a\n  fixture or a commit.", "Not in a fixture or a commit, except a local one.",
     "adds 'except'"),
    ("hedge in two words", "not an obstacle to route around.", "not an obstacle to route around, where possible.",
     "adds 'where possible'"),
    ("negation flipped", "**Never send a message, email", "**Always send a message, email",
     "CONTRADICTED: \"Never send a message, email or reply"),
    ("negation dropped", "supplied at run time, never stored.", "supplied at run time, stored.",
     "CONTRADICTED: \"Credential-shaped values are supplied at run time, never stored.\""),
]


class RulesInSync(Case):
    def run_on(self, repo_md, top=fx.TOP):
        ws = self.tmp / "ws"
        write(ws / "CLAUDE.md", top)
        write(ws / "r" / "CLAUDE.md", repo_md)
        return self.cli_json("one", "rules-in-sync", ws / "r", "--root", ws)[1]["results"][0]

    def test_good_copy_passes(self):
        res = self.run_on(fx.GOOD)
        self.assertEqual(res["status"], "ok", res["lines"])

    def test_each_planted_fault_fails_alone_with_one_finding(self):
        for what, old, new, finding in PLANTS:
            with self.subTest(plant=what):
                self.assertIn(old, fx.GOOD, "the plant no longer applies to the good copy")
                res = self.run_on(fx.GOOD.replace(old, new, 1))
                self.assertEqual(res["status"], "fail", res["lines"])
                self.assertEqual(len(res["lines"]), 1, res["lines"])
                self.assertIn(finding, res["lines"][0])

    def test_failing_fixture_counts_its_planted_faults(self):
        res = self.run_on(fx.BAD)
        self.assertEqual(res["status"], "fail")
        self.assertEqual(len(res["lines"]), fx.PLANTED, res["lines"])

    def test_section_absent_or_twice_fails(self):
        start = fx.GOOD.index("## Constraints that don't bend")
        end = fx.GOOD.index("<!-- /shared -->")
        gone = fx.GOOD[:start] + fx.GOOD[end:]
        res = self.run_on(gone)
        self.assertEqual(res["status"], "fail")
        self.assertEqual(res["lines"], ["CLAUDE.md: no section 'Constraints that don't bend'"])
        twice = fx.GOOD + "\n" + fx.GOOD[start:end]
        res = self.run_on(twice)
        self.assertIn("appears 2 times", "\n".join(res["lines"]))

    def test_section_without_bullets_misses_all_four(self):
        res = self.run_on("# r\n\n## Keep an active TODO\n\n## Constraints that don't bend\n\nWe mean well.\n")
        self.assertEqual(res["status"], "fail")
        self.assertEqual(len(res["lines"]), 4, res["lines"])
        self.assertTrue(all("MISSING" in l for l in res["lines"]))

    def test_top_that_drops_a_core_phrase_is_a_broken_reference(self):
        top = fx.TOP.replace("Same for anything public or irreversible.", "")
        res = self.run_on(fx.GOOD, top)
        self.assertEqual(res["status"], "fail")
        self.assertIn("the reference is broken", res["lines"][0])
        self.assertIn("Same for anything public or irreversible", res["lines"][0])

    def test_top_that_drops_a_core_bullet_is_a_broken_reference(self):
        line = next(l for l in fx.TOP.splitlines() if l.startswith("- **Never attempt"))
        res = self.run_on(fx.GOOD, fx.TOP.replace(line + "\n", ""))
        self.assertEqual(res["status"], "fail")
        self.assertIn("no bullet starting \"Never attempt to bypass bot detection\"", res["lines"][0])

    def test_a_new_top_bullet_is_required_without_a_core_entry(self):
        top = fx.TOP + "- **Never delete a backup.** Ask first.\n"
        res = self.run_on(fx.GOOD, top)
        self.assertEqual(res["status"], "fail")
        self.assertEqual(len(res["lines"]), 1, res["lines"])
        self.assertIn("MISSING: no bullet says \"Never delete a backup.\"", res["lines"][0])
        good = fx.GOOD.replace("<!-- /shared -->", "- Never delete a backup, ever.\n<!-- /shared -->")
        self.assertEqual(self.run_on(good, top)["status"], "ok")

    @unittest.skipUnless(WORKSPACE and (WORKSPACE / "CLAUDE.md").is_file(),
                         "no workspace top beside this tool: the real reference went unchecked")
    def test_real_top_agrees_with_core(self):
        res = self.cli_json("one", "rules-in-sync", TOOL_ROOT, "--root", WORKSPACE)[1]["results"][0]
        self.assertNotIn("the reference is broken", "\n".join(res["lines"]))
        self.assertIn(res["status"], ("ok", "fail"), res["lines"])


if __name__ == "__main__":
    unittest.main()
