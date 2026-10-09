#!/usr/bin/env python3
# checks: applies_to=all params=stores,impl,exclude
# Proves: the repo's store has one way in, its CLI (PLAN-routing-tree.md
# §14.8; PLAN-one-source.md §2.4), in three parts:
#   1. a store needs a cli.json: a store-shaped file on disk (*.db, *.sqlite,
#      *.sqlite3, plus the `stores` param's globs; git-ignored ones count,
#      dot-folders, tests/ and test/ do not, nor anything inside a nested git
#      repo: that repo is judged in its own row) in a repo with no cli.json is
#      a finding, and so is one cli.json's `store` does not name (one gated
#      CLI per store);
#   2. cli.json fits schema/cli.schema.json and its x-rules: paths inside the
#      repo, the CLI exists and is executable, every verb is one `<cli> help`
#      lists, nothing twice;
#   3. nothing reads the store around its CLI: no file in scope names the
#      store's file (its basename, as a token) outside the CLI itself and the
#      `impl` param's globs (the CLI's own modules). Every file cli.json's
#      `store` names counts, whatever its extension: a JSON store (todo.json)
#      is gated once cli.json declares it, with no `stores` param needed. Scope:
#      the files git would commit (outside git: every file, nested git repos
#      pruned), minus *.md, .claude/, tests/, test/, the contract files and
#      checks.json, and the `exclude` param's globs.
# No store and no cli.json is ok: nothing to gate. A cli.json whose store
# globs match no file has nothing to look for, so part 3 is UNCHECKED.
# To pass: write cli.json naming the store and its CLI; move the read into the
# CLI (a verb) and call that; list the CLI's own modules in `impl`; a file that
# only mentions the name (data, not a read) goes in `exclude`.
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checkslib import api, contract, scan  # noqa: E402

STORE_SHAPED = ["*.db", "*.sqlite", "*.sqlite3"]
NEVER_SCANNED = list(contract.FILES) + ["checks.json"]


def in_dot_folder(rel):
    return any(part.startswith(".") for part in rel.split("/")[:-1])


def main():
    ctx = api.context()
    exclude = list(ctx.param("exclude", []))
    impl = list(ctx.param("impl", []))
    shaped = STORE_SHAPED + list(ctx.param("stores", []))
    files = scan.walk(ctx.repo)
    on_disk = [p for p in files if scan.matches(p, shaped) and not in_dot_folder(p)
               and not scan.matches(p, ["tests/*", "test/*"] + exclude)]
    doc, found = contract.read(ctx.repo, contract.CLI)
    if doc is None:
        if found:
            api.done(found)
        api.done([f"{p}: a store with no {contract.CLI} naming its one CLI" for p in on_disk])
    stores = [contract.norm(s) for s in ([doc["store"]] if isinstance(doc["store"], str) else doc["store"])]
    declared = contract.store_files(doc, files)
    findings = list(found)
    findings += [f"{p}: a store {contract.CLI} does not name (one gated CLI per store)"
                 for p in on_disk if p not in declared]
    names = sorted({Path(s).name for s in stores if not contract.GLOB & set(s)} | {Path(p).name for p in declared})
    if not names:
        api.done(findings, unchecked=f"{contract.CLI}'s store matches no file: no name to look for around the CLI")
    rx = re.compile(r"(?<![\w.-])(" + "|".join(map(re.escape, names)) + r")(?![\w-]|\.\w)")
    cli = contract.norm(doc["cli"])
    skip = exclude + impl + NEVER_SCANNED
    for rel in scan.in_scope(ctx):
        if rel == cli or rel in declared or scan.matches(rel, skip):
            continue
        t = scan.text(ctx.repo / rel)
        if t is None:
            continue
        for n, line in enumerate(t.splitlines(), 1):
            for m in rx.finditer(line):
                findings.append(f"{rel}:{n}: names the store `{m.group(1)}` around its CLI `{cli}`")
    api.done(findings)


main()
