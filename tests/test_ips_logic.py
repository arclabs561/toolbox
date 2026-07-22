#!/usr/bin/env python3
"""Small offline checks for the statistics contract."""

import math
import runpy
import sys
from pathlib import Path

script = Path(sys.argv[1])
sys.path.insert(0, str(script.parent))
ips = runpy.run_path(str(script), run_name="ips_script")

metrics = ips["latency_metrics"]([10.0, 12.0, 14.0], sent=4)
assert metrics["received"] == 3
assert metrics["lost"] == 1
assert metrics["loss_rate"] == 0.25
assert metrics["rtt_mean_ms"] == 12.0
assert metrics["rtt_sample_variance_ms2"] == 4.0
assert math.isclose(metrics["rtt_sample_stddev_ms"], 2.0)
assert metrics["rtt_ipdv_abs_mean_ms"] == 2.0
assert metrics["rtt_pdv_max_ms"] == 4.0
assert ips["quality_status"](metrics) == "degraded"
assert ips["quality_status"](ips["latency_metrics"]([10.0, 11.0, 12.0], sent=3)) == "pass"
assert ips["quality_status"](ips["latency_metrics"]([], sent=3)) == "unknown"

assert ips["human_rate"](1_000) == "1.00 Kbit/s"
assert ips["human_rate"](1_000_000) == "1.00 Mbit/s"

print("ips logic: ok")
