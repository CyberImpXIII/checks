#!/usr/bin/env python3
# checks: applies_to=roles:audit
# Proves: the repo's check runner fails in parts (PLAN-small-tasks.md §3,
# approved 2026-10-09): it is handed a three-part suite this check writes in
# a temporary folder (the repo's own suite never runs, and nothing in the
# repo is touched), and three things are shown on it:
#   killed  a run killed while one part hangs leaves a progress file whose
#           `passed_steps` names exactly the parts that had passed (§3.2);
#   changed after a full green run, an edit to one part's declared file makes
#           `check --json --resume` run that part and no other, and still
#           report every part, each ok (a skipped part counts as passed: M is
#           the whole suite) (§3.3);
#   hung    a part past its own `timeout_s` is stopped and reported not ok,
#           and the other parts still run and report ok; the text run ends
#           "2 of 3 passed; failed: p2 ..." -- the right N of M, and the
#           failed list naming p2 alone (§3.1, §3.4).
# The contract the runner (`./dev.sh`) keeps:
#   CHECK_PARTS=<file>  run the parts that file lists instead of the repo's own:
#       {"parts": [{"name", "run": "<sh command>", "files": [paths], "timeout_s"}]};
#       `run` runs in the file's folder, `files` are relative to it.
#   PROGRESS_FILE=<file>  the progress file (the shared progress.sh's
#       variable), rewritten as each part ends, with `passed_steps`: the names
#       of the parts that passed (the field the shared suite-parts.sh adds).
#   `./dev.sh check --json`  one `checks[]` entry per part, named by the part,
#       `ok` iff its run exits 0 within its timeout_s.
#   `./dev.sh check --json --resume`  runs only the parts whose files changed
#       since they passed, and the parts that did not pass; every part is in
#       `checks[]`, a skipped one `ok`.
#   `./dev.sh check`  (text) prints a line holding "<N> of <M> passed", then,
#       when any part failed, "; failed: " and each failed part's name.
# It also requires that the runner write no progress of its own run into the
# repo's `.progress/check.json` (a file carrying one of this check's runner
# pids there is a finding).
# A repo with no dev.sh, or whose dev.sh never mentions CHECK_PARTS, is
# UNCHECKED: the contract is unmet, never a pass. It runs the repo's runner,
# so it is `roles:audit` (`checks all --roles audit`, or `checks one
# check-partial <repo>`), and a run nested inside another is UNCHECKED. Each
# runner call gets 60s (CHECKS_CHECK_PARTIAL_RUN_TIMEOUT); a call past it
# is killed with its process group and is a finding of the scenario it ran.
# To pass: make `./dev.sh check` read CHECK_PARTS and PROGRESS_FILE as above,
# run each part with its own timeout, record each part's result as it ends,
# and on --resume compare each part's files with what they were when it passed.
# The one shared runner that does all of this is tools/checks/checkslib/parts.py
# (PLAN-small-tasks §7): a dev.sh can hand CHECK_PARTS to it, and this
# check's fixtures run it.
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checkslib import api  # noqa: E402

GUARD = "CHECKS_CHECK_PARTIAL_ACTIVE"
SCRIPT = "dev.sh"
KEY = "CHECK_PARTS"
RUN_TIMEOUT = float(os.environ.get("CHECKS_CHECK_PARTIAL_RUN_TIMEOUT") or 60)
SETTLE = 10.0          # how long a killed run's progress file may take to catch up
HANG_TIMEOUT = 2       # the hung part's timeout_s
PARTS = ["p1", "p2", "p3"]
SUMMARY = re.compile(r"\b(\d+) of (\d+) passed\b(?:; failed: (.*))?")

# One part: logs its start, then hangs (mode `block`, until the `stop` file
# appears or 300s pass), fails (mode `fail`) or passes, logging the outcome.
PART = """#!/bin/sh
echo "start $1" >> ran.log
case "$(cat "mode.$1" 2>/dev/null)" in
  block) n=0; while [ ! -e stop ] && [ $n -lt 1500 ]; do sleep 0.2; n=$((n+1)); done; exit 1 ;;
  fail) echo "fail $1" >> ran.log; exit 1 ;;
esac
echo "pass $1" >> ran.log
"""


