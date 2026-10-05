# checks TODO

## Own bugs

- `origin` now EXISTS (seen 2026-10-05: `git@github.com:CyberImpXIII/checks.git`,
  origin/main at e9e001d), though the agent brief still says "no remote, never
  push". Commits after e9e001d (bb9abe7 settings.json, the settings-tracked
  commit) are local only. The repo is PUBLIC (`gh repo view`: visibility
  PUBLIC). 2026-10-05 the dispatcher asked for a push; declined: this agent's
  generated config says NEVER push, and a push to a public repo needs Jacob's
  own go-ahead, not an agent message. Open decision for Jacob: allow pushes
  here (then regenerate the agent config to drop "never push").
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

- This repo's `./dev.sh check --json` (checkslib/devjson.py, 2026-10-05) gives
  one failure per failed step with file and line null: it conforms, but the
  `code` view gets no file:line. Per-finding failures would mean parsing
  unittest's and `checks run --json`'s output into rows; not done.

## Open decisions

- `check-json` (built 2026-10-05) is `roles:audit`, not `all`, though the
  brief asked for its results "under `checks all`": it runs the repo's whole
  suite, so pre-commit it would run the suite inside itself (only checks and
  hub call `checks run .` from dev.sh today; hub would pay twice per commit).
  Run it with `checks all --roles audit` or `checks one check-json <repo>`.
  Flipping to `all` is one word: the nesting guard (CHECKS_CHECK_JSON_ACTIVE)
  already exists and is tested.
- The schema (schema/check-json.schema.json) is this repo's concrete reading of
  §4.4's prose: key names `checks`, `name`, `status`, `reason`, `counts.failed`,
  `failures[].{message,file,line,role}`, and the eight `x-rules`. Not yet
  confirmed by the planner. Changing it is a data edit plus its tests; the
  validator refuses a JSON Schema keyword it does not enforce. §4.4's second
  gate (each failure's role exists in its group) is not built: it needs the
  roster, so it would take roles from the caller, the way `--names` works.

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

- hooks-installed user scope (decision 19, built 2026-10-04): a missing or
  drifted copy is covered by a `registered: true` user-scope row; a
  NOT-EXECUTABLE copy is never covered (a copy present but broken is a fault in
  the repo, and the repo's own settings presumably still run it). The brief named
  only missing/drift; if Jacob wants not-executable covered too, add it to
  COVERABLE in source/hooks-installed.py and flip
  test_not_executable_is_never_covered. Per-repo copies stay until setup ships
  its half (order: hooks, checks, setup); nothing is removed here.
- Same change: `checks run`/`one` text now prints an ok check's lines (only
  hooks-installed gives any: `repo copy:` / `covered by user scope:`).
  `checks all` still prints red cells only.

## Unconfirmed suspicions

- check-json's run budget is 280s (under the runner's 300s). tools/todo's
  `dev.sh check --json` took 240.1s on 2026-10-05, run alone; under `checks all`
  (8 repos at once) it may pass 280s and come back `error`. Probe: `checks all
  --roles audit` and read todo's check-json cell. If so, the budget becomes a
  param (a repo's checks.json), not a bigger constant.
- check-json decides "has --json" by the flag appearing anywhere in dev.sh. A
  dev.sh that mentions `--json` only for another subcommand would be run and
  fail `one-document` instead of being UNCHECKED. None does today (checked: the
  five that mention it all take `check --json`).
- tools/setup was not run by check-json (the brief: nothing that writes there).
  unverified: its `check --json` prints `{"ok", "gates"}` (its help line says
  so) and so fails `schema: $: missing checks` -- settle: `cd tools/setup &&
  ./dev.sh check --json | head -c 300`.

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
- hooks-installed copies: reinstalled again after tools/hooks ae91098
  (2026-10-04, commit f92eda2; all six cmp-equal, `hooks copies --gate
  tools/checks` exit 0). `checks all` re-run the same day: no ERR anywhere;
  hooks-installed red only in applications and site-scrapers (drift, theirs to
  reinstall; the real user settings register none of the shared hooks yet, so
  nothing is covered).


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
- setup (2026-10-04, via the dispatcher, decision 19 step 3): hooks-installed
  now counts a user-scope registration as installed. Setup's half: apply the
  `hooks userscope` proposal to the user settings (with Jacob's go-ahead), then
  stop copying the covered hooks and stop registering them in each repo's
  .claude/settings.json (else they run twice). Until then the copies stay.
- 2026-10-05, via the dispatcher (check-json): hooks, hub and todo fail it,
  each `schema: $: missing checks` (`checks one check-json tools/<x>`). todo
  prints `{"ok", "gates": {gate: bool}}`, hub `{"ok", "gates": {gate: status},
  "drift"}`: per-gate verdicts, no counts, failures, file:line or roles. The
  nine repos without `--json` are UNCHECKED. setup: its dev.sh stub template
  prints `{"ok": false, "error": ...}`, red under check-json by design (no
  `checks`); a stub printing a schema-valid red document (one `error` check,
  role code) would fail for the stated reason instead of on shape.
- 2026-10-05, via the dispatcher (settings-tracked, PLAN-repo-setup.md §7.9):
  applies_to=all, so `checks all` is red for hooks, hub and todo until each
  commits its own `.claude/settings.json` (their agents are doing it in the same
  wave). Not run workspace-wide here (brief: `checks all` is heavy); settle per
  repo: `tools/checks/checks one settings-tracked tools/<x>`. The workspace top
  is not a git repo, so its cell is UNCHECKED by design.
- todo (2026-10-04, via the dispatcher): `todo check` has no `--json`
  (`./todo -C . check --json` -> "unrecognized arguments", exit 2), so
  todo-valid parses its text lines. A `--json` with the per-gate results and the
  failed count would let it stop parsing prose.
