"""The commands a program's help documents, read from a real run of it. One
reader for every check that asks "does this program offer that command":
help-matches (dev.sh's help against its case), services-valid and accessor (a
declared verb against the CLI's help).

Documented: in the help output, the lines at the indent of the first indented
line that starts with a lowercase word, an optional `<prog> ` or `./<prog> `
prefix allowed (`  checks list ...`, `  ./dev.sh check ...`, `  check ...`)."""
import re
import subprocess

TIMEOUT = 60


def commands(text, prog="dev.sh"):
    word = re.compile(rf"^(\s+)(?:(?:\./)?{re.escape(prog)}\s+)?([a-z][a-z0-9-]*)\b")
    indent, out = None, set()
    for line in text.splitlines():
        m = word.match(line)
        if not m:
            continue
        if indent is None:
            indent = m.group(1)
        if m.group(1) == indent:
            out.add(m.group(2))
    return out


def run(path, cwd, arg="help", via_bash=False):
    """(stdout+stderr, why): why is None when the program ran (any exit code:
    many CLIs exit non-zero after printing usage), else what stopped it."""
    cmd = (["bash", str(path)] if via_bash else [str(path)]) + [arg]
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, stdin=subprocess.DEVNULL, timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        return "", f"timed out after {TIMEOUT}s"
    except OSError as e:
        return "", f"could not start ({e})"
    return p.stdout + p.stderr, None


_CACHE = {}


def listed(path, cwd, arg="help"):
    """The commands `<path> help` documents, or None with why it could not say
    (it did not run, or it printed no command lines). Cached per process: one
    check may ask about the same CLI for several verbs."""
    key = (str(path), str(cwd), arg)
    if key not in _CACHE:
        text, why = run(path, cwd, arg)
        found = commands(text, path.name) if why is None else set()
        if why is None and not found:
            why = "printed no command lines"
        _CACHE[key] = (found or None, why)
    return _CACHE[key]
