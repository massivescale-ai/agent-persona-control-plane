#!/usr/bin/env python3
"""Ask the gateway policy the same question the gateway asks on every tool call.

Usage: tools/check.py                      run the standard set of calls
       tools/check.py agent project env tool act
act is 'call' (no approval attached) or 'call_approved' (the gateway verified a named approver).
"""
import sys

import casbin

from common import ROOT

STANDARD = [
    ("soc-triage", "soc-tier1", "prod", "siem.search",       "call"),
    ("soc-triage", "soc-tier1", "prod", "case.add_note",     "call"),
    ("soc-triage", "soc-tier1", "prod", "edr.isolate_host",  "call"),
    ("soc-triage", "soc-tier1", "prod", "edr.isolate_host",  "call_approved"),
    ("soc-triage", "soc-tier1", "prod", "idp.disable_user",  "call_approved"),
    ("soc-triage", "payments",  "prod", "siem.search",       "call"),
    ("unregistered-agent", "soc-tier1", "prod", "siem.search", "call"),
]


def main():
    model = ROOT / "out/gateway/model.conf"
    policy = ROOT / "out/gateway/policy.csv"
    if not policy.exists():
        print("no compiled policy. Nothing has been merged, so every call is denied.")
        sys.exit(0)
    e = casbin.Enforcer(str(model), str(policy))
    calls = [tuple(sys.argv[1:6])] if len(sys.argv) == 6 else STANDARD
    for c in calls:
        verdict = "ALLOW" if e.enforce(*c) else "DENY "
        agent, project, env, tool, act = c
        print(f"{verdict}  {agent:<19} {project:<10} {env:<5} {tool:<18} {act}")


if __name__ == "__main__":
    main()
