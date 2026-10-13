# checks TODO

## Own bugs

- The shared parts runner (done 2026-10-09, PLAN-small-tasks §7 step 1):
  checkslib/parts.py (VERSION 1.0.0, stdlib only), this repo's `./dev.sh
  check` = check.parts.json through it (20 parts; `--resume` after a red
  run), check-partial's fixtures run the real file with mutants (8 mutants,
  each alone turning only its scenario red; tests/test_check_partial.py ~135s).
  checkslib/devjson.py removed (its one caller was dev.sh). `--only <part>`
  built 2026-10-12 (VERSION 1.1.0, 5bce6b6; `./dev.sh test <part>`). Not
  built yet: §3.5 `check --quick`; parts run one at a time (no parallel
  parts). Known limits, by design and in the header: the hash is a
  CLAIM (a part reading an undeclared file resumes wrongly; `always` for
  parts whose inputs no `files` can name: rules_in_sync, no_secrets,
  rules_gated, contract, run); the environment is not in the hash (only
  PARTS_RUNTIME / the python version). Not gated: that each test part's
  `files` really covers what it reads (they declare the whole repo minus
  the other test files, so wide on purpose).
- `./dev.sh check` 2026-10-12, run 1: "18 of 20 passed; failed: test.meta;
  test.contract". `run` (hooks-installed) is now OK: setup's 2026-10-10
  re-render of the hook copies is committed (532b54d; `hooks copies --gate
  tools/checks`: ok). test.meta was a test bug, fixed in f91958b: RosterAudit
  copied the live tree, and the gitignored .progress/ logs of an earlier red
  run (naming `.claude/lib`) made no-roster red on the copy. Copies now go
  through tests/helpers.copy_committable (what git would carry). test.contract
  is the lib-coverage item below. Run 2 (after f91958b and 5bce6b6): "19 of
  20 passed; failed: test.contract" (that item, alone). `.claude/settings.json`
  committed 2026-10-13 in 81ef893, as briefed: `cmp` with settings.proposed.json exit 0.
- `./dev.sh check` 2026-10-13 (one run, at 691cbf2): "20 of 22 passed;
  failed: test.contract; run". Both are hook copies, neither from this
  repo's code: `run` = hooks-installed here, 6 rows (git-funnel.sh,
  test-git-funnel.sh, bin/commit.sh missing; prefer-recipes, its test,
  lib/write-targets.sh drift), sources all committed in hooks
  addf8fc/ea7735b minutes before, so setup's re-render of this repo clears
  it. test.contract WithHooks(settings='registered') = the lib-coverage
  decision (ledger.sh, extra-stores.sh, write-targets.sh) plus the new
  bin/commit.sh, which user scope cannot cover either. Not re-run: it
  stays red until the re-render.
- parts.py 1.2.0 (2026-10-13, 2430961; asked by the chronjobScheduler, emailTools
  and data-bridge owners): exit 3 is `unchecked` (reason = last output line;
  not a pass, not kept for --resume, run stays green), and a `FAIL <file>:<n>`
  line fills file/line only when the file exists inside the parts folder
  (a time like 10:30, a missing or outside path: null). Tests in test_parts
  (exit 3 vs 4 counterfactual; six location cases). Every rendered copy is
  now behind until setup re-renders (`tools/setup/setup <repo> --only parts
  --rebuild`); the dispatcher queues those. Not gated: no check-partial
  mutant for the two new behaviours (test_parts holds them).
- parts.py 1.3.0 (2026-10-13): `parts.py usage [--json]`, run's options as
  data (RUN_OPTIONS/RUN_REPEATABLE/RUN_EXCLUSIVE build the usage line, the
  argument check and the JSON; test_parts holds them equal, with a
  counterfactual). Why: tools/todo's IterateRule scraped the help line with a
  regex for `[--flag]` groups only, so `[--resume | --only <name>...]` (1.1.0,
  5bce6b6, not 1.2.0) parsed to None. The text was always going to change:
  td-37 itself says IterateRule turns red once the runner gains --only.
  Consumers read `usage --json`, `run.options[].flag`, never the text.
  `./dev.sh check` at this change: "20 of 22 passed; failed: test.contract;
  run" -- the same hook-copy cause as the item above, now 8 rows (ledger.sh,
  test-store-guard.sh added). Rendered copies drift until setup re-renders.
- PLAN-architecture §12 (2026-10-13, 47237f5, b5f5dc4): cli.json `store` is
  optional and a `read` block declares read verbs; `cli-declared`
  (roles:lag) and `repro` (all) built, with fixtures and tests/test_repro.py.
  repro now compares the fixture copy before and after each verb (sha256
  per path; built 2026-10-13, coordinator's follow-up). Still not compared:
  a verb with no `read.fixture` runs in the live repo, and other processes
  write there (the ok line says so). Not built: no `checks repro`
  alias (`checks one repro <repo>`); `checks practices --json` does not
  exist, so lag items come from `checks all --roles lag --json` today.
  Other §12 gates belong elsewhere: `setup plans --facts` (setup), the
  transcripts detector (transcripts).
- cli.json `not_exported` (2026-10-13, asked by applications): a per-entry
  opt-out from stores-exported, each with why; rule `not-exported-declared`
  holds its keys to `store` entries. stores-readonly ignores it on purpose:
  whether applications' packets/batches (0600, answer values) go 0444 is
  Jacob's call, still open. applications stays red in stores-exported until
  it lists its private entries (and job-urls.json/audit-exempt.tsv still
  need a `verify`, or an opt-out, its owner's choice). unverified: other
  readers of cli.json (hooks store-guard, setup's skeleton) tolerate the new
  key -- settle: tools/hooks' store-guard test with a cli.json carrying
  `not_exported`.
- no-roster skips the root todo store (2026-10-13, 1e51b7a; asked by
  context-hygiene): its local `exclude` of todo.json/todo-history.json is now
  redundant (theirs to drop). Its hooks-installed red the same day was stale
  copies, not hooks mid-edit: all six sources (git-funnel, commit.sh,
  prefer-recipes, write-targets and tests) committed in hooks addf8fc/ea7735b;
  a setup re-render clears it.
- `checks writers` + `silent-writes` (2026-10-13, 691cbf2; RESEARCH-writers.md
  could-not-settle 1): a line scan, not a parser. Blind spots, in
  checkslib/writers.py's header: a failure handled on a later line (hence
  `allow`), a Python try/except around a write, `2>` redirects, writes through
  an alias. On tools/hooks it finds one silent site, source/lib/ledger.sh:84
  (the header write under `set -C`, a deliberate race; the row append after
  it is traced): a false finding until hooks lists that file in its
  checks.json `allow`. Audit-only, so nothing turns red pre-commit.
- Pushing: the agent config regenerated by 2026-10-09 says "commit and push
  to origin right away" (it said "never push" on 2026-10-05). The repo is
  PUBLIC (`gh repo view`, 2026-10-05).
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

- This repo's `./dev.sh check --json` (checkslib/parts.py since 2026-10-09)
  gives one check per part, its failures up to 8 of the part's FAIL/ERROR
  lines, file and line null: it conforms, but the `code` view gets no
  file:line. Per-finding rows would mean parsing unittest's and `checks run
  --json`'s output; not done.

- Lib/bin coverage at user scope: SETTLED 2026-10-13 (hooks 6eb9c65 gave
  `user_scope.support` rows {file, kind, needed_by, covered, why}).
  hooks-installed judges a lib/bin copy by its row: covered true = covered,
  false = a fail naming `why`, null = UNCHECKED; `support` absent or a bad
  row = the contract error. Held by tests/test_hooks_installed.py (4 cases,
  4 mutants, 5 shape errors), the fixture (w.sh's row flips with
  `registered`), and test_contract's real-tool test, which pins hooks'
  split (ledger.sh, extra-stores.sh covered; write-targets.sh,
  bin/commit.sh not) -- a change on their side turns that pin red, by design.
- hooks-installed reads `source_uncommitted` (done 2026-10-09; hooks
  be71746): an uncovered missing/drift row whose source is mid-edit (true) or
  unknown (null) is UNCHECKED, false is a fail. Held by
  tests/test_hooks_installed.py (6 cases, 3 mutants, shape errors) and by
  test_contract's real-tool test (a clone of tools/hooks, one source edited:
  unchecked; the same edit committed: fail). First live use the same day:
  tools/hooks had store-guard.sh (new) and lib/write-targets.sh (` M`)
  mid-edit, and this repo's `checks run .` said UNCHECKED, not red.
  Note: test_contract's real-tool tests read tools/hooks' live working tree,
  so they now split their expected lines by each row's flag.

- check-json's 280s budget is a LOAD test under `checks all` (CONFIRMED
  2026-10-09): `checks all --roles audit --json` took 686s; 14 of 18
  check-json cells were `error` "did not finish in 280.0s" (tools/todo,
  tools/setup and this repo among them), 4 ok (scripts 62s, chronjobScheduler
  85s, data-bridge 135s, emailTools 189s). run_all runs 8 repos at once, and
  other agents' suites were running beside it. `error` is the honest cell, but
  it says nothing about the shape. Fix not chosen: run check-json one repo at a
  time (a per-check `serial` flag in the runner), or make the budget a param.
  A bigger constant alone would only move the wall.
  W17 (2), alone-vs-load, INCOMPLETE (2026-10-09): the sequential sweep
  (scratchpad time-check-json.sh, one repo at a time, nothing else of ours)
  finished 1 of 18 before the dispatcher called time: addon-bench still hit
  280s ALONE, but with foreign load avg 41->34 and 23->16 other `dev.sh
  check` processes alive. So "alone" was not achievable on this machine that
  day. Next: re-run when the machine is quiet, with CHECKS_CHECK_JSON_TIMEOUT
  set high (e.g. 1500), so a time over 280 is measured, not capped.
- `contract.inside()` takes a `~/...` store path as repo-relative (found
  2026-10-09): tools/usage's cli.json stores live under `~/`, so paths-inside
  does not flag them, accessor reads tools/usage as OK, and stores-readonly
  says UNCHECKED ("matches no file"). Decide: a `~` path is outside (a
  finding), or cli.json gets a field for stores kept outside the repo.
- accessor and stores-readonly (done 2026-10-09, PLAN-services §3): accessor
  counts any file cli.json names, a JSON store included (it already flagged
  one; now held by a test), and `scan.walk` no longer walks into a nested git
  repo, which is its own row. Probe: the top's four database findings
  (knowledge-base, data-bridge, site-scrapers x2) were all nested repos; the top
  now reads OK, and each repo's own row is unchanged. stores-readonly judges
  each non-SQLite store's mode (no write bit); live it is UNCHECKED everywhere
  so far (site-scrapers: all SQLite; tools/usage: the `~` bug above).

- check-partial (done 2026-10-09, PLAN-small-tasks §3.7): the three
  scenarios (killed, changed, hung) on a suite the check writes, handed to the
  runner through CHECK_PARTS and PROGRESS_FILE. The contract (the manifest
  shape, `passed_steps`, `--resume`) is defined HERE first, in the check's
  header. The harness (`.claude`) meets it (OK, 2026-10-09); other repos say
  UNCHECKED (seen: scripts, tools/setup); this repo meets it since the
  shared runner (above). Not gated: that a repo's
  REAL parts are declared with the right files (a part whose `files` omit
  what it tests resumes wrongly); only the mechanism is proven. Cost: the
  five tests take 80-110s (SETTLE and the 8s run limit); the full suite took
  727s under load that day (297s before them, also under load).
- W17 caveat (PLAN-architecture-review §4), answered 2026-10-09: `checks
  all` did NOT hide UNCHECKED. Its grid prints each one as `unch` (never `ok`,
  never dropped), and `--json` keeps `status: unchecked`. Proof:
  tests/test_runner.py `test_the_grid_shows_every_unchecked_cell_and_never_as_ok`
  builds a 2-repo x 3-check grid (ok/FAIL/unch); the cell rows passed before
  any change. The real gap was that the text never says the word UNCHECKED
  (so a grep counted 0), and the red-repo detail lists only red cells. The
  closing line now counts them: "N UNCHECKED cell(s) (never ok; ...)". Without
  that change, the test fails on the count. Still open: unchecked REASONS are
  not printed in the grid view (`checks one <check> <repo>` gives them).

- todo import (PLAN-todo-tool §6 phase 3) SKIPPED 2026-10-12, rolled back
  uncommitted. `todo init --prefix ck` + `import TODO.md`: 65 items (13 bug,
  19 decision, 6 suspicion, 27 report), lossless (every bullet body in the
  render, scratch script; 65 of 65 missing against an empty file). But `todo
  check` failed 33: the 6 suspicions lack `probe`, the 27 reports lack
  `reported_to`, and todo-valid would turn this repo's pre-commit red. The
  probes could be filled with `todo edit --probe`; reported_to only through
  `todo report --to <repo>`, which writes a counterpart into the owner's
  store (most owners have none; this repo never writes outside itself).
  Reported to todo (below). Also seen: the "All 2026-10-04, through the
  deep-work report ..." paragraph imports as its own report item, detached
  from the bullets it introduces; fold it in before the next try.

## Open decisions

- todo td-25 (relayed 2026-10-09; context-hygiene hit the same wall): the
  services.schema.json enum allows only `check` and `write`, so read verbs
  (todo get/find/refs) cannot be declared. Recommendation: add a `read`
  service. Its verbs are checked against help, the same way write verbs are,
  but they are NOT required to be within cli.json's write verbs. It extends
  PLAN-routing-tree §14.8's list of services, so the hub/Planner confirm
  before the schema changes. The schema, contract.py and services-valid
  fixtures would change together.
- todo td-29 (relayed 2026-10-09): stores-exported FAILs a store with no
  `verify` verb, which assumes every declared store is exported to
  DATA_REPO. todo's stores have no export, and no plan for one.
  Recommendation: the CHECK changes, not todo. cli.json gets an explicit
  opt-out (e.g. `"export": null` plus a `why`), and the check then says
  UNCHECKED ("declares no export: <why>"), never ok. With no field at all,
  it stays a finding, so silence is never a pass. Whether todo stores
  SHOULD be exported is the top level's call (see todo's td-29).

- The §14.8 contract shapes (2026-10-05): services.json, cli.json and
  node.json are defined HERE first, as schema/{services,cli,node}.schema.json.
  This is this repo's reading of PLAN-routing-tree.md §14.8 and
  PLAN-repo-setup.md §7.10; setup (skeletons, node mode) and hub (the
  registry) have not built them yet and must adopt or refine these shapes.
  Choices that hinge on them: "a verb is implemented" means `<run> help` lists
  it (checkslib/helptext.py, the reader help-matches uses); a `rebuild` is an
  argv run at the root of a scratch clone, with `{origin}` for the real repo's
  path; `generated` holds exact paths, `record` may hold globs; the registry
  is `{"services": {repo path: services.json}}`, and only that object is read.
- registry-matches and the roster: the generic check compares the registry
  with the services.json files only. Whether the registry's roles match the
  roster is the roster owner's gate (harness's gen gate), never here. If it is
  ever wanted here, it takes roles from the caller as `--names` does
  (CLAUDE.md "Roster names arrive from the caller"): no second mechanism.
- stores-exported (2026-10-05, PLAN-repo-setup.md §7.11) is this repo's
  reading of prose that leaves the seams open: the check runs `<cli> verify
  --json` with DATA_REPO from the CALLER's environment (never read from
  .claude/local.env: instance data arrives like `--names`), and reads an item
  report shaped by schema/verify.schema.json (`same`/`differs`/`missing`/
  `unavailable`). §7.11's "reuses the check-json schema" is read as: its
  result shows in `dev.sh check --json` / `checks all`, NOT that verify prints
  the check-json shape (that shape is per-suite, not per-item). The verify
  locates `$DATA_REPO/<tool>/` itself; the check does not guess the folder
  name. Open: who exports DATA_REPO into `checks run`'s environment
  (setup's `data` component, or each dev.sh sourcing local.env)? Until one
  does, stores-exported is UNCHECKED everywhere, never a pass. Not built
  here: §7.11's "path allowlist run over the export" (a state path never in
  the data repo); it reads the data repo, so it is a check run THERE, with
  the allowlist from each tool's contract. Decide its home with setup.
- One CLI per repo (cli.json has one `cli`). A repo with two stores behind
  two CLIs cannot declare it; it would need `cli.json` to become a list.
  Decide when a repo needs it.
- rendered-matches (all) and regenerate (repos:.) both report drift at the
  top: one generated file edited by hand is two red cells there. Kept: each
  says what it proves, and regenerate's count is the whole-top one.
- accessor matches the store's file NAME as a token (`app.db`, not
  `myapp.db`/`app.dbx`/`app.db.bak`). A read that builds the path from
  pieces (`"app" + ".db"`) is not seen: a static audit, said in its
  explanation by what it matches. A read through a variable defined in an
  `impl` module is not seen either; `impl` is trusted.

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

- rules-gated (built 2026-10-05, PLAN-hard-gates.md §5, §7 phase 3). Limits,
  said in its explanation: it proves a gate FILE and a test naming it exist,
  not that the gate runs here (wiring) nor that its test feeds it a failing
  input. Seeded counts: top 34 rows (16 gated, 12 planned, 6 prose); a
  shared-block repo 24 (8 gated, 11 planned, 5 prose). Choices open to the
  planner: `shared-block-unedited` is planned under "§3" though no §3 row
  schedules it (setup's `edited locally` is a report, not a gate);
  `stage-own-paths` (§3 row 4) stays planned with no paths, because git-stamp.sh
  does not block `git add -A` today (a path would be misreported `landed`).
  §3 row 1 ("commits name the agent") has no CLAUDE.md section, so no row:
  a gate without a rule. When hooks lands primary-guard/push-gate/no-secrets.sh,
  rules-gated prints `landed:` for them: flip those rows to active here.
  Done 2026-10-05 after hooks 702bd2d/e9d382a: primary-guard, push-gate,
  no-secrets-write and no-add-all (row 4's git-stamp half) are active; row 4's
  pre-commit ledger half stays planned as stage-own-paths (setup). Shared-block
  repos now 25 rows (12 gated, 8 planned, 5 prose).
- 2026-10-05, setup run here (b223fe5, tools/setup 32aeaa9, §7.12 step 2):
  every shared hook/test/lib is now a repo copy. `./dev.sh check` still RED,
  two causes, neither a fault here. (1) hooks-installed: 3 drift, not covered
  (troubleshooting.sh, test-troubleshooting.sh, test-prefer-recipes.sh); setup
  leaves a drifted copy unchanged, replacing it waits on Jacob (§7.12).
  (2) tests.test_contract.WithHooks (settings='registered') is a FIXTURE test
  (scratch repos, no copies), so installing copies here cannot clear it: it is
  the lib-coverage decision below, unchanged. Also written by setup:
  services.json skeleton (services-valid OK), .githooks/ (inert,
  core.hooksPath unset), .claude/settings.proposed.json (ignored, not applied:
  settings.json is Jacob's).
- SHAPES has two copies on purpose (decided 2026-10-05): source/no-secrets.py
  (Python re) and tools/hooks' no-secrets.sh (ERE, with its own \b
  emulation). One data file was rejected: a hook copy must work with nothing
  beside it, so the file would be one more lib to install and miss, and a
  hook present without its data enforces nothing (the worst state). Held
  equal by hooks' tests/test_secret_shapes.py; tests/test_no_secrets.py runs
  it from here and fails on a skip (planted drift AKIA->AKIB: red).
- no-secrets (2026-10-05): scans the index too (staged copies that differ from
  the working tree), no mode switch. A blob over MAX_BYTES or binary is skipped
  as in the tree scan. If `git diff`/`ls-files`/`cat-file` fails it is a
  finding, never a silent pass.

## Unconfirmed suspicions

- Top `.claude/cli.json` (settled for cli-declared 2026-10-13, harness's
  path): `contract.cli_home` reads it for a non-git folder with no cli.json
  whose .claude is a git repo; `checks one cli-declared ../..` is OK (15
  verbs). Only cli-declared uses cli_home: accessor, repro and stores-* at
  the top still read `<top>/cli.json` (absent: UNCHECKED/ok), as `.claude`
  is its own row in `checks all` and runs them there. Suspicion, unprobed:
  that row split is right for them; settle if the top ever gets a store.
- store-guard (tools/hooks) appears to handle a cli.json with no `store`
  (`else []` near line 162 of store-guard.sh), now that `store` is optional.
  Read, never run. Settle (tools/hooks): a PreToolUse payload against a repo
  whose cli.json has no `store`.

- Foreign output in this repo's check log (2026-10-09): `./dev.sh check >
  <scratch>/check2.out` ended "check: FAILED: test" and was followed IN THE
  SAME FILE by tools/setup's mutant summary ("mutants: 187 of 187 red, 5
  problem(s)", "check: 3 of 6 gates FAILED"). Nothing in tests/, source/ or
  checkslib/ runs setup's suite (grep). Suspect: an orphan from check-json's
  timed-out setup run in `checks all` (killpg reaches the process group only;
  a child in its own session survives and keeps an inherited fd), but the fd
  path does not explain it. No such process was alive afterwards. Probe: run
  `checks one check-json tools/setup` with a 5s CHECKS_CHECK_JSON_TIMEOUT,
  then `ps` for setup's mutant runner.

- check-json decides "has --json" by the flag appearing anywhere in dev.sh. A
  dev.sh that mentions `--json` only for another subcommand would be run and
  fail `one-document` instead of being UNCHECKED. None does today (checked: the
  five that mention it all take `check --json`).
- tools/setup's check-json cell (probed 2026-10-09, same `checks all` run as
  the budget item in Own bugs): `error`, "did not finish in 280.0s", so its
  shape is still unjudged. The old guess (`{"ok", "gates"}`, "missing checks")
  is out of date: its dev.sh now says `--json: the one schema, via
  devtools/checkjson.py` (setup 8187ca8). unverified: it conforms -- settle:
  `cd tools/setup && ./dev.sh check --json | head -c 300`, run alone.

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

- hooks (2026-10-09, W17 run): `hooks copies` and `hooks userscope` refuse the
  whole source ("FAIL lib/extra-stores.sh: no test ... source is not
  well-formed") while `source/lib/extra-stores.sh` sits untracked in
  tools/hooks (last commit a953a98). Every repo's hooks-installed then FAILs
  ("printed no report"), and here 4 WithHooks tests go red (3 JSONDecodeError
  + the userscope one). Expected: a mid-edit lib file not to fail every
  repo's gate. Probably transient. Open decision on this side: should
  hooks-installed say UNCHECKED, not FAIL, when `hooks copies` refuses over
  an uncommitted source file? It FAILs today, and that is honest but noisy.
  Settle: `tools/hooks/hooks copies --json` after its owner commits.

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
- 2026-10-05, via the dispatcher (the five §14.8 gates): site-scrapers is red
  on `accessor`: `data/failures.db` and `data/scrapers.db` have no cli.json
  naming their CLI (`tools/checks/checks one accessor site-scrapers`).
  It is not a pre-commit caller, so it shows only in `checks all`. hub, setup,
  todo and hooks are green on accessor. setup: install the skeletons
  (services.json `{name, services: [check entry]}`, cli.json
  `{store, cli, verbs: []}`) and node.json in node mode, to the shapes in
  schema/; until then services-valid, registry-matches, rendered-matches and
  regenerate are UNCHECKED everywhere. hub: render the registry as
  `{"services": {path: services.json}}` and name it in node.json `registry`.
- 2026-10-05, via the dispatcher (rules-gated): red where a repo has `## `
  sections outside setup's block and no own `gates.json`: tools/setup (its
  "Keeping these rules in sync", CLAUDE.md:259), addon-bench, applications,
  emailTools, knowledge-base, scripts, site-scrapers (hand copies, no block).
  Fix per PLAN-hard-gates.md §7a: setup installs a `gates.json` skeleton; each
  owner classifies its own sections. Only checks and hub run it pre-commit.
  Planner/dispatcher: §3 row 6 reads "on the staged diff"; no-secrets scans
  the index plus the working tree (reword the row to say so); §3 row 1 has no
  rule section in any CLAUDE.md. hooks: §3 row 4's `git add -A` block is not
  in git-stamp.sh.
