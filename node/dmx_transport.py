"""DMX512 transport abstraction for followspot system.

Supports multiple transport backends:
- RS485 serial (DMX512 electrical spec)
- Art-Net (Ethernet)
- sACN/E1.31 (Ethernet multicast)
- Stub (for testing)
"""

from __future__ import annotations

import json
import logging
import os
import struct
import termios
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Dict, Optional

import serial

logger = logging.getLogger("dmx_transport")


@dataclass
class DMXFrame:
    """A complete DMX512 frame (512 channels + start code)."""
    data: bytearray  # 513 bytes: start code (0) + 512 channels
    universe: int = 1

    def __post_init__(self):
        if len(self.data) != 513:
            raise ValueError(f"DMX frame must be 513 bytes, got {len(self.data)}")
        if self.data[0] != 0:
            logger.warning("DMX start code is %d, expected 0", self.data[0])


class DMXTransport(ABC):
    """Abstract base for DMX transport mechanisms."""

    @abstractmethod
    def send(self, frame: DMXFrame) -> bool:
        """Send a DMX frame. Returns True on success."""
        pass

    @abstractmethod
    def close(self) -> None:
        """Clean up resources."""
        pass

    @property
    @abstractmethod
    def is_ready(self) -> bool:
        """Whether transport is initialized and ready."""
        pass


class StubTransport(DMXTransport):
    """No-op transport for testing."""

    def __init__(self):
        self._ready = True
        self.last_frame: Optional[DMXFrame] = None

    def send(self, frame: DMXFrame) -> bool:
        self.last_frame = frame
        logger.debug("StubTransport: pan_ch=%d tilt_ch=%d", frame.data[1], frame.data[3])
        return True

    def close(self) -> None:
        pass

    @property
    def is_ready(self) -> bool:
        return self._ready


class RS485Transport(DMXTransport):
    """RS485 serial transport for DMX512 (250kbps, 8N2)."""

    DMX_BAUDRATE = 250000
    DMX_CHANNELS = 512
    BREAK_DURATION_US = 176  # ≥88μs break + MAB; we send longer break
    MAB_DURATION_US = 12     # ≥8μs Mark After Break
    FRAME_INTERVAL_MS = 22.7  # ~44Hz max (512ch * 44μs + break + MAB ≈ 22.7ms)

    def __init__(
        self,
        port: str = "/dev/ttyAMA0",
        universe: int = 1,
        fixture_profile: Optional[Dict[str, Any]] = None,
    ):
        self.port = port
        self.universe = universe
        self.fixture_profile = fixture_profile or self._default_profile()
        self.serial: Optional[serial.Serial] = None
        self._ready = False
        self._last_send_time = 0.0
        self._frame_buffer = bytearray(513)
        self._frame_buffer[0] = 0  # Start code

    @staticmethod
    def _default_profile() -> Dict[str, Any]:
        return {
            "pan_coarse": 1,
            "pan_fine": 2,
            "tilt_coarse": 3,
            "tilt_fine": 4,
            "dimmer": 5,
            "pan_scale": 1.0,
            "tilt_scale": 1.0,
        }

    def _ensure_serial(self) -> bool:
        """Open serial port with DMX512 parameters (250kbps, 8N2)."""
        if self.serial and self.serial.is_open:
            return True

        try:
            # Use pyserial with low-level termios for break/MAB control
            self.serial = serial.Serial(
                port=self.port,
                baudrate=self.DMX_BAUDRATE,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_TWO,
                timeout=0,
                write_timeout=1,
            )
            self._ready = True
            logger.info("RS485Transport opened %s @ %d baud (8N2)", self.port, self.DMX_BAUDRATE)
            return True
        except Exception as e:
            logger.error("Failed to open RS485 port %s: %s", self.port, e)
            self._ready = False
            return False

    def _send_break_mab(self) -> None:
        """Send DMX break (≥88μs) and Mark After Break (≥8μs) using termios."""
        if not self.serial or not self.serial.is_open:
            return

        fd = self.serial.fileno()
        attrs = termios.tcgetattr(fd)

        # Send break: set baud to very low, send 0x00
        try:
            # Set baud to ~4800 to stretch break (1/4800 * 10 bits ≈ 2ms > 88μs)
            termios.tcsetattr(fd, termios.TCSANOW, [
                attrs[0], attrs[1], attrs[2], attrs[3],
                termios.B4800, termios.B4800,
                attrs[6], attrs[7]
            ])
            os.write(fd, b'\x00')
            termios.tcdrain(fd)
            time.sleep(self.BREAK_DURATION_US / 1_000_000)

            # Restore DMX baud for MAB
            termios.tcsetattr(fd, termios.TCSANOW, [
                attrs[0], attrs[1], attrs[2], attrs[3],
                termios.B250000, termios.B250000,
                attrs[6], attrs[7]
            ])
            # MAB: line held high (mark) for ≥8μs
            time.sleep(self.MAB_DURATION_US / 1_000_000)
        except Exception as e:
            logger.warning("Break/MAB sequence failed: %s", e)

    def send(self, frame: DMXFrame) -> bool:
        if not self._ensure_serial():
            return False

        try:
            # Throttle to max DMX frame rate
            elapsed = time.time() - self._last_send_time
            min_interval = self.FRAME_INTERVAL_MS / 1000.0
            if elapsed < min_interval:
                time.sleep(min_interval - elapsed)

            self._send_break_mab()

            # Write 513 bytes (start code + 512 channels)
            self.serial.write(frame.data)
            self.serial.flush()
            self._last_send_time = time.time()
            return True
        except Exception as e:
            logger.error("RS485Transport send failed: %s", e)
            self._ready = False
            return False

    def close(self) -> None:
        if self.serial and self.serial.is_open:
            self.serial.close()
        self._ready = False

    @property
    def is_ready(self) -> bool:
        return self._ready and self.serial and self.serial.is_open


