#!/usr/bin/env bash
# gemini2md: uv PEP-723 script (beautifulsoup4). Convert a fixture conversation.
. "$(dirname "$0")/lib.sh"
need uv "gemini2md"

out=$("$ROOT/gemini2md/gemini2md" "$(dirname "$0")/fixtures/gemini-sample.html" 2>/dev/null) || true
assert_contains "emits a User turn" "$out" "## User"
assert_contains "keeps user text" "$out" "What is 2+2?"
assert_contains "emits a Gemini turn" "$out" "## Gemini"
assert_contains "preserves bold" "$out" "**4**"
assert_contains "preserves list item" "$out" "- simple arithmetic"

finish
