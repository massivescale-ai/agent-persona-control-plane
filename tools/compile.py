#!/usr/bin/env python3
"""Compile every persona into the two copies. Runs on merge to main.

  out/registry/<id>.json    the registry row: what is admitted, who owns it
  out/gateway/policy.csv    Casbin policy: what the gateway will let through
  out/gateway/model.conf    Casbin model: deny by default

Nobody edits anything under out/ by hand.
"""
import json
import subprocess
import sys

from common import ROOT, catalog, derived_tier, load_yaml, persona_files

MODEL = """\
[request_definition]
r = agent, project, env, tool, act

[policy_definition]
p = agent, project, env, tool, act, eft

[policy_effect]
e = some(where (p.eft == allow)) && !some(where (p.eft == deny))

[matchers]
m = r.agent == p.agent && keyMatch(r.project, p.project) && keyMatch(r.env, p.env) && r.tool == p.tool && keyMatch(r.act, p.act)
"""


def commit():
    try:
        return subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                                       text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return "uncommitted"


def main():
    _, classes, _ = catalog()
    reg = ROOT / "out/registry"
    gw = ROOT / "out/gateway"
    reg.mkdir(parents=True, exist_ok=True)
    gw.mkdir(parents=True, exist_ok=True)
    for old in reg.glob("*.json"):
        old.unlink()  # a persona deleted from Git disappears from the registry

    lines, src = [], commit()
    for path in persona_files(sys.argv[1:]):
        p = load_yaml(path)
        ac = p["action_contract"]
        row = {
            "id": p["id"],
            "status": "active",
            "owner": p["owner"],
            "sponsor": p["sponsor"],
            "purpose": p["purpose"],
            "runs_as": p["identity"]["runs_as"],
            "risk_tier": derived_tier(p, classes),
            "autonomy_level": p["autonomy_level"],
            "expires": p["expires"],
            "tool_scope": p["tool_scope"],
            "bindings": p["bindings"],
            "source": f"personas/{path.name}@{src}",
        }
        (reg / f"{p['id']}.json").write_text(json.dumps(row, indent=2) + "\n")

        lines.append(f"# {p['id']}  owner {p['owner']}  tier {row['risk_tier']}  from {row['source']}")
        for b in p["bindings"]:
            for t in ac["alone"]:
                lines.append(f"p, {p['id']}, {b['project']}, {b['environment']}, {t}, call*, allow")
            for t in ac["needs_approver"]["actions"]:
                lines.append(f"p, {p['id']}, {b['project']}, {b['environment']}, {t}, call_approved, allow")
        for t in ac["never"]:
            lines.append(f"p, {p['id']}, *, *, {t}, *, deny")
        lines.append("")

    (gw / "model.conf").write_text(MODEL)
    (gw / "policy.csv").write_text("\n".join(lines))
    n = len(list(reg.glob("*.json")))
    rules = sum(1 for l in lines if l.startswith("p,"))
    print(f"compiled {n} persona(s) at {src}")
    print(f"  out/registry/         {n} row(s)")
    print(f"  out/gateway/policy.csv  {rules} rule(s), deny by default")


if __name__ == "__main__":
    main()
