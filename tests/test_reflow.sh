#!/usr/bin/env bash
# reflow: pure-python3 tool, no deps -- exercised directly.
# shellcheck disable=SC2016  # single-quoted test inputs hold literal markdown (backticks, etc.)
. "$(dirname "$0")/lib.sh"

reflow() { python3 "$ROOT/reflow/reflow" "$@"; }

# 1. long paragraph wraps to width
para="alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi"
out=$(printf '%s\n' "$para" | reflow -w 20)
maxlen=$(printf '%s\n' "$out" | awk '{ if (length > m) m = length } END { print m }')
if [ "$maxlen" -le 20 ]; then ok "wraps within width 20 (max=$maxlen)"; else fail "wraps within width" "max line=$maxlen > 20"; fi
# word count is invariant under wrapping (no word dropped or split)
nin=$(printf '%s' "$para" | wc -w | tr -d ' ')
nout=$(printf '%s' "$out" | wc -w | tr -d ' ')
assert_eq "no words lost in wrap" "$nin" "$nout"

# 2. blank line between paragraphs preserved (paragraphs stay separate)
out=$(printf 'first para here\n\nsecond para here\n' | reflow -w 80)
assert_contains "paragraph break preserved" "$out" "$(printf 'first para here\n\nsecond para here')"

# 3. fenced code block content untouched
codeln='x=1   # an intentionally long comment line that exceeds the wrap width easily'
out=$(printf '```python\n%s\n```\n' "$codeln" | reflow -w 20)
assert_contains "code line untouched" "$out" "$codeln"
assert_contains "opening fence kept" "$out" '```python'

# 4. heading verbatim
out=$(printf '# A heading that is rather long and would otherwise wrap at width\n' | reflow -w 20)
assert_contains "heading not wrapped" "$out" "# A heading that is rather long and would otherwise wrap at width"

# 5. list items not merged
out=$(printf -- '- item one\n- item two\n' | reflow -w 80)
lines=$(printf '%s\n' "$out" | grep -c '^- item')
assert_eq "two list items stay two lines" "2" "$lines"

# 6. blockquote verbatim
out=$(printf '> quoted line that is quite long and should not be reflowed at all here\n' | reflow -w 20)
assert_contains "blockquote verbatim" "$out" "> quoted line that is quite long and should not be reflowed at all here"

# 7. long URL never broken
url="https://example.com/really/long/path/segment/that/exceeds/the/width/limit"
out=$(printf 'see %s now\n' "$url" | reflow -w 30)
assert_contains "url intact" "$out" "$url"

# 8. tilde fence handled like backtick fence
out=$(printf '~~~\nlong tilde fenced code line that should not be wrapped at all here ok\n~~~\n' | reflow -w 20)
assert_contains "tilde fence content untouched" "$out" "long tilde fenced code line that should not be wrapped at all here ok"

# 9. reads from a file argument
tmp=$(mktemp)
printf 'one two three four five six seven eight nine ten eleven twelve\n' > "$tmp"
out=$(reflow "$tmp" -w 20)
maxlen=$(printf '%s\n' "$out" | awk '{ if (length > m) m = length } END { print m }')
if [ "$maxlen" -le 20 ]; then ok "file arg input wraps"; else fail "file arg input wraps" "max=$maxlen"; fi
rm -f "$tmp"

# 10. idempotent: reflow(reflow(x)) == reflow(x)
src=$(printf '# H\n\nsome prose words that wrap around a small width boundary here yes\n\n- a\n- b\n')
once=$(printf '%s\n' "$src" | reflow -w 25)
twice=$(printf '%s\n' "$once" | reflow -w 25)
assert_eq "idempotent at width 25" "$once" "$twice"

# 11. invalid width rejected
assert_fails "rejects --col-width 0" reflow -w 0 </dev/null

# 12. empty input does not crash
assert_ok "empty input ok" sh -c "printf '' | python3 '$ROOT/reflow/reflow'"

# 13. YAML front matter is preserved verbatim (key: value lines not merged)
out=$(printf -- '---\ntitle: My Post\ndate: 2020\n---\n\nbody words that wrap here\n' | reflow -w 30)
assert_contains "front matter title line intact" "$out" "$(printf 'title: My Post\ndate: 2020')"

# 14. a 4-backtick fence holds 3-backtick lines without leaking content to prose
inner="a very long supposed-code line that certainly exceeds thirty columns wide"
out=$(printf '%s\n' '````' '```' "$inner" '```' '````' | reflow -w 30)
assert_contains "outer fence keeps inner code verbatim" "$out" "$inner"

finish