class ArtNetTransport(DMXTransport):
    """Art-Net 4 transport (UDP, port 6454)."""

    ARTNET_PORT = 6454
    ARTNET_HEADER = b"Art-Net\x00"
    OP_DMX = 0x5000

    def __init__(
        self,
        target_ip: str = "2.0.0.1",
        universe: int = 1,
        net: int = 0,
        subnet: int = 0,
        fixture_profile: Optional[Dict[str, Any]] = None,
    ):
        import socket
        self.target_ip = target_ip
        self.universe = universe
        self.net = net
        self.subnet = subnet
        self.fixture_profile = fixture_profile or RS485Transport._default_profile()
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        self._ready = True
        logger.info("ArtNetTransport -> %s:%d universe=%d", target_ip, self.ARTNET_PORT, universe)

    def send(self, frame: DMXFrame) -> bool:
        if not self._ready:
            return False

        # Art-Net DMX packet structure
        # Header (12) + OpCode (2) + ProtVer (2) + Sequence (1) + Physical (1)
        # + Universe (2, Lo/Hi) + Length (2, Hi/Lo) + Data (512)
        packet = bytearray()
        packet.extend(self.ARTNET_HEADER)           # 8 bytes + null
        packet.extend(struct.pack("<H", self.OP_DMX))  # OpCode (little-endian)
        packet.extend(struct.pack(">H", 14))        # Protocol version (big-endian)
        packet.append(0)                            # Sequence
        packet.append(0)                            # Physical
        packet.extend(struct.pack("<H", self.universe | (self.subnet << 4) | (self.net << 8)))
        packet.extend(struct.pack(">H", 512))       # Length (big-endian, 512 channels)
        packet.extend(frame.data[1:])               # Skip start code, send 512 channels

        try:
            self._socket.sendto(packet, (self.target_ip, self.ARTNET_PORT))
            return True
        except Exception as e:
            logger.error("ArtNetTransport send failed: %s", e)
            return False

    def close(self) -> None:
        self._socket.close()
        self._ready = False

    @property
    def is_ready(self) -> bool:
        return self._ready