- hooks (2026-10-08, via the dispatcher, from hub's report): `hooks copies
  --json` compares installed copies against tools/hooks' working tree, so an
  uncommitted edit in source/hooks/ marks every repo's copy `drift` and turns
  each repo's pre-commit red (seen: prefer-recipes.sh, test-prefer-recipes.sh,
  hooks HEAD 43d2a1e with both sources ` M`). Asked: compare against HEAD, or
  flag the row `source_dirty` so hooks-installed can say UNCHECKED. Settle:
  `cd tools/hooks && git status --short source/ && ./hooks copies ../.. --json`.
  ANSWERED by hooks be71746 (`source_uncommitted`); read here 2026-10-09.
- hooks (2026-10-09, via the dispatcher): libs and user scope. Observed:
  `hooks copies --json` gives `.claude/lib/ledger.sh` / `write-targets.sh`
  rows (missing in a repo with no copies) but `user_scope.hooks` has rows
  only for hooks (kind source/plugin), and no `# hooks:` line says which hooks
  source which lib (write-ledger.sh says `../lib/ledger.sh` in prose only).
  Input: tools/checks `python3 -m unittest
  tests.test_contract.WithHooks.test_hooks_installed_follows_the_real_user_scope_report`
  (settings = the `hooks userscope` proposal, registering every hook).
  Expected: a way to tell a lib copy is unneeded, e.g. a declared
  `uses=lib/ledger.sh` per hook, or a `user_scope` row per lib whose
  `registered` is true iff every hook using it is. Here: nothing changed;
  the test stays red until hooks answers.
- harness (2026-10-09): `.claude` is its own git repo, and its root
  cli.json is read. schema/cli.schema.json now takes `not_verbs` (verb ->
  why) and `_comment`. A new rule, not-verbs-exact, holds verbs +
  not_verbs == the CLI's help, both ways; the real file passes it. Still red
  there, and theirs: accessor gives 133 findings "names the store
  `agents.manifest.json` around its CLI `agents.sh`" (hooks/*.sh and
  others). Theirs: route the reads through agents.sh, or list the readers in
  checks.json's accessor `impl` param with why.
