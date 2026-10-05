#!/usr/bin/env python3
# checks: applies_to=all
# Proves: a node's registry agrees with every services.json under it
# (PLAN-routing-tree.md §14.8, PLAN-repo-setup.md §7.5): the registry
# node.json names (`registry`) has a `services` object keyed by repo path
# (`.` for the node itself, else a child's path from node.json `children`),
# and its rows are exactly those repos' services.json, both ways: a row with
# no matching services.json is a finding, a services.json with no row is a
# finding, and a row that differs names the keys that differ. Every finding
# is listed. Only the registry's `services` object is read: its roles come
# from the roster, which this tool never reads, so whether the registry
# matches the roster is the roster owner's gate, not this one.
# node.json is validated first (schema/node.schema.json); one with any
# finding is reported and its paths are not followed. No node.json is
# UNCHECKED (not a node); so is a node.json with no `registry` and no
# children. Children and no `registry` is a finding.
# To pass: re-render the registry from the services.json files (the node's
# registry is their union, never hand-edited); add a services.json to the
# child the row is for, or drop the row; list the child in node.json.
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from checkslib import api, contract  # noqa: E402

BROKEN = object()


def label(rel):
    return contract.SERVICES if rel == "." else f"{rel}/{contract.SERVICES}"


def differing(a, b):
    if isinstance(a, dict) and isinstance(b, dict):
        return ", ".join(sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k)))
    return "the whole row"


def main():
    ctx = api.context()
    doc, found = contract.read(ctx.repo, contract.NODE)
    if doc is None and not found:
        api.done(unchecked=f"no {contract.NODE}: not a node, so no registry to match")
    if found:
        api.done(found)
    children = [contract.norm(c) for c in doc.get("children", [])]
    if "registry" not in doc:
        if children:
            api.done([f"{contract.NODE}: names children but no `registry`: nothing to hold their services"])
        api.done(unchecked=f"{contract.NODE} names no registry and no children")
    reg = doc["registry"]
    try:
        data = json.loads((ctx.repo / reg).read_text())
    except OSError:
        api.done([f"{reg}: the registry {contract.NODE} names does not exist"])
    except ValueError as e:
        api.done([f"{reg}: does not parse ({e})"])
    if not isinstance(data, dict) or not isinstance(data.get("services"), dict):
        api.done([f"{reg}: no `services` object (repo path -> its services.json)"])
    rows = {contract.norm(k): (k, v) for k, v in data["services"].items()}
    findings, declared = [], {}
    for rel in ["."] + children:
        base = ctx.repo if rel == "." else ctx.repo / rel
        if not base.is_dir():
            findings.append(f"{rel}: a child {contract.NODE} names does not exist")
            continue
        p = base / contract.SERVICES
        if p.is_file():
            try:
                declared[rel] = json.loads(p.read_text())
            except ValueError:
                declared[rel] = BROKEN
                findings.append(f"{label(rel)}: does not parse, so its row cannot be compared")
    for key, (raw, _) in sorted(rows.items()):
        if key not in declared:
            findings.append(f"{reg}: row `{raw}`: no matching services.json (not the node or a child that has one)")
    for rel, mine in sorted(declared.items()):
        if rel not in rows:
            findings.append(f"{label(rel)}: no row in {reg}")
        elif mine is not BROKEN and rows[rel][1] != mine:
            findings.append(f"{reg}: row `{rows[rel][0]}` differs from {label(rel)} at: {differing(rows[rel][1], mine)}")
    api.done(findings)


main()
