"""This repo's `./dev.sh check --json`, in the one schema (schema/check-json.schema.json).

    python3 -m checkslib.devjson <step>:<role>:<exit code> ...

One check per step, in the order given: exit 0 -> ok; anything else -> fail,
with one failure naming the step to re-run (file and line null: dev.sh keeps
no file:line for a whole step, and null is said rather than guessed). Prints
the document and exits 0 iff every step passed, the schema's `exit-agrees`.
tests/test_check_json.py validates what this prints, green and red, through
the real dev.sh."""
import json
import sys


def document(rows):
    checks = []
    for step, role, code in rows:
        failures = [] if code == 0 else [{"message": f"./dev.sh {step} failed (exit {code}); run it for the findings",
                                          "file": None, "line": None, "role": role}]
        checks.append({"name": step, "status": "ok" if code == 0 else "fail",
                       "counts": {"failed": len(failures)}, "failures": failures})
    return {"ok": all(c["status"] == "ok" for c in checks), "checks": checks}


def parse(args):
    rows = []
    for a in args:
        step, role, code = a.split(":")
        rows.append((step, role, int(code)))
    return rows


def main(argv):
    try:
        rows = parse(argv)
    except ValueError:
        print(f"usage: python3 -m checkslib.devjson <step>:<role>:<exit code> ... (got {argv})", file=sys.stderr)
        return 64
    if not rows:
        print("devjson: no steps: a report of nothing is not a pass", file=sys.stderr)
        return 64
    doc = document(rows)
    print(json.dumps(doc))
    return 0 if doc["ok"] else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