- site-scrapers (2026-10-09): accessor in its own row fails on
  `data/failures.db: a store cli.json does not name`. Theirs: name it in
  cli.json's `store`, or say why it is not a store.
- rules-gated, the 8 reds (2026-10-09, `checks one rules-gated <repo>`):
  addon-bench (14 unrowed sections), applications (14), emailTools (13),
  knowledge-base (14), chronjobScheduler (15), data-bridge (13), scripts (10),
  site-scrapers (10). One cause in all eight: CLAUDE.md carries the shared
  rules as a HAND COPY with no `<!-- shared:rules@... -->` markers, so each
  shared heading counts as the repo's own and needs a row (`setup <repo>
  --only rules --dry-run` says "drift: CLAUDE.md has no shared:rules block
  ... its owner replaces them with the block"). Closed by each repo's owner:
  (1) replace the hand copy with setup's block (`setup <repo> --only rules`),
  which rows the shared sections through this repo's gates.json; (2) row what
  is left, its own sections, in its own gates.json as setup did (eb3ef96):
  `Rules` in six of them, plus emailTools "Before committing, and while
  working", chronjobScheduler "Cron constraints that don't bend", data-bridge
  "The design decisions already made", site-scrapers "Commands" and "Working
  in this repo". income and tools/setup are OK.
- scripts, site-scrapers, tools/usage and the top (2026-10-09, `checks all`,
  re-run alone for scripts): hooks-installed `drift` on no-inline-blobs.sh,
  prefer-recipes.sh and their tests (the top also troubleshooting.sh) against
  a committed tools/hooks source: real drift, each owner runs `setup <repo>
  --only hooks --rebuild`. Since hooks b393ccd (store-guard.sh committed),
  every repo with copies also reads store-guard.sh `missing` until its owner
  runs `setup <repo> --only hooks`; this repo did (2026-10-09).
- setup (2026-10-09): PLAN-small-tasks §6 says setup installs check-partial
  with the other checks; its `gates` component's contract-gate list should
  name `check-partial` (roles:audit, so `one check-partial <repo>`).
- every repo owner (2026-10-09, PLAN-small-tasks §5): meet check-partial's
  contract (its header) in `./dev.sh check`. The harness meets it (its
  suite-parts.sh; `checks one check-partial .claude` OK in 19s, 2026-10-09,
  and again after the contract grew "N of M" text and a full --resume report,
  2026-10-09), and other repos can copy that runner.
- harness + setup (2026-10-09, PLAN-small-tasks §7 steps 2-3, via the
  dispatcher): the ONE runner is now tools/checks/checkslib/parts.py; setup
  should render a copy into each repo (the fixture shows how: a dev.sh line
  `python3 parts.py run "${CHECK_PARTS:-check.parts.json}" "$@"`), and the
  harness's `.claude/lib/suite-parts.sh` is a second runner that could be
  replaced by it (same parts-file keys, same progress fields). Not sent
  directly: this session has no SendMessage.
- todo (2026-10-13, via the dispatcher): IterateRule's None is a scrape of
  the help text, not a runner fault; read `python3 <runner> usage --json`
  -> `run.options[].flag` (`--only` takes a value), then reword the iterate
  rule (td-37: the runner has had --only since 1.1.0, `./dev.sh test <part>`
  here). Settle: in tools/todo, `python3 -m unittest tests.test_handoff.IterateRule`.
- setup (2026-10-13): checkslib/parts.py is now VERSION 1.3.0 (`usage --json`).
- setup (2026-10-13, via the dispatcher): the data component's `_cli_shape`
  (setuplib/core.py) requires `store`, but cli.json's `store` has been
  optional since 47237f5 (§12.1): `setup tools/checks --only data` says
  "drift: cli.json has no `store`" for a CLI over no store. Expected: no
  `store` is `none` ("no store is declared here"), like no cli.json.
- setup (2026-10-13): checkslib/parts.py is now VERSION 1.2.0 (2430961:
  exit 3 unchecked, FAIL file:line located); every rendered copy drifts
  until `setup <repo> --only parts --rebuild` (reported to the dispatcher).
- setup (2026-10-12): checkslib/parts.py is now VERSION 1.1.0 (`--only`,
  5bce6b6); tools/setup/devtools/parts.py and every repo copy it rendered
  are 1.0.0 and drift until setup re-renders. Settle: `cmp
  tools/setup/devtools/parts.py tools/checks/checkslib/parts.py`. todo
  (td-37) can point its brief at `dev.sh test <part>` once a repo's dev.sh
  maps it to `--only` as this repo's does.
- todo (2026-10-12, via the dispatcher): importing a "Reported to other
  owners" section gives `report` items with no `reported_to`, red in `todo
  check` ("report/open requires reported_to", 27 here), and the only way to
  set it, `todo report --to`, writes into the owner's store. Input: `todo -C
  tools/checks init --prefix ck; todo -C tools/checks import TODO.md; todo -C
  tools/checks check`. Expected: an import whose result passes its own check,
  e.g. reported_to {repo, date, their_id: null} parsed from the bullet lead
  (pairing UNCHECKED where the owner has no store), or `edit --reported-to`
  without a counterpart write. Same for suspicions: their "Probe:"/"settle:"
  text could fill `probe`. This repo's import waits on the answer.
- todo (2026-10-04, via the dispatcher): `todo check` has no `--json`
  (`./todo -C . check --json` -> "unrecognized arguments", exit 2), so
  todo-valid parses its text lines. A `--json` with the per-gate results and the
  failed count would let it stop parsing prose.
