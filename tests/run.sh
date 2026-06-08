#!/usr/bin/env bash
# Run every tests/test_*.sh. Exit nonzero if any test file reports a failure.
#
#   tests/run.sh                 # core + uv tests (skips browser tools)
#   TOOLBOX_BROWSER=1 tests/run.sh   # also run webshot/check-math
set -uo pipefail

here="$(cd "$(dirname "$0")" && pwd)"
failed=0
total=0

for f in "$here"/test_*.sh; do
  [ -e "$f" ] || continue
  total=$((total + 1))
  printf '\n=== %s ===\n' "${f##*/}"
  if ! bash "$f"; then
    failed=$((failed + 1))
  fi
done

printf '\n========================================\n'
if [ "$failed" -eq 0 ]; then
  printf 'ALL %d test files passed\n' "$total"
else
  printf '%d/%d test files FAILED\n' "$failed" "$total"
fi
exit "$failed"
