"""Passive native neighbor-cache collection for the ips command."""

import contextlib
import ipaddress
import platform
import re
import socket
import subprocess

import psutil


def peer_cache() -> dict[str, object]:
    """Read the native neighbor cache; this does not probe the LAN."""
    system = platform.system()
    if system == "Darwin":
        commands = [["arp", "-an"], ["ndp", "-an"]]
    elif system == "Windows":
        commands = [["arp", "-a"]]
    else:
        commands = [["ip", "neigh", "show"], ["arp", "-an"]]

    outputs: list[tuple[list[str], str]] = []
    for command in commands:
        try:
            result = subprocess.run(command, capture_output=True, text=True, check=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            continue
        outputs.append((command, result.stdout))

    if not outputs:
        return {"status": "unavailable", "detail": "no neighbor-cache command found", "peers": []}

    mac_pattern = re.compile(r"(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}", re.I)
    ip_pattern = re.compile(r"(?<![\w:])(?:\d{1,3}\.){3}\d{1,3}(?!\w)|[0-9a-f:]{3,}", re.I)
    local_addresses = {
        addr.address.split("%", 1)[0]
        for iface_addresses in psutil.net_if_addrs().values()
        for addr in iface_addresses
        if addr.family in (socket.AF_INET, socket.AF_INET6)
    }
    peers: list[dict[str, str | None]] = []
    seen: set[tuple[str, str | None, str | None]] = set()
    for _command, output in outputs:
        current_interface: str | None = None
        for line in output.splitlines():
            if system == "Windows" and line.strip().startswith("Interface:"):
                current_interface = line.split(":", 1)[1].split("---", 1)[0].strip()
                continue
            ip_match = ip_pattern.search(line)
            if not ip_match:
                continue
            address = ip_match.group(0)
            with contextlib.suppress(ValueError):
                parsed_address = ipaddress.ip_address(address)
                if (
                    address in local_addresses
                    or parsed_address.is_multicast
                    or parsed_address.is_loopback
                    or parsed_address.is_unspecified
                ):
                    continue
            mac_match = mac_pattern.search(line)
            if mac_match:
                mac = mac_match.group(0).lower().replace("-", ":")
                first_octet = int(mac.split(":", 1)[0], 16)
                if mac == "ff:ff:ff:ff:ff:ff" or first_octet & 1:
                    continue
            else:
                mac = None
            interface = current_interface
            tokens = line.split()
            if "dev" in tokens:
                interface = tokens[tokens.index("dev") + 1]
            elif "on" in tokens:
                interface = tokens[tokens.index("on") + 1]
            state_tokens = {token.upper() for token in tokens}
            state = next(
                (
                    candidate
                    for candidate in (
                        "REACHABLE",
                        "STALE",
                        "DELAY",
                        "PROBE",
                        "FAILED",
                        "INCOMPLETE",
                        "DYNAMIC",
                    )
                    if candidate in state_tokens
                ),
                None,
            )
            key = (address, mac, interface)
            if key in seen:
                continue
            seen.add(key)
            peers.append(
                {
                    "address": address,
                    "mac": mac,
                    "interface": interface,
                    "state": state,
                }
            )

    peers.sort(key=lambda peer: (peer["interface"] or "", peer["address"]))
    return {
        "status": "pass",
        "source": [" ".join(command) for command, _output in outputs],
        "peers": peers,
    }
