"""The `# checks:` declaration a check carries in its leading comment block,
read against vocab.json (the one list of keys), and the source tree it lives
in. The same shape as tools/hooks' `# hooks:` line, so a check contributed by
another layer (`roles:`) arrives the way a generic one does.

A check is refused, with the reason, when any of these is off: its declaration
(unknown key, key given twice, required key missing, value off its pattern),
its explanation (the comment block must say `Proves:` and `To pass:`), its
executable bit, or its fixtures (`fixtures/<name>.py` defining both `passing`
and `failing`). Every fault is collected, never only the first."""
import ast
import json
import os
import re
from pathlib import Path

TOOL_ROOT = Path(__file__).resolve().parent.parent
VOCAB = json.loads((TOOL_ROOT / "vocab.json").read_text())
KEYS = VOCAB["keys"]
NAME_RX = re.compile(r"^[a-z][a-z0-9-]*$")
FIXTURES = "fixtures"
EXPLAIN_PARTS = ("Proves:", "To pass:")

_LINE = re.compile(r"^#\s*checks:\s*(.*?)\s*$")


class DeclError(ValueError):
    pass


def header(text):
    """The leading comment block: the lines up to the first that is not a comment."""
    out = []
    for line in text.splitlines():
        if not line.startswith("#"):
            break
        out.append(line)
    return out


def parse(path):
    path = Path(path)
    found = {}
    lines = [m.group(1) for m in map(_LINE.match, header(path.read_text())) if m]
    if not lines:
        raise DeclError(f"{path.name}: no `# checks:` declaration in its leading comment block")
    for body in lines:
        for pair in body.split():
            if "=" not in pair:
                raise DeclError(f"{path.name}: `{pair}` is not key=value")
            key, value = pair.split("=", 1)
            if key not in KEYS:
                raise DeclError(f"{path.name}: unknown key `{key}` (vocab.json has {', '.join(sorted(KEYS))})")
            if key in found:
                raise DeclError(f"{path.name}: `{key}` given twice")
            found[key] = value
    out = {}
    for key, spec in KEYS.items():
        if key not in found:
            if spec.get("required"):
                raise DeclError(f"{path.name}: required key `{key}` missing")
            found[key] = spec["default"]
        value = found[key]
        if not re.match(spec["pattern"], value):
            raise DeclError(f"{path.name}: {key}={value} does not match {spec['pattern']}")
        out[key] = value
    return out


def explanation(path):
    """The comment block minus the shebang and the declaration: what `explain` prints."""
    out = []
    for line in header(Path(path).read_text()):
        if line.startswith("#!") or _LINE.match(line):
            continue
        out.append(re.sub(r"^# ?", "", line))
    while out and not out[0].strip():
        out.pop(0)
    return "\n".join(out).rstrip() + "\n"


def scope(applies_to):
    """`all` -> ("all", []); `tools` -> ("tools", []); `repos:a,b` -> ("repos", ["a", "b"])."""
    if applies_to in ("all", "tools"):
        return applies_to, []
    kind, _, names = applies_to.partition(":")
    return kind, names.split(",")


def _defines(path, names):
    """Which of `names` the module at path defines as top-level functions (parsed, never imported)."""
    tree = ast.parse(Path(path).read_text(), filename=str(path))
    have = {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}
    return [n for n in names if n not in have]


class Entry:
    def __init__(self, path, d):
        self.path = Path(path)
        self.name = self.path.stem
        self.applies_to = d["applies_to"]
        self.params = [p for p in d["params"].split(",") if p]
        self.fixture = self.path.parent / FIXTURES / f"{self.name}.py"

    def row(self):
        return {"name": self.name, "applies_to": self.applies_to, "params": self.params,
                "file": self.path.name, "fixture": f"{FIXTURES}/{self.fixture.name}"}


def load(src):
    """(entries, refused, faults): the checks that may run, {name: reason} for the
    ones that may not, and faults that belong to no one check (an orphan fixture,
    a file that is not a check)."""
    src = Path(src)
    entries, refused, faults = [], {}, []
    if not src.is_dir():
        return entries, refused, [f"{src}: no such source folder"]
    for p in sorted(src.iterdir()):
        if p.is_dir():
            if p.name not in (FIXTURES, "__pycache__"):
                faults.append(f"{p.name}/: only {FIXTURES}/ belongs beside the checks")
            continue
        if p.suffix != ".py":
            faults.append(f"{p.name}: not a check (checks are <name>.py)")
            continue
        if not NAME_RX.match(p.stem):
            faults.append(f"{p.name}: a check's name must match {NAME_RX.pattern}")
            continue
        why = []
        try:
            d = parse(p)
        except DeclError as e:
            refused[p.stem] = str(e)
            continue
        text = explanation(p)
        why += [f"its explanation lacks `{part}`" for part in EXPLAIN_PARTS if part not in text]
        if not os.access(p, os.X_OK):
            why.append("not executable (the runner runs it directly)")
        e = Entry(p, d)
        if not e.fixture.is_file():
            why.append(f"no fixtures ({FIXTURES}/{e.name}.py with a passing and a failing fixture)")
        else:
            try:
                why += [f"{FIXTURES}/{e.name}.py defines no `{n}` fixture" for n in _defines(e.fixture, ("passing", "failing"))]
            except SyntaxError as err:
                why.append(f"{FIXTURES}/{e.name}.py does not parse: {err}")
        if why:
            refused[e.name] = "; ".join(why)
        else:
            entries.append(e)
    fx = src / FIXTURES
    if fx.is_dir():
        names = {p.stem for p in src.glob("*.py")}
        for p in sorted(fx.glob("*.py")):
            if p.stem not in names:
                faults.append(f"{FIXTURES}/{p.name}: fixtures for no check")
    return entries, refused, faults
