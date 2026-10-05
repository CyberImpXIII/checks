"""rules-in-sync's rule sentences, both ways: the fixture's good copy (own
preamble, explanations and extra bullets) passes; each rule sentence removed
or changed alone fails with exactly one finding naming it; the failing
fixture's planted faults are counted one for one; prose around the sentences
does not change the result while the top's sentences do (the gate-off probe:
the input changes the output); and the real workspace top yields four."""
import importlib.util
import unittest

from tests.helpers import Case, TOOL_ROOT, WORKSPACE, write

_spec = importlib.util.spec_from_file_location("fx_rules", TOOL_ROOT / "source" / "fixtures" / "rules-in-sync.py")
fx = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fx)

SENTENCES = ["Never send a message, email or reply on Jacob's behalf without asking first.",
             "Never attempt to bypass bot detection.",
             "Credential-shaped values are supplied at run time, never stored.",
             "Report key names, never captured values"]

# (what is planted, old text in fx.GOOD, new text, the sentence then missing)
PLANTS = [
    ("sentence deleted", "- Never attempt to bypass bot detection. A wall is reported, in this repo's words.\n", "",
     SENTENCES[1]),
    ("a word dropped", "Never send a message, email or reply", "Never send a message or reply", SENTENCES[0]),
    ("negation flipped", "supplied at run time, never stored.", "supplied at run time, then stored.", SENTENCES[2]),
    ("reworded", "**Report key names, never captured values.**", "**Name the key, not the value.**", SENTENCES[3]),
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
        for what, old, new, sentence in PLANTS:
            with self.subTest(plant=what):
                self.assertIn(old, fx.GOOD, "the plant no longer applies to the good copy")
                res = self.run_on(fx.GOOD.replace(old, new, 1))
                self.assertEqual(res["status"], "fail", res["lines"])
                self.assertEqual(len(res["lines"]), 1, res["lines"])
                self.assertIn(f"rule sentence missing (from the top's 'Constraints that don't bend'): \"{sentence}\"",
                              res["lines"][0])

    def test_failing_fixture_counts_its_planted_faults(self):
        res = self.run_on(fx.BAD)
        self.assertEqual(res["status"], "fail")
        self.assertEqual(len(res["lines"]), fx.PLANTED, res["lines"])

    def test_prose_around_the_sentences_is_ignored(self):
        noisy = fx.GOOD.replace("These hold whatever the task (a preamble of this repo's own).",
                                "Anything at all, even: we usually send without asking.") \
                       .replace("Not in a\n  fixture.", "Except, sometimes, in a fixture.")
        res = self.run_on(noisy)
        self.assertEqual(res["status"], "ok", res["lines"])

    def test_the_tops_sentences_are_the_input(self):
        # gate-off probe: the same copy goes red when the top's sentence changes,
        # so the check reads the reference, not a list of its own.
        top = fx.TOP.replace("**Never attempt to bypass bot detection.**", "**Never attempt to evade bot detection.**")
        res = self.run_on(fx.GOOD, top)
        self.assertEqual(res["status"], "fail")
        self.assertIn("\"Never attempt to evade bot detection.\"", res["lines"][0])
        top5 = fx.TOP + "- **Never delete a backup.** Ask first.\n"
        res = self.run_on(fx.GOOD, top5)
        self.assertEqual(res["lines"], ["CLAUDE.md: rule sentence missing (from the top's 'Constraints that don't "
                                        "bend'): \"Never delete a backup.\""])

    def test_section_absent_misses_all_four(self):
        res = self.run_on("# r\n\n## Keep an active TODO\n\nWe mean well.\n")
        self.assertEqual(res["status"], "fail")
        self.assertEqual(len(res["lines"]), 4, res["lines"])

    def test_broken_reference_fails(self):
        res = self.run_on(fx.GOOD, fx.TOP.replace("## Constraints that don't bend", "## Constraints"))
        self.assertEqual(res["status"], "fail")
        self.assertIn("the reference is broken", res["lines"][0])

    @unittest.skipUnless(WORKSPACE and (WORKSPACE / "CLAUDE.md").is_file(),
                         "no workspace top beside this tool: the real reference went unchecked")
    def test_real_top_yields_the_four_sentences(self):
        # Read through the check itself: a copy holding exactly the four sentences
        # passes against the real top, and drops to one finding without one.
        md = "# r\n\n" + "\n".join(f"- **{s}**" for s in SENTENCES) + "\n"
        heads = [l for l in (WORKSPACE / "CLAUDE.md").read_text().splitlines() if l.startswith("## ")]
        md += "\n".join(heads) + "\n"      # every top section heading, so only the sentences are tested
        top = (WORKSPACE / "CLAUDE.md").read_text()
        self.assertEqual(self.run_on(md, top)["status"], "ok")
        res = self.run_on(md.replace(f"- **{SENTENCES[1]}**\n", ""), top)
        self.assertEqual(len(res["lines"]), 1, res["lines"])


if __name__ == "__main__":
    unittest.main()