class Suite:
    """The three-part suite in its own folder, and the runner calls on it."""

    def __init__(self, root, repo, env, timeouts):
        self.dir, self.repo, self.pids = Path(root), repo, []
        self.dir.mkdir(parents=True)
        (self.dir / "part.sh").write_text(PART)
        for p in PARTS:
            (self.dir / f"{p}.txt").write_text(f"{p}\n")
        self.manifest = self.dir / "parts.json"
        self.manifest.write_text(json.dumps({"parts": [
            {"name": p, "run": f"sh part.sh {p}", "files": [f"{p}.txt"], "timeout_s": timeouts.get(p, 30)}
            for p in PARTS]}, indent=1) + "\n")
        self.progress = self.dir / "progress" / "check.json"
        self.env = dict(env, **{KEY: str(self.manifest), "PROGRESS_FILE": str(self.progress)})

    def mode(self, part, mode):
        (self.dir / f"mode.{part}").write_text(mode)

    def log(self):
        try:
            lines = (self.dir / "ran.log").read_text().split()
        except OSError:
            return {}
        out = {}
        for verb, name in zip(lines[::2], lines[1::2]):
            out.setdefault(verb, []).append(name)
        return out

    def clear_log(self):
        (self.dir / "ran.log").unlink(missing_ok=True)

    def start(self, *extra):
        out = open(self.dir / f"out.{len(self.pids)}", "w+")
        p = subprocess.Popen([str(self.repo / SCRIPT), "check", *extra], cwd=self.repo, env=self.env,
                             stdin=subprocess.DEVNULL, stdout=out, stderr=subprocess.DEVNULL,
                             start_new_session=True)
        self.pids.append(p.pid)
        return p, out

    def kill(self, p):
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except OSError:
            pass
        p.wait()

    def text(self, *extra):
        """(stdout and exit code, or None and why)."""
        p, out = self.start(*extra)
        try:
            p.wait(timeout=RUN_TIMEOUT)
        except subprocess.TimeoutExpired:
            self.kill(p)
            out.close()
            return None, f"did not finish in {RUN_TIMEOUT:g}s"
        out.seek(0)
        text = out.read()
        out.close()
        return text, p.returncode

    def run(self, *extra):
        """(the parsed --json document or None, why it is None, finished in time)."""
        text, code = self.text("--json", *extra)
        if text is None:
            return None, code, False
        try:
            doc = json.loads(text)
        except ValueError:
            return None, f"printed no JSON document (exit {code}): {text.strip()[:120]!r}", True
        if not isinstance(doc, dict) or not isinstance(doc.get("checks"), list):
            return None, f"printed no `checks` list (exit {code})", True
        return doc, "", True

    def unstop(self):
        (self.dir / "stop").unlink(missing_ok=True)

    def passed_steps(self):
        try:
            got = json.loads(self.progress.read_text()).get("passed_steps")
        except (OSError, ValueError, AttributeError):
            return None
        return sorted(set(got)) if isinstance(got, list) and all(isinstance(x, str) for x in got) else None

    def stop(self):
        (self.dir / "stop").write_text("")


def statuses(doc):
    return {c.get("name"): c.get("status") for c in doc["checks"] if isinstance(c, dict)}


def killed(s, findings):
    s.mode("p2", "block")
    p, _ = s.start("--json")
    deadline = time.monotonic() + RUN_TIMEOUT
    while "p2" not in s.log().get("start", []) and p.poll() is None and time.monotonic() < deadline:
        time.sleep(0.1)
    if "p2" not in s.log().get("start", []):
        s.kill(p)
        s.stop()
        findings.append(f"killed: the hanging part p2 never started ({'the run ended' if p.poll() is not None else 'timed out'});"
                        f" the runner did not run the {KEY} suite")
        return
    # Let every other started part end and the progress file catch up, then kill.
    deadline = time.monotonic() + SETTLE
    while time.monotonic() < deadline:
        log = s.log()
        settled = set(log.get("start", [])) - {"p2"} <= set(log.get("pass", []) + log.get("fail", []))
        if settled and set(log.get("pass", [])) <= set(s.passed_steps() or []):
            break
        time.sleep(0.1)
    s.kill(p)
    s.stop()
    want, got = sorted(set(s.log().get("pass", []))), s.passed_steps()
    if got is None:
        findings.append(f"killed: a run killed while p2 hung left no progress file with `passed_steps` at"
                        f" PROGRESS_FILE (passed by then: {', '.join(want) or 'none'})")
    elif got != want:
        findings.append(f"killed: a run killed while p2 hung left `passed_steps` {got}, but the parts that"
                        f" had passed were {want}")
    elif not want:
        findings.append("killed: no part passed before p2 hung (p1 comes first): nothing shown")


