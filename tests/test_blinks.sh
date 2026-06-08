#!/usr/bin/env bash
# blinks: bash, no deps. Verify it reports broken symlinks and only those.
. "$(dirname "$0")/lib.sh"

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

ln -s /no/such/target "$work/broken-link"
ln -s "$ROOT/README.md" "$work/good-link" # valid target

out=$(cd "$work" && "$ROOT/blinks/blinks")
assert_contains "reports the broken link" "$out" "broken-link"
assert_not_contains "ignores the valid link" "$out" "good-link"

empty=$(mktemp -d)
out=$(cd "$empty" && "$ROOT/blinks/blinks")
assert_contains "clean dir reports none" "$out" "no broken symlinks"
rm -rf "$empty"

finish
