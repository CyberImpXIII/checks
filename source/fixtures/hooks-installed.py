import json

from checkslib.fixture import Fixture, write

HOOK = "#!/usr/bin/env bash\ncat >/dev/null 2>&1\nexit 0\n"
TEST = "#!/usr/bin/env bash\necho ok\n"

# A stand-in for `hooks copies --json`, answering with a fixed report. The real
# tool's output is held to this shape by tests/test_contract.py.
REPORT = {"root": "<ws>", "ok": False, "unresolved": [], "locations": [
    {"path": ".", "files": [{"file": ".claude/hooks/a.sh", "status": "ok"}]},
    {"path": "r", "files": [{"file": ".claude/hooks/a.sh", "status": "drift"},
                            {"file": ".claude/hooks/test-a.sh", "status": "missing"},
                            {"file": ".claude/hooks/b.sh", "status": "extra"}]}]}


def passing(t):
    # standalone: no workspace, so present + executable + parses is the whole check
    repo = t / "r"
    write(repo / ".claude" / "hooks" / "a.sh", HOOK, 0o755)
    write(repo / ".claude" / "hooks" / "test-a.sh", TEST, 0o644)
    return Fixture(repo)


def failing(t):
    ws = t / "ws"
    write(ws / "tools" / "hooks" / "hooks", "#!/usr/bin/env bash\ncat <<'EOF'\n" + json.dumps(REPORT) + "\nEOF\n", 0o755)
    write(ws / "r" / ".claude" / "hooks" / "a.sh", HOOK, 0o755)
    return Fixture(ws / "r", workspace=ws, expect=[".claude/hooks/a.sh: drift", ".claude/hooks/test-a.sh: missing"])
