"""silent-writes' fixtures: the same append, handled (passing) and with its
failure discarded (failing), so the handling alone turns the result."""
from checkslib.fixture import Fixture, git_repo

HANDLED = """#!/usr/bin/env bash
printf '%s\\n' "$row" >> "$ledger" || { echo "append failed: $ledger" >&2; exit 1; }
echo "a > b"
"""
SILENT = """#!/usr/bin/env bash
{ printf '%s\\n' "$row" >> "$ledger"; } 2>/dev/null || true
"""


def passing(t):
    return Fixture(git_repo(t / "r", {"log.sh": HANDLED, "tests/plant.sh": SILENT}))


def failing(t):
    return Fixture(git_repo(t / "r", {"log.sh": SILENT}),
                   expect=["log.sh:2: >>: its failure is discarded and not handled"])
