# checks TODO

## Own bugs

- No `origin`: `setup tools/checks --github` was refused by the permission
  classifier on 2026-10-04 (public repo creation), so this repo is local only and
  nothing is pushed. Once Jacob creates `CyberImpXIII/checks` (public, per
  PLAN-tools-folder.md), add the remote and push.
- `./dev.sh check` runs `no-roster` on this repo without roster names (this tool
  must not read the roster), so the names half is UNCHECKED in the pre-commit
  run. It runs in full only when a caller passes `--names` /
  `CHECKS_ROSTER_NAMES` (tests/test_meta.py RosterAudit runs it planted and
  unplanted). Still open 2026-10-04: `.claude/agents.sh` has no caller of
  `checks` and no `names` command (grep for tools/checks, CHECKS_ROSTER: none).
- `todo-valid` now runs `todo check` on a repo with a todo.json (2026-10-04),
  reading its TEXT output: `todo check` has no `--json`. The reading is held
  by tests/test_contract.py (real tool: fresh store ok, hand edit red) and
  tests/test_todo_valid.py (each broken contract is an error). Swap to JSON if
  todo ever offers it (asked of todo, below).

## Open decisions

- `tree-clean` was built 2026-10-04 as `roles:audit`: it runs only under
  `checks all --roles audit`, never pre-commit (where uncommitted work is what
  is about to be committed). If Jacob would rather drop it, delete
  source/tree-clean.py, its fixture, tests/test_tree_clean.py and its table row.
- `check-fails` (each repo's `./dev.sh check` shown red on a planted fault) is
  still not built, on purpose. Blockers: (1) the fault is repo-specific, so each
  owner must provide a plant (e.g. a `checks.json` param naming a script that
  breaks one thing in a copy); none exists; (2) running another repo's suite
  can write outside the copy (browsers, ~/.proficiently, databases by absolute
  path), and this tool never writes outside itself; (3) a `git clone --local`
  copy lacks node_modules and ignored state, so the unplanted run may already
  be red and prove nothing. Recursion is not a blocker: as `roles:audit` it
  would not run inside the suite's own `checks run .`. Hinges on (1) and (2):
  the owners' plants, and Jacob accepting that an audit runs their suites.

## Unconfirmed suspicions

- `rules-in-sync` checks only the four rule sentences (decision 12 revised,
  2026-10-04), anywhere in the file: a sentence kept but contradicted by the
  prose around it ("..., unless it is urgent") passes, by that decision. Its
  first by-meaning version (commit 2815d3b: claim + core phrases, hedges,
  flipped negations) is in history if a drift audit is ever wanted.
- Re-routed items (2026-10-04), checked against `hooks-installed`:
  knowledge-base "no check-hooks.sh or DECLARED list": covered. `hooks copies`
  finds every location by walking, so no repo keeps a list; `checks all` runs
  hooks-installed in knowledge-base (a cell in the grid). scripts item 10
  ("dev.sh check does not run this folder's hook tests"): covered only in
  part. hooks-installed holds every copy, test-*.sh included, equal to the one
  source (the stale-copy cause of the skipped cases), but it does not RUN the
  tests in each folder or count skips. unverified: tools/hooks' own suite runs
  each hook test and fails on a skipped case -- settle: `cd tools/hooks &&
  ./dev.sh check` (could not settle: hooks is mid-edit, below).
- hooks-installed is red in all 14 locations on 2026-10-04 because tools/hooks
  has uncommitted edits to source/hooks/no-inline-blobs.sh and
  test-no-inline-blobs.sh (first: every copy "drift"; later: `hooks copies
  --json` crashes, `AttributeError: 'Namespace' object has no attribute
  'gate'` in hookslib/cli.py cmd_copies). Another session's work in progress,
  not reported as a bug; re-run `./checks all` once hooks commits.


## Reported to other owners

All 2026-10-04, through the deep-work report that built this repo (the
dispatcher relays). Evidence: `tools/checks/checks all --names <roster names>`
from the top, 14 locations, 12 red.
- harness: a roster entry for this repo, and a caller that passes roster names
  (`checks all --names ...` from `agents.sh check`, or an `agents.sh names`).
- dispatcher (top-level prose): CLAUDE.md tool table lacks rows for
  scriptingTools/data-bridge, tools/checks, tools/hooks, tools/hub, tools/todo
  (`docs-rows`).
- emailTools: no `dev.sh`; CLAUDE.md lacks "Report a problem in someone else's
  code"; constraints section reworded.
- site-scrapers: CLAUDE.md has no "Constraints that don't bend" section; `.env`
  not git-ignored; check-hooks should give way to `hooks-installed` (PLAN §9).
- addon-bench: `.env` not git-ignored; constraints section reworded.
- applications, knowledge-base, chronjobScheduler, data-bridge, scripts:
  constraints section differs from the top's (`./checks one rules-in-sync <repo>`).
  Superseded 2026-10-04 by the rule-sentence check (decision 12 revised):
  addon-bench, applications, knowledge-base and chronjobScheduler pass; still
  red: emailTools (4 of 4 sentences missing, and no "Report a problem"
  section), data-bridge (4), scripts (4), site-scrapers (3: it has "**Never**
  attempt to bypass bot detection." at CLAUDE.md:394). Relayed through the
  dispatcher.
- hooks: `no-roster` fails on `.claude/lib` (its install destination) in
  audit-terms.json, vocab.json, source/lib/write-targets.sh, and on the literal
  `"site-scrapers"` (a package.json name) in two hooks and their tests. Fix in
  hooks' own `checks.json`: `exclude` for the data files, `allow_names:
  ["site-scrapers"]`.
- setup and todo: `no-roster` fails on their audit-terms data (roster names and
  paths listed as audit patterns); the same `checks.json` `exclude` fix.
- setup: its check component should install `checks run .` as each repo's
  generic pre-commit step.
- todo (2026-10-04, via the dispatcher): `todo check` has no `--json`
  (`./todo -C . check --json` -> "unrecognized arguments", exit 2), so
  todo-valid parses its text lines. A `--json` with the per-gate results and the
  failed count would let it stop parsing prose.
