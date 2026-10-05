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

# The four rule sentences, with prose of this repo's own all around them: its
# own preamble, its own explanations, rewrapped, one sentence unbolded, a curly
# quote, and extra bullets of its own. All of that is ignored.
GOOD = """# repo

<!-- shared:rules@000000000000 -->
## Keep an active TODO — write it when you notice it

Wording here may differ.

## Constraints that don't bend

These hold whatever the task (a preamble of this repo's own).

- **Never write outside this repo without asking.** A rule of this repo's own.
- **Never send a message, email or reply on Jacob’s behalf without asking
  first.** Making this repo public counts.
- Never attempt to bypass bot detection. A wall is reported, in this repo's words.
- **Credential-shaped values are supplied at run time, never stored.** Not in a
  fixture.
- **Report key names, never captured values.**
- **Never commit real data.** Another of its own.
<!-- /shared -->

## A section of the repo's own
"""

# One rule sentence gone (bot detection, said only in other words), and one
# required section gone.
BAD = GOOD.replace("Never attempt to bypass bot detection.", "Do not try to get round bot checks.") \
          .replace("## Keep an active TODO — write it when you notice it", "## Notes")

PLANTED = 2


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
                           "rule sentence missing (from the top's 'Constraints that don't bend'): "
                           "\"Never attempt to bypass bot detection.\""])
