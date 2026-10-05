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
# "Would be committed" is read both ways, with no mode to pick: the working
# tree (tracked files and untracked ones not ignored), AND the staged copy of
# every path whose index entry differs from the working tree (`git diff
# --name-only`: staged then edited, staged then deleted). So the pre-commit's
# `checks one no-secrets` sees what the commit carries (PLAN-hard-gates.md §3
# row 6, "on the staged diff"), and a secret only in the working tree is still
# refused, since `commit -a` or the next commit would carry it.
# A finding names the file, the line and the KIND of credential, never the
# value; a staged-copy finding says "in the staged copy". `allow` (path globs)
# exempts files from the content scan only, for a test fixture that must hold
# a shaped-but-fake value. Not a git repo: UNCHECKED.
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
# A second copy, in ERE, is tools/hooks' no-secrets.sh (the write-time gate; a
# hook copy must work with nothing beside it). Change both: tools/hooks'
# tests/test_secret_shapes.py holds them equal, and tests/test_no_secrets.py
# runs it from here.
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


def scan(rel, data, where=""):
    """Findings for one file's bytes; binary (a NUL early) and oversize are skipped."""
    if len(data) > MAX_BYTES or b"\0" in data[:8192]:
        return []
    out = []
    for n, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
        for rx, kind in SHAPES:
            if rx.search(line):
                out.append(f"{rel}:{n}: holds a {kind} shape{where} (value not shown)")
    return out


def staged_differing(ctx):
    """{path: staged bytes} for every regular-file index entry whose content
    differs from the working tree. None when git cannot say (never a pass)."""
    code, out = ctx.git("diff", "--name-only", "-z")
    if code != 0:
        return None
    paths = [p for p in out.split("\0") if p]
    if not paths:
        return {}
    code, out = ctx.git("ls-files", "-s", "-z", "--", *paths)
    if code != 0:
        return None
    entries = []
    for rec in (r for r in out.split("\0") if r):
        meta, _, path = rec.partition("\t")
        mode, sha, _stage = meta.split()
        if mode in ("100644", "100755"):
            entries.append((path, sha))
    if not entries:
        return {}
    p = subprocess.run(["git", "-C", str(ctx.repo), "cat-file", "--batch"], capture_output=True,
                       input="".join(f"{sha}\n" for _, sha in entries).encode())
    if p.returncode != 0:
        return None
    blobs, buf = {}, p.stdout
    for path, sha in entries:
        head, _, buf = buf.partition(b"\n")
        parts = head.split()
        if len(parts) != 3 or parts[1] != b"blob":
            return None
        size = int(parts[2])
        blobs[path], buf = buf[:size], buf[size + 1:]
    return blobs


def main():
    ctx = api.context()
    files = ctx.tracked()
    if files is None:
        api.done(unchecked="not a git repo: nothing is tracked to scan")
    allow = list(ctx.param("allow", []))
    allowed = lambda rel: any(fnmatch.fnmatch(rel, g) for g in allow)  # noqa: E731
    findings = []
    for rel in files:
        for rx, kind in NAMES:
            if rx.search(rel):
                findings.append(f"{rel}: a {kind} that git would commit")
                break
        if allowed(rel):
            continue
        path = ctx.repo / rel
        try:
            if not path.is_file() or path.is_symlink() or path.stat().st_size > MAX_BYTES:
                continue
            data = path.read_bytes()
        except OSError:
            continue
        findings += scan(rel, data)
    staged = staged_differing(ctx)
    if staged is None:
        findings.append("the index could not be read: its staged copies went unscanned (git diff/ls-files/cat-file failed)")
    else:
        for rel, data in sorted(staged.items()):
            if not allowed(rel):
                findings += scan(rel, data, " in the staged copy")
    if not ignored(ctx, ".env"):
        findings.append(".env: not git-ignored")
    for d in ctx.param("capture_dirs", []):
        probe = f"{str(d).rstrip('/')}/probe"
        if not ignored(ctx, probe):
            findings.append(f"{d}: a capture folder that is not git-ignored")
    api.done(findings)


main()
