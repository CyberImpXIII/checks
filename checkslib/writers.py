"""The write-site scan (RESEARCH-writers.md Q4, "could not settle" 1): every line
in a repo's code that writes a file, classified by its primitive and by what
that primitive does to a file at mode 0444 (Q1's probe). Read by `checks
writers` (the report) and the `silent-writes` check (the gate on one class).

It is a SCAN, not a proof: a line-by-line match over the files git would
commit (scan.in_scope: docs, `.claude/` hook copies and tests left out, as
the research's scan did), each hit for a person to read at its line. Comment
lines are skipped. Shell is matched only in shell files (`.sh`, `.bash`, or a
`#!` line naming sh/bash/zsh); quoted text is blanked first, so `echo "a > b"`
is no write. What it cannot see, and says nowhere else: a write through a
variable holding the function (`w = f.write_text; w(...)`), a Python
`try/except: pass` around a write (silent, unseen), and `2>` redirects.

The kinds (Q1): rename (a temp file renamed over the target: goes through at
0444, and may change the mode), in-place (opens the file itself: loud at
0444), sqlite (loud at 0444), chmod (changes the mode), crontab (not a file).
A shell write whose stderr goes to /dev/null and whose failure is not
handled ON THAT LINE (no `||` other than `|| true` / `|| :`, no `&&`, not an
`if`/`while`/`until` condition) is `silent`: at 0444 the row is lost and
nothing says so. A failure handled on a later line is not seen: `silent-writes`
takes an `allow` list of files whose silent sites a person has read."""
import re

from checkslib import scan

AT_0444 = {"rename": "goes through", "in-place": "loud", "sqlite": "loud",
           "chmod": "changes the mode", "crontab": "n/a (not a file)", "silent": "silent"}

PY = [("os.replace", r"\bos\.(?:replace|rename)\(", "rename"),
      ("shutil.move", r"\bshutil\.move\(", "rename"),
      ("write_text", r"\.write_(?:text|bytes)\(", "in-place"),
      ("open(w|a|x)", r"\bopen\([^)]*?['\"][rbt]*[wax+][rbt+]*['\"]", "in-place"),
      ("shutil.copy", r"\bshutil\.copy(?:file|2)?\(", "in-place"),
      ("sqlite3.connect", r"\bsqlite3\.connect\(", "sqlite"),
      ("chmod", r"\b(?:os\.f?chmod|\w+\.chmod)\(", "chmod")]
JS = [("writeFileSync", r"\b(?:writeFileSync|appendFileSync|writeFile|appendFile|createWriteStream)\(", "in-place"),
      ("renameSync", r"\b(?:renameSync|fs\.rename|fs\.promises\.rename)\(", "rename"),
      ("chmodSync", r"\b(?:chmodSync|fs\.chmod)\(", "chmod"),
      ("DatabaseSync", r"\bnew\s+DatabaseSync\(", "sqlite")]
_W = r"(?:^|[\s;&|(])"
SH = [("mv", _W + r"mv\s", "rename"),                  # first: `> "$tmp" && mv "$tmp" f` is a rename (Q1)
      ("sed -i", _W + r"(?:sed\s+-i|perl\s+-[a-z]*i)", "rename"),
      ("install", _W + r"install\s+-", "rename"),
      (">>", r"(?<![<>&0-9])>>\s*(?!&|/dev/(?:null|stderr|stdout)\b)\S", "in-place"),
      (">", r"(?<![<>&0-9=!-])>(?![>&=])\s*(?!/dev/(?:null|stderr|stdout)\b)[\"$~./\w{]", "in-place"),
      ("cp", _W + r"cp\s", "in-place"),
      ("tee", r"\|\s*tee\s", "in-place"),
      ("chmod", _W + r"chmod\s", "chmod"),
      ("crontab -", r"\bcrontab\s+-(?:\s|$)", "crontab"),
      ("sqlite3", _W + r"sqlite3\s", "sqlite")]
LANGS = {"py": (PY, "#"), "js": (JS, "//"), "sh": (SH, "#")}
EXT = {".py": "py", ".js": "js", ".mjs": "js", ".cjs": "js", ".ts": "js", ".sh": "sh", ".bash": "sh"}
SHEBANG = re.compile(r"^#!.*\b(python3?|node|sh|bash|zsh)\b")
BY_SHEBANG = {"python": "py", "python3": "py", "node": "js", "sh": "sh", "bash": "sh", "zsh": "sh"}
QUOTED = re.compile(r"\"(?:[^\"\\]|\\.)*\"|'[^']*'")
ARITH = re.compile(r"\$\(\([^)]*\)\)|\(\([^)]*\)\)")
STDERR_DROPPED = re.compile(r"(?:2|&)>\s*/dev/null")
HANDLED = re.compile(r"\|\|\s*(?!true\b|:(?:\s|$|;))\S|&&|^\s*(?:if|while|until|elif)\b")
COMPILED = {lang: [(n, re.compile(rx), k) for n, rx, k in pats] for lang, (pats, _) in LANGS.items()}


def lang_of(rel, text):
    for ext, lang in EXT.items():
        if rel.endswith(ext):
            return lang
    m = SHEBANG.match(text)
    return BY_SHEBANG[m.group(1)] if m else None


def _silent(line):
    return bool(STDERR_DROPPED.search(line)) and not HANDLED.search(line)


def sites_in(rel, text):
    """[{file, line, primitive, kind, at_0444, code}] for one file's text."""
    lang = lang_of(rel, text)
    if lang is None:
        return []
    comment = LANGS[lang][1]
    out = []
    for n, raw in enumerate(text.splitlines(), 1):
        s = raw.strip()
        if not s or s.startswith(comment) or (lang == "js" and s.startswith("*")):
            continue
        probe = ARITH.sub("0", QUOTED.sub('"s"', raw)) if lang == "sh" else raw
        for name, rx, kind in COMPILED[lang]:
            if rx.search(probe):
                if lang == "sh" and kind == "in-place" and _silent(probe):
                    kind = "silent"
                out.append({"file": rel, "line": n, "primitive": name, "kind": kind,
                            "at_0444": AT_0444[kind], "code": s[:160]})
                break                                   # one row per line: its first primitive
    return out


def scan_repo(ctx):
    """Every write site in the files ctx's repo would commit, file then line order."""
    out = []
    for rel in scan.in_scope(ctx):
        text = scan.text(ctx.repo / rel)
        if text is not None:
            out += sites_in(rel, text)
    return out


def counts(sites):
    c = {}
    for s in sites:
        c[s["kind"]] = c.get(s["kind"], 0) + 1
    return dict(sorted(c.items()))
