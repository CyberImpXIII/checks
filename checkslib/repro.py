"""Same input, same output (PLAN-architecture.md §12.2): the comparison `repro`
makes between two runs of one read verb. One reader of cli.json's `read`
(the volatile paths, `{fixture}`), used by source/repro.py and held by
tests/test_repro.py.

A volatile path is dot-separated keys from the document's root; `*` is every
key of an object or every item of an array (contract.volatile_parts parses it,
contract's `volatile-paths` rule holds its shape). Removing a path deletes
the key (or every item, for a final `*` on an array). `strip` counts what
each path removed, so a path that removes nothing in either run is a finding:
a declared input that changes nothing is caught, never trusted.

The comparison is of the re-serialised documents with key order KEPT (no
sort): an object whose keys come out in a different order is a difference,
as an unsorted list is. Whitespace is not compared: the same program prints
the same document the same way.

A read verb also leaves its fixture as it found it: `snapshot` before and
after a verb's two runs, `tree_changes` names each path added, removed or
changed (contents by sha256, so a rewrite with the same bytes is no change)."""
import copy
import hashlib
import json
import os
from pathlib import Path

from checkslib import contract

SHOW = 80


def _remove(node, parts):
    """Delete what `parts` names inside node, in place; the number of values removed."""
    head, rest = parts[0], parts[1:]
    if isinstance(node, dict):
        keys = list(node) if head == "*" else ([head] if head in node else [])
        if not rest:
            for k in keys:
                del node[k]
            return len(keys)
        return sum(_remove(node[k], rest) for k in keys)
    if isinstance(node, list) and head == "*":
        if not rest:
            n = len(node)
            node.clear()
            return n
        return sum(_remove(item, rest) for item in node)
    return 0


def strip(doc, volatile):
    """(a copy of doc with every volatile path removed, {path: values removed})."""
    doc = copy.deepcopy(doc)
    removed = {}
    for path in volatile:
        parts = contract.volatile_parts(path)
        removed[path] = _remove(doc, parts) if parts else 0
    return doc, removed


def canonical(doc):
    return json.dumps(doc, ensure_ascii=False, separators=(",", ":"))


def _show(v):
    s = json.dumps(v, ensure_ascii=False)
    return s if len(s) <= SHOW else s[:SHOW - 3] + "..."


def first_difference(a, b, where="$"):
    """Where two documents first differ, as `<path>: <a> vs <b>`; None when equal (order kept)."""
    if type(a) is not type(b):
        return f"{where}: {_show(a)} vs {_show(b)}"
    if isinstance(a, dict):
        if list(a) != list(b):
            return f"{where}: keys {_show(list(a))} vs {_show(list(b))}"
        for k in a:
            d = first_difference(a[k], b[k], f"{where}.{k}")
            if d:
                return d
        return None
    if isinstance(a, list):
        for i, (x, y) in enumerate(zip(a, b)):
            d = first_difference(x, y, f"{where}[{i}]")
            if d:
                return d
        if len(a) != len(b):
            return f"{where}: {len(a)} items vs {len(b)}"
        return None
    return None if a == b else f"{where}: {_show(a)} vs {_show(b)}"


def snapshot(root):
    """{relative posix path: what it holds} for every entry under root: a file's
    sha256, a link's target, a folder's marker (so an added empty folder counts)."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        base = Path(dirpath)
        for name in dirnames + filenames:
            p = base / name
            rel = p.relative_to(root).as_posix()
            if p.is_symlink():
                out[rel] = "link:" + os.readlink(p)
            elif p.is_dir():
                out[rel] = "dir"
            else:
                out[rel] = "sha256:" + hashlib.sha256(p.read_bytes()).hexdigest()
    return out


def tree_changes(before, after):
    """`added x`, `removed x`, `changed x` between two snapshots, sorted by path; [] when equal."""
    return [f"{'added' if p not in before else 'removed' if p not in after else 'changed'} {p}"
            for p in sorted(set(before) | set(after)) if before.get(p) != after.get(p)]


def substitute(text, fixture):
    """`{fixture}` replaced by the scratch copy's path (None: no fixture, left as is)."""
    return text if fixture is None else text.replace(contract.FIXTURE_MARK, str(fixture))


def compare(verb, runs, volatile):
    """Findings for one verb's two runs, each (exit code, stdout). Every one
    found: an output that is not JSON, a volatile path that removed nothing,
    a different exit code, a different document."""
    out, docs = [], []
    for n, (code, text) in enumerate(runs, 1):
        try:
            docs.append(json.loads(text))
        except ValueError as e:
            first = (text.strip().splitlines() or ["(nothing on stdout)"])[0][:SHOW]
            out.append(f"`{verb}`: run {n} printed no JSON document (exit {code}; {getattr(e, 'msg', e)}): {first}")
    if len(docs) != len(runs):
        return out
    stripped, hits = [], {p: 0 for p in volatile}
    for d in docs:
        s, removed = strip(d, volatile)
        stripped.append(s)
        for p, k in removed.items():
            hits[p] += k
    out += [f"`{verb}`: volatile `{p}` removes nothing in either run (misspelt, or no longer printed): "
            f"a declared field that changes nothing" for p in volatile if not hits[p]]
    codes = [c for c, _ in runs]
    if len(set(codes)) > 1:
        out.append(f"`{verb}`: exit codes differ between runs: {' vs '.join(map(str, codes))}")
    if canonical(stripped[0]) != canonical(stripped[1]):
        out.append(f"`{verb}`: two runs differ after the volatile fields are removed, first at "
                   f"{first_difference(stripped[0], stripped[1]) or '$ (how a value is written)'}")
    return out
