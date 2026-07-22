#!/usr/bin/env bash
# pinglet: uv PEP-723 script (httpx, psutil). -h is offline and validates that the
# deps resolve and the script parses.
. "$(dirname "$0")/lib.sh"
need uv "pinglet"

help=$("$ROOT/pinglet/pinglet" -h 2>&1) || true
assert_contains "help mentions public IP" "$help" "public"
assert_contains "help lists -v geo flag" "$help" "geo"
assert_contains "help explains network path" "$help" "active network path"

link=$("$ROOT/pinglet/pinglet" link --json 2>&1)
assert_contains "link diagnostics emit JSON host" "$link" '"host"'
assert_contains "link diagnostics identify mode" "$link" '"mode": "link"'
assert_contains "link diagnostics include route data" "$link" '"gateway"'
assert_not_contains "link addresses do not claim each address is default" "$link" '"default"'

peers=$("$ROOT/pinglet/pinglet" peers --json 2>&1)
assert_contains "peer view reports cache status" "$peers" '"status"'
assert_contains "peer view identifies peer list" "$peers" '"peers"'

speed_help=$("$ROOT/pinglet/pinglet" -h 2>&1)
assert_contains "help names speed mode" "$speed_help" "speed"

logic=$(
  uv run --with httpx --with psutil python "$ROOT/tests/test_pinglet_logic.py" "$ROOT/pinglet/pinglet" 2>&1
)
assert_contains "offline metric checks pass" "$logic" "pinglet logic: ok"

adapters=$(
  uv run --with httpx --with psutil python "$ROOT/tests/test_pinglet_adapters.py" "$ROOT/pinglet" 2>&1
)
assert_contains "offline adapter checks pass" "$adapters" "pinglet adapters: ok"

speed=$(
  uv run --with httpx --with psutil python "$ROOT/tests/test_pinglet_speed.py" "$ROOT/pinglet/pinglet" 2>&1
)
assert_contains "offline speed envelope checks pass" "$speed" "pinglet speed: ok"

finish
