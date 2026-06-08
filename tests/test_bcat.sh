#!/usr/bin/env bash
# bcat: bash, no deps. Stub out the browser launcher so tests don't open tabs.
. "$(dirname "$0")/lib.sh"

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

bindir="$work/bin"
mkdir -p "$bindir"
# Stub `open` (macOS) and `xdg-open` (Linux): record the path, launch nothing.
cat > "$bindir/open" <<EOF
#!/bin/sh
printf '%s' "\$1" > "$work/captured"
EOF
cp "$bindir/open" "$bindir/xdg-open"
chmod +x "$bindir/open" "$bindir/xdg-open"

export PATH="$bindir:$PATH"
export TMPDIR="$work"

printf '<h1>hi</h1>' | "$ROOT/bcat/bcat"
captured=$(cat "$work/captured" 2>/dev/null || true)
assert_contains "writes under \$TMPDIR/bcat" "$captured" "$work/bcat/"
assert_ok "opened file exists" test -f "$captured"
assert_eq "file holds piped content" "<h1>hi</h1>" "$(cat "$captured" 2>/dev/null || true)"

printf '{"a":1}' | "$ROOT/bcat/bcat" -t json
captured=$(cat "$work/captured")
assert_contains "-t sets extension" "$captured" ".json"

# Regression: old bcat did `mktemp -d` per call, leaking a subdir each time.
subdirs=$(find "$work/bcat" -mindepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')
assert_eq "no per-call subdirs leaked" "0" "$subdirs"

finish
