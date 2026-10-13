import json

from checkslib.fixture import Fixture, write

HOOK = "#!/usr/bin/env bash\ncat >/dev/null 2>&1\nexit 0\n"

# A stand-in for `hooks copies --json`, answering with a fixed report. The real
# tool's output is held to this shape by tests/test_contract.py. The two
# fixtures differ only in whether the user settings register the drifted hook
# (`registered`) and so whether the lib it reads is covered (its `support` row's
# `covered`, hooks' own verdict), so that input is what turns the result.
# Standalone mode, the null (unchecked) cases and a source mid-edit
# (`source_uncommitted` true/null: unchecked) are in tests/test_hooks_installed.py.
LIB_WHY = ".claude/hooks/a.sh is not registered there"


def report(registered):
    return {"root": "<ws>", "ok": False, "unresolved": [], "locations": [
        {"path": ".", "files": [{"file": ".claude/hooks/a.sh", "status": "ok", "source_uncommitted": False}]},
        {"path": "r", "files": [{"file": ".claude/hooks/a.sh", "status": "drift", "source_uncommitted": False},
                                {"file": ".claude/hooks/test-a.sh", "status": "missing", "source_uncommitted": False},
                                {"file": ".claude/bin/w.sh", "status": "missing", "source_uncommitted": False},
                                {"file": ".claude/hooks/b.sh", "status": "extra", "source_uncommitted": False}]}],
        "user_scope": {"settings": "<home>/.claude/settings.json", "exists": True, "error": None,
                       "source": "<ws>/tools/hooks/source", "left_per_repo": [], "ok": registered,
                       "hooks": [{"file": ".claude/hooks/a.sh", "kind": "source", "test": ".claude/hooks/test-a.sh",
                                  "event": "PreToolUse", "matcher": "Bash", "command": "<ws>/tools/hooks/source/hooks/a.sh",
                                  "registered": registered}],
                       "support": [{"file": ".claude/bin/w.sh", "kind": "source", "needed_by": [".claude/hooks/a.sh"],
                                    "covered": registered, "why": None if registered else LIB_WHY}]}}


def workspace(t, registered):
    ws = t / "ws"
    body = json.dumps(report(registered))
    write(ws / "tools" / "hooks" / "hooks", "#!/usr/bin/env bash\ncat <<'EOF'\n" + body + "\nEOF\n", 0o755)
    write(ws / "r" / ".claude" / "hooks" / "a.sh", HOOK, 0o755)
    return ws


def passing(t):
    # the drifted copy and its missing test are covered: user scope runs a.sh from its
    # source, so the support file a.sh reads is the source's too (`support` covered true)
    return Fixture(workspace(t, True) / "r", workspace=t / "ws")


def failing(t):
    ws = workspace(t, False)
    return Fixture(ws / "r", workspace=ws, expect=[".claude/hooks/a.sh: drift; not covered by user scope",
                                                   ".claude/hooks/test-a.sh: missing; not covered by user scope",
                                                   f".claude/bin/w.sh: missing; not covered by user scope ({LIB_WHY})"])
