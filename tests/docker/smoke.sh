#!/usr/bin/env sh
set -eu

python ips/ips link --json > /tmp/link.json
python ips/ips peers --json > /tmp/peers.json

python - <<'PY'
import json

link = json.load(open("/tmp/link.json"))
peers = json.load(open("/tmp/peers.json"))
assert link["mode"] == "link"
assert "addresses" in link
assert peers["status"] in {"pass", "unavailable"}
print("docker linux smoke: ok")
PY
