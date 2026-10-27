"""Network helpers for Wi-Fi IR beacons (Xiao ESP32-C6 firmware).

Lightweight HTTP client using stdlib only; avoids extra deps.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
import ipaddress
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, Optional

DEFAULT_TIMEOUT = 2.5
DISCOVERY_PORT = 4210
DISCOVERY_MESSAGE = b"AFS_BEACON_DISCOVER\n"


def _request(url: str, *, data: Optional[Dict[str, Any]] = None, timeout: float = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    headers = {"Accept": "application/json"}
    if data is not None:
        body = urllib.parse.urlencode(data).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    else:
        req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        payload = resp.read().decode(charset)
    return json.loads(payload)


def build_beacon_url(beacon, path: str = "/api/status") -> str:
    """Build a canonical HTTP URL for a beacon endpoint."""
    return f"http://{beacon.ip_address}:{beacon.port}{path}"


def is_valid_ip_address(value: str) -> bool:
    """Return whether a configured address is a concrete unicast IP."""
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return not (address.is_unspecified or address.is_multicast or address.is_loopback)


def _probe_http_address(address: str, port: int, timeout: float) -> Optional[Dict[str, Any]]:
    """Probe one address and return a normalized beacon record when it answers."""
    try:
        payload = _request(f"http://{address}:{port}/api/status", timeout=timeout)
    except (OSError, ValueError, urllib.error.URLError, json.JSONDecodeError):
        return None
    beacon_id = payload.get("beacon_id", payload.get("id"))
    if beacon_id is None:
        return None
    return {
        "beacon_id": str(beacon_id),
        "ip_address": address,
        "port": port,
        "status": payload,
    }


def discover_beacons(
    network: Optional[str] = None,
    *,
    ports: tuple[int, ...] = (5000, 80),
    udp_port: int = DISCOVERY_PORT,
    timeout: float = 0.25,
    max_hosts: int = 254,
) -> list[Dict[str, Any]]:
    """Find beacons without requiring pre-entered IP addresses.

    UDP discovery is fast and works across a normal theatre LAN. A bounded
    HTTP scan is retained for older firmware and networks that filter UDP.
    """
    discovered: Dict[str, Dict[str, Any]] = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(timeout)
    try:
        sock.sendto(DISCOVERY_MESSAGE, ("255.255.255.255", udp_port))
        while True:
            try:
                raw, address = sock.recvfrom(2048)
            except socket.timeout:
                break
            try:
                payload = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                continue
            beacon_id = payload.get("beacon_id", payload.get("id"))
            if beacon_id is not None:
                discovered[str(beacon_id)] = {
                    "beacon_id": str(beacon_id),
                    "ip_address": address[0],
                    "port": int(payload.get("port", 5000)),
                    "status": payload,
                }
    except OSError:
        pass
    finally:
        sock.close()

    if network is None:
        try:
            route_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            route_sock.connect(("10.255.255.255", 1))
            local_address = route_sock.getsockname()[0]
            route_sock.close()
            network = f"{local_address}/24"
        except OSError:
            network = None

    if network:
        try:
            hosts = list(ipaddress.ip_network(network, strict=False).hosts())[:max_hosts]
        except ValueError:
            hosts = []
        with ThreadPoolExecutor(max_workers=32) as executor:
            futures = [
                executor.submit(_probe_http_address, str(host), port, timeout)
                for host in hosts for port in ports
                if str(host) not in {entry["ip_address"] for entry in discovered.values()}
            ]
            for future in as_completed(futures):
                result = future.result()
                if result:
                    discovered.setdefault(result["beacon_id"], result)

    return list(discovered.values())


def fetch_status(beacon, *, timeout: float = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """Fetch live status from a beacon.

    Expected firmware endpoint: GET /api/status returning JSON.
    """
    url = build_beacon_url(beacon, "/api/status")
    return _request(url, timeout=timeout)


def push_telemetry(beacon, *, telemetry: Dict[str, Any], timeout: float = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """Push program telemetry to a beacon-side endpoint when supported."""
    url = build_beacon_url(beacon, "/api/telemetry")
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    body = json.dumps(telemetry).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        payload = resp.read().decode(charset)
    return json.loads(payload)


def push_config(beacon, *, brightness_pct: int, led_on: bool, timeout: float = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """Send brightness/power settings to the beacon.

    Firmware accepts POST /api/config with query-encoded form data.
    brightness_pct: 0-100
    led_on: True to enable pulses, False to pause output
    """
    url = f"http://{beacon.ip_address}:{beacon.port}/api/config"
    payload = {
        "brightness": int(max(0, min(100, brightness_pct))),
        "led": 1 if led_on else 0,
    }
    return _request(url, data=payload, timeout=timeout)


def push_name(beacon, *, name: str, timeout: float = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """Send display name to beacon; persisted in NVS and returned in status."""
    url = f"http://{beacon.ip_address}:{beacon.port}/api/config"
    payload = {"name": name}
    return _request(url, data=payload, timeout=timeout)


def push_wifi(beacon, *, ssid: str, password: str, timeout: float = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """Send Wi-Fi credentials; firmware stores and restarts."""
    url = f"http://{beacon.ip_address}:{beacon.port}/api/wifi"
    payload = {"ssid": ssid, "pass": password}
    return _request(url, data=payload, timeout=timeout)


def push_ota(beacon, *, firmware_url: str, timeout: float = 30.0) -> Dict[str, Any]:
    """Trigger OTA firmware update from a URL.

    Firmware accepts POST /api/ota with JSON {"url": "http://.../firmware.bin"}
    """
    url = f"http://{beacon.ip_address}:{beacon.port}/api/ota"
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    body = json.dumps({"url": firmware_url}).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        charset = resp.headers.get_content_charset() or "utf-8"
        payload = resp.read().decode(charset)
    return json.loads(payload)
