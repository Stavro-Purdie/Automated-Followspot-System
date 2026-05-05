"""Network helpers for Wi-Fi IR beacons (Xiao ESP32-C6 firmware).

Lightweight HTTP client using stdlib only; avoids extra deps.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional

DEFAULT_TIMEOUT = 2.5


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


def fetch_status(beacon, *, timeout: float = DEFAULT_TIMEOUT) -> Dict[str, Any]:
    """Fetch live status from a beacon.

    Expected firmware endpoint: GET /api/status returning JSON.
    """
    url = f"http://{beacon.ip_address}:{beacon.port}/api/status"
    return _request(url, timeout=timeout)


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
