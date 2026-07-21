#!/usr/bin/env bash
# ips: uv PEP-723 script (httpx, psutil). -h is offline and validates that the
# deps resolve and the script parses.
. "$(dirname "$0")/lib.sh"
need uv "ips"

help=$("$ROOT/ips/ips" -h 2>&1) || true
assert_contains "help mentions public IP" "$help" "public"
assert_contains "help lists -v geo flag" "$help" "geo"
assert_contains "help explains network path" "$help" "active network path"

link=$("$ROOT/ips/ips" link --json 2>&1)
assert_contains "link diagnostics emit JSON host" "$link" '"host"'
assert_contains "link diagnostics identify mode" "$link" '"mode": "link"'
assert_contains "link diagnostics include route data" "$link" '"gateway"'
assert_not_contains "link addresses do not claim each address is default" "$link" '"default"'

peers=$("$ROOT/ips/ips" peers --json 2>&1)
assert_contains "peer view reports cache status" "$peers" '"status"'
assert_contains "peer view identifies peer list" "$peers" '"peers"'

speed_help=$("$ROOT/ips/ips" -h 2>&1)
assert_contains "help names speed mode" "$speed_help" "speed"

logic=$(
  uv run --with httpx --with psutil python "$ROOT/tests/test_ips_logic.py" "$ROOT/ips/ips" 2>&1
)
assert_contains "offline metric checks pass" "$logic" "ips logic: ok"

finish
