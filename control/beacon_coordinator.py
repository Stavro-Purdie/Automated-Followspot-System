"""Coordinate beacon discovery, health, and modulation assignments."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Optional

from control.beacon_network import discover_beacons, fetch_status, push_telemetry, is_valid_ip_address

logger = logging.getLogger("beacon_coordinator")


@dataclass
class BeaconNode:
    beacon_id: str
    ip_address: str
    port: int = 5000
    slot: int = 0
    online: bool = False
    last_seen: float = 0.0
    last_status: Dict[str, Any] = field(default_factory=dict)


class BeaconCoordinator:
    """Keep a stable logical roster while network addresses change."""

    def __init__(self, config: Optional[Dict[str, Any]] = None, *, discovery_interval: float = 5.0):
        self.config = config or {}
        self.discovery_interval = discovery_interval
        self.nodes: Dict[str, BeaconNode] = {}
        self.last_discovery = 0.0
        self.stats = {
            "discoveries": 0,
            "online": 0,
            "offline": 0,
            "address_changes": 0,
            "telemetry_failures": 0,
        }
        self.load_config(self.config.get("beacons", {}))

    def load_config(self, entries: Dict[str, Dict[str, Any]]) -> None:
        for key, raw in entries.items():
            beacon_id = str(raw.get("beacon_id", key))
            address = str(raw.get("ip_address", ""))
            if not is_valid_ip_address(address):
                continue
            self.nodes[beacon_id] = BeaconNode(
                beacon_id=beacon_id,
                ip_address=address,
                port=int(raw.get("port", 5000)),
                slot=int(raw.get("slot", 0)),
            )
        self._assign_slots()

    def discover(self, *, network: Optional[str] = None, force: bool = False) -> Dict[str, BeaconNode]:
        now = time.monotonic()
        if not force and now - self.last_discovery < self.discovery_interval:
            return dict(self.nodes)
        discovery_config = self.config.get("discovery", {})
        found = discover_beacons(
            network if network is not None else discovery_config.get("network"),
            ports=tuple(discovery_config.get("http_ports", (5000, 80))),
            udp_port=int(discovery_config.get("udp_port", 4210)),
            timeout=float(discovery_config.get("timeout_seconds", 0.25)),
            max_hosts=int(discovery_config.get("max_hosts", 254)),
        )
        for item in found:
            beacon_id = str(item["beacon_id"])
            node = self.nodes.get(beacon_id)
            if node is None:
                node = BeaconNode(beacon_id=beacon_id, ip_address=item["ip_address"], port=int(item.get("port", 5000)))
                self.nodes[beacon_id] = node
            elif node.ip_address != item["ip_address"] or node.port != int(item.get("port", node.port)):
                self.stats["address_changes"] += 1
                node.ip_address = item["ip_address"]
                node.port = int(item.get("port", node.port))
            node.online = True
            node.last_seen = time.time()
            node.last_status = dict(item.get("status", {}))
        self._assign_slots()
        self.last_discovery = now
        self.stats["discoveries"] += 1
        self.stats["online"] = sum(node.online for node in self.nodes.values())
        self.stats["offline"] = len(self.nodes) - self.stats["online"]
        return dict(self.nodes)

    def poll(self, *, timeout: float = 0.5) -> Dict[str, BeaconNode]:
        for node in self.nodes.values():
            try:
                node.last_status = fetch_status(node, timeout=timeout)
                node.online = True
                node.last_seen = time.time()
            except Exception as exc:
                node.online = False
                logger.debug("Beacon %s unavailable: %s", node.beacon_id, exc)
        self.stats["online"] = sum(node.online for node in self.nodes.values())
        self.stats["offline"] = len(self.nodes) - self.stats["online"]
        return dict(self.nodes)

    def publish_program_state(self, state: Dict[str, Any], *, timeout: float = 0.5) -> None:
        """Send the same show clock and unique modulation slot to each node."""
        for node in self.nodes.values():
            if not node.online:
                continue
            payload = dict(state)
            payload.update({"beacon_id": node.beacon_id, "modulation_slot": node.slot})
            try:
                push_telemetry(node, telemetry=payload, timeout=timeout)
            except Exception:
                self.stats["telemetry_failures"] += 1

    def export_config(self) -> Dict[str, Dict[str, Any]]:
        return {
            node.beacon_id: {
                "beacon_id": node.beacon_id,
                "ip_address": node.ip_address,
                "port": node.port,
                "slot": node.slot,
            }
            for node in self.nodes.values()
        }

    def _assign_slots(self) -> None:
        for slot, node in enumerate(sorted(self.nodes.values(), key=lambda item: item.beacon_id)):
            node.slot = slot
