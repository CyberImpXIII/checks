import json

from checkslib.fixture import Fixture, write

HOOK = "#!/usr/bin/env bash\ncat >/dev/null 2>&1\nexit 0\n"

# A stand-in for `hooks copies --json`, answering with a fixed report. The real
# tool's output is held to this shape by tests/test_contract.py. The two
# fixtures differ only in whether the user settings register the drifted hook
# (`registered`), so that input is what turns the result. Standalone mode and
# the null (unchecked) case are in tests/test_hooks_installed.py.
def report(registered):
    return {"root": "<ws>", "ok": False, "unresolved": [], "locations": [
        {"path": ".", "files": [{"file": ".claude/hooks/a.sh", "status": "ok"}]},
        {"path": "r", "files": [{"file": ".claude/hooks/a.sh", "status": "drift"},
                                {"file": ".claude/hooks/test-a.sh", "status": "missing"},
                                {"file": ".claude/hooks/b.sh", "status": "extra"}]}],
        "user_scope": {"settings": "<home>/.claude/settings.json", "exists": True, "error": None,
                       "source": "<ws>/tools/hooks/source", "left_per_repo": [], "ok": registered,
                       "hooks": [{"file": ".claude/hooks/a.sh", "kind": "source", "test": ".claude/hooks/test-a.sh",
                                  "event": "PreToolUse", "matcher": "Bash", "command": "<ws>/tools/hooks/source/hooks/a.sh",
                                  "registered": registered}]}}


def workspace(t, registered):
    ws = t / "ws"
    body = json.dumps(report(registered))
    write(ws / "tools" / "hooks" / "hooks", "#!/usr/bin/env bash\ncat <<'EOF'\n" + body + "\nEOF\n", 0o755)
    write(ws / "r" / ".claude" / "hooks" / "a.sh", HOOK, 0o755)
    return ws


def passing(t):
    # the drifted copy and its missing test are covered: user scope runs a.sh from its source
    return Fixture(workspace(t, True) / "r", workspace=t / "ws")


def failing(t):
    ws = workspace(t, False)
    return Fixture(ws / "r", workspace=ws, expect=[".claude/hooks/a.sh: drift; not covered by user scope",
                                                   ".claude/hooks/test-a.sh: missing; not covered by user scope"])
