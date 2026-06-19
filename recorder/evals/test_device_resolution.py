#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""
test_device_resolution.py -- regression guard for auto_detect_device.

The recorder's no-flag default resolves an avfoundation device by NAME
because indices are positional and reorder when audio hardware changes. A
bare :0 default can resolve to a silent loopback (BlackHole) rather than
the mic. This test pins the resolution cascade:

  1. a BlackHole-containing aggregate device wins (meeting-capture path)
  2. else the first non-loopback input that looks like a mic
  3. else :0 unchanged

and that explicit --device / MEETING_DEVICE always bypass resolution.

It loads auto_detect_device out of the recorder source without importing
the whole script (whose parakeet-mlx/sherpa deps are heavy and irrelevant
here), and injects a fake device list so the assertions are deterministic
regardless of the machine the test runs on.

Run: uv run evals/test_device_resolution.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RECORDER = Path(__file__).resolve().parent.parent / "recorder"


def _load_auto_detect():
    """Exec just auto_detect_device from the recorder source, with a fake
    avfoundation_devices() injected so the test controls the device list."""
    src = RECORDER.read_text()
    m = re.search(
        r"\ndef auto_detect_device\(.*?\n(?=\ndef |\nclass |\n# ----)",
        src, re.S,
    )
    if not m:
        raise AssertionError("auto_detect_device not found in recorder source")
    ns: dict = {"sys": sys}
    exec(m.group(0), ns)
    return ns["auto_detect_device"]


def run(devices, user_device=":0", env_set=False):
    """Resolve against a fixed device list (list of (index, name) tuples)."""
    fn = _load_auto_detect()
    # auto_detect_device calls the module-level avfoundation_devices(); patch
    # it in the function's globals to return our fixture.
    fn.__globals__["avfoundation_devices"] = lambda: devices
    return fn(user_device, env_set)


def main() -> int:
    failures = []

    def check(label, got, want):
        if got != want:
            failures.append(f"{label}: got {got!r}, want {want!r}")

    # The bug case: BlackHole at index 0, mic at index 1, no aggregate.
    # Must resolve the mic, NOT the silent loopback at :0.
    bh_then_mic = [("0", "BlackHole 2ch"), ("1", "MacBook Pro Microphone")]
    check("blackhole-at-0 resolves mic", run(bh_then_mic), ":1")

    # Aggregate present: meeting-capture path wins over a plain mic.
    with_agg = [
        ("0", "BlackHole 2ch"),
        ("1", "MacBook Pro Microphone"),
        ("2", "Recorder Input (Aggregate)"),
    ]
    check("aggregate wins", run(with_agg), ":2")

    # Mic already at :0: leave :0 unchanged (no spurious reindex).
    mic_at_0 = [("0", "MacBook Pro Microphone"), ("1", "BlackHole 2ch")]
    check("mic-at-0 stays :0", run(mic_at_0), ":0")

    # Only a loopback exists, no real mic: fall back to :0 unchanged rather
    # than inventing a device.
    only_loopback = [("0", "BlackHole 2ch")]
    check("loopback-only falls back to :0", run(only_loopback), ":0")

    # Explicit --device must pass through untouched even when it points at
    # the loopback (the user asked for it).
    check("explicit device passes through",
          run(bh_then_mic, user_device=":0", env_set=True), ":0")
    check("explicit non-default passes through",
          run(bh_then_mic, user_device=":3"), ":3")

    # No mic-hint names, but a non-loopback input exists (e.g. a USB
    # interface named oddly): prefer it over :0-is-loopback.
    odd_name = [("0", "BlackHole 2ch"), ("1", "Scarlett Solo USB")]
    check("non-hint non-loopback still beats loopback :0",
          run(odd_name), ":1")

    if failures:
        print("FAIL:")
        for f in failures:
            print("  " + f)
        return 1
    print("PASS: device resolution cascade (7 cases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
