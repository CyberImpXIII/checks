# checks

The ONE source of the generic pre-commit gates every repo here runs, and the
runner that applies them per repo or across the workspace
(PLAN-tools-folder.md §4 step 3, spec §8). A repo's `./dev.sh check` calls
`checks run .`; `checks all` gives the whole workspace as one grid. A gate
is written once here and never re-implemented in a repo.

| doing this | use |
|---|---|
| before committing | `./dev.sh check` (unit tests, every check's fixtures, this repo's own checks, the roster audit) |
| run the gates on a repo | `./checks run [PATH]` (exit 1 on any fail or error) |
| run them everywhere | `./checks all [ROOT] --names <roster names>` -- a repo-by-check grid, then every red cell's findings |
| what a check proves, how to pass it | `./checks explain <name>` |
| what the source holds | `./checks list [--json]` (setup's check component should read the `--json`) |
| the one shape of every repo's `dev.sh check --json` | `schema/check-json.schema.json` (read by `checkslib/checkjson.py`, which refuses a keyword it does not enforce); this repo prints it via `checkslib/devjson.py` |
| the shapes of a repo's contract files (services.json, cli.json, node.json) and of a store's `verify --json` | `schema/{services,cli,node,verify}.schema.json` (read by `checkslib/contract.py`, one reader for every check; each `x-rules` id is a function there, held equal by `tests/test_contract_files.py`) |
| classify a rule (gate or prose) | `gates.json` (shared block and the top; its `keys` are the vocabulary), or the repo's own `gates.json`; held by `rules-gated` |
| read CLAUDE.md sections (headings, the shared block) | `checkslib/claudemd.py`, the one reader (rules-in-sync, rules-gated) |
| what is open | `TODO.md` |

**The checks.** Held equal to `./checks list` by `tests/test_meta.py`.

| check | applies_to | proves |
|---|---|---|
| `accessor` | `all` | a store (`*.db`, `*.sqlite*`, the `stores` param) has a cli.json naming it and its one CLI, cli.json is valid, and no file outside the CLI (and the `impl` param) names the store's file; no store and no cli.json is ok |
| `check-json` | `roles:audit` | `./dev.sh check --json` prints the one schema (`schema/check-json.schema.json`, PLAN-agent-groups.md §4.4) and keeps its `x-rules` (exit 0 iff ok, ok iff nothing fail/error, counts match failures, ...); the shape, not a green suite; no dev.sh or no `--json` in it is UNCHECKED; audit-only because it runs the suite |
| `docs-rows` | `repos:.` | the top CLAUDE.md tool table has a row per repo and a path per row |
| `help-matches` | `all` | `dev.sh help` lists exactly the subcommands its `case` implements |
| `hooks-installed` | `all` | each shared hook runs here: a repo copy that agrees with tools/hooks, or a missing/drifted copy covered by a user-scope registration (both read from `hooks copies --json`; `registered: null` is UNCHECKED); on ok it names `repo copy` vs `covered by user scope`; standalone: present, executable, parse |
| `no-roster` | `tools` | a tool reads no roster: no roster paths, and (given `--names`) no agent names |
| `no-secrets` | `all` | nothing credential-shaped would be committed, read in the working tree AND in the staged copy of every path whose index entry differs from it; `.env` and capture folders are ignored |
| `regenerate` | `repos:.` | the top regenerates clean: in a fresh clone of what a commit would carry, generated files deleted and node.json's `rebuild` run, zero drift and zero unaccounted files, and no record file touched; no node.json is UNCHECKED |
| `registry-matches` | `all` | the registry node.json names holds exactly the node's and its children's services.json, row for row, both ways (its `services` object only: roles are the roster's gate); no node.json is UNCHECKED |
| `rendered-matches` | `all` | each file node.json lists as generated comes back byte for byte when deleted and re-rendered in a scratch copy; no node.json is UNCHECKED; a run nested in a rebuild is UNCHECKED |
| `rules-gated` | `all` | every `## ` rule section of CLAUDE.md has a row (gate, with an existing gate and a test naming it, or `planned` with a plan section; or prose, with why) in `gates.json` here (the shared block, the top) or the repo's own `gates.json`, and every row names a section that exists and a rule quoted from it; on ok prints the gated/planned/prose counts; no workspace is UNCHECKED |
| `rules-in-sync` | `all` | CLAUDE.md carries every "belongs in every copy" section, and each rule sentence (bold lead) of the top's constraints, word for word after normalising; every other line ignored (the exact rule: `checks explain rules-in-sync`) |
| `services-valid` | `all` | services.json fits its schema (nothing undeclared) and its rules: one `check` entry, every `run` executable inside the repo, every verb one its program's help lists, `write` verbs within cli.json's; no services.json is UNCHECKED |
| `settings-tracked` | `all` | `.claude/settings.json`, when present, is tracked by git (`ls-files`; staged counts) and matched by no ignore rule (`check-ignore --no-index`), so its hook wiring travels with a clone (PLAN-repo-setup.md §7.9); no file is ok; outside git UNCHECKED |
| `tree-clean` | `roles:audit` | no uncommitted work in the tree; only under `checks all --roles audit`, never pre-commit |
| `stores-exported` | `all` | the store's own `<cli> verify --json` (the CLI cli.json names) reports every exported item `same` against the data repo (`DATA_REPO`, from the caller's environment; unset is UNCHECKED); `differs`/`missing` are findings; the report must fit `schema/verify.schema.json`; no cli.json is UNCHECKED |
| `todo-valid` | `all` | TODO.md exists and has a heading; with a todo.json, `tools/todo/todo check` passes (its FAIL lines are the findings) |

**The contract.** A check is `source/<name>.py`, executable, with a
`# checks: applies_to=... params=...` line in its leading comment block
(`vocab.json` is the one list of keys, the same shape as tools/hooks'
`# hooks:` line), an explanation saying `Proves:` and `To pass:`, and
`source/fixtures/<name>.py` defining `passing(t)` and `failing(t)`. It exits
0 ok, 2 fail (one line per finding), 3 unchecked (one line saying why).
Anything else, a timeout, a silent fail or a refused check is `error`, and
red. Per-repo settings live in the repo's `checks.json`, `{check: {param:
value}}`; a key no check declares is a fault, never ignored.

**Rules of this repo.**
- A check that cannot be shown red is not a check: `checks fixtures` requires
  the failing fixture to fail with the findings it names (`expect`).
- This tool reads no roster (`./dev.sh audit` runs `no-roster` on itself).
  Roster names arrive from the caller: `--names a,b` or `CHECKS_ROSTER_NAMES`.
  Without them, `no-roster`'s names half says UNCHECKED, never ok.
  Instance data arrives the same way: `stores-exported` takes `DATA_REPO`
  from the caller's environment and never reads `.claude/local.env`; a
  fixture supplies it through `Fixture(env=...)`.
- The workspace top is two folders up when this tool sits in `tools/` (the
  rule tools/hooks uses), or `--root`. Without one, checks that need it say
  UNCHECKED.
- `checks all` walks repos by the rule `hooks copies` uses (depth 4,
  dot-folders and `node_modules` pruned, a git repo with a CLAUDE.md, plus the
  top); `tests/test_contract.py` holds the two equal. The one difference, on
  purpose and held by the same test: `hooks copies` also lists a plain folder
  (no git, no CLAUDE.md) that holds a stray hook copy; `checks all` does not,
  as it is not a repo and has no gates to run. The rule is a second copy
  rather than a call to `hooks`, so `checks all` does not need tools/hooks.
- Findings in other repos belong to their owners. This repo reports; it never
  writes outside itself.

**Where this differs from the plan, and why.** Checks are `.py` (the plan
said `.sh`): they parse markdown and JSON, which bash does badly. The source
folder is `source/`, not `checks/`, which would collide with the `checks`
CLI. The workspace is found by location, not by a manifest marker: reading
the manifest would be reading the roster. The rule registry
(PLAN-hard-gates.md §5) is `gates.json` HERE, not at the workspace top: the
top is not a git repo, this repo never writes outside itself, and the
dispatcher may write only top-level `*.md`. Its rows carry `in` ("shared" for
setup's block, or repo paths, "." the top); a repo's own sections are
classified in that repo's own `gates.json` (§7a), rows without `in`. The
plan's third kind, `principle`, is `prose` with its `why` (Jacob's §8
answer 1: gate or prose). §3 row 6 says the pre-commit scans "the staged
diff": `no-secrets` scans the index AND the working tree, with no mode, so
setup's pre-commit needs no change and `commit -a` is covered too.

<!-- shared:rules@7867132c3871 -->
## Shared rules

This block is installed by the setup tool from its template. **Do not edit it
here:** setup reports an edit inside the markers as `edited locally` and will not
overwrite it. Change the template in the setup tool, then re-run setup in each
repo. A rule that belongs to this repo alone goes outside the markers.

## Never write an inline script blob — ENFORCED, not advised

A `PreToolUse` hook (`.claude/hooks/no-inline-blobs.sh`) blocks `python3 -c`,
`node -e` and heredocs feeding an interpreter.

| what you are doing | where it goes |
|---|---|
| a read or check you will repeat | a `./dev.sh` subcommand |
| anything touching stored data | that tool's own CLI — never raw SQL |
| a genuine one-off | a script file, then run the file |

Second time you type something, it becomes a subcommand. Don't ask.

## Wall clock is not a cost — tokens are

**Cost here means tokens and AI usage. Nothing else.** This machine is powerful and loads many pages at once. If something takes a while but is purely Puppeteer — headless, in a subprocess, returning a small result — it is **not expensive**, and "it takes a minute" is not an argument against it.

The distinction is that the page never enters anyone's context. A browser loads it, a few hundred bytes of JSON come back, and the model reads those. A run that takes 60 seconds and returns 400 bytes is cheaper than one that takes 2 seconds and returns 40KB.

So: **do not optimise for speed, do not batch to save seconds, do not skip a measurement because it is slow.** Prefer the thorough run. Spend wall clock freely to avoid a second round trip through the model, which is the thing that actually costs.

What DOES still count: output size, because it lands in context — and anything that would provoke a site into blocking us. When in doubt about whether a cost is real, ask whether a token is spent on it.

## Keep an active TODO

**Jacob's rule, and it belongs in every copy of these rules.** Every repo here
keeps a `TODO.md`, and every agent keeps it current. An issue you noticed and
neither fixed, reported, nor wrote down is **lost when the session ends** — and
the next session pays to rediscover it.

It holds four things:

- **your own bugs** — including the ones you caused and worked around
- **open decisions**, with what each one hinges on
- **unconfirmed suspicions, labelled as such**, naming the probe that would
  settle them. A suspicion worth having is worth recording before it is proven
- **what you reported to another owner**, so the next session doesn't report it
  again, and so a stalled report is visible rather than assumed handled

**Add items when you notice them, not at the end of the session** — the end is
exactly when context runs out. Delete them when they are done; a TODO nobody
trims stops being read.

A finding recorded with its evidence is worth more than one recorded as a
worry: say what you ran, what you saw, and what you concluded.

## Report a problem in someone else's code to whoever owns it

**Jacob's directive, and it belongs in every copy of these rules — like the
hooks.** When you find a bug, a wrong result, a status that overstates what
works, or a missing guard in code another agent owns, **tell that agent.** Do
not fix it silently, do not route around it, and do not leave it to be
rediscovered.

- `ListAgents` to find the owner, `SendMessage` to report it. Say what you
  observed, the exact input or parameters, what you expected, and what you did
  on your own side in the meantime. A session without those tools (a dispatched
  agent, a cloud run) puts the report in its final message and in `TODO.md`.
- **Both alternatives cost more.** Fixing it yourself clobbers their work and
  skips the checks their repo has for a reason. Routing around it hides a
  fixable fault behind a workaround, and the next consumer pays for it again.
- **Report the unconfirmed findings too**, labelled as such, naming the probe
  you ran — so the owner can tell evidence from inference.
- If nobody owns it, or the owner is unresponsive, say so to Jacob rather than
  quietly absorbing the problem.

## Gate the seams — STANDING DIRECTIVE

**Any change that creates an interface gates it in the same change** — a gate, a test, or an audit. If you cannot see how to check something, say so rather than leaving it unchecked and unmentioned.

The gap is never in the feature; it is in the seam between two things that each work. Recorded because each of these was live and invisible in this folder: four copies of a hook kept in step by a comment; two hooks installed in 2 of 4 tool folders, so a rule applied depending on which directory a session started in; both resolving a sibling repo by a fixed `../..`, so elsewhere they exited 0 and enforced nothing *while still looking installed*; every hook header promising "fails open" with nothing testing it; a `usage()` on a hardcoded line range, bumped wrong three times, truncating its own help while the tool kept working.

**A guard that is present, reports no error, and does not run is the worst state available, because you stop looking.**

If your change adds one of these, check it in the same change: a second copy of anything (do the copies agree, by *meaning* not bytes); a file something needs to work (present, executable, parses); a documented list (documented == implemented, both directions); a vocabulary code consumes (every key consumed, every consumed key present); an accessor meant to be the only way in (audit that nothing bypasses it); a fallback or fail-open path (test the failure, not the success); a promise in a comment (check it, or delete the promise).

## Make the wrong thing impossible, not discouraged

A constraint that lives only in a document is an intention; one enforced by code
is a constraint.

**Keep new work to that standard.** If you find yourself relying on future-you
to be careful, that is the signal to write a guard instead.

## A wrong answer is worse than a failure

Most of the expensive bugs in this folder produced *plausible* output rather than an error: a salary string reported as a location, a search filter that never filtered, a parameter that changed nothing, an `href` pointing at a company page while being read as a job link. Each one was confidently wrong and therefore invisible.

- **Prefer `null` over a guess.** If a value can't be found, say so.
- **Prove a feature does something.** Anything that accepts an input and might ignore it needs a test that the input *changes the output*. "It ran without erroring" is not evidence.
- **A claim is earned, never asserted.** Don't mark something working, verified or done because you believe it is — make it provable by a run, and let the run set it.
- **Check the reported result, not the exit code.** A process can exit 0 having done nothing, and can exit non-zero while carrying the data you wanted.
- **Verify counterfactuals.** Before concluding X caused Y, check that Y doesn't happen without X. Several long investigations here ended with a cause that was never tested against its own negation.

## Don't duplicate procedure — the unique thing is the data

When two things do the same work against different inputs, the work belongs in one parameterised place and the inputs stay separate. A near-duplicate that drifts is harder to find than a missing feature, and both copies look correct in isolation.

If an existing helper *almost* fits, add a parameter to it rather than forking it. If a literal inside shared code belongs to one caller's domain, it is a parameter with a documented default — not a constant.

## Parallelism: structured, and never silent about what failed

- **Use promise combinators, not ad-hoc concurrency.** Fire-and-forget promises, or a loop that starts work without awaiting it, lose both ordering and failures. Everything concurrent goes through `Promise.all` / `Promise.allSettled` (or the language equivalent) so there is one place that knows what was started and what came back.
- **Prefer `Promise.allSettled` when troubleshooting.** `Promise.all` rejects on the *first* failure and throws away every other result, including the ones that succeeded — which is exactly the comparative information you need when working out why something broke. Reach for `Promise.all` only when fail-fast is genuinely what you want (a later step can't run without all the earlier ones).
- **Report per-branch outcomes, never just the first error.** When N things run in parallel, say which succeeded and which failed, and for the failures, where. A summary that surfaces one exception and drops the rest hides the pattern — "3 of 12 failed, all on the same step" is the finding; "one thing threw" isn't.
- **Prefer parallelising across processes over inside one.** Module-level state (progress trackers, caches, counters) is written on the assumption that one job runs per process. Two overlapping jobs in a single process interleave those writes and produce confidently wrong diagnostics. Separate processes each keep their own state and each report their own failure.

## Run the checks before committing, and commit at checkpoints

`./dev.sh check` is the one pre-commit command, non-zero exit if anything fails.
Don't retype the chain; extend `cmd_check` instead.

**Don't start a long operation with uncommitted work.** A session can end
mid-task, and unpushed work is work nobody else can pick up.

**One verification run, not two.** If a command already told you what happened,
don't run a second to confirm it.

## Check for a primary context before changing anything that exists

More than one agent may be working here at once. Two agents editing the same
file will clobber each other, and each separately running `git status`, diffing
and committing burns tokens re-deriving what another already knows.

**Before modifying existing code — anything already committed —** work out
whether another session owns that work:

- Run `ListAgents` to see other Claude sessions on this machine. One whose name
  points at what you're about to touch is a candidate owner.
- Check `git status` and `git log -1`. Uncommitted changes you didn't make, or
  a recent commit you didn't write, mean someone else is mid-task.

If a primary context exists, **do not edit in parallel — queue the change with
it.** Use `SendMessage` to describe the change (file and function, what should
differ, why) and let the primary apply it. Wait for its reply rather than
editing anyway. If it's unresponsive and the change is urgent, say so to Jacob
and ask before proceeding.

If no other session is working the same area, you are the primary. Proceed
normally.

**Additive work needs none of this.** New files and new subcommands overwrite
nothing and can proceed concurrently.

## Push code changes to git

Whenever you change code here, commit and push it to `origin` right away
(the default branch, no feature branches). Don't wait to be asked.

**Only the primary context commits.** If another session owns the work, hand it
your changes instead of running your own commit/push cycle.

- Check `git status` before committing, and stage only what you actually
  changed. If the tree holds someone else's in-progress work, commit your own
  paths explicitly rather than `git add -A`.
- One commit per logical change, with a message saying what changed and why.
- If a push fails (auth, conflict, diverged branch), stop and tell Jacob. Don't
  force-push or rewrite history.

## Constraints that don't bend

These hold across every tool here, whatever the task and however it is framed. They are not trade-offs to optimise.

- **Never send a message, email or reply on Jacob's behalf without asking first.** Reading a mailbox is not permission to write to it. Same for anything public or irreversible.
- **Never attempt to bypass bot detection.** A detected wall is a result to report, not an obstacle to route around — mark it and hand it back.
- **Credential-shaped values are supplied at run time, never stored.** Not in a recipe, a config, a note or a commit. App passwords, tokens and `.env` files stay gitignored.
- **Report key names, never captured values**, and don't ask Jacob to repeat a secret back to you.
<!-- /shared -->
