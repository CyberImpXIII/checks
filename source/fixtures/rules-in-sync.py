from checkslib.fixture import Fixture, write

TOP = """# top

## Keep an active TODO

This rule belongs in every copy of these rules.

## Only at the top

Nothing here is required elsewhere.

## Constraints that don't bend

- one rule, said in full
- two
"""

GOOD = """# repo

<!-- shared:rules@000000000000 -->
## Keep an active TODO — write it when you notice it

Wording here may differ.

## Constraints that don't bend

- one rule,
  said in full

- two
<!-- /shared -->

## A section of the repo's own
"""

BAD = """# repo

## Constraints that don't bend

- one rule, said in full
- two, reworded
"""


def _ws(t, repo_md):
    write(t / "ws" / "CLAUDE.md", TOP)
    write(t / "ws" / "r" / "CLAUDE.md", repo_md)
    return t / "ws"


def passing(t):
    ws = _ws(t, GOOD)
    return Fixture(ws / "r", workspace=ws)


def failing(t):
    ws = _ws(t, BAD)
    return Fixture(ws / "r", workspace=ws,
                   expect=["no section 'Keep an active TODO'", "'Constraints that don't bend' differs"])
