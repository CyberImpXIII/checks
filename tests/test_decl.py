"""The declaration line and the source tree: every malformed form is refused
with its reason, every fault is collected (never only the first)."""
import unittest

from tests.helpers import Case, write, check_text
from checkslib import decl


class Parse(Case):
    def parse(self, line):
        p = write(self.tmp / "c.py", f"#!/usr/bin/env bash\n{line}\n# Proves: x\nexit 0\n")
        return decl.parse(p)

    def test_good_line_and_default(self):
        self.assertEqual(self.parse("# checks: applies_to=all"), {"applies_to": "all", "params": ""})
        self.assertEqual(self.parse("# checks: applies_to=repos:.,tools/x params=a,b_c"),
                         {"applies_to": "repos:.,tools/x", "params": "a,b_c"})

    def test_each_bad_form_is_refused_with_its_reason(self):
        cases = {
            "# checks: applies_to=all colour=red": "unknown key `colour`",
            "# checks: applies_to=all applies_to=tools": "given twice",
            "# checks: params=a": "required key `applies_to` missing",
            "# checks: applies_to=some": "does not match",
            "# checks: applies_to=repos:": "does not match",
            "# checks: applies_to=all params=Bad-Name": "does not match",
            "# checks: applies_to": "is not key=value",
            "# nothing declared": "no `# checks:` declaration",
        }
        for line, why in cases.items():
            with self.subTest(line=line):
                with self.assertRaises(decl.DeclError) as cm:
                    self.parse(line)
                self.assertIn(why, str(cm.exception))

    def test_declaration_below_the_comment_block_is_not_read(self):
        p = write(self.tmp / "c.py", "#!/usr/bin/env bash\necho hi\n# checks: applies_to=all\n")
        with self.assertRaises(decl.DeclError):
            decl.parse(p)

    def test_scope(self):
        self.assertEqual(decl.scope("all"), ("all", []))
        self.assertEqual(decl.scope("tools"), ("tools", []))
        self.assertEqual(decl.scope("repos:.,a/b"), ("repos", [".", "a/b"]))
        self.assertEqual(decl.scope("roles:x"), ("roles", ["x"]))

    def test_explanation_drops_shebang_and_declaration(self):
        p = write(self.tmp / "c.py", check_text("exit 0"))
        self.assertEqual(decl.explanation(p), "Proves: a test check.\nTo pass: nothing.\n")


class Load(Case):
    def test_a_good_check_loads(self):
        self.add_check("good", "exit 0", params="k")
        entries, refused, faults = decl.load(self.src)
        self.assertEqual([(e.name, e.params) for e in entries], [("good", ["k"])])
        self.assertEqual((refused, faults), ({}, []))

    def test_every_refusal_reason_is_collected(self):
        self.add_check("vague", "exit 0", proves=False, executable=False, fixture=None)
        _, refused, _ = decl.load(self.src)
        why = refused["vague"]
        for part in ("lacks `Proves:`", "lacks `To pass:`", "not executable", "no fixtures"):
            self.assertIn(part, why)

    def test_fixture_must_define_both_and_parse(self):
        self.add_check("half", "exit 0", fixture="def passing(t):\n    pass\n")
        self.add_check("broken", "exit 0", fixture="def passing(t:\n")
        _, refused, _ = decl.load(self.src)
        self.assertIn("defines no `failing` fixture", refused["half"])
        self.assertIn("does not parse", refused["broken"])

    def test_bad_declaration_is_refused_not_crashed(self):
        write(self.src / "odd.py", "#!/usr/bin/env bash\n# checks: applies_to=nowhere\nexit 0\n", 0o755)
        entries, refused, _ = decl.load(self.src)
        self.assertEqual(entries, [])
        self.assertIn("does not match", refused["odd"])

    def test_tree_faults(self):
        self.add_check("good", "exit 0")
        write(self.src / "notes.txt", "x")
        write(self.src / "Bad_Name.py", check_text("exit 0"), 0o755)
        write(self.src / "lib" / "x.py", "")
        write(self.src / "fixtures" / "ghost.py", "")
        entries, _, faults = decl.load(self.src)
        self.assertEqual([e.name for e in entries], ["good"])
        text = "\n".join(faults)
        for part in ("notes.txt: not a check", "Bad_Name.py: a check's name", "lib/: only fixtures/",
                     "fixtures/ghost.py: fixtures for no check"):
            self.assertIn(part, text)

    def test_missing_source(self):
        self.assertIn("no such source folder", decl.load(self.tmp / "nope")[2][0])


if __name__ == "__main__":
    unittest.main()
