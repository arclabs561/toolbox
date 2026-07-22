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

mac_wifi = """
{
  "SPAirPortDataType": [{
    "spairport_airport_interfaces": [{
      "_name": "en0",
      "spairport_current_network_information": {
        "spairport_network_channel": "157 (5GHz, 80MHz)",
        "spairport_network_mcs": 7,
        "spairport_network_phymode": "802.11ac",
        "spairport_network_rate": 650,
        "spairport_signal_noise": "-55 dBm / -95 dBm"
      }
    }]
  }]
}
"""
assert net_platform.parse_macos_wifi(mac_wifi, "en0") == {
    "signal_dbm": -55,
    "noise_dbm": -95,
    "channel": 157,
    "channel_width_mhz": 80,
    "band": "5GHz",
    "phy": "802.11ac",
    "tx_rate_mbps": 650,
    "mcs": 7,
}

linux_wifi = """
Connected to aa:bb:cc:dd:ee:ff
\tfreq: 5180
\tsignal: -55.00 dBm
\ttx bitrate: 650.0 MBit/s
"""
assert net_platform.parse_linux_wifi(linux_wifi) == {
    "frequency_mhz": 5180,
    "signal_dbm": -55,
    "tx_rate_mbps": 650,
}

windows_wifi = """
    State                   : connected
    Signal                  : 80%
    Channel                 : 157
    Receive rate (Mbps)     : 600
    Transmit rate (Mbps)    : 650
    Radio type              : 802.11ax
"""
assert net_platform.parse_windows_wifi(windows_wifi) == {
    "signal_percent": 80,
    "channel": 157,
    "rx_rate_mbps": 600,
    "tx_rate_mbps": 650,
    "phy": "802.11ax",
}

print("pinglet adapters: ok")