def changed(s, findings):
    s.clear_log()
    doc, why, _ = s.run()
    if doc is None:
        findings.append(f"changed: the full run {why}")
        return
    st = statuses(doc)
    bad = [f"{p}={st.get(p)}" for p in PARTS if st.get(p) != "ok"]
    if bad:
        findings.append(f"changed: the full run of three passing parts reported {', '.join(bad)} (each wanted ok)")
        return
    s.clear_log()
    with open(s.dir / "p3.txt", "a") as f:
        f.write("edited\n")
    doc, why, _ = s.run("--resume")
    ran = sorted(set(s.log().get("start", [])))
    if doc is None:
        findings.append(f"changed: `check --json --resume` {why}")
    else:
        st = statuses(doc)
        bad = [f"{p}={st.get(p)}" for p in PARTS if st.get(p) != "ok"]
        if bad or len(doc["checks"]) != len(PARTS):
            findings.append(f"changed: `--resume` reported {len(doc['checks'])} part(s), {', '.join(bad) or 'none missing'}"
                            f" (wanted all {len(PARTS)}, each ok: a skipped part passed, so N of M counts it)")
    if ran != ["p3"]:
        findings.append(f"changed: after an edit to p3's file only, `--resume` ran {', '.join(ran) or 'no part'}"
                        " (wanted p3 alone)")


def hung(s, findings):
    s.mode("p2", "block")
    doc, why, done = s.run()
    s.stop()
    if not done:
        findings.append(f"hung: one part past its timeout_s ({HANG_TIMEOUT}s) held the whole run: it {why}")
        return
    if doc is None:
        findings.append(f"hung: the run with one hung part {why}")
        return
    st = statuses(doc)
    if st.get("p2") in (None, "ok"):
        findings.append(f"hung: the part past its timeout_s was reported {st.get('p2') or 'not at all'} (wanted not ok)")
    bad = [f"{p}={st.get(p)}" for p in ("p1", "p3") if st.get(p) != "ok"]
    if bad:
        findings.append(f"hung: beside one hung part the others reported {', '.join(bad)} (each wanted ok)")
    # §3.1: the text run's own report, "2 of 3 passed; failed: p2 ...".
    s.unstop()
    text, code = s.text()
    s.stop()
    if text is None:
        findings.append(f"hung: the text run (`./{SCRIPT} check`) {code}")
        return
    said = [(line.strip(), m) for line in text.splitlines() if (m := SUMMARY.search(line))]
    if not said:
        findings.append(f"hung: the text run printed no `N of M passed` line (exit {code}; last: {text.strip()[-120:]!r})")
        return
    line, m = said[-1]
    if (int(m[1]), int(m[2])) != (2, 3):
        findings.append(f"hung: the text run said `{line[:160]}` (wanted 2 of 3 passed)")
    named = [p for p in PARTS if re.search(rf"\b{p}\b", m[3] or "")]
    if named != ["p2"]:
        findings.append(f"hung: the text run's failed list named {', '.join(named) or 'nothing'}"
                        f" in `{line[:160]}` (wanted p2 alone)")


def own_progress(repo, pids):
    try:
        pid = json.loads((repo / ".progress" / "check.json").read_text()).get("pid")
    except (OSError, ValueError, AttributeError):
        return []
    return [f"the runner wrote this check's run (pid {pid}) into the repo's own .progress/check.json,"
            " not PROGRESS_FILE"] if pid in pids else []


def main():
    ctx = api.context()
    if os.environ.get(GUARD):
        api.done(unchecked="nested inside another check-partial run")
    script = ctx.repo / SCRIPT
    if not script.is_file():
        api.done(unchecked=f"no {SCRIPT}: no runner to hand a suite to (the contract is unmet)")
    if KEY not in script.read_text(errors="replace"):
        api.done(unchecked=f"{SCRIPT} never mentions {KEY}: it cannot run a given suite (the contract is unmet)")
    if not os.access(script, os.X_OK):
        api.done([f"{SCRIPT}: not executable (it is run directly, as ./{SCRIPT})"])
    env = {k: v for k, v in os.environ.items() if k not in (api.ENV_PARAMS, api.ENV_WORKSPACE, "PROGRESS_FILE")}
    env[GUARD] = "1"
    tmp = Path(tempfile.mkdtemp(prefix="checks-partial-"))
    findings, pids = [], []
    try:
        for name, timeouts, scenario in (("killed", {"p2": 120}, killed), ("changed", {}, changed),
                                         ("hung", {"p2": HANG_TIMEOUT}, hung)):
            s = Suite(tmp / name, ctx.repo, env, timeouts)
            try:
                scenario(s, findings)
            finally:
                s.stop()
                pids += s.pids
        findings += own_progress(ctx.repo, pids)
    finally:
        time.sleep(0.5)    # a stopped part notices `stop` within 0.2s
        shutil.rmtree(tmp, ignore_errors=True)
    if not findings:
        print("killed, changed and hung: each shown on a three-part suite (with N of M, text and --json)")
    api.done(findings)


main()
