#!/usr/bin/env bash
# perplexity-export: uv PEP-723 script. CLI smoke only; browser/auth paths are
# intentionally manual because they depend on Perplexity account state.
# shellcheck source=tests/lib.sh
. "$(dirname "$0")/lib.sh"
need uv "perplexity-export"

out=$("$ROOT/perplexity-export/perplexity-export" --help 2>/dev/null) || true
assert_contains "top-level help names auth" "$out" "auth"
assert_contains "top-level help names verify" "$out" "verify"
assert_contains "top-level help names start" "$out" "start"
assert_contains "top-level help names export" "$out" "export"

out=$("$ROOT/perplexity-export/perplexity-export" auth --help 2>/dev/null) || true
assert_contains "auth help exposes op item" "$out" "--op-item"

out=$("$ROOT/perplexity-export/perplexity-export" verify --help 2>/dev/null) || true
assert_contains "verify help exposes headed opt-in" "$out" "--headed"

out=$("$ROOT/perplexity-export/perplexity-export" export --help 2>/dev/null) || true
assert_contains "export help exposes asset toggle" "$out" "--no-assets"
assert_contains "export help exposes implied daemon ttl" "$out" "--ttl"

assert_ok "bin symlink exists" test -L "$ROOT/bin/perplexity-export"

out=$(
  uv run --quiet --with playwright python -c '
import runpy
import sys
from types import SimpleNamespace

module = runpy.run_path(sys.argv[1], run_name="perplexity_export_test")
args = module["build_parser"]().parse_args(["ask", "hello", "--export"])
print("parser", args.export, args.prompt == ["hello"])
print("real-origin", module["is_perplexity_url"]("https://www.perplexity.ai/search/example"))
print("lookalike-origin", module["is_perplexity_url"]("https://www.perplexity.ai.evil.example/"))

requests = []
command_globals = module["export_command"].__globals__
command_globals["ensure_daemon"] = lambda **_kwargs: None

def send_request(request):
    requests.append(request["action"])
    return {"chats": []}

command_globals["send_request"] = send_request
module["export_command"](
    SimpleNamespace(
        ttl=1,
        wait=0,
        headed=False,
        urls=[],
        all=True,
        interactive=False,
        limit=10,
    )
)
print("empty-selection-requests", requests)
' "$ROOT/perplexity-export/perplexity-export" 2>/dev/null
) || true
assert_contains "ask options remain options after the prompt" "$out" "parser True True"
assert_contains "accepts the Perplexity origin" "$out" "real-origin True"
assert_contains "rejects a lookalike hostname" "$out" "lookalike-origin False"
assert_contains "empty discovery does not trigger export" "$out" "empty-selection-requests ['explore']"

tmpdir=$(mktemp -d)
sleep 30 &
child_pid=$!
cleanup() {
  kill "$child_pid" 2>/dev/null || true
  wait "$child_pid" 2>/dev/null || true
  rm -rf "$tmpdir"
}
trap cleanup EXIT

mkdir -p "$tmpdir/state/perplexity-export"
printf '%s\n' "$child_pid" >"$tmpdir/state/perplexity-export/daemon.pid"
out=$(
  XDG_STATE_HOME="$tmpdir/state" \
    XDG_CACHE_HOME="$tmpdir/cache" \
    XDG_DATA_HOME="$tmpdir/data" \
    "$ROOT/perplexity-export/perplexity-export" stop 2>/dev/null
) || true
assert_contains "stop reports a stale pid file" "$out" "stale pid file"
assert_ok "stop does not signal an unrelated live pid" kill -0 "$child_pid"

finish
