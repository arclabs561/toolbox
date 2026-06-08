# shellcheck shell=bash
# Tiny assert library for the toolbox test suite. Source it from a test_*.sh
# file; call assertions; end with `finish`.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export ROOT
PASS=0
FAIL=0
SKIP=0

_green() { printf '\033[32m%s\033[0m' "$1"; }
_red() { printf '\033[31m%s\033[0m' "$1"; }
_yellow() { printf '\033[33m%s\033[0m' "$1"; }

ok() {
  PASS=$((PASS + 1))
  printf '  %s %s\n' "$(_green ok)" "$1"
}

fail() {
  FAIL=$((FAIL + 1))
  printf '  %s %s\n' "$(_red FAIL)" "$1"
  [ -n "${2:-}" ] && printf '       %s\n' "$2"
  return 0
}

skip() {
  SKIP=$((SKIP + 1))
  printf '  %s %s\n' "$(_yellow skip)" "$1"
}

assert_eq() { # desc expected actual
  if [ "$2" = "$3" ]; then ok "$1"; else fail "$1" "expected [$2] got [$3]"; fi
}

assert_contains() { # desc haystack needle
  case "$2" in
    *"$3"*) ok "$1" ;;
    *) fail "$1" "output missing substring [$3]" ;;
  esac
}

assert_not_contains() { # desc haystack needle
  case "$2" in
    *"$3"*) fail "$1" "output unexpectedly contains [$3]" ;;
    *) ok "$1" ;;
  esac
}

assert_ok() { # desc cmd...
  local desc="$1"
  shift
  if "$@" >/dev/null 2>&1; then ok "$desc"; else fail "$desc" "command failed: $*"; fi
}

assert_fails() { # desc cmd...   (expects nonzero exit)
  local desc="$1"
  shift
  if "$@" >/dev/null 2>&1; then fail "$desc" "command unexpectedly succeeded: $*"; else ok "$desc"; fi
}

# Require a command on PATH or skip the rest of the file cleanly.
need() { # cmd-name human-reason
  if ! command -v "$1" >/dev/null 2>&1; then
    skip "$2 (requires '$1' on PATH)"
    finish
    exit 0
  fi
}

finish() {
  printf -- '--- %s: %d passed, %d failed, %d skipped ---\n' \
    "${0##*/}" "$PASS" "$FAIL" "$SKIP"
  [ "$FAIL" -eq 0 ]
}
