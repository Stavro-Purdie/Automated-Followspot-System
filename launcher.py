#!/usr/bin/env python3
"""Command-line launcher for the Automated Followspot System.

The GUI launcher still lives in ``launcher_gui.py``.  This module focuses on
headless and embedded deployments, providing a text-based operations console
with direct commands for installing the control, roof node, and front truss
node stacks.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from node import setup_utils

PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = PROJECT_ROOT / "launcher_config.json"

DEFAULT_CONFIG: Dict[str, Any] = {
    "system_info": {
        "version": "1.0.0",
        "last_updated": None,
        "os_info": platform.platform(),
        "installation_path": str(PROJECT_ROOT),
    },
    "installations": {
        "control_stack": {
            "installed": False,
            "version": None,
            "install_date": None,
            "dependencies_verified": False,
            "last_dependency_check": None,
            "cron_enabled": False,
        },
        "node_stack": {
            "installed": False,
            "version": None,
            "install_date": None,
            "dependencies_verified": False,
            "last_dependency_check": None,
            "cron_enabled": False,
        },
        "front_node_stack": {
            "installed": False,
            "version": None,
            "install_date": None,
            "dependencies_verified": False,
            "last_dependency_check": None,
        },
    },
    "settings": {
        "auto_dependency_check": True,
        "check_interval_days": 7,
        "allow_concurrent_stacks": False,
        "debug_mode": False,
    },
    "update_settings": {
        "release_channel": "stable",
        "auto_check": True,
        "check_interval_hours": 12,
        "auto_update_nodes": False,
        "branches": {
            "main": {
                "last_remote": None,
                "last_prompted": None,
                "last_applied": None,
                "last_node_applied": None,
                "last_checked": None,
            },
            "testing": {
                "last_remote": None,
                "last_prompted": None,
                "last_applied": None,
                "last_node_applied": None,
                "last_checked": None,
            },
        },
    },
}

STACK_METADATA = {
    "control": {
        "label": "Control Stack",
        "requirements": PROJECT_ROOT / "control" / "requirements.txt",
        "config_key": "control_stack",
    },
    "node": {
        "label": "Roof Node Stack",
        "requirements": PROJECT_ROOT / "node" / "requirements.txt",
        "config_key": "node_stack",
    },
    "front-node": {
        "label": "Front Truss Node Stack",
        "requirements": PROJECT_ROOT / "node" / "requirements.txt",
        "config_key": "front_node_stack",
    },
}

INDUSTRIAL_DIVIDER = "#" * 65
_GUI_AVAILABLE_CACHE: Optional[bool] = None


def load_config() -> Dict[str, Any]:
    """Load launcher configuration, merging with defaults when needed."""
    config = deepcopy(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            with CONFIG_PATH.open("r", encoding="utf-8") as handle:
                existing = json.load(handle)
        except json.JSONDecodeError as exc:
            print(f"[CONFIG] Failed to parse launcher_config.json: {exc}. Using defaults.")
            return config
        except Exception as exc:
            print(f"[CONFIG] Unable to load configuration: {exc}. Using defaults.")
            return config

        def deep_merge(dst: Dict[str, Any], src: Dict[str, Any]) -> Dict[str, Any]:
            for key, value in src.items():
                if isinstance(value, dict) and isinstance(dst.get(key), dict):
                    deep_merge(dst[key], value)
                else:
                    dst[key] = value
            return dst

        deep_merge(config, existing)
    else:
        config["system_info"]["last_updated"] = datetime.now().isoformat()
    return config


def save_config(config: Dict[str, Any]) -> None:
    """Persist configuration to disk."""
    try:
        with CONFIG_PATH.open("w", encoding="utf-8") as handle:
            json.dump(config, handle, indent=2)
    except Exception as exc:
        print(f"[CONFIG] Failed to save configuration: {exc}")


def gui_available() -> bool:
    global _GUI_AVAILABLE_CACHE
    if _GUI_AVAILABLE_CACHE is not None:
        return _GUI_AVAILABLE_CACHE

    if sys.platform.startswith("linux"):
        if not (
            os.environ.get("DISPLAY")
            or os.environ.get("WAYLAND_DISPLAY")
            or os.environ.get("MIR_SOCKET")
        ):
            _GUI_AVAILABLE_CACHE = False
            return _GUI_AVAILABLE_CACHE

    try:
        import tkinter as tk  # Local import to avoid hard dependency at module import

        root = tk.Tk()
        root.withdraw()
        root.update_idletasks()
        root.destroy()
    except Exception:
        _GUI_AVAILABLE_CACHE = False
    else:
        _GUI_AVAILABLE_CACHE = True

    return _GUI_AVAILABLE_CACHE


def collect_node_setup_cli(config_section: Dict[str, Any], stack_slug: str) -> Dict[str, Any]:
    defaults = config_section.get("node_setup", {}) if config_section else {}
    profile_defaults = {
        "node": {
            "camera_device": "imx219",
            "port": 8080,
        },
        "front-node": {
            "camera_device": "imx477",
            "port": 8000,
        },
    }
    prof_def = profile_defaults.get(stack_slug, {})

    print(INDUSTRIAL_DIVIDER)
    print("#  NODE SETUP CONFIGURATION")
    print("#  Leave fields blank to skip; values are stored for documentation.")

    static_ip = input(
        f"Static IP address [{defaults.get('static_ip', '') or 'skip'}]: "
    ).strip() or defaults.get("static_ip")
    hostname = input(
        f"Hostname [{defaults.get('hostname', '') or 'skip'}]: "
    ).strip() or defaults.get("hostname")
    camera_device = input(
        f"Camera device ({prof_def.get('camera_device', 'sensor id or /dev path')}): "
    ).strip() or defaults.get("camera_device") or prof_def.get("camera_device")
    interface = input(
        f"Network interface [{defaults.get('interface', 'eth0')}]: "
    ).strip() or defaults.get("interface") or "eth0"
    gateway = input(
        f"Default gateway [{defaults.get('gateway', '') or 'skip'}]: "
    ).strip() or defaults.get("gateway")
    dns = input(
        f"DNS servers (space separated) [{defaults.get('dns', '') or 'skip'}]: "
    ).strip() or defaults.get("dns")
    default_port_display = defaults.get('port') or prof_def.get('port', 8080)
    port_input = input(
        f"Node service port [{default_port_display}]: "
    ).strip()

    try:
        port = int(port_input) if port_input else int(defaults.get("port") or prof_def.get("port", 8080))
    except ValueError:
        fallback_port = prof_def.get("port", 8080)
        print(f"Invalid port provided. Using default {fallback_port}.")
        port = int(fallback_port)

    setup = {
        "static_ip": static_ip,
        "hostname": hostname,
        "camera_device": camera_device,
        "interface": interface,
        "gateway": gateway,
        "dns": dns,
        "port": port,
    }

    return setup


def industrial_header(title: str = "OPERATIONS CONSOLE") -> str:
    """Return a chunky ASCII banner for the CLI surface."""
    block = [
        INDUSTRIAL_DIVIDER,
        "#  AUTOMATED FOLLOWSPOT SYSTEM // {}".format(title.ljust(33)[:33]),
        "#  [CTRL] [ROOF NODE] [FRONT TRUSS NODE]",
        "#  Weapons-Grade Lighting Automation Interface",
        INDUSTRIAL_DIVIDER,
    ]
    return "\n".join(block)


def industrial_status(config: Dict[str, Any]) -> str:
    installations = config.get("installations", {})
    lines = ["#  STACK STATUS CHECKPOINT"]
    for slug, meta in (
        ("control", "Control Stack"),
        ("node", "Roof Node Stack"),
        ("front-node", "Front Truss Node"),
    ):
        key = STACK_METADATA[slug]["config_key"]
        info = installations.get(key, {})
        status = "ONLINE" if info.get("installed") else "OFFLINE"
        timestamp = info.get("install_date") or "--"
        lines.append(f"#   - {meta:<24} : {status:<7} :: {timestamp}")
    lines.append(INDUSTRIAL_DIVIDER)
    return "\n".join(lines)


def run_pip_install(requirements_file: Path) -> bool:
    """Install dependencies listed in the provided requirements file."""
    if not requirements_file.exists():
        print(f"[INSTALL] Requirements file missing: {requirements_file}")
        return False

    cmd = [sys.executable, "-m", "pip", "install", "-r", str(requirements_file)]
    print(f"[INSTALL] Executing: {' '.join(cmd)}")

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        universal_newlines=True,
    )

    assert process.stdout is not None
    for line in process.stdout:
        print(f"[pip] {line.rstrip()}")

    process.wait()
    if process.returncode != 0:
        print(f"[INSTALL] Pip exited with code {process.returncode}")
        return False

    print("[INSTALL] Base dependencies installed.")

    # Ensure certifi is present for TLS operations in updater and REST clients.
    cert_cmd = [sys.executable, "-m", "pip", "install", "certifi"]
    print(f"[INSTALL] Verifying certifi: {' '.join(cert_cmd)}")
    cert_process = subprocess.Popen(
        cert_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        universal_newlines=True,
    )

    assert cert_process.stdout is not None
    for line in cert_process.stdout:
        print(f"[pip] {line.rstrip()}")

    cert_process.wait()
    if cert_process.returncode != 0:
        print("[INSTALL] Warning: unable to install certifi automatically.")

    return True


def flash_beacon() -> None:
    """Run the Xiao ESP32-C6 beacon flasher helper."""
    script = PROJECT_ROOT / "tools" / "beacon_flash.py"
    if not script.exists():
        print(f"[FLASH] Helper not found: {script}")
        input("Press Enter to continue...")
        return

    print(INDUSTRIAL_DIVIDER)
    print("#  BEACON FLASHER (Xiao ESP32-C6)")
    print("#  Requires: arduino-cli, esp32 core, Adafruit SSD1306/GFX libs")
    print(INDUSTRIAL_DIVIDER)

    ssid = input("Wi-Fi SSID (required): ").strip()
    password = input("Wi-Fi Password (required): ").strip()
    port = input("Serial port (e.g., /dev/tty.usbmodemXYZ or COM5): ").strip()

    if not ssid or not password or not port:
        print("[FLASH] Missing required fields; aborting.")
        input("Press Enter to continue...")
        return

    # Validate user-provided values before passing them as command arguments.
    # SSID: 1-32 printable chars, no control/newline/null bytes.
    # Password: 8-63 chars (WPA/WPA2 typical), no control/newline/null bytes.
    # Port: allowlist expected serial device formats.
    ssid_ok = (
        1 <= len(ssid) <= 32
        and "\x00" not in ssid
        and "\n" not in ssid
        and "\r" not in ssid
    )
    password_ok = (
        8 <= len(password) <= 63
        and "\x00" not in password
        and "\n" not in password
        and "\r" not in password
    )
    port_ok = bool(re.fullmatch(r"(COM[0-9]{1,3}|/dev/(tty|cu)[A-Za-z0-9._-]+)", port))

    if not ssid_ok:
        print("[FLASH] Invalid SSID format; aborting.")
        input("Press Enter to continue...")
        return
    if not password_ok:
        print("[FLASH] Invalid Wi-Fi password format; aborting.")
        input("Press Enter to continue...")
        return
    if not port_ok:
        print("[FLASH] Invalid serial port format; aborting.")
        input("Press Enter to continue...")
        return

    cmd = [
        sys.executable,
        str(script),
        "--ssid",
        ssid,
        "--password",
        password,
        "--port",
        port,
    ]

    cmd_for_log = cmd.copy()
    if "--password" in cmd_for_log:
        pwd_idx = cmd_for_log.index("--password")
        if pwd_idx + 1 < len(cmd_for_log):
            cmd_for_log[pwd_idx + 1] = "******"

    print(f"[FLASH] Executing: {' '.join(cmd_for_log)}")
    try:
        result = subprocess.run(cmd, check=True)
        print(f"[FLASH] Completed with code {result.returncode}")
    except subprocess.CalledProcessError as exc:
        print(f"[FLASH] Failed (exit {exc.returncode})")
    except Exception as exc:
        print(f"[FLASH] Error: {exc}")
    input("Press Enter to continue...")


def install_stack(stack_slug: str, config: Dict[str, Any]) -> bool:
    """Install the requested stack and update configuration metadata."""
    if stack_slug not in STACK_METADATA:
        print(f"[INSTALL] Unknown stack '{stack_slug}'.")
        return False

    meta = STACK_METADATA[stack_slug]
    print(industrial_header(f"DEPLOY {meta['label'].upper()}"))
    print(f"#  Target requirements: {meta['requirements']}")
    print(INDUSTRIAL_DIVIDER)

    config_section = config.setdefault("installations", {}).setdefault(meta["config_key"], {})
    setup_details: Optional[Dict[str, Any]] = None

    if stack_slug in {"node", "front-node"}:
        setup_details = collect_node_setup_cli(config_section, stack_slug)

    success = run_pip_install(meta["requirements"])
    if not success:
        print(f"[INSTALL] {meta['label']} deployment failed.")
        return False

    install_date = datetime.now().isoformat()
    config_section.update(
        {
            "installed": True,
            "version": "1.0.0",
            "install_date": install_date,
            "dependencies_verified": True,
            "last_dependency_check": install_date,
        }
    )

    if setup_details and stack_slug in {"node", "front-node"}:
        profile = "front_truss" if stack_slug == "front-node" else "roof_array"
        setup_details["profile"] = profile
        setup_details["configured_at"] = install_date
        setup_summary = setup_utils.finalize_node_setup(
            stack_slug=stack_slug,
            project_root=PROJECT_ROOT,
            python_exec=sys.executable,
            setup=setup_details,
        )
        config_section["node_setup"] = setup_details
        config_section["autostart"] = setup_summary

        print(INDUSTRIAL_DIVIDER)
        service_info = setup_summary.get("service", {})
        if service_info.get("enabled"):
            print(f"#  Autostart service enabled: {service_info.get('service_name')}")
        else:
            print("#  Autostart service needs manual attention.")
            if service_info.get("enable_error"):
                print(f"#   Error: {service_info['enable_error']}")
        hostname_info = setup_summary.get("hostname", {})
        if hostname_info.get("applied"):
            print("#  Hostname updated successfully.")
        elif hostname_info.get("requested"):
            print("#  Hostname change pending manual action.")
            if hostname_info.get("message"):
                print(f"#   {hostname_info['message']}")
        notes = setup_summary.get("static_ip_notes", {}).get("notes_file")
        if notes:
            print(f"#  Static IP guidance written to: {notes}")
        print(INDUSTRIAL_DIVIDER)

    save_config(config)

    print(INDUSTRIAL_DIVIDER)
    print(f"#  {meta['label']} deployment complete :: {install_date}")
    print(INDUSTRIAL_DIVIDER)
    return True


def show_status(config: Dict[str, Any]) -> None:
    print(industrial_header("SYSTEM SNAPSHOT"))
    print(industrial_status(config))


def launch_gui() -> None:
    """Defer to the Tkinter launcher."""
    from launcher_gui import LauncherGUI  # Local import to avoid Tk deps in CLI

    gui = LauncherGUI()
    gui.root.mainloop()


def clear_screen() -> None:
    command = "cls" if os.name == "nt" else "clear"
    try:
        subprocess.run(command, check=False, shell=True)
    except Exception:
        print("\n" * 3)


def interactive_cli(config: Dict[str, Any]) -> None:
    """Run the interactive operations console."""
    while True:
        clear_screen()
        print(industrial_header())
        print(industrial_status(config))
        print("#  SELECT AN OPERATION:")
        print("#    [1] Install Control Stack")
        print("#    [2] Install Roof Node Stack")
        print("#    [3] Install Front Truss Node Stack")
        print("#    [4] Show Status Report")
        print("#    [5] Launch GUI Mode")
        print("#    [6] Flash Beacon (Xiao ESP32-C6)")
        print("#    [0] Exit")
        print(INDUSTRIAL_DIVIDER)
        choice = input("COMMAND> ").strip()

        if choice == "1":
            install_stack("control", config)
        elif choice == "2":
            install_stack("node", config)
        elif choice == "3":
            install_stack("front-node", config)
        elif choice == "4":
            show_status(config)
            input("Press Enter to continue...")
        elif choice == "5":
            launch_gui()
        elif choice == "6":
            flash_beacon()
        elif choice == "0":
            print("Stand down. Returning to shell.")
            break
        else:
            print("Unrecognized command. Try again.")
            input("Press Enter to continue...")


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Automated Followspot Launcher")
    parser.add_argument(
        "-cli",
        "--cli",
        action="store_true",
        help="Start the industrial command-line launcher",
    )
    parser.add_argument(
        "--gui",
        action="store_true",
        help="Force the graphical launcher",
    )
    parser.add_argument(
        "--install-deps",
        choices=sorted(STACK_METADATA.keys()),
        help="Install dependencies for the specified stack and exit",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show installation status summary and exit",
    )
    return parser.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    config = load_config()
    has_gui = gui_available()

    if args.install_deps:
        success = install_stack(args.install_deps, config)
        return 0 if success else 1

    if args.status:
        show_status(config)
        return 0

    if args.gui and args.cli:
        print("Cannot launch both GUI and CLI simultaneously.")
        return 2

    if args.gui:
        if not has_gui:
            print("GUI environment not detected. Falling back to CLI mode.")
            interactive_cli(config)
        else:
            launch_gui()
        return 0

    if args.cli:
        interactive_cli(config)
        return 0

    # Default behaviour: fall back to GUI when available, otherwise CLI.
    if has_gui:
        try:
            launch_gui()
        except Exception as exc:
            print(f"[GUI] Unable to start GUI launcher: {exc}")
            print("Falling back to CLI mode.")
            interactive_cli(config)
    else:
        print("GUI environment not detected. Starting CLI mode.")
        interactive_cli(config)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
