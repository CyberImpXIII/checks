"""The one schema for a repo's `dev.sh check --json` (schema/check-json.schema.json,
PLAN-agent-groups.md §4.4), and the validator `source/check-json.py` runs.

The schema file is the one source. This module interprets exactly the JSON
Schema keywords that file uses (KEYWORDS + ANNOTATIONS) and refuses any other
(SchemaError), so a keyword added to the file without code to enforce it is an
error, never a keyword silently ignored. The rules JSON Schema cannot say live
in the file's `x-rules`; RULES below implements each by id, and
tests/test_check_json.py holds the two sets equal.

`validate(stdout, exit_code)` returns findings, one line each, every one found
(never only the first): `<rule>: <where>: <what>`, where a structural finding's
rule is `schema` and its where is a JSON path ($.checks[0].status)."""
import json
from pathlib import Path

from checkslib import runner

TOOL_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_FILE = TOOL_ROOT / "schema" / "check-json.schema.json"

KEYWORDS = {"type", "enum", "required", "properties", "additionalProperties", "items",
            "minItems", "minimum", "minLength"}
ANNOTATIONS = {"$schema", "$id", "title", "description", "x-rules"}
TYPES = {"object", "array", "string", "integer", "number", "boolean", "null"}


class SchemaError(ValueError):
    pass


def _audit(node, where):
    """Every keyword in the schema is one this module enforces or a mere annotation."""
    if not isinstance(node, dict):
        raise SchemaError(f"{where}: a schema must be an object")
    unknown = sorted(set(node) - KEYWORDS - ANNOTATIONS)
    if unknown:
        raise SchemaError(f"{where}: keyword(s) this validator does not enforce: {', '.join(unknown)}")
    types = node.get("type")
    for t in ([types] if isinstance(types, str) else types or []):
        if t not in TYPES:
            raise SchemaError(f"{where}: unknown type {t!r}")
    for name, sub in (node.get("properties") or {}).items():
        _audit(sub, f"{where}.properties.{name}")
    for key in ("items", "additionalProperties"):
        if isinstance(node.get(key), dict):
            _audit(node[key], f"{where}.{key}")


def load(path=SCHEMA_FILE):
    schema = json.loads(Path(path).read_text())
    _audit(schema, "$")
    if not isinstance(schema.get("x-rules"), dict):
        raise SchemaError("$: no x-rules")
    return schema


def _is(value, t):
    if t == "object":
        return isinstance(value, dict)
    if t == "array":
        return isinstance(value, list)
    if t == "string":
        return isinstance(value, str)
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if t == "boolean":
        return isinstance(value, bool)
    return value is None                                    # "null"


def _show(value):
    return json.dumps(value)[:60]


def structure(value, node, where="$"):
    """Findings for `value` against schema `node`. Each keyword applies only to
    the type it is about (JSON Schema's rule), so minLength on a string-or-null
    lets null through."""
    out = []
    if "type" in node:
        types = [node["type"]] if isinstance(node["type"], str) else node["type"]
        if not any(_is(value, t) for t in types):
            return [f"schema: {where}: {_show(value)} is not {' or '.join(types)}"]
    if "enum" in node and value not in node["enum"]:
        return [f"schema: {where}: {_show(value)} is not one of {', '.join(map(str, node['enum']))}"]
    if isinstance(value, str) and len(value) < node.get("minLength", 0):
        out.append(f"schema: {where}: shorter than {node['minLength']} character(s)")
    if _is(value, "number") and "minimum" in node and value < node["minimum"]:
        out.append(f"schema: {where}: {value} is below {node['minimum']}")
    if isinstance(value, list):
        if len(value) < node.get("minItems", 0):
            out.append(f"schema: {where}: fewer than {node['minItems']} item(s)")
        if isinstance(node.get("items"), dict):
            for i, item in enumerate(value):
                out += structure(item, node["items"], f"{where}[{i}]")
    if isinstance(value, dict):
        props = node.get("properties") or {}
        out += [f"schema: {where}: missing `{k}`" for k in node.get("required", []) if k not in value]
        for k, v in value.items():
            if k in props:
                out += structure(v, props[k], f"{where}.{k}")
            elif isinstance(node.get("additionalProperties"), dict):
                out += structure(v, node["additionalProperties"], f"{where}.{k}")
    return out


def _exit_agrees(doc, code):
    if (code == 0) != doc["ok"]:
        return [f"exit-agrees: exit {code} but ok is {json.dumps(doc['ok'])}"]
    return []


def _verdict(doc, code):
    red = [c["name"] for c in doc["checks"] if c["status"] in runner.RED]
    if doc["ok"] == bool(red):
        return [f"verdict: ok is {json.dumps(doc['ok'])} but "
                + (f"{', '.join(red)} {'is' if len(red) == 1 else 'are'} fail/error" if red else "no check is fail or error")]
    return []


def _counted(doc, code):
    return [f"counted: $.checks[{i}] ({c['name']}): counts.failed is {c['counts']['failed']}, "
            f"failures has {len(c['failures'])}"
            for i, c in enumerate(doc["checks"]) if c["counts"]["failed"] != len(c["failures"])]


def _status_failures(doc, code):
    out = []
    for i, c in enumerate(doc["checks"]):
        n = len(c["failures"])
        if c["status"] in ("ok", "unchecked") and n:
            out.append(f"status-failures: $.checks[{i}] ({c['name']}): {c['status']} with {n} failure(s)")
        if c["status"] in runner.RED and not n:
            out.append(f"status-failures: $.checks[{i}] ({c['name']}): {c['status']} with no failure saying what")
    return out


def _unchecked_reason(doc, code):
    return [f"unchecked-reason: $.checks[{i}] ({c['name']}): unchecked with no `reason`"
            for i, c in enumerate(doc["checks"]) if c["status"] == "unchecked" and not c.get("reason")]


def _unique_names(doc, code):
    seen, out = set(), []
    for i, c in enumerate(doc["checks"]):
        if c["name"] in seen:
            out.append(f"unique-names: $.checks[{i}]: `{c['name']}` given twice")
        seen.add(c["name"])
    return out


def _line_needs_file(doc, code):
    return [f"line-needs-file: $.checks[{i}].failures[{j}]: line {f['line']} with no file"
            for i, c in enumerate(doc["checks"]) for j, f in enumerate(c["failures"])
            if f["line"] is not None and f["file"] is None]


# `one-document` is decided before any of these can run (validate, below).
RULES = {"one-document": None, "exit-agrees": _exit_agrees, "verdict": _verdict, "counted": _counted,
         "status-failures": _status_failures, "unchecked-reason": _unchecked_reason,
         "unique-names": _unique_names, "line-needs-file": _line_needs_file}


def validate(stdout, code, schema=None):
    schema = schema or load()
    text = (stdout or "").strip()
    if not text:
        return [f"one-document: printed nothing on stdout (exit {code})"]
    try:
        doc = json.loads(text)
    except ValueError as e:
        first = text.splitlines()[0][:100]
        return [f"one-document: stdout is not one JSON document ({getattr(e, 'msg', e)}, line "
                f"{getattr(e, 'lineno', '?')}); it starts: {first}"]
    found = structure(doc, schema)
    if found:                                   # the cross rules need the structure to hold, but
        if isinstance(doc, dict) and isinstance(doc.get("ok"), bool) and RULES["exit-agrees"]:
            found += RULES["exit-agrees"](doc, code)    # exit-agrees needs only `ok`: said anyway
        return found
    for fn in RULES.values():
        if fn is not None:
            found += fn(doc, code)
    return found
