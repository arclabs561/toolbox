"""Platform-specific network discovery used by the ips command."""

import contextlib
import functools
import platform
import socket
import subprocess
from pathlib import Path

import psutil

SKIP_IFACES = {"lo", "lo0", "awdl0", "llw0", "ap1", "anpi0", "anpi1"}

IFACE_LABELS: dict[str, str] = {
    "eth0": "ethernet",
    "eth1": "ethernet",
    "wlan0": "wifi",
    "wlp0s20f3": "wifi",
    "docker0": "docker",
}


def is_ipv4(addr: str) -> bool:
    return "." in addr


def label_for(iface: str) -> str:
    if platform.system() == "Darwin":
        mac_label = mac_link_labels().get(iface)
        if mac_label:
            return mac_label
    if iface in IFACE_LABELS:
        return IFACE_LABELS[iface]
    for prefix in ("br-", "veth"):
        if iface.startswith(prefix):
            return "docker"
    if iface.startswith(("utun", "tun", "wg")):
        return "vpn"
    if iface.startswith("tailscale"):
        return "tailscale"
    if iface.startswith("wl"):
        return "wifi"
    if iface.startswith(("en", "eth")):
        return "ethernet"
    return iface


@functools.lru_cache(maxsize=1)
def mac_link_labels() -> dict[str, str]:
    """Use macOS hardware-port names instead of guessing from enN."""
    if platform.system() != "Darwin":
        return {}
    try:
        output = subprocess.run(
            ["networksetup", "-listallhardwareports"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except (FileNotFoundError, subprocess.CalledProcessError):
        return {}

    labels: dict[str, str] = {}
    hardware_port: str | None = None
    for line in output.splitlines():
        if line.startswith("Hardware Port:"):
            hardware_port = line.split(":", 1)[1].strip().lower()
        elif line.startswith("Device:") and hardware_port:
            iface = line.split(":", 1)[1].strip()
            if any(word in hardware_port for word in ("wi-fi", "wifi", "airport", "wireless")):
                labels[iface] = "wifi"
            elif any(
                word in hardware_port for word in ("ethernet", "thunderbolt", "bridge", "usb")
            ):
                labels[iface] = "ethernet"
            hardware_port = None
    return labels


def default_iface() -> str | None:
    """Return the interface name that carries the default route."""
    try:
        if platform.system() == "Darwin":
            out = subprocess.run(
                ["route", "-n", "get", "default"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            for line in out.splitlines():
                if "interface:" in line:
                    return line.split("interface:")[-1].strip()
        elif platform.system() == "Windows":
            out = subprocess.run(
                ["route", "print", "-4"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 4 and parts[:2] == ["0.0.0.0", "0.0.0.0"]:
                    return parts[3]
        else:
            out = subprocess.run(
                ["ip", "route", "get", "1.1.1.1"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            tokens = out.split()
            if "dev" in tokens:
                return tokens[tokens.index("dev") + 1]
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return None


def gateway_ip() -> str | None:
    """Return the default gateway IP."""
    try:
        if platform.system() == "Darwin":
            out = subprocess.run(
                ["route", "-n", "get", "default"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            for line in out.splitlines():
                if "gateway:" in line:
                    return line.split("gateway:")[-1].strip()
        elif platform.system() == "Windows":
            out = subprocess.run(
                ["route", "print", "-4"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            for line in out.splitlines():
                parts = line.split()
                if len(parts) >= 4 and parts[:2] == ["0.0.0.0", "0.0.0.0"]:
                    return parts[2]
        else:
            out = subprocess.run(
                ["ip", "route", "show", "default"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            parts = out.split()
            if "via" in parts:
                return parts[parts.index("via") + 1]
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return None


def wifi_ssid(iface: str | None) -> str | None:
    """Return current WiFi SSID, or None."""
    try:
        if platform.system() == "Darwin":
            if not iface:
                return None
            out = subprocess.run(
                ["ipconfig", "getsummary", iface],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
            for line in out.splitlines():
                if "SSID" in line and "BSSID" not in line:
                    return line.split(":", 1)[-1].strip()
        else:
            out = subprocess.run(
                ["iwgetid", "-r", "-i", iface] if iface else ["iwgetid", "-r"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
            return out or None
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    return None


def local_ips(active_iface: str | None) -> list[tuple[str, str, str, bool]]:
    """Return (interface, label, addr, is_default) tuples."""
    addrs = psutil.net_if_addrs()
    stats = psutil.net_if_stats()

    results: list[tuple[str, str, str, bool]] = []
    seen: set[str] = set()

    for iface, addr_list in addrs.items():
        if iface in SKIP_IFACES:
            continue
        st = stats.get(iface)
        if st and not st.isup:
            continue
        for addr in addr_list:
            if addr.family not in (socket.AF_INET, socket.AF_INET6):
                continue
            ip = addr.address.split("%")[0]
            if ip in ("127.0.0.1", "::1") or ip.startswith("fe80"):
                continue
            if ip in seen:
                continue
            seen.add(ip)
            is_default = iface == active_iface
            results.append((iface, label_for(iface), ip, is_default))

    results.sort(key=lambda row: (not row[3], row[1], not is_ipv4(row[2])))
    return results


def resolver_servers() -> list[str]:
    """Return configured resolver addresses without making a DNS query."""
    servers: list[str] = []
    resolv_conf = Path("/etc/resolv.conf")
    with contextlib.suppress(OSError):
        for line in resolv_conf.read_text().splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0] == "nameserver":
                servers.append(parts[1])

    if platform.system() == "Windows":
        with contextlib.suppress(FileNotFoundError, subprocess.CalledProcessError):
            out = subprocess.run(
                ["ipconfig", "/all"], capture_output=True, text=True, check=True
            ).stdout
            for line in out.splitlines():
                if "DNS Servers" in line:
                    value = line.split(":", 1)[-1].strip()
                    if value:
                        servers.append(value)
                elif line.startswith(" ") and line.strip() and "." in line:
                    value = line.strip()
                    if value.count(".") == 3:
                        servers.append(value)

    return list(dict.fromkeys(servers))
