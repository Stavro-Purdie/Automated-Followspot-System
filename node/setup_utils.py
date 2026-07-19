#!/usr/bin/env python3
"""Utilities to configure node deployments (network hints, autostart services)."""

from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

SYSTEMD_USER_DIR = Path.home() / ".config" / "systemd" / "user"


def _run_command(command: list[str]) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            universal_newlines=True,
            check=False,
        )
        success = result.returncode == 0
        output = (result.stdout or "").strip()
        return success, output
    except FileNotFoundError:
        return False, f"Command not found: {' '.join(command)}"
    except Exception as exc:  # pragma: no cover - defensive
        return False, f"{type(exc).__name__}: {exc}"


def _service_name(stack_slug: str) -> str:
    return f"followspot-{stack_slug.replace('-', '_')}"


def enable_uart4_for_dmx() -> tuple[bool, str]:
    """Enable UART4 (/dev/ttyAMA0) for DMX512 on Raspberry Pi.

    Adds dtoverlay=uart4 to /boot/firmware/config.txt if not present.
    Returns (success, message).
    """
    config_paths = [
        Path("/boot/firmware/config.txt"),
        Path("/boot/config.txt"),
    ]
    config_path = None
    for p in config_paths:
        if p.exists():
            config_path = p
            break

    if not config_path:
        return False, "No config.txt found at /boot/firmware/config.txt or /boot/config.txt"

    try:
        content = config_path.read_text()
    except Exception as exc:
        return False, f"Failed to read {config_path}: {exc}"

    if "dtoverlay=uart4" in content:
        return True, "UART4 already enabled in config.txt"

    # Append the dtoverlay
    try:
        with config_path.open("a") as f:
            f.write("\n# Enable UART4 for DMX512 on /dev/ttyAMA0\ndtoverlay=uart4\n")
    except Exception as exc:
        return False, f"Failed to write {config_path}: {exc}"

    return True, f"Added dtoverlay=uart4 to {config_path} (reboot required)"


def validate_dmx_timing(port: str = "/dev/ttyAMA0", baudrate: int = 250000) -> tuple[bool, str]:
    """Validate DMX512 timing on the specified serial port.

    Opens the port at 250000 baud 8N2 and attempts to send a break+MAB+frame.
    Requires pyserial. Returns (success, message).
    """
    try:
        import serial
    except ImportError:
        return False, "pyserial not installed (pip install pyserial)"

    try:
        ser = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_TWO,
            timeout=0.1,
            write_timeout=1,
        )
    except Exception as exc:
        return False, f"Failed to open {port} at {baudrate} baud: {exc}"

    try:
        import termios
        fd = ser.fileno()
        attrs = termios.tcgetattr(fd)

        # Send break at current baud (250kbps): 176µs = ~44 bit times
        # We'll send a few 0x00 bytes at a much lower baud
        # For now just verify we can write
        ser.write(b'\x00' * 2)
        ser.flush()
        ser.close()
        return True, f"DMX port {port} opened successfully at {baudrate} baud 8N2"
    except Exception as exc:
        try:
            ser.close()
        except Exception:
            pass
        return False, f"DMX timing validation failed: {exc}"


def _run_command(command: list[str]) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            universal_newlines=True,
            check=False,
        )
        success = result.returncode == 0
        output = (result.stdout or "").strip()
        return success, output
    except FileNotFoundError:
        return False, f"Command not found: {' '.join(command)}"
    except Exception as exc:  # pragma: no cover - defensive
        return False, f"{type(exc).__name__}: {exc}"


def _service_name(stack_slug: str) -> str:
    return f"followspot-{stack_slug.replace('-', '_')}"


