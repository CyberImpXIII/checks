#!/usr/bin/env python3
# checks: applies_to=all params=capture_dirs,allow
# Proves: nothing credential-shaped is tracked by git or would be committed, and the places secrets
# live are ignored:
#   - no such file is named like a secret store (.env, *.env, .env.<x>
#     other than .example/.sample/.template, *.pem, *.p12, *.key, id_rsa,
#     id_ed25519, .netrc, credentials.json, token.json);
#   - no such text file holds a value shaped like a known credential
#     (Anthropic, OpenAI, GitHub, AWS, Slack, Google API, Telegram bot tokens,
#     private key blocks);
#   - `.env` and every folder in the `capture_dirs` param are git-ignored.
# A finding names the file, the line and the KIND of credential, never the
# value. `allow` (path globs) exempts files from the content scan only, for a
# test fixture that must hold a shaped-but-fake value. Not a git repo:
# UNCHECKED.
# To pass: untrack the file (git rm --cached), rotate anything real, and add
# the path to .gitignore; for a capture folder, ignore it.
import fnmatch
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checkslib import api  # noqa: E402

NAMES = [
    (re.compile(r"(^|/)\.env$"), ".env file"),
    (re.compile(r"(^|/)\.env\.(?!example$|sample$|template$)[^/]+$"), ".env.* file"),
    (re.compile(r"[^/]\.env$"), "*.env file"),
    (re.compile(r"\.(pem|p12|key)$"), "key file"),
    (re.compile(r"(^|/)id_(rsa|ed25519|ecdsa)$"), "ssh private key"),
    (re.compile(r"(^|/)\.netrc$"), ".netrc"),
    (re.compile(r"(^|/)(credentials|token)\.json$"), "credentials file"),
]
# Each pattern is written so that it does not match its own source text.
SHAPES = [
    (re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"), "Anthropic API key"),
    (re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9]{32,}"), "OpenAI API key"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}"), "GitHub token"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{50,}"), "GitHub fine-grained token"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key id"),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"), "Slack token"),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"), "Google API key"),
    (re.compile(r"\b\d{8,10}:AA[A-Za-z0-9_-]{33}\b"), "Telegram bot token"),
    (re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----"), "private key block"),
]
MAX_BYTES = 2_000_000


def ignored(ctx, rel):
    p = subprocess.run(["git", "-C", str(ctx.repo), "check-ignore", "-q", "--no-index", rel],
                       capture_output=True, text=True)
    return p.returncode == 0


def main():
    ctx = api.context()
    files = ctx.tracked()
    if files is None:
        api.done(unchecked="not a git repo: nothing is tracked to scan")
    allow = list(ctx.param("allow", []))
    findings = []
    for rel in files:
        for rx, kind in NAMES:
            if rx.search(rel):
                findings.append(f"{rel}: a {kind} that git would commit")
                break
        if any(fnmatch.fnmatch(rel, g) for g in allow):
            continue
        path = ctx.repo / rel
        try:
            if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_BYTES:
                continue
            data = path.read_bytes()
        except OSError:
            continue
        if b"\0" in data[:8192]:
            continue
        for n, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
            for rx, kind in SHAPES:
                if rx.search(line):
                    findings.append(f"{rel}:{n}: holds a {kind} shape (value not shown)")
    if not ignored(ctx, ".env"):
        findings.append(".env: not git-ignored")
    for d in ctx.param("capture_dirs", []):
        probe = f"{str(d).rstrip('/')}/probe"
        if not ignored(ctx, probe):
            findings.append(f"{d}: a capture folder that is not git-ignored")
    api.done(findings)


main()
