#!/usr/bin/env bash
# chatgpt2md: uv PEP-723 script (beautifulsoup4). Convert a captured DOM fixture.
. "$(dirname "$0")/lib.sh"
need uv "chatgpt2md"

out=$("$ROOT/chatgpt2md/chatgpt2md" "$(dirname "$0")/fixtures/chatgpt-sample.html" 2>/dev/null) || true
assert_contains "emits a User turn" "$out" "## User"
assert_contains "keeps multi-paragraph user text" "$out" "Show the reasoning briefly."
assert_contains "emits a ChatGPT turn" "$out" "## ChatGPT"
assert_contains "preserves bold" "$out" "**4**"
assert_contains "preserves list item" "$out" "- It is simple arithmetic."
assert_contains "preserves links" "$out" "[Example](https://example.com/proof)"
assert_contains "preserves KaTeX source" "$out" "\$2 + 2 = 4\$"
assert_contains "preserves CodeMirror code language" "$out" '```python'
assert_contains "preserves CodeMirror line breaks" "$out" "# 4"
assert_contains "preserves tables" "$out" "| Expression | Result |"
assert_not_contains "drops sidebar chat titles" "$out" "Sidebar chat title to ignore"
assert_not_contains "drops hidden reasoning" "$out" "Hidden reasoning to ignore"
assert_not_contains "drops action buttons" "$out" "Retry"
assert_not_contains "drops rendered KaTeX duplicate" "$out" "rendered duplicate"
assert_ok "bin symlink exists" test -L "$ROOT/bin/chatgpt2md"

finish
