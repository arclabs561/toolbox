#!/usr/bin/env bash
# Browser-backed tools (webshot, check-math). Heavy deps (Playwright Chromium,
# and go-grip for check-math), so gated behind TOOLBOX_BROWSER=1.
# shellcheck disable=SC2016  # single-quoted markdown holds literal $...$ math delimiters
. "$(dirname "$0")/lib.sh"

if [ "${TOOLBOX_BROWSER:-0}" != "1" ]; then
  skip "webshot/check-math (set TOOLBOX_BROWSER=1 to run)"
  finish
  exit 0
fi
need uv "browser tools"

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

html="$work/page.html"
cat > "$html" <<'EOF'
<!doctype html><html><head><title>Hi There</title>
<meta name="description" content="a test page"></head>
<body><h1>Heading</h1><p>body</p></body></html>
EOF

# -- webshot shot (local file:// -> no network, 'load' wait is fast) --
if out=$("$ROOT/webshot/webshot" shot "$html" -o "$work/out.png" 2>&1); then
  assert_ok "webshot writes a non-empty png" test -s "$work/out.png"
else
  fail "webshot shot ran" "$out"
fi

# -- webshot meta --
meta=$("$ROOT/webshot/webshot" meta "$html" --json 2>/dev/null) || true
assert_contains "meta extracts title" "$meta" "Hi There"
assert_contains "meta extracts description" "$meta" "a test page"

# -- check-math (needs go-grip) --
if command -v go-grip >/dev/null 2>&1; then
  good="$work/good.md"
  printf '# Math\n\nInline $a^2 + b^2 = c^2$ works.\n' > "$good"
  assert_ok "check-math passes clean math" "$ROOT/check-math/check-math" "$good"

  bad="$work/bad.md"
  printf '# Math\n\nUses $\\operatorname{rank}(A)$ which GitHub blocks.\n' > "$bad"
  assert_fails "check-math flags blocked macro" "$ROOT/check-math/check-math" "$bad"
else
  skip "check-math (requires go-grip on PATH)"
fi

finish
