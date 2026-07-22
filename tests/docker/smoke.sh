#!/usr/bin/env sh
set -eu

python ips/ips link --json > /tmp/link.json
set +e
python ips/ips peers --json > /tmp/peers.json
peers_code=$?
set -e
[ "$peers_code" -eq 0 ] || [ "$peers_code" -eq 2 ]

python - <<'PY'
import json

link = json.load(open("/tmp/link.json"))
peers = json.load(open("/tmp/peers.json"))
assert link["mode"] == "link"
assert "addresses" in link
assert peers["status"] in {"pass", "unavailable"}
assert peers["status"] == "pass" or peers["peers"] == []
print("docker linux smoke: ok")
PY
