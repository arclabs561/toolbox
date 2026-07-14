#!/usr/bin/env bash
# gh-dependabot: use a fake gh binary to test pagination, ordering, and failure handling.
. "$(dirname "$0")/lib.sh"
need uv "gh-dependabot"
need python3 "gh-dependabot JSON assertions"
assert_ok "bin symlink exists" test -L "$ROOT/bin/gh-dependabot"

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
mkdir -p "$work/bin"

cat >"$work/bin/gh" <<'FAKE_GH'
#!/usr/bin/env bash
set -u

if [ "${1:-}" = "api" ] && [ "${2:-}" = "user" ]; then
  printf 'tester\n'
  exit 0
fi

if [ "${1:-}" = "repo" ] && [ "${2:-}" = "list" ]; then
  printf '%s\n' '[{"nameWithOwner":"tester/zeta"},{"nameWithOwner":"tester/alpha"}]'
  exit 0
fi

if [ "${1:-}" != "api" ]; then
  printf 'unexpected gh invocation: %s\n' "$*" >&2
  exit 64
fi

case "${GH_DEPENDABOT_SCENARIO:-alerts}:${2:-}" in
  alerts:repos/tester/alpha/dependabot/alerts)
    cat <<'JSON'
[[{"number":7,"dependency":{"package":{"ecosystem":"pip","name":"later"},"manifest_path":"uv.lock","scope":"development"},"security_advisory":{"ghsa_id":"GHSA-LATER","cve_id":null,"summary":"later issue","severity":"low"},"security_vulnerability":{"first_patched_version":null,"vulnerable_version_range":"< 2"},"html_url":"https://example.test/alpha/7"}],[{"number":2,"dependency":{"package":{"ecosystem":"pip","name":"first"},"manifest_path":"uv.lock","scope":"runtime"},"security_advisory":{"ghsa_id":"GHSA-FIRST","cve_id":"CVE-TEST","summary":"first issue","severity":"high"},"security_vulnerability":{"first_patched_version":{"identifier":"1.2.3"},"vulnerable_version_range":"< 1.2.3"},"html_url":"https://example.test/alpha/2"}]]
JSON
    ;;
  alerts:repos/tester/zeta/dependabot/alerts | none:repos/tester/alpha/dependabot/alerts | none:repos/tester/zeta/dependabot/alerts | error:repos/tester/alpha/dependabot/alerts)
    printf '[[]]\n'
    ;;
  error:repos/tester/zeta/dependabot/alerts)
    printf 'simulated API failure\n' >&2
    exit 1
    ;;
  *)
    printf 'unexpected gh invocation: %s\n' "$*" >&2
    exit 64
    ;;
esac
FAKE_GH
chmod +x "$work/bin/gh"

run_tool() {
  local scenario="$1"
  shift
  if OUTPUT=$(env PATH="$work/bin:$PATH" GH_DEPENDABOT_SCENARIO="$scenario" \
    "$ROOT/gh-dependabot/gh-dependabot" "$@" 2>"$work/stderr"); then
    RC=0
  else
    RC=$?
  fi
}

run_tool alerts
assert_eq "alerts produce exit 1" "1" "$RC"
expected=$'REPOSITORY\tALERT\tSEVERITY\tDEPENDENCY\tMANIFEST\tADVISORY\tPATCHED\tSUMMARY\tURL\ntester/alpha\t#2\thigh\tpip/first\tuv.lock\tGHSA-FIRST\t1.2.3\tfirst issue\thttps://example.test/alpha/2\ntester/alpha\t#7\tlow\tpip/later\tuv.lock\tGHSA-LATER\tunpatched\tlater issue\thttps://example.test/alpha/7\n2 repositories scanned; 2 open alerts; 0 errors'
assert_eq "flattens pages and sorts alerts" "$expected" "$OUTPUT"

run_tool alerts --json
assert_eq "JSON alerts produce exit 1" "1" "$RC"
json_check=$(JSON_OUTPUT="$OUTPUT" python3 -c '
import json
import os

data = json.loads(os.environ["JSON_OUTPUT"])
assert data["owner"] == "tester"
assert data["repositories_requested"] == 2
assert data["repositories_scanned"] == 2
assert data["open_alerts"] == 2
assert [alert["number"] for alert in data["alerts"]] == [2, 7]
assert data["errors"] == []
print("ok")
')
assert_eq "emits valid structured JSON" "ok" "$json_check"

run_tool none
assert_eq "no alerts produce exit 0" "0" "$RC"
assert_eq "reports a complete zero" "2 repositories scanned; 0 open alerts; 0 errors" "$OUTPUT"

run_tool error
assert_eq "an API failure produces exit 2" "2" "$RC"
assert_contains "marks a partial scan incomplete" "$OUTPUT" "INCOMPLETE:"
assert_contains "reports one error" "$OUTPUT" "1 errors"
stderr=$(<"$work/stderr")
assert_contains "names the failed repository" "$stderr" "tester/zeta"
assert_not_contains "does not claim a clean scan" "$OUTPUT" "0 open alerts; 0 errors"

finish