class SACNTransport(DMXTransport):
    """sACN/E1.31 transport (multicast UDP)."""

    SACN_PORT = 5568
    # Multicast: 239.255.x.y where universe = (x << 8) | y

    def __init__(
        self,
        universe: int = 1,
        source_name: str = "followspot",
        fixture_profile: Optional[Dict[str, Any]] = None,
    ):
        import socket
        import struct
        self.universe = universe
        self.source_name = source_name[:63].encode("utf-8")
        self.fixture_profile = fixture_profile or RS485Transport._default_profile()
        self.cid = os.urandom(16)  # Component Identifier
        self.sequence = 0

        # Calculate multicast address: 239.255.(universe>>8).(universe&0xFF)
        u1 = (universe >> 8) & 0xFF
        u2 = universe & 0xFF
        self.mcast_addr = f"239.255.{u1}.{u2}"

        self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._socket.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 32)
        self._ready = True
        logger.info("SACNTransport -> %s:%d universe=%d", self.mcast_addr, self.SACN_PORT, universe)

    def _build_root_layer(self, length: int) -> bytearray:
        """Build sACN root layer (preamble + postamble + ACN packet identifier + length + vector + CID)."""
        root = bytearray()
        root.extend(b'\x00\x10')  # Preamble size (16)
        root.extend(b'\x00\x00')  # Postamble size (0)
        root.extend(b'ASC-E1.17\x00\x00\x00')  # ACN packet identifier
        root.extend(struct.pack(">H", 0x7000 | (length & 0x3FFF)))  # Flags + Length
        root.extend(b'\x00\x00\x00\x04')  # Vector: Root (4)
        root.extend(self.cid)  # CID (16 bytes)
        return root

    def _build_framing_layer(self, length: int) -> bytearray:
        """Build framing layer (vector + source name + priority + sync + universe)."""
        framing = bytearray()
        framing.extend(struct.pack(">H", 0x7000 | (length & 0x3FFF)))
        framing.extend(b'\x00\x00\x00\x02')  # Vector: Framing (2)
        framing.extend(self.source_name)
        framing.extend(b'\x00' * (64 - len(self.source_name)))  # Pad to 64
        framing.append(100)  # Priority
        framing.append(0)    # Sync address
        framing.extend(struct.pack(">H", self.universe))  # Universe
        return framing

    def _build_dmp_layer(self, data: bytearray) -> bytearray:
        """Build DMP layer (DMX data)."""
        dmp = bytearray()
        dmp.extend(struct.pack(">H", 0x7000 | ((len(data) + 10) & 0x3FFF)))
        dmp.extend(b'\x00\x00\x00\x02')  # Vector: DMP (2)
        dmp.append(0xA1)  # Type: DMP_SET_PROPERTY
        dmp.append(0x01)  # First property address (1 = start code)
        dmp.extend(struct.pack(">H", len(data)))  # Property count
        dmp.extend(data)
        return dmp

    def send(self, frame: DMXFrame) -> bool:
        if not self._ready:
            return False

        self.sequence = (self.sequence + 1) & 0xFF
        dmx_data = frame.data  # 513 bytes including start code

        # Build layers
        dmp = self._build_dmp_layer(dmx_data)
        framing = self._build_framing_layer(len(dmp))
        root = self._build_root_layer(len(framing) + len(dmp))

        packet = root + framing + dmp

        try:
            self._socket.sendto(packet, (self.mcast_addr, self.SACN_PORT))
            return True
        except Exception as e:
            logger.error("SACNTransport send failed: %s", e)
            return False

    def close(self) -> None:
        self._socket.close()
        self._ready = False

    @property
    def is_ready(self) -> bool:
        return self._ready


