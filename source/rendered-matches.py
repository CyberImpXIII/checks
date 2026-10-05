#!/usr/bin/env python3
# checks: applies_to=all
# Proves: every file the repo's node.json lists as generated is exactly what
# its generator renders now (PLAN-repo-setup.md §7.2, §7.10): in a scratch
# copy of what a commit would carry (a clone overlaid with the working tree's
# committable files, never the repo itself), each generated file is deleted,
# node.json's `rebuild` is run, and each must come back byte for byte. Deleting
# first is the point: a generator that skips an existing file would otherwise
# pass by leaving it alone. Findings: `absent` (listed, not in the tree),
# `rebuild` (it would not start or exited non-zero), `missing` (not rendered),
# `drift` (rendered differently; the first differing line is named). The
# comparison is this check's own (bytes), never the generator's own report.
# node.json is validated first (schema/node.schema.json and its x-rules); one
# with any finding is reported and not rebuilt. No node.json is UNCHECKED (the
# contract is unmet, never a pass); so is a folder outside git, and a run
# nested inside a rebuild (setup runs `checks run .` as its last step). The
# rebuild gets 240s; one that does not finish is an error.
# To pass: never edit a generated file by hand: change its source (the parent's
# template) and re-render (`setup <path>`), then commit the render. For
# `absent`/`missing`, list only files the rebuild renders and commit them.
# What regenerate adds at the top (unaccounted files, record safety) is
# `checks explain regenerate`.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checkslib import regen  # noqa: E402

regen.main(("absent", "rebuild", "missing", "drift"))
