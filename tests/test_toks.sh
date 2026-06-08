#!/usr/bin/env bash
# toks: uv PEP-723 script (tiktoken). -h is offline; counting needs the
# encoding download (network), so that part is best-effort.
. "$(dirname "$0")/lib.sh"
need uv "toks"

help=$("$ROOT/toks/toks" -h 2>&1) || true
assert_contains "help mentions tiktoken" "$help" "tiktoken"

count=$(printf 'hello world' | "$ROOT/toks/toks" 2>/dev/null) || true
if printf '%s' "$count" | grep -qE '^[0-9]+$'; then
  ok "returns an integer token count ($count)"
else
  skip "token count (needs network for tiktoken encoding)"
fi

finish
