#!/usr/bin/env python3
"""Offline checks for platform and neighbor-cache adapters."""

import socket
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ips_dir = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ips_dir))
import neighbors  # noqa: E402
import net_platform  # noqa: E402


def result(command: list[str], stdout: str) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(command, 0, stdout=stdout, stderr="")


with (
    patch.object(net_platform.platform, "system", return_value="Darwin"),
    patch.object(
        net_platform.subprocess,
        "run",
        return_value=result(
            ["networksetup"],
            """Hardware Port: Wi-Fi
Device: en0

Hardware Port: USB Ethernet
Device: en5
""",
        ),
    ),
):
    labels = net_platform.mac_link_labels()
    assert labels == {"en0": "wifi", "en5": "ethernet"}


with (
    patch.object(net_platform.platform, "system", return_value="Linux"),
    patch.object(
        net_platform.subprocess,
        "run",
        side_effect=[
            result(["ip", "route", "get"], "1.1.1.1 dev wlan0 src 192.0.2.2\n"),
            result(["ip", "route", "show"], "default via 192.0.2.1 dev wlan0\n"),
        ],
    ),
):
    assert net_platform.default_iface() == "wlan0"
    assert net_platform.gateway_ip() == "192.0.2.1"


def neighbor_run(command: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
    if command == ["ip", "neigh", "show"]:
        return result(
            command,
            """192.168.1.1 dev eth0 lladdr aa:bb:cc:dd:ee:ff REACHABLE
192.168.1.50 dev eth0 lladdr ff:ff:ff:ff:ff:ff STALE
192.168.1.223 dev eth0 lladdr 11:22:33:44:55:66 STALE
fe80::2 dev eth0 lladdr 22:33:44:55:66:77 STALE
""",
        )
    return result(command, "192.168.1.1 dev eth0 lladdr aa:bb:cc:dd:ee:ff\n")


with (
    patch.object(neighbors.platform, "system", return_value="Linux"),
    patch.object(neighbors.subprocess, "run", side_effect=neighbor_run),
    patch.object(
        neighbors.psutil,
        "net_if_addrs",
        return_value={"eth0": [SimpleNamespace(family=socket.AF_INET, address="192.168.1.223")]},
    ),
):
    data = neighbors.peer_cache()

assert data["status"] == "pass"
assert data["source"] == ["ip neigh show", "arp -an"]
assert [peer["address"] for peer in data["peers"]] == ["192.168.1.1", "fe80::2"]
assert data["peers"][0]["state"] == "REACHABLE"

print("ips adapters: ok")
