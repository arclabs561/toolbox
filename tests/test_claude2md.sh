#!/usr/bin/env bash
# claude2md: uv PEP-723 script (beautifulsoup4). Convert a fixture conversation.
. "$(dirname "$0")/lib.sh"
need uv "claude2md"

out=$("$ROOT/claude2md/claude2md" "$(dirname "$0")/fixtures/claude-sample.html" 2>/dev/null) || true
assert_contains "emits a User turn" "$out" "## User"
assert_contains "keeps multi-line user text" "$out" "and why?"
assert_contains "emits a Claude turn" "$out" "## Claude"
assert_contains "preserves bold" "$out" "**4**"
assert_contains "preserves list item" "$out" "- simple arithmetic"
assert_contains "citation chip becomes a link" "$out" "[Example](https://example.com/proof)"
assert_contains "preserves fenced code" "$out" '```python'
assert_not_contains "drops sidebar chat titles" "$out" "Sidebar chat title to ignore"
assert_not_contains "drops thinking summaries" "$out" "Pondered arithmetic briefly"
assert_not_contains "drops action-bar buttons" "$out" "Retry"

finish
