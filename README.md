# Agent persona control plane

One YAML file for each kind of AI agent. A pull request is the review. Merging it
builds the two things a gateway uses: a registry row and a policy.

This is the code from the [un]prompted 2026 talk "What 40 enterprises who asked for
agent governance had, and the control plane that came out of it." You can run
every step from the slides yourself.

## Quick start

You need git and Python 3.9 or newer.

```sh
git clone https://github.com/massivescale-ai/agent-persona-control-plane
cd agent-persona-control-plane
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt

python tools/lint.py
python tools/compile.py
python tools/check.py
./demo.sh
```

`demo.sh` replays the talk in a throwaway copy with its own Git history. It checks
each verdict along the way and ends with `DEMO OK`. Your files don't change.

## How the pieces fit

1. **The persona file.** There's one per kind of agent, in `personas/`. It names
   the person who owns the agent. It says the agent runs as itself. It lists the
   data it touches and the tools it can reach. Its action contract says which
   tools need a named approver and which it can never call.
2. **Lint on every pull request.** `tools/lint.py` checks the file against ten
   rules. One failure blocks the merge. `CODEOWNERS` says who has to sign.
3. **Compile on merge.** `tools/compile.py` turns each file into two copies under
   `out/`. One is the registry row. It says what's admitted and who owns it. The
   other is the gateway policy, written for Casbin, an open policy engine. Any call
   the policy doesn't list is denied.
4. **Check.** `tools/check.py` asks the policy the same question a gateway asks on
   each call. Which agent is calling? From which project and environment? Which
   tool? Did a named person approve it?

Nobody edits `out/` by hand. To switch gateways, you rewrite the bottom of
`compile.py`. The persona files stay the same.

The workflow in `.github/workflows/persona.yml` runs lint and the demo on each
pull request that changes code or a persona. It compiles on each merge to `main`.

```
personas/      one file per kind of agent (the only thing people edit)
catalog/       tool registry, data class tiers, model routes, autonomy limits
schema/        the persona schema
tools/         lint.py, compile.py, check.py, and common.py for shared loaders
demo/          the persona as found, and the first try at promotion
demo-output/   the recorded run the slides came from
```

## The ten lint rules

| Rule | What it checks |
|---|---|
| P001 | The file matches the schema. Unknown fields are refused. |
| P002 | There's no secret in the file. It names a route, never a key. |
| P003 | One named person owns the agent, not a team alias. |
| P004 | The agent runs as itself, not as the person who started it. |
| P005 | It reaches models only through a named gateway route. |
| P006 | Lint works out the risk tier from the data classes. A typed tier has to match. |
| P007 | Every tool in scope is in the tool registry. |
| P008 | Each tool in scope sits in one column of the action contract. Nothing on the never list is in scope. |
| P009 | What the agent does alone fits its autonomy level. |
| P010 | The persona expires, and no more than 365 days out. |

## What it doesn't cover

A file can't close a network path. An app that holds its own model key can still
call the model directly. The network has to send agent traffic to the gateway.

The file doesn't reach these agents yet:

- Agents that run on a SaaS platform's own identity
- Contractor builds on a shared key
- Desktop agents that run as the person
- Low-code agents with their own stored connection credentials

This is a reference build. Nobody runs the whole pipeline in production yet.

## Before you run it

**The persona expires on 2027-04-01.** After that date lint fails P010. That's on
purpose, because every persona expires. To run it later, change `expires` to a date
less than 365 days out. Change it in `personas/soc-triage.yaml` and in both files
under `demo/`.

**The CODEOWNERS teams are examples.** `@identity-team` and the others don't exist
here, so GitHub marks them unknown. Put your own teams in.

**Your hashes won't match the slides.** `demo-output/transcript.txt` is the run the
slides came from. Your commit hashes and dates will differ. The verdicts won't.

## Agentic Trust Framework

This maps to the Agentic Trust Framework (ATF), published by the Cloud Security
Alliance in February 2026 under CC BY 4.0.

| ATF element | In the file |
|---|---|
| Identity Management | `owner`, `identity.runs_as` |
| Data Governance | `data_classes` and the derived risk tier |
| Segmentation | `tool_scope`, `bindings` |
| Behavioral Monitoring | The gateway's log of each call, joined to the registry row |
| Incident Response | Revert the merge to demote it. Delete the file to stop it. |

## License

Apache License 2.0. See `LICENSE`.

## Author

Josh Woodruff, MassiveScale.AI. [massivescale.ai](https://massivescale.ai)
