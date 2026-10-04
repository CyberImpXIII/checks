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
  unplanted).
- `todo-valid` only checks TODO.md exists with a heading; when a repo has a
  `todo.json` it says UNCHECKED rather than calling `todo check`. Wire it to
  tools/todo's CLI once that exists and its JSON output is fixed (contract test
  in tests/test_contract.py, the same way hooks-installed is held).
- `checks all` runs `hooks copies` once per repo (14 workspace walks). Tokens: none;
  noted only in case a run ever times out (TIMEOUT 300s per check).

## Open decisions

- `tree-clean` (PLAN §8) is not built: a clean working tree contradicts a
  pre-commit check, since uncommitted work is exactly what is about to be
  committed. Options: run it only from `checks all` (a `--roles audit`-style
  scope), or drop it. Hinges on whether `checks all` is ever run at a point
  where a dirty tree means "someone is mid-task".
- `check-fails` (each repo's `./dev.sh check` shown red on a planted fault) is
  not built: running a repo's suite inside a check recurses through
  `checks run`, and running it in a copy can have side effects (browsers, DB
  writes). Hinges on a per-repo "plant" hook the repo owner provides.

## Unconfirmed suspicions

- `rules-in-sync` (by meaning since 2026-10-04) does not catch a contradiction
  written in the section's prose or in a repo's own extra bullet without a hedge
  word (said in its docs). CORE (what each bullet keeps beyond its claim) is a
  judgement: "Reading a mailbox is not permission", "mark it and hand it back"
  and the `.env` sentence were ruled example or restatement. If Jacob reads any
  of them as load-bearing, add it to CORE; addon-bench then goes red (it lacks
  all three).

- `discover()` repeats `hooks copies`' location rule (a second copy).
  tests/test_contract.py holds them equal on a fixture workspace, but only for
  repos: `hooks copies` also lists a non-repo folder that HOLDS a hook copy,
  which `checks all` does not visit. Probe: plant a stray
  `.claude/hooks/no-inline-blobs.sh` in a plain folder and compare.

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
  Superseded 2026-10-04 by the by-meaning compare: addon-bench, applications,
  knowledge-base and chronjobScheduler now pass it; still red, each lacking the
  shared bullets (MISSING, the closest bullet named): emailTools (all four, and
  no "Report a problem" section), data-bridge (all four), scripts (all four),
  site-scrapers (no section). Relayed through the dispatcher.
- hooks: `no-roster` fails on `.claude/lib` (its install destination) in
  audit-terms.json, vocab.json, source/lib/write-targets.sh, and on the literal
  `"site-scrapers"` (a package.json name) in two hooks and their tests. Fix in
  hooks' own `checks.json`: `exclude` for the data files, `allow_names:
  ["site-scrapers"]`.
- setup and todo: `no-roster` fails on their audit-terms data (roster names and
  paths listed as audit patterns); the same `checks.json` `exclude` fix.
- setup: its check component should install `checks run .` as each repo's
  generic pre-commit step.
