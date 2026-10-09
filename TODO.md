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

- `./dev.sh check` is RED, ONE cause (2026-10-09): tests/test_contract.py
  WithHooks.test_hooks_installed_follows_the_real_user_scope_report
  (settings='registered'). Not a stale expectation: "ok" is the right
  real-world verdict (every hook registered at user scope runs from
  tools/hooks/source and sources source/lib/, so a repo's missing lib copy is
  harmless), but the check cannot reach it: `.claude/lib/ledger.sh` and
  `write-targets.sh` read "missing; not covered by user scope (no shared hook
  of that name there)" because `hooks copies --json`'s `user_scope` has no lib
  rows and no `# hooks:` line links a lib to the hooks that source it.
  Treating every missing lib as covered (or UNCHECKED) would hide a real fault:
  a repo-copy hook whose lib is missing fails open. Reported to hooks
  (2026-10-09, below). Open decision if hooks declines: drop libs from the
  test's expectation (and say libs are unjudged at user scope).
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
  header; no repo meets it yet, so it is UNCHECKED everywhere (seen: this
  repo, scripts, tools/setup). tests/test_check_partial.py shows each of five
  runner faults turning only its own scenario red. Not gated: that a repo's
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
- `.claude/hooks/store-guard.sh` and its test are installed here (`setup
  tools/checks --only hooks`, 2026-10-09) but NOT committed: tools/hooks has
  the source mid-edit again, so hooks-installed says UNCHECKED for them.
  Commit the copies (re-run the install first) once tools/hooks' source is
  committed.

## Open decisions

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
- `./dev.sh check` still red after hooks committed (2026-10-05): the
  "Own bugs" lib item above, now two libs (`.claude/lib/ledger.sh`,
  `write-targets.sh`: user scope never covers a lib), in hooks-installed and
  tests.test_contract.WithHooks (settings='registered'); plus hooks-installed
  listing every shared hook missing from this repo's .claude/hooks (setup
  installs copies, or the user-scope proposal is applied). Not a fault here.
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
- harness (2026-10-09, via the dispatcher): the top's `.claude/cli.json`
  (store agents.manifest.json) is not read by accessor, which reads a repo's
  root `cli.json` only, and it has a `not_verbs` key that
  schema/cli.schema.json (additionalProperties false) would refuse. Expected:
  move it to the root as `cli.json` without `not_verbs`, or ask here for the
  key and for `.claude/cli.json` as a second location.
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
  contract (its header) in `./dev.sh check`. harness's suite-steps.sh
  fingerprints the whole tree, so it needs a per-part files hash for
  `--resume` to run only the changed parts.
- todo (2026-10-04, via the dispatcher): `todo check` has no `--json`
  (`./todo -C . check --json` -> "unrecognized arguments", exit 2), so
  todo-valid parses its text lines. A `--json` with the per-gate results and the
  failed count would let it stop parsing prose.
