#!/usr/bin/env python3
"""
Manages performer identities, including photos and meta data, for the ReID system.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import uuid
import webbrowser
import platform
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk, ImageOps

if hasattr(Image, "Resampling"):
    _LANCZOS = Image.Resampling.LANCZOS  # type: ignore[attr-defined]
else:  # pragma: no cover - compatibility for older Pillow
    _LANCZOS = Image.LANCZOS  # type: ignore[attr-defined]


def set_native_theme(style: ttk.Style) -> None:
    """Set ttk theme to match the operating system."""
    system = platform.system()
    if system == "Darwin":  # macOS
        theme = "aqua"
    elif system == "Windows":
        theme = "vista"
    else:
        theme = "clam"
    try:
        style.theme_use(theme)
    except tk.TclError:
        try:
            style.theme_use('default')
        except Exception:
            pass


class IdentityConfigurator:
    def __init__(self) -> None:
        # Project structure
        self.control_dir = Path(__file__).resolve().parent
        self.project_root = self.control_dir.parent
        self.identity_root = self.project_root / "identity_gallery"
        self.identity_root.mkdir(exist_ok=True)
        self.manifest_path = self.identity_root / "manifest.json"

        # UI root
        self.root = tk.Tk()
        self.root.title("Identity Configurator - Automated Followspot System")
        self.root.geometry("1200x780")
        self.root.minsize(1000, 640)
        self.root.configure(bg="SystemButtonFace")
        
        # Configure ttk style for native theme
        style = ttk.Style()
        set_native_theme(style)
        
        # Data models
        self.identity_data: Dict[str, List[Dict]] = {"identities": []}
        self.filtered_order: List[str] = []
        self.current_identity_id: Optional[str] = None
        self.preview_image: Optional[ImageTk.PhotoImage] = None

        # Tk variables
        self.search_var = tk.StringVar()
        self.name_var = tk.StringVar()
        self.code_var = tk.StringVar()
        self.created_var = tk.StringVar(value="—")
        self.updated_var = tk.StringVar(value="—")
        self.status_var = tk.StringVar(value="Ready")

        # Widgets initialised later
        self.identity_listbox: Optional[tk.Listbox] = None
        self.photo_listbox: Optional[tk.Listbox] = None
        self.preview_label: Optional[tk.Label] = None
        self.primary_label: Optional[ttk.Label] = None

        # Load manifest then build UI
        self.identity_data = self._load_manifest()
        self._build_ui()
        self._build_menubar()
        self.refresh_identity_list()

        # Event bindings
        self.search_var.trace_add("write", lambda *_: self.refresh_identity_list())
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_menubar(self) -> None:
        """Wire up quick navigation between identity tasks and sister tools."""
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="New Identity", command=self.create_identity)
        file_menu.add_command(label="Save Manifest", command=self._save_manifest)
        file_menu.add_command(label="Reload Manifest", command=self.refresh_identity_list)
        file_menu.add_separator()
        file_menu.add_command(label="Open Launcher", command=self._open_launcher)
        file_menu.add_separator()
        file_menu.add_command(label="Close", command=self._on_close)
        menubar.add_cascade(label="File", menu=file_menu)

        tools_menu = tk.Menu(menubar, tearoff=0)
        tools_menu.add_command(label="Import Photos", command=self.import_photos)
        tools_menu.add_command(label="Open Gallery Folder", command=self.open_identity_folder)
        tools_menu.add_command(label="Refresh List", command=self.refresh_identity_list)
        tools_menu.add_separator()
        tools_menu.add_command(
            label="Open Camera Configurator",
            command=lambda: self._launch_tool("camera_config_gui.py", "Camera Configurator"),
        )
        tools_menu.add_command(
            label="Open ReID Configurator",
            command=lambda: self._launch_tool("reid_configurator.py", "ReID Configurator"),
        )
        menubar.add_cascade(label="Tools", menu=tools_menu)

        help_menu = tk.Menu(menubar, tearoff=0)
        help_menu.add_command(
            label="Project README",
            command=lambda: webbrowser.open_new_tab(
                "https://github.com/Stavro-Purdie/Automated-Followspot-System"
            ),
        )
        help_menu.add_command(
            label="Report Issue",
            command=lambda: webbrowser.open_new_tab(
                "https://github.com/Stavro-Purdie/Automated-Followspot-System/issues/new/choose"
            ),
        )
        menubar.add_cascade(label="Help", menu=help_menu)

        self.root.config(menu=menubar)

    def _launch_tool(self, script_name: str, description: str) -> None:
        script_path = self.control_dir / script_name
        if not script_path.exists():
            messagebox.showerror("Missing Tool", f"{description} not found at:\n{script_path}")
            return
        try:
            subprocess.Popen([sys.executable, str(script_path)])
        except Exception as exc:
            messagebox.showerror("Launch Failed", f"Could not start {description}:\n{exc}")

    def _open_launcher(self) -> None:
        launcher_path = self.project_root / "launcher_gui.py"
        if not launcher_path.exists():
            messagebox.showerror("Launcher Missing", "launcher_gui.py could not be found.")
            return
        try:
            subprocess.Popen([sys.executable, str(launcher_path)])
        except Exception as exc:
            messagebox.showerror("Launcher Error", f"Failed to open launcher:\n{exc}")

    # ------------------------------------------------------------------
    # Manifest helpers
    # ------------------------------------------------------------------
    def _load_manifest(self) -> Dict:
        if not self.manifest_path.exists():
            manifest = {"identities": []}
            self._save_manifest(manifest)
            return manifest

        try:
            with open(self.manifest_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception as exc:
            messagebox.showerror("Manifest Error", f"Failed to load manifest:\n{exc}")
            return {"identities": []}

        identities: List[Dict] = []
        for entry in data.get("identities", []):
            identity = dict(entry)
            identity.setdefault("images", [])
            identity.setdefault("created_at", datetime.now().isoformat())
            identity.setdefault("updated_at", identity["created_at"])
            identity.setdefault("code", "")
            identity.setdefault("primary_image", None)
            identities.append(identity)

            # Ensure directory exists
            (self.identity_root / identity["id"]).mkdir(exist_ok=True)

        return {"identities": identities}

    def _save_manifest(self, manifest: Optional[Dict] = None) -> None:
        data = manifest or self.identity_data
        try:
            with open(self.manifest_path, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2)
        except Exception as exc:
            messagebox.showerror("Save Error", f"Failed to write manifest:\n{exc}")

    def _get_identity(self, identity_id: str) -> Optional[Dict]:
        for identity in self.identity_data.get("identities", []):
            if identity.get("id") == identity_id:
                return identity
        return None

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        paned = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        paned.grid(row=0, column=0, sticky="nsew")

        # Left: identity list and controls
        list_frame = ttk.Frame(paned, padding=12)
        list_frame.columnconfigure(0, weight=1)
        list_frame.rowconfigure(2, weight=1)

        ttk.Label(list_frame, text="Identities", font=("Arial", 14, "bold")).grid(row=0, column=0, sticky="w")

        search_frame = ttk.Frame(list_frame)
        search_frame.grid(row=1, column=0, sticky="ew", pady=(8, 6))
        search_frame.columnconfigure(1, weight=1)
        ttk.Label(search_frame, text="Search:").grid(row=0, column=0, sticky="w")
        ttk.Entry(search_frame, textvariable=self.search_var).grid(row=0, column=1, sticky="ew")

        self.identity_listbox = tk.Listbox(list_frame, height=18, exportselection=False)
        self.identity_listbox.grid(row=2, column=0, sticky="nsew")
        identity_scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.identity_listbox.yview)
        identity_scroll.grid(row=2, column=1, sticky="ns")
        self.identity_listbox.configure(yscrollcommand=identity_scroll.set)
        self.identity_listbox.bind("<<ListboxSelect>>", self._on_identity_select)

        button_frame = ttk.Frame(list_frame)
        button_frame.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        for col in range(3):
            button_frame.columnconfigure(col, weight=1)

        ttk.Button(button_frame, text="New Identity", command=self.create_identity).grid(row=0, column=0, padx=2, pady=2, sticky="ew")
        ttk.Button(button_frame, text="Import Photos", command=self.import_photos).grid(row=0, column=1, padx=2, pady=2, sticky="ew")
        ttk.Button(button_frame, text="Delete Identity", command=self.delete_identity).grid(row=0, column=2, padx=2, pady=2, sticky="ew")
        ttk.Button(button_frame, text="Open Folder", command=self.open_identity_folder).grid(row=1, column=0, padx=2, pady=2, sticky="ew")
        ttk.Button(button_frame, text="Refresh", command=self.refresh_identity_list).grid(row=1, column=1, padx=2, pady=2, sticky="ew")
        ttk.Button(button_frame, text="Close", command=self.root.destroy).grid(row=1, column=2, padx=2, pady=2, sticky="ew")

        paned.add(list_frame, weight=1)

        # Right: details and preview
        detail_frame = ttk.Frame(paned, padding=12)
        detail_frame.columnconfigure(0, weight=1)
        detail_frame.rowconfigure(4, weight=1)
        paned.add(detail_frame, weight=2)

        header = ttk.Label(detail_frame, text="Identity Details", font=("Arial", 14, "bold"))
        header.grid(row=0, column=0, sticky="w")

        form = ttk.Frame(detail_frame)
        form.grid(row=1, column=0, sticky="ew", pady=(10, 6))
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="Identity Name:").grid(row=0, column=0, sticky="w", pady=2)
        ttk.Entry(form, textvariable=self.name_var).grid(row=0, column=1, sticky="ew", pady=2)

        ttk.Label(form, text="Performer Code:").grid(row=1, column=0, sticky="w", pady=2)
        ttk.Entry(form, textvariable=self.code_var).grid(row=1, column=1, sticky="ew", pady=2)

        meta_frame = ttk.Frame(form)
        meta_frame.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        meta_frame.columnconfigure(1, weight=1)
        ttk.Label(meta_frame, text="Created:").grid(row=0, column=0, sticky="w")
        ttk.Label(meta_frame, textvariable=self.created_var).grid(row=0, column=1, sticky="w")
        ttk.Label(meta_frame, text="Updated:").grid(row=1, column=0, sticky="w")
        ttk.Label(meta_frame, textvariable=self.updated_var).grid(row=1, column=1, sticky="w")

        action_bar = ttk.Frame(detail_frame)
        action_bar.grid(row=2, column=0, sticky="ew")
        action_bar.columnconfigure(0, weight=1)
        ttk.Button(action_bar, text="Save Metadata", command=self.save_metadata).grid(row=0, column=0, sticky="w", padx=(0, 6))
        ttk.Button(action_bar, text="Open Identity Folder", command=self.open_identity_folder).grid(row=0, column=1, sticky="w")

        ttk.Separator(detail_frame, orient=tk.HORIZONTAL).grid(row=3, column=0, sticky="ew", pady=10)

        photo_pane = ttk.Panedwindow(detail_frame, orient=tk.HORIZONTAL)
        photo_pane.grid(row=4, column=0, sticky="nsew")

        photo_list_frame = ttk.Frame(photo_pane)
        photo_list_frame.columnconfigure(0, weight=1)
        photo_list_frame.rowconfigure(1, weight=1)
        ttk.Label(photo_list_frame, text="Photos", font=("Arial", 12, "bold")).grid(row=0, column=0, sticky="w")

        self.photo_listbox = tk.Listbox(photo_list_frame, height=10, exportselection=False)
        self.photo_listbox.grid(row=1, column=0, sticky="nsew")
        photo_scroll = ttk.Scrollbar(photo_list_frame, orient=tk.VERTICAL, command=self.photo_listbox.yview)
        photo_scroll.grid(row=1, column=1, sticky="ns")
        self.photo_listbox.configure(yscrollcommand=photo_scroll.set)
        self.photo_listbox.bind("<<ListboxSelect>>", self._on_photo_select)

        photo_buttons = ttk.Frame(photo_list_frame)
        photo_buttons.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        for col in range(3):
            photo_buttons.columnconfigure(col, weight=1)
        ttk.Button(photo_buttons, text="Set Primary", command=self.set_primary_photo).grid(row=0, column=0, padx=2, pady=2, sticky="ew")
        ttk.Button(photo_buttons, text="Open Photo", command=self.open_photo).grid(row=0, column=1, padx=2, pady=2, sticky="ew")
        ttk.Button(photo_buttons, text="Remove Photo", command=self.remove_photo).grid(row=0, column=2, padx=2, pady=2, sticky="ew")

        photo_pane.add(photo_list_frame, weight=1)

        preview_frame = ttk.Frame(photo_pane)
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(0, weight=0)
        preview_frame.rowconfigure(1, weight=1)
        ttk.Label(preview_frame, text="Preview", font=("Arial", 12, "bold")).grid(row=0, column=0, sticky="w")

        self.preview_label = tk.Label(
            preview_frame,
            text="Select a photo",
            bd=1,
            relief=tk.SUNKEN,
            anchor="center",
            bg="#101010",
            fg="white",
        )
        self.preview_label.grid(row=1, column=0, sticky="nsew", pady=(6, 6))

        self.primary_label = ttk.Label(preview_frame, text="Primary: —", font=("Arial", 10, "italic"))
        self.primary_label.grid(row=2, column=0, sticky="w")

        preview_buttons = ttk.Frame(preview_frame)
        preview_buttons.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        preview_buttons.columnconfigure(0, weight=1)
        ttk.Button(preview_buttons, text="Open Containing Folder", command=self.open_photo_folder).grid(row=0, column=0, padx=2, pady=2, sticky="ew")

        photo_pane.add(preview_frame, weight=2)

        status_bar = ttk.Label(self.root, textvariable=self.status_var, anchor="w")
        status_bar.grid(row=1, column=0, sticky="ew", padx=8, pady=(0, 4))

    # ------------------------------------------------------------------
    # Identity list management
    # ------------------------------------------------------------------
    def refresh_identity_list(self) -> None:
        if self.identity_listbox is None:
            return

        search = self.search_var.get().strip().lower()
        identities = sorted(
            self.identity_data.get("identities", []),
            key=lambda ident: ident.get("name", "").lower(),
        )

        filtered = []
        for identity in identities:
            name = identity.get("name", "Unnamed")
            code = identity.get("code") or ""
            if search and search not in name.lower() and search not in code.lower():
                continue
            filtered.append(identity)

        self.identity_listbox.delete(0, tk.END)
        self.filtered_order = []
        for identity in filtered:
            count = len(identity.get("images", []))
            display = identity.get("name", "Unnamed")
            code = identity.get("code") or ""
            parts = [display]
            if code:
                parts.append(f"[{code}]")
            if identity.get("primary_image"):
                parts.append("⭐")
            parts.append(f"({count})")
            self.identity_listbox.insert(tk.END, " ".join(parts))
            self.filtered_order.append(identity["id"])

        if self.filtered_order:
            # Retain previous selection if possible
            if self.current_identity_id and self.current_identity_id in self.filtered_order:
                index = self.filtered_order.index(self.current_identity_id)
            else:
                index = 0
            self.identity_listbox.selection_clear(0, tk.END)
            self.identity_listbox.selection_set(index)
            self.identity_listbox.activate(index)
            self.identity_listbox.event_generate("<<ListboxSelect>>")
        else:
            self.current_identity_id = None
            self._clear_identity_details()

    def _on_identity_select(self, event: tk.Event) -> None:
        if self.identity_listbox is None:
            return
        selection = self.identity_listbox.curselection()
        if not selection:
            return
        index = selection[0]
        if 0 <= index < len(self.filtered_order):
            self.current_identity_id = self.filtered_order[index]
            self._populate_identity_details()

    def _clear_identity_details(self) -> None:
        self.name_var.set("")
        self.code_var.set("")
        self.created_var.set("—")
        self.updated_var.set("—")
        if self.photo_listbox is not None:
            self.photo_listbox.delete(0, tk.END)
        if self.preview_label is not None:
            self.preview_label.config(text="Select an identity", image="")
        if self.primary_label is not None:
            self.primary_label.config(text="Primary: —")
        self.preview_image = None

    def _populate_identity_details(self) -> None:
        identity = self._get_identity(self.current_identity_id) if self.current_identity_id else None
        if identity is None:
            self._clear_identity_details()
            return

        self.name_var.set(identity.get("name", ""))
        self.code_var.set(identity.get("code", ""))
        self.created_var.set(identity.get("created_at", "—"))
        self.updated_var.set(identity.get("updated_at", "—"))

        if self.photo_listbox is not None:
            self.photo_listbox.delete(0, tk.END)
            for rel_path in identity.get("images", []):
                label = rel_path
                if rel_path == identity.get("primary_image"):
                    label = f"{rel_path}  (primary)"
                self.photo_listbox.insert(tk.END, label)
            if identity.get("images"):
                primary = identity.get("primary_image") or identity["images"][0]
                try:
                    index = identity["images"].index(primary)
                except ValueError:
                    index = 0
                self.photo_listbox.selection_clear(0, tk.END)
                self.photo_listbox.selection_set(index)
                self.photo_listbox.activate(index)
                self.photo_listbox.event_generate("<<ListboxSelect>>")
            else:
                if self.preview_label is not None:
                    self.preview_label.config(text="No photos", image="")
                if self.primary_label is not None:
                    self.primary_label.config(text="Primary: —")
                self.preview_image = None
        if self.primary_label is not None:
            self.primary_label.config(text=f"Primary: {identity.get('primary_image') or '—'}")

    # ------------------------------------------------------------------
    # Identity operations
    # ------------------------------------------------------------------
    def create_identity(self) -> None:
        name = simple_prompt(self.root, "New Identity", "Enter identity or performer name:")
        if name is None:
            return
        name = name.strip()
        if not name:
            messagebox.showinfo("Name Required", "Identity name cannot be empty.")
            return

        code = simple_prompt(self.root, "Performer Code", "Enter optional performer code (leave blank if none):")
        code = code.strip() if code else ""

        identity_id = uuid.uuid4().hex[:8]
        while self._get_identity(identity_id) is not None:
            identity_id = uuid.uuid4().hex[:8]

        timestamp = datetime.now().isoformat()
        new_identity = {
            "id": identity_id,
            "name": name,
            "code": code,
            "images": [],
            "primary_image": None,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        self.identity_data.setdefault("identities", []).append(new_identity)
        (self.identity_root / identity_id).mkdir(exist_ok=True)
        self._save_manifest()
        self.current_identity_id = identity_id
        self.status_var.set(f"Identity created: {name}")
        self.refresh_identity_list()

    def delete_identity(self) -> None:
        identity = self._get_identity(self.current_identity_id) if self.current_identity_id else None
        if identity is None:
            messagebox.showinfo("Select Identity", "Choose an identity to delete.")
            return

        if not messagebox.askyesno(
            "Delete Identity",
            f"Delete identity '{identity.get('name', 'Unnamed')}' and all associated photos?",
            parent=self.root,
        ):
            return

        folder = self.identity_root / identity["id"]
        try:
            if folder.exists():
                shutil.rmtree(folder)
        except Exception as exc:
            messagebox.showerror("Delete Failed", f"Unable to delete identity folder:\n{exc}")
            return

        self.identity_data["identities"] = [i for i in self.identity_data.get("identities", []) if i.get("id") != identity["id"]]
        self._save_manifest()
        self.status_var.set(f"Identity removed: {identity.get('name', 'Unnamed')}")
        self.current_identity_id = None
        self.refresh_identity_list()

    def save_metadata(self) -> None:
        identity = self._get_identity(self.current_identity_id) if self.current_identity_id else None
        if identity is None:
            messagebox.showinfo("Select Identity", "Choose an identity to update.")
            return

        name = self.name_var.get().strip()
        if not name:
            messagebox.showinfo("Name Required", "Identity name cannot be empty.")
            return

        identity["name"] = name
        identity["code"] = self.code_var.get().strip()
        identity["updated_at"] = datetime.now().isoformat()
        self._save_manifest()
        self.status_var.set(f"Saved metadata for {name}")
        self.refresh_identity_list()

    def import_photos(self) -> None:
        identity = self._get_identity(self.current_identity_id) if self.current_identity_id else None
        if identity is None:
            messagebox.showinfo("Select Identity", "Choose an identity before importing photos.")
            return

        filepaths = filedialog.askopenfilenames(
            parent=self.root,
            title="Select identity photos",
            filetypes=[
                ("Image files", "*.jpg *.jpeg *.png *.bmp *.tif *.tiff *.webp"),
                ("All files", "*.*"),
            ],
        )
        if not filepaths:
            return

        allowed = {".jpg", ".jpeg", ".png", ".bmp", ".tif", ".tiff", ".webp"}
        dest_dir = self.identity_root / identity["id"]
        dest_dir.mkdir(exist_ok=True)

        added = 0
        first_new: Optional[str] = None
        for filepath in filepaths:
            src = Path(filepath)
            ext = src.suffix.lower()
            if ext not in allowed:
                self.status_var.set(f"Skipped unsupported file: {src.name}")
                continue
            dest_name = f"{uuid.uuid4().hex}{ext}"
            dest_path = dest_dir / dest_name
            try:
                shutil.copy2(src, dest_path)
            except Exception as exc:
                self.status_var.set(f"Failed to import {src.name}: {exc}")
                continue

            rel_path = str(dest_path.relative_to(self.identity_root))
            if rel_path not in identity.setdefault("images", []):
                identity["images"].append(rel_path)
                if first_new is None:
                    first_new = rel_path
                added += 1

        if added:
            if identity.get("primary_image") is None and first_new is not None:
                identity["primary_image"] = first_new
            identity["updated_at"] = datetime.now().isoformat()
            self._save_manifest()
            self.status_var.set(f"Imported {added} photo(s)")
            self.refresh_identity_list()
        else:
            self.status_var.set("No photos imported")

    def open_identity_folder(self) -> None:
        identity = self._get_identity(self.current_identity_id) if self.current_identity_id else None
        if identity is None:
            messagebox.showinfo("Select Identity", "Choose an identity first.")
            return
        folder = self.identity_root / identity["id"]
        folder.mkdir(exist_ok=True)
        open_path(folder)

    # ------------------------------------------------------------------
    # Photo list operations
    # ------------------------------------------------------------------
    def _selected_photo(self) -> Optional[str]:
        identity = self._get_identity(self.current_identity_id) if self.current_identity_id else None
        if identity is None or not self.photo_listbox:
            return None
        selection = self.photo_listbox.curselection()
        if not selection:
            return None
        index = selection[0]
        images = identity.get("images", [])
        if 0 <= index < len(images):
            return images[index]
        return None

    def _on_photo_select(self, event: tk.Event) -> None:
        identity = self._get_identity(self.current_identity_id) if self.current_identity_id else None
        if identity is None:
            return
        rel_path = self._selected_photo()
        if rel_path is None:
            return
        if self.primary_label is not None:
            self.primary_label.config(text=f"Primary: {identity.get('primary_image') or '—'}")
        self._load_preview(rel_path)

    def _preview_target_size(self) -> tuple[int, int]:
        if self.preview_label is None:
            return (720, 540)
        self.preview_label.update_idletasks()
        width = self.preview_label.winfo_width()
        height = self.preview_label.winfo_height()
        if width <= 1 or height <= 1:
            width = self.preview_label.winfo_reqwidth()
            height = self.preview_label.winfo_reqheight()
        if width <= 1 or height <= 1:
            width, height = 720, 540
        return max(320, width), max(240, height)

    def _load_preview(self, rel_path: str) -> None:
        if self.preview_label is None:
            return
        image_path = self.identity_root / rel_path
        if not image_path.exists():
            self.preview_label.config(text="Image missing", image="")
            self.preview_image = None
            return
        try:
            with Image.open(image_path) as img:
                preview = ImageOps.exif_transpose(img.copy())
        except Exception as exc:
            self.preview_label.config(text=f"Preview error\n{exc}", image="")
            self.preview_image = None
            return

        target_size = self._preview_target_size()
        if preview.mode not in ("RGB", "RGBA"):
            preview = preview.convert("RGBA")
        fitted = ImageOps.contain(preview, target_size, method=_LANCZOS)
        if fitted.mode != "RGBA":
            fitted = fitted.convert("RGBA")

        background = Image.new("RGBA", target_size, (16, 16, 16, 255))
        offset = ((target_size[0] - fitted.width) // 2, (target_size[1] - fitted.height) // 2)
        background.paste(fitted, offset, fitted)

        display = background.convert("RGB")
        self.preview_image = ImageTk.PhotoImage(display)
        self.preview_label.config(image=self.preview_image, text="")

    def set_primary_photo(self) -> None:
        identity = self._get_identity(self.current_identity_id) if self.current_identity_id else None
        if identity is None:
            messagebox.showinfo("Select Identity", "Choose an identity first.")
            return
        rel_path = self._selected_photo()
        if rel_path is None:
            messagebox.showinfo("Select Photo", "Select a photo to mark as primary.")
            return

        identity["primary_image"] = rel_path
        identity["updated_at"] = datetime.now().isoformat()
        self._save_manifest()
        self.status_var.set("Primary photo updated")
        self.refresh_identity_list()

    def open_photo(self) -> None:
        identity = self._get_identity(self.current_identity_id) if self.current_identity_id else None
        if identity is None:
            messagebox.showinfo("Select Identity", "Choose an identity first.")
            return
        rel_path = self._selected_photo()
        if rel_path is None:
            messagebox.showinfo("Select Photo", "Select a photo to open.")
            return
        image_path = self.identity_root / rel_path
        if not image_path.exists():
            messagebox.showerror("Not Found", "The selected photo no longer exists.")
            return
        open_path(image_path)

    def remove_photo(self) -> None:
        identity = self._get_identity(self.current_identity_id) if self.current_identity_id else None
        if identity is None:
            messagebox.showinfo("Select Identity", "Choose an identity first.")
            return
        rel_path = self._selected_photo()
        if rel_path is None:
            messagebox.showinfo("Select Photo", "Select a photo to remove.")
            return

        if not messagebox.askyesno("Remove Photo", "Remove the selected photo from this identity?", parent=self.root):
            return

        image_path = self.identity_root / rel_path
        try:
            if image_path.exists():
                image_path.unlink()
        except Exception as exc:
            messagebox.showerror("Remove Failed", f"Unable to delete photo:\n{exc}")
            return

        images = identity.get("images", [])
        if rel_path in images:
            images.remove(rel_path)
        if identity.get("primary_image") == rel_path:
            identity["primary_image"] = images[0] if images else None
        identity["updated_at"] = datetime.now().isoformat()
        self._save_manifest()
        self.status_var.set("Removed photo")
        self.refresh_identity_list()

    def open_photo_folder(self) -> None:
        rel_path = self._selected_photo()
        if rel_path is None:
            self.open_identity_folder()
            return
        folder = (self.identity_root / rel_path).parent
        open_path(folder)

    # ------------------------------------------------------------------
    # Misc helpers
    # ------------------------------------------------------------------
    def _on_close(self) -> None:
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


# ----------------------------------------------------------------------
# Helper utilities
# ----------------------------------------------------------------------

def simple_prompt(parent: tk.Tk, title: str, prompt: str) -> Optional[str]:
    """A lightweight prompt dialog using tkinter.simpledialog-like behaviour."""
    dialog = tk.Toplevel(parent)
    dialog.title(title)
    dialog.grab_set()
    dialog.resizable(False, False)
    tk.Label(dialog, text=prompt, wraplength=360, justify="left").grid(row=0, column=0, columnspan=2, padx=12, pady=(12, 6))

    value_var = tk.StringVar()
    entry = tk.Entry(dialog, textvariable=value_var, width=40)
    entry.grid(row=1, column=0, columnspan=2, padx=12, pady=6)
    entry.focus_set()

    result: Dict[str, Optional[str]] = {"value": None}

    def on_ok() -> None:
        result["value"] = value_var.get()
        dialog.destroy()

    def on_cancel() -> None:
        dialog.destroy()

    ok_button = ttk.Button(dialog, text="OK", command=on_ok)
    ok_button.grid(row=2, column=0, padx=(12, 4), pady=(6, 12))
    cancel_button = ttk.Button(dialog, text="Cancel", command=on_cancel)
    cancel_button.grid(row=2, column=1, padx=(4, 12), pady=(6, 12))

    dialog.bind("<Return>", lambda _event: on_ok())
    dialog.bind("<Escape>", lambda _event: on_cancel())
    parent.wait_window(dialog)
    return result["value"]


def open_path(path: Path) -> None:
    try:
        if sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
        elif os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            subprocess.run(["xdg-open", str(path)], check=False)
    except Exception as exc:
        messagebox.showerror("Open Failed", f"Unable to open path:\n{exc}")


if __name__ == "__main__":
    app = IdentityConfigurator()
    app.run()
