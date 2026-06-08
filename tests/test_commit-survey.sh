#!/usr/bin/env bash
# commit-survey: uv PEP-723 script. Survey this repo and assert structured output.
. "$(dirname "$0")/lib.sh"
need uv "commit-survey"

out=$("$ROOT/commit-survey/commit-survey" -n 50 2>/dev/null) || true
assert_contains "reports the repo path" "$out" "repo:"
assert_contains "reports the trunk" "$out" "trunk:"
assert_contains "reports the commit sample" "$out" "commits sampled:"

# A non-git path exits 1.
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
if "$ROOT/commit-survey/commit-survey" "$work" >/dev/null 2>&1; then rc=0; else rc=$?; fi
assert_eq "exits 1 on a non-git path" "1" "$rc"

finish
