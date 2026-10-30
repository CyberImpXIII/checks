"""Every way a check can end without judging is classified, on purpose
(ELABORATION-2.4-2.6.md §1.2 part 1): `na` (nothing of this kind is here, a pass
with its reason) or `unchecked` (something is here and this run could not judge
it; never a pass). The list is tests/results-classified.json, one row per
`api.done(na=...)` or `api.done(unchecked=...)` call in source/, keyed by the
check and the reason's literal text. A new call, a changed reason or a class
flipped from one to the other fails here until the list says so, so a branch
cannot slip in unclassified, and a flip is a reviewed line in a diff."""
import ast
import json
import unittest

from tests.helpers import TOOL_ROOT

LIST = TOOL_ROOT / "tests" / "results-classified.json"


def literal(node):
    """The reason as written: string parts kept, each {...} written `{}`; a bare name `<name>`."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(v.value if isinstance(v, ast.Constant) else "{}" for v in node.values)
    if isinstance(node, ast.BinOp):
        return literal(node.left) + literal(node.right)
    if isinstance(node, ast.Name):
        return f"<{node.id}>"
    if isinstance(node, ast.Subscript):
        return f"<{ast.unparse(node)}>"
    return f"<{type(node).__name__}>"


def sites():
    """[{check, class, reason}] for every done(na=...) / done(unchecked=...) in source/."""
    out = []
    for path in sorted((TOOL_ROOT / "source").glob("*.py")):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Call) and getattr(node.func, "attr", getattr(node.func, "id", "")) == "done":
                for kw in node.keywords:
                    if kw.arg in ("na", "unchecked"):
                        out.append({"check": path.stem, "class": kw.arg, "reason": literal(kw.value)})
    return sorted(out, key=lambda s: (s["check"], s["reason"]))


class ResultsClassified(unittest.TestCase):
    def test_every_na_and_unchecked_site_is_listed_with_its_class(self):
        listed = sorted(json.loads(LIST.read_text())["sites"], key=lambda s: (s["check"], s["reason"]))
        self.assertEqual(sites(), listed,
                         "a check gained, lost or reclassified an na/unchecked ending: list it in "
                         "tests/results-classified.json with its class (na: nothing of this kind is "
                         "here; unchecked: something is here and could not be judged)")

    def test_the_scan_sees_both_classes(self):
        got = {s["class"] for s in sites()}
        self.assertEqual(got, {"na", "unchecked"})


if __name__ == "__main__":
    unittest.main()
