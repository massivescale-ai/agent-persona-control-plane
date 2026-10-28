#!/usr/bin/env python3
"""Lint persona files. Exit 1 if any rule fails. Runs on every pull request.

Usage: tools/lint.py [persona.yaml ...]     (default: every file in personas/)
"""
import datetime
import json
import re
import sys

import jsonschema

from common import ROOT, catalog, derived_tier, load_yaml, persona_files

SECRET = re.compile(r"(api[_-]?key|secret|password|token\s*:|sk-[A-Za-z0-9]{8,}|AKIA[0-9A-Z]{12,}|BEGIN [A-Z ]*PRIVATE KEY)", re.I)
NAMED_PERSON = re.compile(r"^[a-z]+\.[a-z]+$")


def lint(path, tools, classes, platform, today):
    errors = []
    err = lambda rule, msg: errors.append((rule, msg))
    raw = path.read_text()
    p = load_yaml(path)

    # P001  the file matches the schema. Unknown fields are refused, so nobody can
    #       add a free "policy_ref" and point the agent at a weaker policy.
    schema = json.loads((ROOT / "schema/persona.schema.json").read_text())
    typed = dict(p)
    if "risk_tier" in typed and str(typed["risk_tier"]).isdigit():
        typed["risk_tier"] = int(typed["risk_tier"])
    for e in sorted(jsonschema.Draft202012Validator(schema).iter_errors(typed), key=str):
        where = "/".join(str(x) for x in e.absolute_path) or "(top level)"
        err("P001", f"{where}: {e.message}")
    if any(e[0] == "P001" for e in errors):
        return errors  # the rest of the rules assume the shape is right

    # P002  no secret ever sits in a persona file.
    for n, line in enumerate(raw.splitlines(), 1):
        if SECRET.search(line):
            err("P002", f"line {n}: looks like secret material. A persona names routes, never keys.")

    # P003  one named person owns it. A team alias can't be paged and can't be held to account.
    if not NAMED_PERSON.match(p["owner"]):
        err("P003", f"owner '{p['owner']}' is not a named person (expected first.last).")

    # P004  the agent runs as itself. On a person's account you can't tell the two apart.
    if p["identity"]["runs_as"] != "agent":
        err("P004", "identity.runs_as is 'user'. The agent must hold its own identity, "
                    "so its logs, limits, and off switch are its own.")

    # P005  the model is reached through a named gateway route.
    if p["model_access"] not in platform["model_routes"]:
        err("P005", f"model_access '{p['model_access']}' is not a gateway route {platform['model_routes']}.")

    # P006  risk tier is derived from data classes. If someone typed one, it has to match.
    unknown = [c for c in p["data_classes"] if c not in classes]
    for c in unknown:
        err("P006", f"data class '{c}' is not in catalog/data-classes.yaml.")
    if not unknown and "risk_tier" in p:
        want = derived_tier(p, classes)
        if int(p["risk_tier"]) != want:
            top = max(p["data_classes"], key=lambda c: classes[c])
            err("P006", f"risk_tier is {p['risk_tier']} but data class '{top}' makes it {want}. "
                        "Delete the field or fix it.")

    # P007  every tool in scope is in the tool registry.
    scope = p["tool_scope"]
    for t in scope:
        if t not in tools:
            err("P007", f"tool '{t}' is not registered in catalog/tools.yaml.")

    # P008  the action contract covers the scope exactly. Every tool in scope is in one
    #       column. Nothing on the never list is in scope at all.
    ac = p["action_contract"]
    alone, approve, never = ac["alone"], ac["needs_approver"]["actions"], ac["never"]
    for t in scope:
        cols = (t in alone) + (t in approve)
        if cols == 0:
            err("P008", f"'{t}' is in tool_scope but in no column of the action contract.")
        if cols == 2:
            err("P008", f"'{t}' is in both 'alone' and 'needs_approver'.")
    for t in alone + approve:
        if t not in scope:
            err("P008", f"'{t}' is in the action contract but not in tool_scope.")
    for t in never:
        if t in scope:
            err("P008", f"'{t}' is on the never list and also in tool_scope. Take it out of scope.")
    if approve and not ac["needs_approver"]["role"]:
        err("P008", "needs_approver has actions but no approver role.")

    # P009  what the agent does alone has to fit its autonomy level.
    ceiling = platform["autonomy_ceiling"][p["autonomy_level"]]
    for t in alone:
        if t in tools and tools[t]["blast"] not in ceiling:
            err("P009", f"'{t}' has blast '{tools[t]['blast']}'. A {p['autonomy_level']} "
                        f"can't run it alone. Move it to needs_approver or promote the agent.")

    # P010  every persona expires, and not too far out.
    exp = datetime.date.fromisoformat(p["expires"])
    limit = int(platform["max_lifetime_days"])
    if exp <= today:
        err("P010", f"expires {exp} is in the past.")
    elif (exp - today).days > limit:
        err("P010", f"expires {exp} is more than {limit} days out.")

    return errors


def main():
    tools, classes, platform = catalog()
    today = datetime.date.today()
    failed = 0
    for path in persona_files(sys.argv[1:]):
        errors = lint(path, tools, classes, platform, today)
        name = path.name
        if errors:
            failed += 1
            print(f"FAIL  {name}")
            for rule, msg in errors:
                print(f"  {rule}  {msg}")
        else:
            print(f"PASS  {name}")
    if failed:
        print(f"\n{failed} persona file(s) failed lint. Merge is blocked.")
        sys.exit(1)


if __name__ == "__main__":
    main()
