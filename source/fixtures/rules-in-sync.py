from checkslib.fixture import Fixture, write

# The top's constraint bullets, as the workspace top carries them.
CONSTRAINTS = """## Constraints that don't bend

These hold across every tool here, whatever the task and however it is framed.

- **Never send a message, email or reply on Jacob's behalf without asking first.** Reading a mailbox is not permission to write to it. Same for anything public or irreversible.
- **Never attempt to bypass bot detection.** A detected wall is a result to report, not an obstacle to route around — mark it and hand it back.
- **Credential-shaped values are supplied at run time, never stored.** Not in a recipe, a config, a note or a commit. App passwords, tokens and `.env` files stay gitignored.
- **Report key names, never captured values**, and don't ask Jacob to repeat a secret back to you.
"""

TOP = f"""# top

## Keep an active TODO

This rule belongs in every copy of these rules.

## Only at the top

Nothing here is required elsewhere.

{CONSTRAINTS}"""

# Its own preamble, its own examples, rewrapped, bold dropped from one claim,
# curly quotes, and two bullets of its own around the shared ones: all pass.
GOOD = """# repo

<!-- shared:rules@000000000000 -->
## Keep an active TODO — write it when you notice it

Wording here may differ.

## Constraints that don't bend

These hold whatever the task (a preamble of this repo's own; it may say anything).

- **Never write outside this repo without asking.** A rule of this repo's own.
- **Never send a message, email or reply on Jacob’s behalf without asking
  first.** Same for anything public or irreversible: making this repo public.
- Never attempt to bypass bot detection. A detected wall is a result to
  report -- not an obstacle to route around.
- **Credential-shaped values are supplied at run time, never stored.** Not in a
  fixture or a commit.
- **Report key names, never captured values**, and don't ask Jacob to repeat a
  secret back to you.
- **Never commit real data.** Another of its own.
<!-- /shared -->

## A section of the repo's own
"""

# Five planted faults, one finding each: a required section gone, a claim
# reworded (missing), a core phrase dropped, a hedge added, a negation flipped.
BAD = """# repo

## Constraints that don't bend

- **Never send, reply to or draft a message on Jacob's behalf without asking first.**
  Same for anything public or irreversible.
- **Never attempt to bypass bot detection.** Route around it if you must.
- **Credential-shaped values are supplied at run time, never stored**, unless the
  run is local.
- **Report key names, always captured values**, and don't ask Jacob to repeat a
  secret back to you.
"""

PLANTED = 5


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
                   expect=["no section 'Keep an active TODO'",
                           "MISSING: no bullet says \"Never send a message, email or reply",
                           "WEAKENED: the bullet \"Never attempt to bypass bot detection.\" drops",
                           "WEAKENED: the bullet \"Credential-shaped values are supplied at run time, never stored.\" "
                           "adds 'unless'",
                           "CONTRADICTED: \"Report key names, never captured values\""])
