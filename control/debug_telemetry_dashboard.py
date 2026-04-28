#!/usr/bin/env python3
"""Debug telemetry dashboard for simulated beacon/node data."""

from __future__ import annotations

import random
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk


NODES = [
    {"id": "NODE_01", "ip": "192.168.1.112", "mac": "A4:CF:12:8F:44:01"},
    {"id": "NODE_02", "ip": "192.168.1.113", "mac": "A4:CF:12:8F:44:02"},
    {"id": "NODE_03", "ip": "192.168.1.114", "mac": "A4:CF:12:8F:44:03"},
    {"id": "NODE_04", "ip": "192.168.1.115", "mac": "A4:CF:12:8F:44:04"},
]


def generate_hex() -> str:
    """Simulate the raw UDP binary payload as a hex string."""
    return "0x" + "".join(random.choice("0123456789ABCDEF") for _ in range(32))


class TelemetryDashboard(tk.Tk):
    """A lightweight debug dashboard for synthetic telemetry streams."""

    def __init__(self) -> None:
        super().__init__()
        self.title("Debug Telemetry Dashboard")
        self.geometry("1180x640")
        self.configure(bg="#1e1e1e")

        self.update_interval_ms = 200
        self.paused = False
        self.sequence = 0
        self.latest_rows: dict[str, dict[str, str]] = {}

        self._setup_style()
        self._build_ui()
        self._seed_rows()
        self._update_details(None)
        self.after(self.update_interval_ms, self._tick)

    def _setup_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(
            "Dark.TFrame",
            background="#1e1e1e",
        )
        style.configure(
            "Title.TLabel",
            background="#1e1e1e",
            foreground="#00ffcc",
            font=("Consolas", 16, "bold"),
        )
        style.configure(
            "Status.TLabel",
            background="#1e1e1e",
            foreground="#d0d0d0",
            font=("Consolas", 10),
        )
        style.configure(
            "Treeview",
            background="#262626",
            fieldbackground="#262626",
            foreground="#ffffff",
            rowheight=24,
            font=("Consolas", 10),
        )
        style.configure(
            "Treeview.Heading",
            background="#333333",
            foreground="#00ffcc",
            font=("Consolas", 10, "bold"),
        )
        style.map("Treeview", background=[("selected", "#3c3c3c")])

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=16, style="Dark.TFrame")
        root.pack(fill=tk.BOTH, expand=True)

        header = ttk.Frame(root, style="Dark.TFrame")
        header.pack(fill=tk.X, pady=(0, 12))

        ttk.Label(header, text="RAW TELEMETRY STREAM", style="Title.TLabel").pack(side=tk.LEFT)
        self.status_label = ttk.Label(
            header,
            text="STATUS: CONNECTED (SIMULATED 5Hz)",
            style="Status.TLabel",
        )
        self.status_label.pack(side=tk.RIGHT)

        summary = ttk.Frame(root, padding=(0, 0, 0, 10), style="Dark.TFrame")
        summary.pack(fill=tk.X)
        self.summary_label = ttk.Label(summary, text="Nodes: 4   Updates: 0   Mode: Live", style="Status.TLabel")
        self.summary_label.pack(side=tk.LEFT)
        self.rate_label = ttk.Label(summary, text="Interval: 200 ms", style="Status.TLabel")
        self.rate_label.pack(side=tk.RIGHT)

        body = ttk.Panedwindow(root, orient=tk.HORIZONTAL)
        body.pack(fill=tk.BOTH, expand=True)

        list_frame = ttk.Frame(body, padding=(0, 0, 10, 0), style="Dark.TFrame")
        detail_frame = ttk.Frame(body, style="Dark.TFrame")
        body.add(list_frame, weight=3)
        body.add(detail_frame, weight=2)

        columns = ("node_id", "ip", "mac", "raw_hex", "v_batt", "i_draw", "t_core", "t_amb", "pwm", "status")
        self.tree = ttk.Treeview(list_frame, columns=columns, show="headings")
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        widths = [90, 120, 160, 270, 90, 90, 90, 90, 70, 70]
        headings = ["Node ID", "IP", "MAC", "Raw Hex", "V_BATT", "I_DRAW", "T_CORE", "T_AMB", "PWM", "STATUS"]
        for column, width, heading in zip(columns, widths, headings):
            self.tree.heading(column, text=heading)
            self.tree.column(column, width=width, anchor=tk.CENTER)

        tree_scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tree_scroll.set)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.bind("<<TreeviewSelect>>", self._on_selection_change)

        ttk.Label(detail_frame, text="Debug Details", style="Status.TLabel").pack(anchor=tk.W, pady=(0, 6))
        self.details = scrolledtext.ScrolledText(
            detail_frame,
            height=18,
            width=42,
            bg="#111111",
            fg="#d9f7ff",
            insertbackground="#ffffff",
            font=("Consolas", 10),
            relief=tk.FLAT,
        )
        self.details.pack(fill=tk.BOTH, expand=True)

        self._append_details("Debug dashboard ready. Select a node to inspect the latest synthetic telemetry.")

        button_row = ttk.Frame(root, padding=(0, 12, 0, 0), style="Dark.TFrame")
        button_row.pack(fill=tk.X)

        self.toggle_button = ttk.Button(button_row, text="Pause Updates", command=self._toggle_updates)
        self.toggle_button.pack(side=tk.LEFT)
        ttk.Button(button_row, text="Refresh Now", command=self._refresh_now).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(button_row, text="Copy Snapshot", command=self._copy_snapshot).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(button_row, text="Close", command=self.destroy).pack(side=tk.RIGHT)

    def _seed_rows(self) -> None:
        for node in NODES:
            row = self._generate_row(node)
            self.latest_rows[node["id"]] = row
            self.tree.insert(
                "",
                tk.END,
                iid=node["id"],
                values=self._row_values(row),
            )

    def _row_values(self, row: dict[str, str]) -> tuple[str, ...]:
        return (
            row["node_id"],
            row["ip"],
            row["mac"],
            row["raw_hex"],
            row["v_batt"],
            row["i_draw"],
            row["t_core"],
            row["t_amb"],
            row["pwm"],
            row["status"],
        )

    def _generate_row(self, node: dict[str, str]) -> dict[str, str]:
        voltage = 3.7000 + random.uniform(-0.0450, 0.0450)
        current = 450.0 + random.uniform(-80.0, 95.0)
        core_temp = 45.20 + random.uniform(-1.25, 1.25)
        ambient_temp = 28.50 + random.uniform(-0.50, 0.50)
        pwm_duty = random.randint(180, 255)

        return {
            "node_id": node["id"],
            "ip": node["ip"],
            "mac": node["mac"],
            "raw_hex": generate_hex(),
            "v_batt": f"{voltage:.4f}V",
            "i_draw": f"{current:.2f}mA",
            "t_core": f"{core_temp:.3f}°C",
            "t_amb": f"{ambient_temp:.3f}°C",
            "pwm": str(pwm_duty),
            "status": "OK",
        }

    def _tick(self) -> None:
        if not self.paused:
            self.sequence += 1
            for node in NODES:
                row = self._generate_row(node)
                self.latest_rows[node["id"]] = row
                self.tree.item(node["id"], values=self._row_values(row))

            selected = self.tree.selection()
            if selected:
                self._update_details(selected[0])
            else:
                self._update_details(None)

            self.summary_label.config(
                text=f"Nodes: {len(NODES)}   Updates: {self.sequence}   Mode: Live"
            )

        self.after(self.update_interval_ms, self._tick)

    def _refresh_now(self) -> None:
        self.sequence += 1
        for node in NODES:
            row = self._generate_row(node)
            self.latest_rows[node["id"]] = row
            self.tree.item(node["id"], values=self._row_values(row))

        selected = self.tree.selection()
        if selected:
            self._update_details(selected[0])
        self.summary_label.config(
            text=f"Nodes: {len(NODES)}   Updates: {self.sequence}   Mode: {'Paused' if self.paused else 'Live'}"
        )
        self.status_label.config(text="STATUS: MANUAL REFRESH COMPLETE")
        self.after(800, self._restore_status_text)

    def _restore_status_text(self) -> None:
        if self.paused:
            self.status_label.config(text="STATUS: PAUSED")
        else:
            self.status_label.config(text="STATUS: CONNECTED (SIMULATED 5Hz)")

    def _toggle_updates(self) -> None:
        self.paused = not self.paused
        self.toggle_button.config(text="Resume Updates" if self.paused else "Pause Updates")
        self.summary_label.config(
            text=f"Nodes: {len(NODES)}   Updates: {self.sequence}   Mode: {'Paused' if self.paused else 'Live'}"
        )
        self._restore_status_text()

    def _on_selection_change(self, _event: tk.Event) -> None:
        selected = self.tree.selection()
        if not selected:
            self._update_details(None)
            return

        self._update_details(selected[0])

    def _update_details(self, node_id: str | None) -> None:
        self.details.delete(1.0, tk.END)
        if not node_id or node_id not in self.latest_rows:
            self.details.insert(tk.END, "Select a node to inspect its latest debug payload.\n")
            return

        row = self.latest_rows[node_id]
        self.details.insert(tk.END, f"Node: {row['node_id']}\n")
        self.details.insert(tk.END, f"IP: {row['ip']}\n")
        self.details.insert(tk.END, f"MAC: {row['mac']}\n")
        self.details.insert(tk.END, f"Status: {row['status']}\n")
        self.details.insert(tk.END, f"Battery: {row['v_batt']}\n")
        self.details.insert(tk.END, f"Current draw: {row['i_draw']}\n")
        self.details.insert(tk.END, f"Core temperature: {row['t_core']}\n")
        self.details.insert(tk.END, f"Ambient temperature: {row['t_amb']}\n")
        self.details.insert(tk.END, f"PWM duty: {row['pwm']}\n")
        self.details.insert(tk.END, f"Raw payload: {row['raw_hex']}\n")
        self.details.insert(tk.END, f"Sequence: {self.sequence}\n")
        self.details.see(tk.END)

    def _append_details(self, message: str) -> None:
        self.details.insert(tk.END, f"{message}\n")
        self.details.see(tk.END)

    def _copy_snapshot(self) -> None:
        snapshot_lines = ["Debug Telemetry Snapshot"]
        for row in self.latest_rows.values():
            snapshot_lines.append(
                ", ".join(
                    [
                        row["node_id"],
                        row["ip"],
                        row["mac"],
                        row["v_batt"],
                        row["i_draw"],
                        row["t_core"],
                        row["t_amb"],
                        row["pwm"],
                        row["raw_hex"],
                        row["status"],
                    ]
                )
            )

        self.clipboard_clear()
        self.clipboard_append("\n".join(snapshot_lines))
        self.update_idletasks()
        messagebox.showinfo("Snapshot Copied", "The current debug snapshot has been copied to the clipboard.")


def main() -> None:
    dashboard = TelemetryDashboard()
    dashboard.mainloop()


if __name__ == "__main__":
    main()