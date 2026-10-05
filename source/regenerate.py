#!/usr/bin/env python3
# checks: applies_to=repos:.
# Proves: the workspace top regenerates clean from its one config file
# (PLAN-repo-setup.md §7.10, PLAN-portable-env.md §3.3b step 2): in a fresh
# clone of what a commit would carry (no ignored instance state), every file
# node.json lists as generated is deleted, its `rebuild` is run, and then
# zero drift and zero unaccounted: each generated file comes back byte for
# byte (`absent`, `rebuild`, `missing`, `drift`: as rendered-matches), every
# committable file before or after the rebuild is generated, a record file,
# node.json itself or under a child (`unaccounted`, the progress still to
# make), and no record file was deleted or changed by the rebuild (`record`).
# The counts are this check's own, from git and bytes: it never trusts the
# generator's printed report. It runs at the top only (`repos:.`); a child's
# generated files are its own rendered-matches. node.json is validated first;
# one with any finding is not rebuilt. No node.json, a top outside git, and a
# run nested inside a rebuild are UNCHECKED. The rebuild gets 240s; one that
# does not finish is an error.
# To pass: drift: re-render, never hand-edit; unaccounted: name the file in
# node.json (`generated` if a generator makes it, `record` if it is content),
# or make it a generator's output, or ignore it if it is instance state;
# record: the generator must never touch a record file.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checkslib import regen  # noqa: E402

regen.main(regen.CATEGORIES)
