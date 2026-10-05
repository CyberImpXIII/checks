#!/usr/bin/env python3
# checks: applies_to=roles:audit
# Proves: the repo's `./dev.sh check --json` prints the one schema
# (schema/check-json.schema.json, PLAN-agent-groups.md §4.4): one JSON
# document on stdout, `ok` plus a `checks` list, each check with a name, a
# status (ok, fail, unchecked, error), counts with `failed`, and failures that
# carry a message, file, line and the role they belong to; and the rules
# between fields (`x-rules` in the schema): the exit code is 0 iff ok, ok is
# false iff some check is fail or error, counts.failed equals the failures
# listed, a fail has a failure and an ok has none, an unchecked says why,
# names are unique, a line names its file. Every finding is listed.
# It proves the SHAPE, not a green suite: a red run in the right shape passes.
# It runs the repo's suite, so it is `roles:audit` (`checks all --roles audit`,
# or `checks one check-json <repo>`), never pre-commit, where it would run the
# suite inside itself. A run nested inside another check-json is UNCHECKED.
# A repo with no dev.sh, or whose dev.sh never mentions `--json`, is
# UNCHECKED: the contract is unmet, which is never a pass. The suite gets
# 280s; a run that does not finish is an error.
# To pass: make `./dev.sh check --json` print exactly that document and
# nothing else on stdout (the explanation is in the schema's descriptions;
# tools/checks' own dev.sh is a working example, via checkslib/report.py).
import os
import signal
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checkslib import api, checkjson  # noqa: E402

GUARD = "CHECKS_CHECK_JSON_ACTIVE"
SCRIPT = "dev.sh"
# Under the runner's 300s, so this says why rather than being killed. The
# environment override exists for tests/test_check_json.py's timeout case.
TIMEOUT = float(os.environ.get("CHECKS_CHECK_JSON_TIMEOUT") or 280)


def error(why):
    print(why)
    sys.exit(1)


def main():
    ctx = api.context()
    if os.environ.get(GUARD):
        api.done(unchecked="nested inside another check-json run, which is validating this very output")
    script = ctx.repo / SCRIPT
    if not script.is_file():
        api.done(unchecked=f"no {SCRIPT}: no `{SCRIPT} check --json` to validate (the contract is unmet)")
    if "--json" not in script.read_text(errors="replace"):
        api.done(unchecked=f"{SCRIPT} has no --json (no line of it mentions the flag): the contract is unmet")
    if not os.access(script, os.X_OK):
        api.done([f"{SCRIPT}: not executable (it is run directly, as ./{SCRIPT})"])
    env = {k: v for k, v in os.environ.items() if k not in (api.ENV_PARAMS, api.ENV_WORKSPACE)}
    env[GUARD] = "1"
    try:
        schema = checkjson.load()
    except (OSError, ValueError) as e:
        error(f"the schema did not load: {e}")
    try:
        p = subprocess.Popen([str(script), "check", "--json"], cwd=ctx.repo, env=env, stdin=subprocess.DEVNULL,
                             stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, start_new_session=True)
    except OSError as e:
        error(f"could not run {SCRIPT} check --json: {e}")
    try:
        out, _ = p.communicate(timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)        # the whole suite, not only the shell
        p.communicate()
        error(f"{SCRIPT} check --json did not finish in {TIMEOUT}s")
    api.done(checkjson.validate(out, p.returncode, schema))


main()