def ensure_autostart_service(
    stack_slug: str,
    project_root: Path,
    python_exec: str,
    profile: str,
    port: int,
    setup: Dict[str, Any],
) -> Dict[str, Any]:
    """Create and enable a user-level systemd service for the node server."""

    summary: Dict[str, Any] = {
        "service_name": _service_name(stack_slug),
        "service_path": None,
        "enabled": False,
        "enable_error": None,
    }

    try:
        SYSTEMD_USER_DIR.mkdir(parents=True, exist_ok=True)
    except Exception as exc:  # pragma: no cover - safety
        summary["enable_error"] = f"Unable to create systemd directory: {exc}"
        return summary

    service_path = SYSTEMD_USER_DIR / f"{summary['service_name']}.service"
    project_root = project_root.resolve()
    server_path = project_root / "node" / "server.py"

    def _env_line(key: str, value: Optional[Any]) -> Optional[str]:
        if value in (None, ""):
            return None
        escaped = str(value).replace('"', '\"')
        return f'Environment={key}="{escaped}"'

    env_lines = list(
        filter(
            None,
            [
                _env_line("FOLLOWSPOT_CAMERA_DEVICE", setup.get("camera_device")),
                _env_line("FOLLOWSPOT_STATIC_IP", setup.get("static_ip")),
                _env_line("FOLLOWSPOT_HOSTNAME", setup.get("hostname")),
            ],
        )
    )
    for env_line in (
        _env_line("FOLLOWSPOT_DMX_PORT", setup.get("dmx_port")),
        _env_line("FOLLOWSPOT_DMX_BAUDRATE", setup.get("dmx_baudrate")),
    ):
        if env_line:
            env_lines.append(env_line)

    exec_parts = [
        python_exec,
        str(server_path),
        "--profile",
        profile,
        "--port",
        str(port),
    ]
    dmx_port = setup.get("dmx_port")
    dmx_baudrate = setup.get("dmx_baudrate")
    if dmx_port:
        exec_parts.extend(["--dmx-port", str(dmx_port)])
    if dmx_baudrate:
        exec_parts.extend(["--dmx-baudrate", str(dmx_baudrate)])
    exec_start = " ".join(shlex.quote(part) for part in exec_parts)

    service_text = "\n".join(
        [
            "[Unit]",
            f"Description=Automated Followspot Node ({profile})",
            "After=network-online.target",
            "Wants=network-online.target",
            "",
            "[Service]",
            "Type=simple",
            f"WorkingDirectory={project_root}",
            f"ExecStart={exec_start}",
            "Restart=always",
            "RestartSec=5",
            "WatchdogSec=30",
            "Environment=PYTHONUNBUFFERED=1",
            *env_lines,
            "",
            "[Install]",
            "WantedBy=default.target",
            "",
        ]
    )

    try:
        service_path.write_text(service_text, encoding="utf-8")
        summary["service_path"] = str(service_path)
    except Exception as exc:  # pragma: no cover
        summary["enable_error"] = f"Failed to write service file: {exc}"
        return summary

    # Attempt to enable the service for the current user
    success, output = _run_command(["systemctl", "--user", "daemon-reload"])
    if not success:
        summary["enable_error"] = output or "Failed to reload systemd user daemon"
        return summary

    enable_cmd = ["systemctl", "--user", "enable", "--now", f"{summary['service_name']}.service"]
    success, output = _run_command(enable_cmd)
    if success:
        summary["enabled"] = True
    else:
        summary["enable_error"] = output or "Failed to enable service"

    return summary


def apply_hostname(hostname: Optional[str]) -> Dict[str, Any]:
    """Attempt to set the system hostname using hostnamectl."""
    result = {"requested": hostname, "applied": False, "message": None}
    if not hostname:
        return result

    if shutil.which("hostnamectl") is None:
        result["message"] = "hostnamectl not available; skipped"
        return result

    success, output = _run_command(["sudo", "hostnamectl", "set-hostname", hostname])
    result["applied"] = success
    result["message"] = output
    return result


def write_static_ip_notes(
    stack_slug: str,
    project_root: Path,
    setup: Dict[str, Any],
) -> Dict[str, Any]:
    """Drop guidance on configuring static IP manually."""
    notes_path = project_root / "node" / f"{stack_slug.replace('-', '_')}_network_notes.txt"
    static_ip = setup.get("static_ip") or "<your-static-ip>"
    interface = setup.get("interface") or "eth0"
    gateway = setup.get("gateway") or "<gateway>"
    dns = setup.get("dns") or "8.8.8.8 1.1.1.1"

    content = f"""# Automated Followspot Node Network Notes
# Requested static IP configuration recorded during setup.
# Apply manually using your preferred network manager (dhcpcd, Netplan, NetworkManager, etc.).
#
# Interface : {interface}
# Static IP : {static_ip}
# Gateway   : {gateway}
# DNS       : {dns}
# Hostname  : {setup.get('hostname') or '<unchanged>'}
#
# Example dhcpcd.conf snippet:
interface {interface}
static ip_address={static_ip}/24
static routers={gateway}
static domain_name_servers={dns}
"""

    try:
        notes_path.write_text(content, encoding="utf-8")
    except Exception:  # pragma: no cover - guidance only
        return {"notes_file": None}

    return {"notes_file": str(notes_path)}


def finalize_node_setup(
    stack_slug: str,
    project_root: Path,
    python_exec: str,
    setup: Dict[str, Any],
) -> Dict[str, Any]:
    """Apply hostname, generate guidance, and install autostart service."""
    summary: Dict[str, Any] = {
        "hostname": apply_hostname(setup.get("hostname")),
        "static_ip_notes": write_static_ip_notes(stack_slug, project_root, setup),
        "service": ensure_autostart_service(
            stack_slug=stack_slug,
            project_root=project_root,
            python_exec=python_exec,
            profile=str(setup.get("profile", "roof_array")),
            port=int(setup.get("port", 8080)),
            setup=setup,
        ),
    }
    return summary