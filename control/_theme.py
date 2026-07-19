"""Industrial UI theme and gates/wall/annunciator widgets.

Exports:
  IND_PALETTE, DARK_*, GREEN_OK, AMBER_WARN, RED_ERR

  FailsafeAnnunciator   - alarm tile panel (top of window)
  StealthAnnunciator    - single-LED strip (bottom of dialog)
  FailsafeOverride      - timed confirmation gate for destructive actions
  DarkTerminal          - scrolled text with severity-coloured output

  get_status_color      - map status string -> hex colour
  hex_to_rgb / darken / brighten
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

import tkinter as tk
from tkinter import ttk


# ──────────────────────────────────────────────────────────────────
#  Industrial palette
# ──────────────────────────────────────────────────────────────────
IND_PALETTE: Dict[str, str] = {
    "bg_dark":       "#1a1d20",
    "bg_medium":     "#22262b",
    "bg_light":      "#2e3338",
    "bg_input":      "#262b30",
    "fg_primary":    "#e8e4d8",
    "fg_secondary":  "#aeaa9c",
    "fg_muted":      "#6b685e",
    "accent_amber":  "#d48d2b",
    "accent_green":  "#50a548",
    "accent_red":    "#d1412d",
    "accent_blue":   "#2678b2",
    "border":        "#3d4349",
    "border_light":  "#525b63",
    "border_dark":   "#2a2e33",
    "white":         "#ffffff",
    "black":         "#000000",
}

DARK_BG       = IND_PALETTE["bg_dark"]
DARK_BG_MED   = IND_PALETTE["bg_medium"]
DARK_BG_LIGHT = IND_PALETTE["bg_light"]
DARK_FG       = IND_PALETTE["fg_primary"]
DARK_FG_SEC   = IND_PALETTE["fg_secondary"]
DARK_FG_MUTED = IND_PALETTE["fg_muted"]
GREEN_OK      = IND_PALETTE["accent_green"]
AMBER_WARN    = IND_PALETTE["accent_amber"]
RED_ERR       = IND_PALETTE["accent_red"]
BLUE_LINK     = IND_PALETTE["accent_blue"]

SEVERITY_COLORS = {
    "DEBUG": DARK_FG_MUTED,
    "INFO":  DARK_FG,
    "WARN":  AMBER_WARN,
    "WARNING": AMBER_WARN,
    "ERROR": RED_ERR,
    "CRIT":  RED_ERR,
    "OK":    GREEN_OK,
}


# Exported colour helpers
def darken_color(h: str, factor: float = 0.15) -> str:
    return darken(h, factor)


def brighten_color(h: str, factor: float = 0.15) -> str:
    return brighten(h, factor)


def get_status_color(s: str) -> str:
    s = s.lower()
    if s in ("online", "ok", "good", "green"):
        return GREEN_OK
    if s in ("offline", "error", "critical"):
        return RED_ERR
    if s in ("warn", "warning", "stale"):
        return AMBER_WARN
    return DARK_FG_MUTED


def apply_treeview_style(tv: ttk.Treeview) -> None:
    tv.configure(
        background=DARK_BG_MED,
        foreground=DARK_FG,
        fieldbackground=DARK_BG_MED,
        bordercolor=DARK_BG_MED,
        selectbackground=DARK_BG_LIGHT,
        selectforeground=DARK_FG,
        font=("Arial", 9),
    )
    tv.tag_configure("online_tag", foreground=GREEN_OK)
    tv.tag_configure("offline_tag", foreground=RED_ERR)


# ══════════════════════════════════════════════════════════════════
#  FailsafeAnnunciator
# ══════════════════════════════════════════════════════════════════

class FailsafeAnnunciator:
    """Paging/alarm panel – top of each window.

    Top row: up to 4 severity-coloured alarm tiles.
    Bottom: scroller line for the most recent message.
    """

    HEIGHT = 68
    TILE_W  = 180

    def __init__(self, master: tk.Widget, max_alarms: int = 4):
        self.max_alarms = max_alarms
        self.alarms: List[Dict[str, str]] = []
        self.flash_state = False
        self._flash_id: Optional[str] = None

        self.frame = tk.Frame(
            master, bg=DARK_BG,
            highlightbackground=IND_PALETTE["border"],
            highlightthickness=1, height=self.HEIGHT,
        )
        self.frame.pack_propagate(False)

        # Top tile row
        tiles_frame = tk.Frame(self.frame, bg=DARK_BG)
        tiles_frame.pack(fill=tk.X, padx=4, pady=(4, 0))

        self.tile_frames: List[tk.Frame] = []
        self.tile_icon: List[tk.Label] = []
        self.tile_text: List[tk.Label] = []

        for _ in range(max_alarms):
            tile = tk.Frame(
                tiles_frame, bg=DARK_BG,
                highlightbackground=DARK_BG_MED,
                highlightthickness=1,
                width=self.TILE_W, height=34,
            )
            tile.pack_propagate(False)
            tile.pack(side=tk.LEFT, padx=(0, 4))

            icon = tk.Label(tile, bg=DARK_BG, fg=GREEN_OK,
                            font=("Segoe UI", 8, "bold"), anchor="w")
            icon.pack(side=tk.LEFT, padx=4, pady=2, fill=tk.X, expand=True)

            txt = tk.Label(tile, bg=DARK_BG, fg=GREEN_OK,
                           font=("Segoe UI", 8), anchor="w")
            txt.pack(side=tk.RIGHT, padx=4, pady=2, fill=tk.X, expand=True)

            self.tile_frames.append(tile)
            self.tile_icon.append(icon)
            self.tile_text.append(txt)

        # Scroller row
        sc = tk.Frame(self.frame, bg=DARK_BG)
        sc.pack(fill=tk.BOTH, padx=4, expand=True)
        self.scroller = tk.Label(
            sc, bg=DARK_BG, fg=GREEN_OK,
            font=("Segoe UI", 9), anchor="w", padx=4,
            text="System OK",
        )
        self.scroller.pack(fill=tk.BOTH, expand=True)

        # Initialise empty tiles
        self._refresh()

    # ─ Public API ──────────────────────────────────────────────────

    def acknowledge(self) -> None:
        self.alarms.clear()
        self._stop_flash()
        self.scroller.configure(fg=GREEN_OK, text="System OK")
        self._refresh()

    def set_ok(self) -> None:
        self.acknowledge()

    def push_error(self, msg: str, alarm_id: str = "") -> None:
        self._push(msg, "error")

    def push_warning(self, msg: str, alarm_id: str = "", is_stale: bool = False) -> None:
        self._push(msg, "stale" if is_stale else "warning")

    def push_ok(self, msg: str) -> None:
        pass  # no-op

    def scroll_message(self, msg: str, severity: str = "info") -> None:
        c = SEVERITY_COLORS.get(severity.upper(), DARK_FG)
        self.scroller.configure(fg=c, text=msg)

    def destroy(self) -> None:
        self._stop_flash()
        self.frame.destroy()

    def pack(self, **kw: Any) -> None:
        self.frame.pack(**kw)

    # ─ Internals ──────────────────────────────────────────────────

    def _push(self, msg: str, sev: str) -> None:
        if len(self.alarms) >= self.max_alarms:
            self.alarms.pop(0)
        self.alarms.append({"msg": msg, "sev": sev})
        self.scroll_message(msg, sev)
        if sev in ("error", "stale"):
            self._start_flash()
        self._refresh()

    def _stop_flash(self) -> None:
        if self._flash_id:
            try:
                self.frame.after_cancel(self._flash_id)
            except Exception:
                pass
            self._flash_id = None
        self.flash_state = False
        for idx in range(len(self.tile_frames)):
            self.tile_frames[idx].configure(bg=DARK_BG)
            for w in self.tile_frames[idx].winfo_children():
                try:
                    w.configure(bg=DARK_BG)
                except Exception:
                    pass

    def _start_flash(self) -> None:
        self.flash_state = not self.flash_state
        for idx, alarm in enumerate(self.alarms):
            if alarm["sev"] in ("error", "stale"):
                bg = RED_ERR if alarm["sev"] == "error" else AMBER_WARN
                bg = bg if self.flash_state else DARK_BG
                self.tile_frames[idx].configure(bg=bg)
                for w in self.tile_frames[idx].winfo_children():
                    try:
                        w.configure(bg=bg)
                    except Exception:
                        pass
        self._flash_id = self.frame.after(500, self._start_flash)

    def _refresh(self) -> None:
        for idx in range(self.max_alarms):
            if idx < len(self.alarms):
                alarm = self.alarms[idx]
                self.tile_frames[idx].pack()
                fg = RED_ERR if alarm["sev"] == "error" else AMBER_WARN
                icon = "✖" if alarm["sev"] == "error" else "⚠"
                self.tile_icon[idx].configure(text=icon, fg=fg)
                self.tile_text[idx].configure(text=alarm["msg"], fg=fg)
            else:
                self.tile_frames[idx].pack_forget()


# ══════════════════════════════════════════════════════════════════
#  StealthAnnunciator - thin LED strip at bottom
# ══════════════════════════════════════════════════════════════════

class StealthAnnunciator:
    def __init__(self, master: tk.Widget):
        self.master = master
        self.frame = tk.Frame(master, bg=DARK_BG, height=32)
        self.frame.pack(side=tk.BOTTOM, fill=tk.X)
        self.frame.pack_propagate(False)

        self.led = tk.Label(self.frame, text="⬤", fg=GREEN_OK,
                            bg=DARK_BG, font=("Arial", 12), padx=6)
        self.led.pack(side=tk.LEFT)

        self.text = tk.Label(self.frame, fg=DARK_FG, bg=DARK_BG,
                             anchor=tk.W, padx=4)
        self.text.pack(side=tk.LEFT, fill=tk.X, expand=True)

    def set_ok(self, msg: str = "OK") -> None:
        self.led.configure(text="⬤", fg=GREEN_OK)
        self.text.configure(text=msg)

    def set_warning(self, msg: str) -> None:
        self.led.configure(text="⬤", fg=AMBER_WARN)
        self.text.configure(text=msg)

    def set_error(self, msg: str) -> None:
        self.led.configure(text="⬤", fg=RED_ERR)
        self.text.configure(text=msg)


# ══════════════════════════════════════════════════════════════════
#  FailsafeOverride – timed gate for destructive actions
# ══════════════════════════════════════════════════════════════════

class FailsafeOverride:
    def __init__(
        self,
        annunciator: FailsafeAnnunciator,
        action: Callable[[], Any],
        title: str = "Confirm",
        timeout: int = 5,
        retries: int = 0,
    ):
        self.annunciator = annunciator
        self.action = action
        self.title = title
        self.timeout = timeout
        self._retries = retries
        self.active = False
        self._counter = 0
        self._id: Optional[str] = None

    def request(self) -> None:
        self.active = True
        self._counter = self.timeout
        self.annunciator.push_warning(f"{self.title}: confirm or cancel")
        self._tick()

    def confirm(self) -> None:
        if not self.active:
            return
        try:
            self.action()
            self.active = False
            self._cancel()
            self.annunciator.scroll_message(f"{self.title}: ok", "OK")
        except Exception as e:
            if self._retries > 0:
                self._retries -= 1
                self.annunciator.push_error(f"{self.title} failed ({e})")
                self._counter = self.timeout
                self.active = True
            else:
                self.annunciator.push_error(f"{self.title} failed: out of retries")

    def reset(self) -> None:
        self.active = False
        self._cancel()

    def destroy(self) -> None:
        self._cancel()

    def _tick(self) -> None:
        if not self.active:
            return
        if self._counter <= 0:
            self.active = False
            self.annunciator.push_warning(f"{self.title}: timed out")
            return
        self.annunciator.scroll_message(f"{self.title} {self._counter}s", "warning")
        self._counter -= 1
        self._id = self.annunciator.frame.after(1000, self._tick)

    def _cancel(self) -> None:
        if self._id:
            try:
                self.annunciator.frame.after_cancel(self._id)
            except Exception:
                pass
            self._id = None


# ══════════════════════════════════════════════════════════════════
#  DarkTerminal - scrolled text with severity-coloured output
# ══════════════════════════════════════════════════════════════════

class DarkTerminal:
    def __init__(self, parent: ttk.Frame, height: int = 20):
        self.text = tk.Text(
            parent, height=height,
            font=("Consolas", 10),
            bg=DARK_BG, fg=DARK_FG,
            insertbackground=DARK_FG,
            selectbackground=DARK_BG_LIGHT,
            selectforeground=DARK_FG,
            wrap=tk.WORD, state=tk.DISABLED,
            relief=tk.FLAT,
            borderwidth=2,
        )
        self.scroll = ttk.Scrollbar(parent, orient=tk.VERTICAL,
                                     command=self.text.yview)
        self.text.configure(yscrollcommand=self.scroll.set)

    def pack(self, **kw: Any) -> None:
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, **kw)
        self.scroll.pack(side=tk.RIGHT, fill=tk.Y)

    def grid(self, **kw: Any) -> None:
        self.text.grid(**kw)
        self.scroll.grid(row=kw.get("row", 0), column=kw.get("column", 0) + 1,
                          sticky="ns")

    def clear(self) -> None:
        self.text.config(state=tk.NORMAL)
        self.text.delete("1.0", tk.END)
        self.text.config(state=tk.DISABLED)

    def log(self, message: str, severity: str = "INFO") -> None:
        self.text.config(state=tk.NORMAL)
        color = SEVERITY_COLORS.get(severity.upper(), DARK_FG)
        tag = severity.lower()
        self.text.insert(tk.END, f"{message}\n")
        self.text.tag_add(tag, "end-2l", "end-1l")
        self.text.tag_configure(tag, foreground=color)
        self.text.see(tk.END)
        self.text.config(state=tk.DISABLED)

    def debug(self, m: str) -> None: self.log(m, "DEBUG")
    def info(self, m: str) -> None: self.log(m, "INFO")
    def warn(self, m: str) -> None: self.log(m, "WARN")
    def error(self, m: str) -> None: self.log(m, "ERROR")
    def stat(self, m: str) -> None: self.log(m, "OK")