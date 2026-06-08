#!/usr/bin/env bash
# trunk: bash, prints the current repo's default branch.
. "$(dirname "$0")/lib.sh"

# Inside a git repo (this one): prints a non-empty branch; --remote qualifies it.
branch=$("$ROOT/trunk/trunk")
assert_ok "prints a non-empty branch" test -n "$branch"
rem=$("$ROOT/trunk/trunk" --remote)
assert_contains "--remote qualifies with origin/" "$rem" "origin/$branch"

# Outside a git repo: exit 1 with a clear message.
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
if out=$(cd "$work" && "$ROOT/trunk/trunk" 2>&1); then rc=0; else rc=$?; fi
assert_eq "exits 1 outside a git repo" "1" "$rc"
assert_contains "explains not-a-repo" "$out" "not in a git repo"

# Unknown argument: exit 2.
assert_fails "rejects an unknown arg" "$ROOT/trunk/trunk" --bogus

finish
