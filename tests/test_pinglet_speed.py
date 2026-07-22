#!/usr/bin/env python3
"""Offline check for the speed command's loaded-latency envelope."""

import contextlib
import io
import json
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

script = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(script.parent))
pinglet = runpy.run_path(str(script), run_name="pinglet_speed_test")
module_globals = pinglet["show_speed"].__globals__

baseline = pinglet["Check"](
    "gateway",
    "pass",
    "gateway",
    10,
    pinglet["latency_metrics"]([9.0, 10.0, 11.0], sent=3),
    "pass",
)
loaded = pinglet["Check"](
    "gateway",
    "pass",
    "gateway",
    30,
    pinglet["latency_metrics"]([10.0, 30.0, 90.0], sent=3),
    "degraded",
)
iperf = SimpleNamespace(
    returncode=0,
    stdout=json.dumps({"end": {"sum_sent": {"bits_per_second": 1_000_000}}}),
    stderr="",
)
args = SimpleNamespace(command_target="192.0.2.10", ipv4=False, ipv6=False, json=True)
ping_results = iter((baseline, loaded))
output = io.StringIO()
with (
    patch.object(module_globals["shutil"], "which", return_value="/usr/bin/iperf3"),
    patch.dict(
        module_globals,
        {
            "gateway_ip": lambda: "192.0.2.1",
            "ping_check": lambda *_args: next(ping_results),
        },
    ),
    patch.object(module_globals["subprocess"], "run", return_value=iperf),
    contextlib.redirect_stdout(output),
):
    assert pinglet["show_speed"](args) == 0

payload = json.loads(output.getvalue())
assert payload["gateway_latency"]["baseline"]["quality"] == "pass"
assert payload["gateway_latency"]["loaded"]["quality"] == "degraded"
assert payload["report"]["end"]["sum_sent"]["bits_per_second"] == 1_000_000

print("pinglet speed: ok")