def create_transport(config: Dict[str, Any]) -> DMXTransport:
    """Factory function to create transport from config dict.

    Config keys:
        transport: "stub" | "rs485_serial" | "artnet" | "sacn"
        serial_port: for rs485_serial
        artnet_ip: for artnet
        universe: DMX universe (default 1)
        fixture_profile: dict with channel mappings
    """
    transport_type = config.get("transport", "stub").lower()
    universe = config.get("universe", 1)
    fixture_profile = config.get("fixture_profile")

    if transport_type == "rs485_serial":
        port = config.get("serial_port", "/dev/ttyAMA0")
        return RS485Transport(port=port, universe=universe, fixture_profile=fixture_profile)
    elif transport_type == "artnet":
        target_ip = config.get("artnet_ip", "2.0.0.1")
        net = config.get("artnet_net", 0)
        subnet = config.get("artnet_subnet", 0)
        return ArtNetTransport(target_ip=target_ip, universe=universe, net=net, subnet=subnet, fixture_profile=fixture_profile)
    elif transport_type == "sacn":
        source_name = config.get("sacn_source", "followspot")
        return SACNTransport(universe=universe, source_name=source_name, fixture_profile=fixture_profile)
    else:
        logger.info("Using StubTransport (transport='%s')", transport_type)
        return StubTransport()


class DMXEncoder:
    """Encodes lighting commands into DMX512 frames using a fixture profile."""

    def __init__(self, fixture_profile: Dict[str, Any]):
        self.profile = fixture_profile
        # Default 16-bit pan/tilt at addresses 1-4, dimmer at 5
        self.pan_coarse = self.profile.get("pan_coarse", 1)
        self.pan_fine = self.profile.get("pan_fine", 2)
        self.tilt_coarse = self.profile.get("tilt_coarse", 3)
        self.tilt_fine = self.profile.get("tilt_fine", 4)
        self.dimmer = self.profile.get("dimmer", 5)
        self.pan_scale = self.profile.get("pan_scale", 1.0)
        self.tilt_scale = self.profile.get("tilt_scale", 1.0)

        # Pan/tilt range from profile or defaults
        self.pan_min = self.profile.get("pan_min_deg", -180.0)
        self.pan_max = self.profile.get("pan_max_deg", 180.0)
        self.tilt_min = self.profile.get("tilt_min_deg", -90.0)
        self.tilt_max = self.profile.get("tilt_max_deg", 90.0)

    def encode(self, pan_deg: float, tilt_deg: float, brightness_pct: float = 100.0) -> DMXFrame:
        """Encode pan/tilt/brightness into DMX frame.

        Uses 16-bit values: 0-65535 maps to pan_min-pan_max / tilt_min-tilt_max
        """
        frame = bytearray(513)
        frame[0] = 0  # Start code

        # Clamp to fixture limits
        pan_deg = max(self.pan_min, min(self.pan_max, pan_deg))
        tilt_deg = max(self.tilt_min, min(self.tilt_max, tilt_deg))
        brightness = max(0.0, min(100.0, brightness_pct))

        # Convert degrees to 16-bit DMX values
        pan_range = self.pan_max - self.pan_min
        tilt_range = self.tilt_max - self.tilt_min

        if pan_range > 0:
            pan_norm = (pan_deg - self.pan_min) / pan_range
        else:
            pan_norm = 0.5

        if tilt_range > 0:
            tilt_norm = (tilt_deg - self.tilt_min) / tilt_range
        else:
            tilt_norm = 0.5

        pan_raw = int(pan_norm * 65535)
        tilt_raw = int(tilt_norm * 65535)
        dimmer_raw = int(brightness / 100.0 * 255)

        # Apply scale factors
        pan_raw = int(pan_raw * self.pan_scale)
        tilt_raw = int(tilt_raw * self.tilt_scale)

        # Clamp to 16-bit
        pan_raw = max(0, min(65535, pan_raw))
        tilt_raw = max(0, min(65535, tilt_raw))

        # Write coarse/fine (big-endian: MSB first per DMX512)
        frame[self.pan_coarse] = (pan_raw >> 8) & 0xFF
        frame[self.pan_fine] = pan_raw & 0xFF
        frame[self.tilt_coarse] = (tilt_raw >> 8) & 0xFF
        frame[self.tilt_fine] = tilt_raw & 0xFF
        frame[self.dimmer] = dimmer_raw

        return DMXFrame(data=frame, universe=self.profile.get("universe", 1))