#!/usr/bin/env bash
# Replay the story from the talk, step by step, and check every verdict.
#
# Usage: ./demo.sh
#
# It runs in a throwaway copy with its own Git history, so your files stay as
# they are. Each pull request is a branch plus a --no-ff merge, the way GitHub
# merges one. It needs python3 with requirements.txt installed. Set PYTHON to
# use a different interpreter. Works with the bash 3.2 that ships with macOS.
#
# The run ends with DEMO OK, or names the step that broke and exits 1.

set -u

ROOT=$(cd "$(dirname "$0")" && pwd)
PY=${PYTHON:-python3}
STEP=setup
OUT=""
RC=0

fail() {
  echo
  echo "DEMO FAILED at step $STEP: $1"
  exit 1
}

step() {
  STEP=$1
  if [ "$1" != 1 ]; then echo; fi
  echo "### $1. $2"
}

# Print the command, run it, and keep its output in OUT and its exit status in RC.
run() {
  echo
  echo "\$ $*"
  OUT=$("$@" 2>&1)
  RC=$?
  if [ -n "$OUT" ]; then echo "$OUT"; fi
  if [ "$RC" -ne 0 ]; then echo "[exit $RC]"; fi
}

# Each commit gets its own fixed time, a minute after the last one. History
# sorts the same way on every run, and the hashes come out the same too.
CLOCK=1791378000
tick() {
  CLOCK=$((CLOCK + 60))
  export GIT_AUTHOR_DATE="$CLOCK -0400" GIT_COMMITTER_DATE="$CLOCK -0400"
}

# Git steps the slides don't show: commits, branches, merges.
quiet() {
  tick
  "$@" >/dev/null 2>&1 || fail "'$*' failed"
}

expect_rc() {
  [ "$RC" -eq "$1" ] || fail "expected exit $1, got $RC"
}

expect_has() {
  case "$OUT" in
    *"$1"*) ;;
    *) fail "expected the output to contain: $1" ;;
  esac
}

expect_out() {
  [ "$OUT" = "$1" ] || fail "the output didn't match. Expected:
$1"
}

# The lint rules that fired, as a space-separated list.
expect_rules() {
  got=$(echo "$OUT" | sed -n 's/^  \(P[0-9][0-9][0-9]\)  .*/\1/p' | sort -u | tr '\n' ' ')
  [ "$got" = "$1 " ] || fail "expected lint rules $1, got ${got:-none}"
}

"$PY" -c 'import yaml, jsonschema, casbin' 2>/dev/null ||
  fail "$PY can't load the packages it needs. Run: pip install -r requirements.txt"
command -v git >/dev/null 2>&1 || fail "git isn't installed"

WORK=$(mktemp -d "${TMPDIR:-/tmp}/persona-demo.XXXXXX") || fail "couldn't make a temp folder"
trap 'rm -rf "$WORK"' EXIT

