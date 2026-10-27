#!/usr/bin/env python3
"""Unified production camera-rig configurator for roof and front arrays."""
from __future__ import annotations

import json
import os
import shutil
import socket
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from typing import Any, Dict, Optional

import cv2
from PIL import Image, ImageTk

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "config"


def _read_json(path: Path, fallback: Dict[str, Any]) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, dict) else fallback
    except (OSError, ValueError):
        return fallback


def _write_json(path: Path, value: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2)
        handle.write("\n")
    os.replace(temporary, path)


class CameraRigConfigurator:
    """One operator surface for the complete camera rig."""

    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("Camera Rig Configurator")
        self.root.geometry("1120x760")
        self.root.minsize(920, 620)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.bind("<Command-s>", lambda _event: self.save())
        self.root.bind("<Control-s>", lambda _event: self.save())

        self.roof_path = CONFIG_DIR / "roof_array_config.json"
        self.front_path = CONFIG_DIR / "front_array_config.json"
        self.roof = _read_json(self.roof_path, {"grid_config": {}, "cameras": []})
        self.front = _read_json(self.front_path, {})
        self.dirty = False
        self.show_lock = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Ready")
        self.roof_selection: Optional[int] = None
        self.camera_states: Dict[str, str] = {}
        self.roof_grid_window: Optional[tk.Toplevel] = None
        self.front_view_window: Optional[tk.Toplevel] = None
        self.front_view_label: Optional[ttk.Label] = None
        self.front_view_status: Optional[tk.StringVar] = None
        self.front_capture = None
        self.front_view_running = False

        self._ensure_defaults()
        self._build_menu()
        self._build_ui()
        self._refresh_roof_list()
        self._load_front_fields()
        self._update_dirty_state()
        self.root.after(400, self.check_all_connections)

    def _ensure_defaults(self) -> None:
        grid = self.roof.setdefault("grid_config", {})
        grid.setdefault("cameras_per_row", 4)
        grid.setdefault("total_cameras", len(self.roof.get("cameras", [])))
        grid.setdefault("cell_width", 320)
        grid.setdefault("cell_height", 240)
        grid.setdefault("auto_arrange", True)
        camera = self.front.setdefault("camera", {}).setdefault("front_camera", {})
        camera.setdefault("camera_id", "front")
        camera.setdefault("server_url", "http://192.168.0.50:8000")
        camera.setdefault("protocol", "webrtc")
        camera.setdefault("resolution", [1920, 1080])
        self.front.setdefault("performance", {}).setdefault("target_fps", 15)
        self.front.setdefault("performance", {}).setdefault("confidence_threshold", 0.6)
        self.front.setdefault("stage_geometry", {}).setdefault("width", 16.0)
        self.front.setdefault("stage_geometry", {}).setdefault("depth", 16.0)

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="Save Camera Rig", command=self.save, accelerator="Cmd-S")
        file_menu.add_command(label="Validate Configuration", command=self.validate_and_report)
        file_menu.add_separator()
        file_menu.add_command(label="Close", command=self.close)
        menubar.add_cascade(label="File", menu=file_menu)
        tools = tk.Menu(menubar, tearoff=False)
        tools.add_command(label="Check All Camera Connections", command=self.check_all_connections)
        tools.add_command(label="Auto-arrange Roof Array", command=self.auto_arrange)
        menubar.add_cascade(label="Tools", menu=tools)
        self.root.configure(menu=menubar)

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=18)
        outer.pack(fill="both", expand=True)
        outer.rowconfigure(1, weight=1)
        outer.columnconfigure(0, weight=1)

        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky="ew", pady=(0, 14))
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Camera Rig", font=("SF Pro Display", 22, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(header, text="Roof array, front ReID camera, and show-safe connection checks", foreground="#666666").grid(row=1, column=0, sticky="w")
        ttk.Checkbutton(header, text="Show lock", variable=self.show_lock).grid(row=0, column=1, rowspan=2, padx=12)
        ttk.Button(header, text="Save Changes", command=self.save).grid(row=0, column=2, rowspan=2, padx=(0, 8))
        ttk.Button(header, text="Validate", command=self.validate_and_report).grid(row=0, column=3, rowspan=2)

        self.notebook = ttk.Notebook(outer)
        self.notebook.grid(row=1, column=0, sticky="nsew")
        self._build_roof_tab()
        self._build_front_tab()
        self._build_health_tab()

        footer = ttk.Frame(outer)
        footer.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.status_var).grid(row=0, column=0, sticky="w")
        ttk.Label(footer, text="Cmd/Ctrl-S saves both camera configurations", foreground="#777777").grid(row=0, column=1, sticky="e")

    def _build_roof_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=16)
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(1, weight=1)
        self.notebook.add(tab, text="Roof Array")
        grid = ttk.LabelFrame(tab, text="Array layout", padding=12)
        grid.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        self.roof_grid_vars = {
            "cameras_per_row": tk.StringVar(),
            "cell_width": tk.StringVar(),
            "cell_height": tk.StringVar(),
        }
        for col, (key, label) in enumerate((("cameras_per_row", "Cameras / row"), ("cell_width", "Cell width"), ("cell_height", "Cell height"))):
            ttk.Label(grid, text=label).grid(row=0, column=col * 2, sticky="w", padx=(0, 6))
            ttk.Entry(grid, textvariable=self.roof_grid_vars[key], width=9).grid(row=0, column=col * 2 + 1, padx=(0, 18))
        ttk.Button(grid, text="Auto-arrange", command=self.auto_arrange).grid(row=0, column=6, padx=(0, 8))
        ttk.Button(grid, text="Pop-out grid", command=self.open_roof_grid).grid(row=0, column=7)

        list_frame = ttk.LabelFrame(tab, text="Cameras", padding=10)
        list_frame.grid(row=1, column=0, sticky="nsew", padx=(0, 12))
        list_frame.rowconfigure(0, weight=1)
        self.roof_tree = ttk.Treeview(list_frame, columns=("id", "url", "state"), show="headings", height=16)
        for column, heading, width in (("id", "ID", 100), ("url", "Endpoint", 250), ("state", "Online", 80)):
            self.roof_tree.heading(column, text=heading)
            self.roof_tree.column(column, width=width, anchor="w")
        self.roof_tree.grid(row=0, column=0, sticky="nsew")
        self.roof_tree.bind("<<TreeviewSelect>>", self._select_roof_camera)
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.roof_tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.roof_tree.configure(yscrollcommand=scroll.set)
        actions = ttk.Frame(list_frame)
        actions.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ttk.Button(actions, text="Add", command=self.add_roof_camera).pack(side="left")
        ttk.Button(actions, text="Remove", command=self.remove_roof_camera).pack(side="left", padx=6)
        ttk.Button(actions, text="Check selected", command=self.check_selected_roof).pack(side="left")

        edit = ttk.LabelFrame(tab, text="Selected camera", padding=14)
        edit.grid(row=1, column=1, sticky="nsew")
        edit.columnconfigure(1, weight=1)
        self.roof_id_var = tk.StringVar()
        self.roof_url_var = tk.StringVar()
        self.roof_enabled_var = tk.BooleanVar(value=True)
        for row, label, variable in ((0, "Camera ID", self.roof_id_var), (1, "Server URL", self.roof_url_var)):
            ttk.Label(edit, text=label).grid(row=row, column=0, sticky="w", pady=7)
            ttk.Entry(edit, textvariable=variable, width=42).grid(row=row, column=1, sticky="ew", padx=(14, 0), pady=7)
        ttk.Checkbutton(edit, text="Enabled for show", variable=self.roof_enabled_var, command=self._mark_dirty).grid(row=2, column=1, sticky="w", pady=7)
        ttk.Label(edit, text="Position and crop are managed by Auto-arrange and Auto-crop in the legacy editor.", wraplength=390, foreground="#666666").grid(row=3, column=0, columnspan=2, sticky="w", pady=(18, 0))
        ttk.Button(edit, text="Apply camera fields", command=self._apply_roof_fields).grid(row=4, column=1, sticky="e", pady=(20, 0))

    def _build_front_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=22)
        tab.columnconfigure(1, weight=1)
        self.notebook.add(tab, text="Front ReID")
        self.front_vars = {key: tk.StringVar() for key in ("server_url", "protocol", "width", "height", "target_fps", "confidence", "stage_width", "stage_depth")}
        fields = (("Camera endpoint", "server_url"), ("Protocol", "protocol"), ("Width", "width"), ("Height", "height"), ("Target FPS", "target_fps"), ("Detection confidence", "confidence"), ("Stage width (m)", "stage_width"), ("Stage depth (m)", "stage_depth"))
        for row, (label, key) in enumerate(fields):
            ttk.Label(tab, text=label).grid(row=row, column=0, sticky="w", pady=8)
            if key == "protocol":
                ttk.Combobox(tab, textvariable=self.front_vars[key], values=("webrtc", "rtsp"), state="readonly", width=18).grid(row=row, column=1, sticky="w", padx=18)
            else:
                ttk.Entry(tab, textvariable=self.front_vars[key], width=36).grid(row=row, column=1, sticky="w", padx=18)
        self.front_status_var = tk.StringVar(value="Unknown")
        ttk.Label(tab, text="Camera status").grid(row=8, column=0, sticky="w", pady=(20, 0))
        ttk.Label(tab, textvariable=self.front_status_var).grid(row=8, column=1, sticky="w", padx=18, pady=(20, 0))
        ttk.Label(tab, text="Production view", foreground="#666666").grid(row=9, column=0, sticky="w", pady=10)
        ttk.Button(tab, text="Open front camera view", command=self.open_front_view).grid(row=9, column=1, sticky="w", padx=18, pady=10)
        ttk.Label(tab, text="This is the only camera view window. The roof array uses the separate scaled grid pop-out.", wraplength=560, foreground="#666666").grid(row=10, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Button(tab, text="Apply front camera fields", command=self._apply_front_fields).grid(row=11, column=1, sticky="e", pady=(20, 0))

    def _build_health_tab(self) -> None:
        tab = ttk.Frame(self.notebook, padding=22)
        tab.columnconfigure(0, weight=1)
        self.notebook.add(tab, text="Show Check")
        ttk.Label(tab, text="Pre-show readiness", font=("SF Pro Display", 16, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(tab, text="Run checks before opening the house. A failed check does not change configuration.", foreground="#666666").grid(row=1, column=0, sticky="w", pady=(4, 18))
        self.health_text = tk.Text(tab, height=16, width=88, state="disabled", relief="flat", background="#f5f5f5")
        self.health_text.grid(row=2, column=0, sticky="nsew")
        tab.rowconfigure(2, weight=1)
        ttk.Button(tab, text="Run camera checks", command=self.check_all_connections).grid(row=3, column=0, sticky="e", pady=(14, 0))

    def _load_front_fields(self) -> None:
        camera = self.front["camera"]["front_camera"]
        performance = self.front["performance"]
        stage = self.front["stage_geometry"]
        values = {"server_url": camera.get("server_url", ""), "protocol": camera.get("protocol", "webrtc"), "width": camera.get("resolution", [1920, 1080])[0], "height": camera.get("resolution", [1920, 1080])[1], "target_fps": performance.get("target_fps", 15), "confidence": performance.get("confidence_threshold", 0.6), "stage_width": stage.get("width", 16), "stage_depth": stage.get("depth", 16)}
        for key, value in values.items():
            self.front_vars[key].set(str(value))

    def _refresh_roof_list(self) -> None:
        for item in self.roof_tree.get_children():
            self.roof_tree.delete(item)
        for index, camera in enumerate(self.roof.get("cameras", [])):
            camera_id = str(camera.get("camera_id", f"Cam {index + 1}"))
            state = self.camera_states.get(camera_id, "Unknown") if camera.get("enabled", True) else "Disabled"
            self.roof_tree.insert("", "end", iid=str(index), values=(camera_id, camera.get("server_url", ""), state))
        self.roof["grid_config"]["total_cameras"] = len(self.roof.get("cameras", []))
        for key, value in self.roof["grid_config"].items():
            if key in self.roof_grid_vars:
                self.roof_grid_vars[key].set(str(value))
        if self.roof_grid_window is not None and self.roof_grid_window.winfo_exists():
            self._render_roof_grid()

    def open_roof_grid(self) -> None:
        """Open one compact spatial model of the roof camera array."""
        if self.roof_grid_window is not None and self.roof_grid_window.winfo_exists():
            self.roof_grid_window.deiconify()
            self.roof_grid_window.lift()
            self._render_roof_grid()
            return
        self.roof_grid_window = tk.Toplevel(self.root)
        self.roof_grid_window.title("Roof Camera Grid")
        self.roof_grid_window.geometry("780x540")
        self.roof_grid_window.minsize(520, 360)
        self.roof_grid_window.protocol("WM_DELETE_WINDOW", self._close_roof_grid)
        frame = ttk.Frame(self.roof_grid_window, padding=16)
        frame.pack(fill="both", expand=True)
        frame.rowconfigure(1, weight=1)
        frame.columnconfigure(0, weight=1)
        ttk.Label(frame, text="Roof camera layout", font=("SF Pro Display", 16, "bold")).grid(row=0, column=0, sticky="w")
        self.roof_grid_canvas = tk.Canvas(frame, background="#eef1f5", highlightthickness=0)
        self.roof_grid_canvas.grid(row=1, column=0, sticky="nsew", pady=(12, 0))
        self._render_roof_grid()

    def _render_roof_grid(self) -> None:
        if not hasattr(self, "roof_grid_canvas") or not self.roof_grid_canvas.winfo_exists():
            return
        canvas = self.roof_grid_canvas
        canvas.delete("all")
        cameras = self.roof.get("cameras", [])
        if not cameras:
            canvas.create_text(20, 20, anchor="nw", text="No roof cameras configured", fill="#555555")
            return
        try:
            per_row = max(1, int(self.roof["grid_config"].get("cameras_per_row", 4)))
        except (TypeError, ValueError):
            per_row = 4
        columns = min(per_row, max(1, len(cameras)))
        rows = (len(cameras) + columns - 1) // columns
        width = max(520, canvas.winfo_width())
        height = max(300, canvas.winfo_height())
        tile_width = max(120, (width - 24 - (columns - 1) * 10) // columns)
        tile_height = max(78, (height - 24 - (rows - 1) * 10) // rows)
        for index, camera in enumerate(cameras):
            row, column = divmod(index, columns)
            x0 = 12 + column * (tile_width + 10)
            y0 = 12 + row * (tile_height + 10)
            x1, y1 = x0 + tile_width, y0 + tile_height
            camera_id = str(camera.get("camera_id", f"Cam {index + 1}"))
            state = self.camera_states.get(camera_id, "Unknown")
            color = {"Online": "#2e9d62", "Offline": "#cf4b4b", "Disabled": "#969da6"}.get(state, "#c68a2c")
            canvas.create_rectangle(x0, y0, x1, y1, fill="#ffffff", outline="#c9ced6", width=1)
            canvas.create_rectangle(x0, y0, x0 + 6, y1, fill=color, outline=color)
            canvas.create_text(x0 + 16, y0 + 16, anchor="w", text=camera_id, fill="#18212b", font=("SF Pro Text", 11, "bold"))
            canvas.create_oval(x1 - 30, y0 + 10, x1 - 18, y0 + 22, fill=color, outline=color)
            canvas.create_text(x0 + 16, y0 + 40, anchor="w", text=state, fill="#59636e", font=("SF Pro Text", 10))
            canvas.create_text(x0 + 16, y1 - 14, anchor="w", text=str(camera.get("server_url", "")), fill="#7a838d", font=("SF Pro Text", 8))

    def _close_roof_grid(self) -> None:
        if self.roof_grid_window is not None:
            self.roof_grid_window.destroy()
        self.roof_grid_window = None

    def _select_roof_camera(self, _event=None) -> None:
        selection = self.roof_tree.selection()
        if not selection:
            return
        self.roof_selection = int(selection[0])
        camera = self.roof["cameras"][self.roof_selection]
        self.roof_id_var.set(str(camera.get("camera_id", "")))
        self.roof_url_var.set(str(camera.get("server_url", "")))
        self.roof_enabled_var.set(bool(camera.get("enabled", True)))

    def _apply_roof_fields(self) -> None:
        if self.roof_selection is None:
            return
        camera = self.roof["cameras"][self.roof_selection]
        camera.update({"camera_id": self.roof_id_var.get().strip(), "server_url": self.roof_url_var.get().strip(), "enabled": self.roof_enabled_var.get()})
        self._refresh_roof_list()
        self._mark_dirty()

    def _apply_front_fields(self) -> bool:
        try:
            width, height = int(self.front_vars["width"].get()), int(self.front_vars["height"].get())
            fps = int(self.front_vars["target_fps"].get())
            confidence = float(self.front_vars["confidence"].get())
            stage_width, stage_depth = float(self.front_vars["stage_width"].get()), float(self.front_vars["stage_depth"].get())
            if min(width, height, fps, stage_width, stage_depth) <= 0 or not 0 < confidence <= 1:
                raise ValueError
        except ValueError:
            messagebox.showerror("Invalid front camera values", "Resolution, FPS, stage dimensions, and confidence must be valid positive values.")
            return False
        camera = self.front["camera"]["front_camera"]
        camera.update({"server_url": self.front_vars["server_url"].get().strip(), "protocol": self.front_vars["protocol"].get(), "resolution": [width, height]})
        self.front["performance"].update({"target_fps": fps, "confidence_threshold": confidence, "detection_resolution": [width, height]})
        self.front["stage_geometry"].update({"width": stage_width, "depth": stage_depth})
        self._mark_dirty()
        self.status_var.set("Front camera fields applied")
        return True

    def add_roof_camera(self) -> None:
        index = len(self.roof.get("cameras", [])) + 1
        self.roof.setdefault("cameras", []).append({"camera_id": f"Cam {index}", "server_url": "http://", "crop_rect": [0, 0, 320, 240], "position": [0, 0], "enabled": True, "auto_crop": True, "overlap_threshold": 0.1})
        self._refresh_roof_list()
        self._mark_dirty()

    def remove_roof_camera(self) -> None:
        if self.roof_selection is None:
            return
        if not messagebox.askyesno("Remove camera", "Remove this camera from the roof array?"):
            return
        self.roof["cameras"].pop(self.roof_selection)
        self.roof_selection = None
        self._refresh_roof_list()
        self._mark_dirty()

    def auto_arrange(self) -> None:
        try:
            per_row = max(1, int(self.roof_grid_vars["cameras_per_row"].get()))
        except ValueError:
            messagebox.showerror("Invalid layout", "Cameras per row must be a positive integer.")
            return
        for index, camera in enumerate(self.roof.get("cameras", [])):
            camera["position"] = [index % per_row, index // per_row]
        self.roof["grid_config"].update({"cameras_per_row": per_row, "total_cameras": len(self.roof.get("cameras", [])), "auto_arrange": True})
        self._refresh_roof_list()
        self._mark_dirty()

    def _validate(self) -> list[str]:
        errors: list[str] = []
        if not self.roof.get("cameras"):
            errors.append("Roof array has no cameras")
        ids = set()
        for index, camera in enumerate(self.roof.get("cameras", []), 1):
            camera_id = str(camera.get("camera_id", "")).strip()
            url = str(camera.get("server_url", "")).strip()
            if not camera_id or camera_id in ids:
                errors.append(f"Roof camera {index}: missing or duplicate ID")
            ids.add(camera_id)
            if not url.startswith(("http://", "https://")):
                errors.append(f"Roof camera {index}: endpoint must start with http:// or https://")
        if not self.front_vars["server_url"].get().strip().startswith(("http://", "https://")):
            errors.append("Front camera endpoint must start with http:// or https://")
        return errors

    def validate_and_report(self) -> bool:
        self._apply_roof_fields()
        if not self._apply_front_fields():
            return False
        errors = self._validate()
        if errors:
            self.status_var.set(f"Validation failed: {len(errors)} issue(s)")
            messagebox.showerror("Configuration needs attention", "\n".join(f"• {error}" for error in errors))
            return False
        self.status_var.set("Configuration is ready for a show")
        messagebox.showinfo("Configuration valid", "Camera rig configuration passed validation.")
        return True

    def save(self) -> None:
        if self.show_lock.get():
            messagebox.showwarning("Show lock enabled", "Disable Show lock before changing camera configuration.")
            return
        self._apply_roof_fields()
        if not self._apply_front_fields():
            return
        if not self._validate():
            self.validate_and_report()
            return
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        for path in (self.roof_path, self.front_path):
            if path.exists():
                shutil.copy2(path, path.with_suffix(path.suffix + f".bak.{stamp}"))
        self.roof["last_updated"] = datetime.now().isoformat()
        self.front["last_updated"] = datetime.now().isoformat()
        _write_json(self.roof_path, self.roof)
        _write_json(self.front_path, self.front)
        self.dirty = False
        self.status_var.set(f"Saved at {datetime.now().strftime('%H:%M:%S')}")

    def _mark_dirty(self) -> None:
        self.dirty = True
        self._update_dirty_state()

    def _update_dirty_state(self) -> None:
        if self.dirty:
            self.status_var.set("Unsaved camera changes")

    def check_selected_roof(self) -> None:
        if self.roof_selection is None:
            return
        self._check_url(self.roof["cameras"][self.roof_selection].get("server_url", ""), self.roof["cameras"][self.roof_selection].get("camera_id", "Camera"))

    def open_front_view(self) -> None:
        """Open the one front-camera view window and reuse it on repeat clicks."""
        if self.front_view_window is not None and self.front_view_window.winfo_exists():
            self.front_view_window.deiconify()
            self.front_view_window.lift()
            return
        self.front_view_window = tk.Toplevel(self.root)
        self.front_view_window.title("Front Camera View")
        self.front_view_window.geometry("860x560")
        self.front_view_window.protocol("WM_DELETE_WINDOW", self._close_front_view)
        container = ttk.Frame(self.front_view_window, padding=12)
        container.pack(fill="both", expand=True)
        container.rowconfigure(0, weight=1)
        container.columnconfigure(0, weight=1)
        self.front_view_label = ttk.Label(container, text="Connecting to front camera...", anchor="center")
        self.front_view_label.grid(row=0, column=0, sticky="nsew")
        self.front_view_status = tk.StringVar(value=self.front_vars["server_url"].get())
        ttk.Label(container, textvariable=self.front_view_status, foreground="#666666").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.front_view_running = True
        threading.Thread(target=self._front_view_worker, daemon=True).start()

    def _front_view_worker(self) -> None:
        url = self.front_vars["server_url"].get().strip()
        capture = cv2.VideoCapture(url)
        self.front_capture = capture
        if not capture.isOpened():
            self.root.after(0, self._set_front_view_status, "No direct video stream at endpoint; use WebRTC live mode for the production feed.")
            capture.release()
            self.front_capture = None
            return
        self.root.after(0, self._set_front_view_status, "Online")
        while self.front_view_running:
            ok, frame = capture.read()
            if not ok:
                self.root.after(0, self._set_front_view_status, "Stream interrupted")
                break
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            image = Image.fromarray(frame)
            image.thumbnail((820, 480), Image.Resampling.LANCZOS)
            photo = ImageTk.PhotoImage(image)
            self.root.after(0, self._show_front_frame, photo)
            time.sleep(0.03)
        capture.release()
        self.front_capture = None

    def _show_front_frame(self, photo: ImageTk.PhotoImage) -> None:
        if self.front_view_label is not None and self.front_view_label.winfo_exists():
            self.front_view_label.configure(image=photo, text="")
            self.front_view_label.image = photo

    def _set_front_view_status(self, status: str) -> None:
        self.front_status_var.set(status)
        if self.front_view_status is not None:
            self.front_view_status.set(status)

    def _close_front_view(self) -> None:
        self.front_view_running = False
        if self.front_capture is not None:
            self.front_capture.release()
        if self.front_view_window is not None:
            self.front_view_window.destroy()
        self.front_view_window = None
        self.front_view_label = None
        self.front_view_status = None

    def check_all_connections(self) -> None:
        urls = [(camera.get("server_url", ""), camera.get("camera_id", "Roof camera")) for camera in self.roof.get("cameras", []) if camera.get("enabled", True)]
        urls.append((self.front_vars["server_url"].get(), "Front camera"))
        self.health_text.configure(state="normal")
        self.health_text.delete("1.0", "end")
        self.health_text.insert("end", "Checking camera endpoints...\n\n")
        self.health_text.configure(state="disabled")
        self.camera_states.update({name: "Checking" for _, name in urls})
        self._refresh_roof_list()
        if self.roof_grid_window is not None and self.roof_grid_window.winfo_exists():
            self._render_roof_grid()
        self.front_status_var.set("Checking")
        threading.Thread(target=self._check_urls_worker, args=(urls,), daemon=True).start()

    def _check_urls_worker(self, urls) -> None:
        results = []
        with ThreadPoolExecutor(max_workers=max(1, len(urls))) as executor:
            pending = {
                executor.submit(self._probe, url, name): name
                for url, name in urls
            }
            for future in as_completed(pending):
                name = pending[future]
                try:
                    result = future.result()
                except Exception as exc:
                    result = f"FAIL  {name}: {exc}"
                results.append(result)
                self.root.after(0, self._apply_camera_check_result, name, result)
        self.root.after(0, self._show_health_results, results)

    def _apply_camera_check_result(self, name: str, result: str) -> None:
        state = "Online" if result.startswith("PASS") else "Offline"
        self.camera_states[name] = state
        if name == "Front camera":
            self.front_status_var.set(state)
        self._refresh_roof_list()
        if self.roof_grid_window is not None and self.roof_grid_window.winfo_exists():
            self._render_roof_grid()
        self.health_text.configure(state="normal")
        self.health_text.insert("end", result + "\n")
        self.health_text.see("end")
        self.health_text.configure(state="disabled")

    @staticmethod
    def _probe(url: str, name: str) -> str:
        try:
            request = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(request, timeout=2.0) as response:
                return f"PASS  {name}: HTTP {response.status}"
        except (urllib.error.URLError, ValueError, TimeoutError, OSError) as exc:
            return f"FAIL  {name}: {exc}"

    def _show_health_results(self, results: list[str]) -> None:
        self.health_text.configure(state="normal")
        self.health_text.delete("1.0", "end")
        self.health_text.insert("end", "\n".join(results) + "\n")
        self.health_text.configure(state="disabled")
        self._refresh_roof_list()
        if self.roof_grid_window is not None and self.roof_grid_window.winfo_exists():
            self._render_roof_grid()
        passed = sum(result.startswith("PASS") for result in results)
        self.status_var.set(f"Camera check complete: {passed}/{len(results)} reachable")

    def _check_url(self, url: str, name: str) -> None:
        result = self._probe(url, name)
        messagebox.showinfo("Camera check", result)

    def close(self) -> None:
        if self.dirty and not messagebox.askyesno("Unsaved changes", "Discard unsaved camera changes?"):
            return
        self._close_front_view()
        self._close_roof_grid()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    CameraRigConfigurator().run()


if __name__ == "__main__":
    main()
