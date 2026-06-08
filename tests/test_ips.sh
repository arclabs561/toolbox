#!/usr/bin/env bash
# ips: uv PEP-723 script (httpx, psutil). -h is offline and validates that the
# deps resolve and the script parses.
. "$(dirname "$0")/lib.sh"
need uv "ips"

help=$("$ROOT/ips/ips" -h 2>&1) || true
assert_contains "help mentions public IP" "$help" "public"
assert_contains "help lists -v geo flag" "$help" "geo"

finish