# Copy the repo. Keep the finished persona to one side, then start with no personas.
REPO=$WORK/repo
mkdir "$REPO"
cp -R "$ROOT/." "$REPO/"
rm -rf "$REPO/.git" "$REPO/out"
find "$REPO" -name __pycache__ -prune -exec rm -rf {} +
cp "$REPO/personas/soc-triage.yaml" "$WORK/fixed.yaml"
rm -f "$REPO"/personas/*.yaml
cd "$REPO" || fail "couldn't open the temp copy"

export GIT_AUTHOR_NAME="Demo" GIT_AUTHOR_EMAIL="demo@example.com"
export GIT_COMMITTER_NAME="Demo" GIT_COMMITTER_EMAIL="demo@example.com"
quiet git init -q
quiet git symbolic-ref HEAD refs/heads/main
quiet git config commit.gpgsign false
quiet git config core.hooksPath .no-hooks
quiet git add -A
quiet git commit -q -m "Catalog, schema, lint, compile, check"

ALL_DENY="DENY   soc-triage          soc-tier1  prod  siem.search        call
DENY   soc-triage          soc-tier1  prod  case.add_note      call
DENY   soc-triage          soc-tier1  prod  edr.isolate_host   call
DENY   soc-triage          soc-tier1  prod  edr.isolate_host   call_approved
DENY   soc-triage          soc-tier1  prod  idp.disable_user   call_approved
DENY   soc-triage          payments   prod  siem.search        call
DENY   unregistered-agent  soc-tier1  prod  siem.search        call"

step 1 "Before anything is merged: the gateway has no policy"
run "$PY" tools/check.py
expect_rc 0
expect_out "no compiled policy. Nothing has been merged, so every call is denied."

step 2 "Pull request opened: the persona as found. Lint runs."
quiet git checkout -q -b add-soc-triage
cp demo/as-found/soc-triage.yaml personas/soc-triage.yaml
quiet git add personas/soc-triage.yaml
quiet git commit -q -m "Add soc-triage persona, written the way we found it"
run "$PY" tools/lint.py
expect_rc 1
expect_rules "P004 P006"
expect_has "Merge is blocked."

step 3 "The fix"
cp "$WORK/fixed.yaml" personas/soc-triage.yaml
run git --no-pager diff --no-color -U1
expect_has "-  runs_as: user"
expect_has "+  runs_as: agent"
expect_has "-risk_tier: 1"
run "$PY" tools/lint.py
expect_rc 0
expect_out "PASS  soc-triage.yaml"
quiet git commit -q -a -m "Give the agent its own identity. Let lint derive the tier."

step 4 "Merge. The compile job runs."
quiet git checkout -q main
quiet git merge -q --no-ff -m "Merge pull request #1: add soc-triage persona" add-soc-triage
run "$PY" tools/compile.py
expect_rc 0
expect_has "out/registry/         1 row(s)"
expect_has "out/gateway/policy.csv  7 rule(s), deny by default"
run cat out/registry/soc-triage.json
expect_has '"runs_as": "agent"'
expect_has '"risk_tier": 3'
run cat out/gateway/policy.csv
expect_has "p, soc-triage, soc-tier1, prod, edr.isolate_host, call_approved, allow"
expect_has "p, soc-triage, *, *, idp.disable_user, *, deny"
run cat out/gateway/model.conf
expect_has "e = some(where (p.eft == allow)) && !some(where (p.eft == deny))"

step 5 "Same calls as step 1, asked of the compiled policy"
run "$PY" tools/check.py
expect_rc 0
expect_out "ALLOW  soc-triage          soc-tier1  prod  siem.search        call
ALLOW  soc-triage          soc-tier1  prod  case.add_note      call
DENY   soc-triage          soc-tier1  prod  edr.isolate_host   call
ALLOW  soc-triage          soc-tier1  prod  edr.isolate_host   call_approved
DENY   soc-triage          soc-tier1  prod  idp.disable_user   call_approved
DENY   soc-triage          payments   prod  siem.search        call
DENY   unregistered-agent  soc-tier1  prod  siem.search        call"

step 6 "Promotion, first try: move isolate_host to 'alone' and nothing else"
quiet git checkout -q -b promote-soc-triage
cp demo/promotion-first-try/soc-triage.yaml personas/soc-triage.yaml
run "$PY" tools/lint.py
expect_rc 1
expect_rules "P009"
expect_has "A junior can't run it alone."

step 7 "Promotion as a pull request"
sed 's/^autonomy_level: junior$/autonomy_level: senior/' \
  demo/promotion-first-try/soc-triage.yaml > personas/soc-triage.yaml
run git --no-pager diff --no-color -U1
expect_has "+    - edr.isolate_host"
expect_has "+autonomy_level: senior"
run "$PY" tools/lint.py
expect_rc 0
expect_out "PASS  soc-triage.yaml"
quiet git commit -q -a -m "Promote soc-triage to senior: isolate_host runs alone"
quiet git checkout -q main
quiet git merge -q --no-ff -m "Merge pull request #2: promote soc-triage to senior" promote-soc-triage
run "$PY" tools/compile.py
expect_rc 0
expect_has "7 rule(s), deny by default"
run "$PY" tools/check.py soc-triage soc-tier1 prod edr.isolate_host call
expect_out "ALLOW  soc-triage          soc-tier1  prod  edr.isolate_host   call"

step 8 "Demotion: revert the promotion merge"
tick
run git revert --no-edit -m 1 HEAD
expect_rc 0
expect_has 'Revert "Merge pull request #2: promote soc-triage to senior"'
run "$PY" tools/compile.py
expect_rc 0
expect_has "7 rule(s), deny by default"
run "$PY" tools/check.py soc-triage soc-tier1 prod edr.isolate_host call
expect_out "DENY   soc-triage          soc-tier1  prod  edr.isolate_host   call"
run "$PY" tools/check.py soc-triage soc-tier1 prod edr.isolate_host call_approved
expect_out "ALLOW  soc-triage          soc-tier1  prod  edr.isolate_host   call_approved"

step 9 "Off switch: delete the file, merge, recompile"
quiet git checkout -q -b retire-soc-triage
quiet git rm -q personas/soc-triage.yaml
quiet git commit -q -m "Retire soc-triage"
quiet git checkout -q main
quiet git merge -q --no-ff -m "Merge pull request #3: retire soc-triage" retire-soc-triage
run "$PY" tools/compile.py
expect_rc 0
expect_has "compiled 0 persona(s)"
expect_has "out/registry/         0 row(s)"
expect_has "out/gateway/policy.csv  0 rule(s), deny by default"
run "$PY" tools/check.py
expect_rc 0
expect_out "$ALL_DENY"

STEP=History
echo
echo "### History"
run git --no-pager log --oneline --no-color
OUT=$(git log --format=%s)
expect_out 'Merge pull request #3: retire soc-triage
Retire soc-triage
Revert "Merge pull request #2: promote soc-triage to senior"
Merge pull request #2: promote soc-triage to senior
Promote soc-triage to senior: isolate_host runs alone
Merge pull request #1: add soc-triage persona
Give the agent its own identity. Let lint derive the tier.
Add soc-triage persona, written the way we found it
Catalog, schema, lint, compile, check'

echo
echo "DEMO OK"
