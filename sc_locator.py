"""
Starboard
----------
Leave this window open, then type /showlocation in the in-game chat. The game
copies your coordinates to the clipboard; this app picks them up and shows
where you are, what is nearby, and what can be mined on that planet or moon.

Run:  py sc_locator.py   (Python 3.9+ from python.org; no extra packages)
"""

import math
import random
import re
import os
import queue
import sys
import threading
import time
import tkinter as tk
import tkinter.font as tkfont
import webbrowser
from tkinter import filedialog, messagebox, simpledialog, ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import core  # noqa: E402
import data_update  # noqa: E402
import hauling  # noqa: E402
import ledger  # noqa: E402
import hangar  # noqa: E402
import shop  # noqa: E402
import refining  # noqa: E402
import combat  # noqa: E402
import gamelog  # noqa: E402
import wikidata  # noqa: E402
import mydata  # noqa: E402
import gametext  # noqa: E402
import crafting  # noqa: E402
import shipbuild  # noqa: E402
import hotkeys_win  # noqa: E402
import ocr_reader  # noqa: E402
import signatures  # noqa: E402
import ticker  # noqa: E402
import events  # noqa: E402
import belts  # noqa: E402
import edition  # noqa: E402

EDITION = edition.load(core.HERE)  # plain Starboard, or e.g. the BSquaredTV edition
APP_TITLE = EDITION["name"]
APP_VERSION = "12.7.2"
POLL_MS = 400
HEADER_H = 92
DISCLAIMER = ("Starboard is an unofficial Star Citizen fan tool, made by the community for the community. It is not affiliated with, endorsed by or sponsored by the Cloud Imperium group of companies. Star Citizen\u00ae, Squadron 42\u00ae, Roberts Space Industries\u00ae and Cloud Imperium\u00ae are registered trademarks of Cloud Imperium Rights LLC. All game content, names and images belong to Cloud Imperium Games and Roberts Space Industries. Other data belongs to its sources, credited below.")

# HUD palette
BG = "#06131e"
PANEL = "#0b1e2d"
PANEL_HI = "#123048"
CARD = "#0e2537"
BAND = "#12304a"
LINE = "#1d4561"
CYAN = "#4ab8f5"
CYAN_DIM = "#2b7cae"
CYAN_FAINT = "#173d58"
FG = "#e3eff7"
MUTED = "#809fb4"
AMBER = "#ffb84d"
ORANGE = "#e9861a"
ORANGE_HI = "#ffa23a"
GREEN = "#43e6a6"
RED = "#ff5d6c"
PURPLE = "#b48cff"
TEAL = "#3fd6c8"

ROW_ALT = "#0f2638"
BTN_HOVER = "#10283a"
ACCENT_PRESSED = "#b9660c"
PLATE = "#071a29"
SKY_TOP = "#080f19"
SKY_BOTTOM = "#0b1a27"
STAR_DIM = "#2c4a63"
STAR_BRIGHT = "#e6f4ff"
HAZE = "#1a3a5c"
PLANET_DARK = "#0a2236"
PLANET_LIGHT = "#3b8fd0"
ON_ACCENT = "#1a0d00"  # text on orange (accent) buttons

# Color modes. Each one swaps colors that carry meaning (good, warning, danger) for ones that
# people with that kind of color vision can tell apart. Applied once at startup.
COLOR_MODES = ["Default", "Red-green colorblind", "Blue-yellow colorblind", "High contrast"]
THEMES = {
    # protanopia / deuteranopia: blue for good, orange for danger, yellow for warning (Okabe-Ito)
    "Red-green colorblind": {"GREEN": "#56b4e9", "RED": "#ff8a2b", "AMBER": "#f0e442", "ORANGE": "#e69f00",
                             "ORANGE_HI": "#ffb733", "CYAN": "#c9dcff", "CYAN_DIM": "#7f9cc4",
                             "TEAL": "#9fd8ff", "PURPLE": "#cc79a7"},
    # tritanopia: red / green stay apart, so keep those; move highlights off blue
    "Blue-yellow colorblind": {"GREEN": "#2fd27a", "RED": "#ff4d6d", "AMBER": "#ff9a3c", "CYAN": "#f2f2f2",
                               "CYAN_DIM": "#a3a3a3", "TEAL": "#7fe0c0", "PURPLE": "#ff7fb0"},
    "High contrast": {"BG": "#000000", "PANEL": "#000000", "PANEL_HI": "#1c1c1c", "CARD": "#080808",
                      "BAND": "#1c1c1c", "LINE": "#a0a0a0", "CYAN": "#5ee2ff", "CYAN_DIM": "#b8ecff",
                      "CYAN_FAINT": "#00506b", "FG": "#ffffff", "MUTED": "#e0e0e0", "AMBER": "#ffd000",
                      "GREEN": "#4dff9a", "RED": "#ff6b6b", "ORANGE": "#ffa000", "ORANGE_HI": "#ffc040",
                      "ROW_ALT": "#141414"},
}
# words used in help text, so "green is best" stays true in every mode
COLOR_WORDS = {"Red-green colorblind": {"green": "blue", "red": "orange", "amber": "yellow"},
               "Blue-yellow colorblind": {"amber": "orange"},
               "High contrast": {"amber": "yellow"}}
TEXT_SIZES = [("Small", 0.9), ("Normal", 1.0), ("Large", 1.15), ("Extra large", 1.3), ("Huge", 1.5)]
WINDOW_SIZES = [("Remember last size", None), ("Small", (760, 820)), ("Standard", (800, 920)),
                ("Tall", (800, 1040)), ("Large", (960, 1040))]
FONT_CHOICES = ["Default", "Atkinson Hyperlegible", "OpenDyslexic", "Verdana", "Segoe UI", "Tahoma", "Arial",
                "Calibri"]


def _startup_settings():
    try:
        import json
        with open(os.path.join(core.USER_DIR, "settings.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


COLOR_MODE = _startup_settings().get("color_mode", "Default")
if COLOR_MODE not in COLOR_MODES:
    COLOR_MODE = "Default"
globals().update({k: v for k, v in (EDITION.get("palette") or {}).items() if k.isupper()})
globals().update(THEMES.get(COLOR_MODE, {}))


def cw(word, cap=False):
    """The name of a status color in the current color mode."""
    w = COLOR_WORDS.get(COLOR_MODE, {}).get(word, word)
    return w.capitalize() if cap else w


RARITY_COLOR = {"Legendary": AMBER, "Epic": PURPLE, "Rare": CYAN, "Uncommon": GREEN}
SCAN_SHOW_SECONDS = 45

ORE_LABELS = [("ship", "SHIP MINING"), ("vehicle", "ROC MINING"),
              ("hand", "FPS MINING"), ("harvestable", "HARVESTABLES")]


def pick_font(candidates, fallback):
    have = set(tkfont.families())
    for c in candidates:
        if c in have:
            return c
    return fallback


def age_words(days):
    """'updated today', 'updated 3 days ago'."""
    if days is None:
        return "not downloaded yet"
    if days < 1:
        return "updated today"
    if days < 2:
        return "updated yesterday"
    return f"updated {days:.0f} days ago"


CLOCK_12H = False  # set from SETTINGS > GENERAL > CLOCK


def clock_str(t, fmt):
    """Format a time (datetime or time.struct_time) with the 12 or 24 hour clock the user picked."""
    if CLOCK_12H and "%H" in fmt:
        fmt = fmt.replace("%H", "%I").replace(":%S", ":%S").rstrip() + " %p"
    out = t.strftime(fmt) if hasattr(t, "strftime") else time.strftime(fmt, t)
    if CLOCK_12H:
        out = re.sub(r"(^|\s)0(\d:)", r"\1\2", out)
    return out


def clip_text(text, n):
    return text if len(text) <= n else text[:n - 1] + "…"


def _num0(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def spaced(text):
    """Letter-spaced uppercase, the look of in-game HUD labels."""
    return " ".join(text.upper())


def round_points(x1, y1, x2, y2, r):
    """Points for a rounded rectangle drawn with create_polygon(..., smooth=True)."""
    r = max(0, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
    return [x1 + r, y1, x1 + r, y1, x2 - r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y1 + r, x2, y2 - r,
            x2, y2 - r, x2, y2, x2 - r, y2, x2 - r, y2, x1 + r, y2, x1 + r, y2, x1, y2, x1, y2 - r,
            x1, y2 - r, x1, y1 + r, x1, y1 + r, x1, y1]


def _hex_rgb(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def round_png(w, h, r, fill, border, top_only=False, grow=(0, 0)):
    """A PNG (as base64) of a rounded rectangle with smooth, see-through corners.
    Used for buttons and tabs; ttk tiles the middle and keeps the corners. grow=(extra width,
    extra height) makes the middle bigger by repeating the middle column and row, so ttk needs
    one tile per button instead of hundreds (each tile is a slow see-through copy on Windows)."""
    import base64
    import struct
    import zlib
    fr, br = _hex_rgb(fill), _hex_rgb(border)
    hh = (h + r + 2) if top_only else h          # tabs: the bottom edge runs off the image (no corners there)
    cx, cy, hx, hy = w / 2, hh / 2, w / 2 - r, hh / 2 - r
    rows = []
    for y in range(h):
        row = bytearray([0])
        for x in range(w):
            cover = edge = 0
            for sy in (0.125, 0.375, 0.625, 0.875):
                for sx in (0.125, 0.375, 0.625, 0.875):
                    qx, qy = abs(x + sx - cx) - hx, abs(y + sy - cy) - hy
                    d = (max(qx, 0) ** 2 + max(qy, 0) ** 2) ** 0.5 + min(max(qx, qy), 0) - r
                    if d <= 0:
                        cover += 1
                        if d > -1.15:
                            edge += 1
            a = cover / 16
            e = edge / max(cover, 1)
            col = tuple(int(fr[i] * (1 - e) + br[i] * e) for i in range(3))
            row += bytes(col) + bytes([int(a * 255)])
        rows.append(bytes(row))
    gx, gy = grow
    if gx or gy:
        m = w // 2
        rows = [r_[:1 + 4 * m] + r_[1 + 4 * m:1 + 4 * (m + 1)] * (gx + 1) + r_[1 + 4 * (m + 1):] for r_ in rows]
        mid = h // 2
        rows = rows[:mid] + [rows[mid]] * (gy + 1) + rows[mid + 1:]
        w, h = w + gx, h + gy

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xffffffff)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)) + \
        chunk(b"IDAT", zlib.compress(b"".join(rows))) + chunk(b"IEND", b"")
    return base64.b64encode(png)


class RoundBox(tk.Canvas):
    """A card with rounded corners, an optional colored left edge, and widgets inside `.inner`."""

    def __init__(self, parent, fill=None, border=None, accent=None, radius=14, pad=(10, 6), **kw):
        try:
            pbg = parent.cget("bg")
        except tk.TclError:
            pbg = PANEL
        super().__init__(parent, bg=pbg, highlightthickness=0, bd=0, **kw)
        self.fill, self.border, self.accent = fill or CARD, border or LINE, accent
        self.radius, self.padx, self.pady = radius, pad[0], pad[1]
        self.inner = tk.Frame(self, bg=self.fill)
        self._win = self.create_window(self.padx + (4 if accent else 0), self.pady, window=self.inner,
                                       anchor="nw")
        self.inner.bind("<Configure>", self._fit)
        self.bind("<Configure>", self._draw)

    def set_border(self, color):
        self.border = color
        self.itemconfigure("edge", outline=color)

    def _fit(self, _e=None):
        need = self.inner.winfo_reqheight() + self.pady * 2
        if int(self.cget("height")) != need:
            self.configure(height=need)

    def _draw(self, _e=None):
        w, h = self.winfo_width(), self.winfo_height()
        if w < 4 or h < 4:
            return
        r, left = self.radius, (4 if self.accent else 0)
        self.itemconfigure(self._win, width=max(1, w - self.padx * 2 - left))
        self.delete("deco")
        if self.accent:
            self.create_polygon(round_points(1, 1, w - 1, h - 1, r), smooth=True, fill=self.accent,
                                outline="", tags="deco")
            self.create_polygon(round_points(4, 1, w - 1, h - 1, r), smooth=True, fill=self.fill,
                                outline="", tags="deco")
            self.create_rectangle(w // 2, 1, w - r, h - 1, fill=self.fill, outline="", tags="deco")
        else:
            self.create_polygon(round_points(1, 1, w - 1, h - 1, r), smooth=True, fill=self.fill,
                                outline="", tags="deco")
        self.create_polygon(round_points(1, 1, w - 1, h - 1, r), smooth=True, fill="", outline=self.border,
                            width=1, tags=("deco", "edge"))
        self.tag_lower("deco")


class Suggest:
    """Matches as you type for every typeable picker (ship, place, refinery, ore...): a small list
    opens under the box while you type, without taking the keyboard away from it. Up and Down move
    through it, Enter or a click picks, Escape closes. The picker's own filtering decides what is in
    the list (it narrows the picker's values as you type)."""

    MAX_ROWS = 8

    def __init__(self, root, app):
        self.root, self.app = root, app
        self.win = self.lb = self.cb = None
        root.bind_class("TCombobox", "<KeyRelease>", self._typed, add="+")

    def _editable(self, cb):
        try:
            return "readonly" not in cb.state() and not getattr(cb, "_no_suggest", False)
        except tk.TclError:
            return False

    def _typed(self, e):
        cb = e.widget
        if not isinstance(cb, ttk.Combobox) or not self._editable(cb):
            return
        if e.keysym in ("Up", "Down", "Return", "KP_Enter", "Escape", "Tab", "Left", "Right", "Home", "End",
                        "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R"):
            return
        text = cb.get().strip()
        vals = list(cb.cget("values") or ())
        if not text:
            self.close()
            return
        q = text.lower()
        matches = [v for v in vals if all(w in str(v).lower() for w in q.split())]
        if not matches or (len(matches) == 1 and str(matches[0]).lower() == q):
            self.close()
            return
        self.show(cb, matches)

    def show(self, cb, items):
        if self.cb is not cb:
            self.close()
            self.cb = cb
            if not getattr(cb, "_suggest_keys", False):
                cb._suggest_keys = True
                # ours run first, so Enter picks the highlighted match before the box's own Enter action
                for seq, fn in (("<Down>", lambda e: self._move(1)), ("<Up>", lambda e: self._move(-1)),
                                ("<Return>", lambda e: self._pick_current()), ("<Escape>", lambda e: self._esc())):
                    old = cb.bind(seq)
                    cb.bind(seq, fn)
                    if old:
                        cb.bind(seq, old, add="+")
                cb.bind("<FocusOut>", lambda e: self.root.after(150, self._focus_check), add="+")
        if self.win is None:
            top = cb.winfo_toplevel()
            self.win = tk.Toplevel(top)
            self.win.overrideredirect(True)
            self.win.attributes("-topmost", True)
            self.win.configure(bg=CYAN_DIM)
            self.lb = tk.Listbox(self.win, bg=PANEL_HI, fg=FG, selectbackground=CYAN_FAINT,
                                 selectforeground="#ffffff", highlightthickness=0, bd=0, activestyle="none",
                                 font=(self.app.F_UI, 10), exportselection=False)
            self.lb.pack(fill="both", expand=True, padx=1, pady=1)
            self.lb.bind("<ButtonRelease-1>", lambda e: self._pick_current())
            self.lb.bind("<Motion>", lambda e: (self.lb.selection_clear(0, "end"),
                                                self.lb.selection_set(self.lb.nearest(e.y))))
        self.lb.delete(0, "end")
        for it in items[:200]:
            self.lb.insert("end", it)
        self.lb.configure(height=min(self.MAX_ROWS, len(items)))
        x, y = cb.winfo_rootx(), cb.winfo_rooty() + cb.winfo_height()
        import tkinter.font as tkfont
        f = tkfont.Font(font=self.lb.cget("font"))
        w = max(cb.winfo_width(), min(int(520 * self.app.scale), max(f.measure(str(i)) for i in items[:200]) + 24))
        self.win.geometry(f"{w}x{self.lb.winfo_reqheight() + 2}+{x}+{y}")
        self.win.deiconify()
        self.win.lift()

    def _focus_check(self):
        try:
            f = self.root.focus_get()
        except (tk.TclError, KeyError):
            f = None
        if f is not self.cb and f is not self.lb:
            self.close()

    def close(self):
        if self.win is not None:
            try:
                self.win.destroy()
            except tk.TclError:
                pass
        self.win = self.lb = None
        self.cb = None

    def _open(self):
        return self.win is not None and self.lb is not None

    def _move(self, d):
        if not self._open():
            return None
        n = self.lb.size()
        cur = self.lb.curselection()
        i = (cur[0] + d) if cur else (0 if d > 0 else n - 1)
        i = max(0, min(n - 1, i))
        self.lb.selection_clear(0, "end")
        self.lb.selection_set(i)
        self.lb.see(i)
        return "break"  # keep ttk from opening its own list

    def _esc(self):
        if self._open():
            self.close()
            return "break"
        return None

    def _pick_current(self):
        if not self._open():
            return None
        cur = self.lb.curselection()
        if not cur:
            if self.lb.size() == 1:
                cur = (0,)
            else:
                self.close()
                return None  # Enter with nothing highlighted: let the box handle it as before
        val = self.lb.get(cur[0])
        cb = self.cb
        self.close()
        cb.set(val)
        cb.icursor("end")
        cb.focus_set()
        cb.event_generate("<<ComboboxSelected>>")
        return "break"


class TabBar(tk.Canvas):
    """The main tabs as rounded pills that wrap onto a second row when the window is narrow
    (ttk's own tabs just get cut off). Drives a ttk.Notebook whose own tab strip is hidden."""

    def __init__(self, parent, app, nb):
        super().__init__(parent, bg=BG, highlightthickness=0, bd=0, height=10)
        self.app, self.nb = app, nb
        import tkinter.font as tkfont
        self.font = tkfont.Font(family=app.F_UI, size=8, weight="bold")
        self.h = int(26 * app.scale)
        self.hover = None
        self._last_w = None
        self.bind("<Configure>", self._resized)
        nb.bind("<<NotebookTabChanged>>", lambda e: self.draw(), add="+")
        self.bind("<Motion>", self._motion)
        self.bind("<Leave>", lambda e: self._set_hover(None))
        self.bind("<Button-1>", self._click)
        self.spots = []

    def _resized(self, e):
        if e.width != self._last_w:
            self._last_w = e.width
            self.draw()

    def _tabs(self):
        out = []
        for t in self.nb.tabs():
            try:
                if self.nb.tab(t, "state") != "hidden":
                    out.append((t, self.nb.tab(t, "text")))
            except tk.TclError:
                pass
        return out

    def draw(self):
        self.delete("all")
        self.spots = []
        W = max(self.winfo_width(), 200)
        try:
            cur = self.nb.select()
        except tk.TclError:
            cur = ""
        x, y, gap, pad = 0, 0, 4, int(9 * self.app.scale)
        for t, text in self._tabs():
            w = self.font.measure(text) + 2 * pad
            if x and x + w > W:
                x, y = 0, y + self.h + gap
            sel, hov = t == cur, t == self.hover
            fill = PANEL_HI if sel else (PANEL if hov else BG)
            line = CYAN_DIM if sel else (CYAN if hov else LINE)
            col = "#ffffff" if sel else (CYAN if hov else MUTED)
            self.create_polygon(round_points(x + 1, y + 1, x + w - 1, y + self.h - 1, 8), smooth=True,
                                fill=fill, outline=line)
            if sel:
                self.create_line(x + 8, y + 2, x + w - 8, y + 2, fill=CYAN, width=2)
            self.create_text(x + w // 2, y + self.h // 2, text=text, fill=col, font=self.font)
            self.spots.append((x, y, x + w, y + self.h, t))
            x += w + gap
        want = y + self.h + 4
        if int(self.cget("height")) != want:
            self.configure(height=want)

    def _at(self, e):
        for x0, y0, x1, y1, t in self.spots:
            if x0 <= e.x <= x1 and y0 <= e.y <= y1:
                return t
        return None

    def _set_hover(self, t):
        if t != self.hover:
            self.hover = t
            self.configure(cursor="hand2" if t else "")
            self.draw()
            self._hint(t)

    def _hint(self, t):
        """After a moment on a tab, show which key opens it."""
        if getattr(self, "_hint_job", None):
            self.after_cancel(self._hint_job)
            self._hint_job = None
        if getattr(self, "_hint_win", None):
            self._hint_win.destroy()
            self._hint_win = None
        if not t or not getattr(self.app, "show_tips", True):
            return

        def show():
            self._hint_job = None
            if self.hover != t:
                return
            name = self.nb.tab(t, "text")
            key = self.app._tab_hotkey(name)
            spot = next((s for s in self.spots if s[4] == t), None)
            if not spot:
                return
            w = tk.Toplevel(self)
            w.overrideredirect(True)
            try:
                w.attributes("-topmost", True)
            except tk.TclError:
                pass
            txt = f"{name}   {key}" if key else f"{name}   (no key: set one in SETTINGS > HOTKEYS)"
            tk.Label(w, text=txt, bg=BG, fg=FG, font=(self.app.F_UI, 9), padx=8, pady=4,
                     highlightthickness=1, highlightbackground=CYAN_DIM).pack()
            w.geometry(f"+{self.winfo_rootx() + spot[0]}+{self.winfo_rooty() + spot[3] + 4}")
            self._hint_win = w
        self._hint_job = self.after(600, show)

    def _motion(self, e):
        self._set_hover(self._at(e))

    def _click(self, e):
        t = self._at(e)
        if t:
            self.nb.select(t)


class Ticker(tk.Frame):
    """A strip that scrolls items right to left like a stock ticker. Hover pauses it;
    click an item to open it. Moves in whole pixels by elapsed time, so it stays smooth
    even when the computer is busy."""

    SPEED = 45.0  # pixels per second
    _all = []
    _job = None
    _last = None

    def __init__(self, parent, app, label, color):
        super().__init__(parent, bg=PANEL)
        self.app = app
        h = int(22 * app.scale)
        self.h, self.label, self.color = h, label, color
        self.badge = tk.Canvas(self, height=h, bg=PANEL, highlightthickness=0, bd=0)
        self.badge.pack(side="left")
        self.c = tk.Canvas(self, height=h, bg=PANEL, highlightthickness=0, bd=0, cursor="hand2")
        self.c.pack(side="left", fill="x", expand=True)
        self.items = []
        self.groups = []  # [[tag, x, width]]
        self.paused = False
        self._frac = 0.0
        self.c.bind("<Enter>", lambda e: setattr(self, "paused", True))
        self.c.bind("<Leave>", lambda e: setattr(self, "paused", False))
        self._draw_badge()
        Ticker._all.append(self)
        if Ticker._job is None:
            Ticker._job = self.after(20, Ticker._tick_all)

    def _draw_badge(self):
        b, F = self.badge, self.app.F_UI
        t = b.create_text(10, self.h // 2, anchor="w", text=self.label, fill="#ffffff", font=(F, 8, "bold"))
        x1 = b.bbox(t)[2] + 10
        p = b.create_polygon(round_points(1, 2, x1, self.h - 2, 8), smooth=True, fill=self.color, outline="")
        b.tag_lower(p)
        b.configure(width=x1 + 8)

    def set_items(self, items):
        self.items = list(items)
        self._layout()

    def _layout(self):
        c = self.c
        c.delete("all")
        self.groups = []
        F, M = self.app.F_UI, self.app.F_MONO
        x = 4
        for n, (segs, click) in enumerate(self.items):
            tag = f"g{n}"
            gx = x
            for text, col in segs:
                t = c.create_text(x, self.h // 2, anchor="w", text=text, fill=col,
                                  font=(M if any(ch.isdigit() for ch in text) and len(text) < 14 else F, 9, "bold"),
                                  tags=tag)
                x = c.bbox(t)[2] + 5
            x += 26
            c.create_text(x - 15, self.h // 2, text="•", fill=LINE, font=(F, 9), tags=tag)
            if click:
                c.tag_bind(tag, "<Button-1>", lambda e, k=click: k())
            self.groups.append([tag, gx, x - gx])
        if not self.items:
            c.create_text(4, self.h // 2, anchor="w", text="Loading...", fill=MUTED, font=(F, 8))

    def _advance(self, px):
        if not self.groups or self.paused:
            return
        self._frac += px
        step = int(self._frac)
        if step < 1:
            return
        self._frac -= step
        c = self.c
        for g in self.groups:
            c.move(g[0], -step, 0)
            g[1] -= step
        first = self.groups[0]
        if first[1] + first[2] < 0:  # scrolled off the left: send it to the end of the line
            last = self.groups[-1]
            end = max(last[1] + last[2], c.winfo_width())
            c.move(first[0], end - first[1], 0)
            first[1] = end
            self.groups.append(self.groups.pop(0))

    @classmethod
    def _tick_all(cls):
        import time as _t
        now = _t.perf_counter()
        dt = min(0.1, now - cls._last) if cls._last else 0.0
        cls._last = now
        alive = []
        for t in cls._all:
            try:
                if t.winfo_exists():
                    alive.append(t)
                    if t.winfo_ismapped():
                        t._advance(cls.SPEED * dt)
            except tk.TclError:
                pass
        cls._all = alive
        if alive:
            cls._job = alive[0].after(16, cls._tick_all)
        else:
            cls._job = None


class HudPanel(tk.Canvas):
    """A panel with a thin outline, cut corner and bracket accents. Put widgets
    inside `.inner`."""

    def __init__(self, parent, pad=12, cut=14, **kw):
        super().__init__(parent, bg=BG, highlightthickness=0, bd=0, **kw)
        self.pad, self.cut = pad, cut
        self.inner = tk.Frame(self, bg=PANEL)
        self._win = self.create_window(pad, pad, window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", self._fit)
        self.bind("<Configure>", self._draw)

    def _fit(self, _e=None):
        h = self.inner.winfo_reqheight() + self.pad * 2
        if int(self.cget("height")) != h:
            self.configure(height=h)

    def _draw(self, _e=None):
        w, h, c, p = self.winfo_width(), self.winfo_height(), self.cut, self.pad
        self.itemconfigure(self._win, width=max(1, w - p * 2))
        self.delete("deco")
        self.create_polygon(round_points(1, 1, w - 1, h - 1, c), smooth=True, fill=PANEL, outline=LINE,
                            width=1, tags="deco")
        # a soft cyan line along the top edge
        self.create_line(c + 6, 1, min(w - c - 6, c + 120), 1, fill=CYAN_DIM, width=2, capstyle="round",
                         tags="deco")
        self.tag_lower("deco")


class WelcomeDialog(tk.Toplevel):
    """A short first-run walkthrough: game log, balance, ships, look and keys."""

    PAGES = ("welcome", "gamelog", "money", "ships", "look", "done")

    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.title(f"Welcome to {APP_TITLE}")
        self.configure(bg=PANEL)
        self.resizable(False, False)
        try:
            self.attributes("-topmost", True)
        except tk.TclError:
            pass
        w, h = int(620 * app.scale), int(440 * app.scale)
        x = master.winfo_rootx() + max(0, (master.winfo_width() - w) // 2)
        y = master.winfo_rooty() + 80
        self.geometry(f"{w}x{h}+{x}+{y}")
        self.i = 0
        bar = tk.Frame(self, bg=PANEL, padx=18, pady=10)
        bar.pack(fill="x", side="bottom")
        self.body = tk.Frame(self, bg=PANEL, padx=18, pady=14)
        self.body.pack(fill="both", expand=True)
        self.lbl_step = tk.Label(bar, text="", bg=PANEL, fg=MUTED, font=(app.F_UI, 8))
        self.lbl_step.pack(side="left")
        self.btn_next = ttk.Button(bar, text="NEXT", style="Accent.TButton", command=self.next)
        self.btn_next.pack(side="right")
        self.btn_back = ttk.Button(bar, text="BACK", command=self.back)
        self.btn_back.pack(side="right", padx=6)
        ttk.Button(bar, text="SKIP", command=self.finish).pack(side="right")
        self.protocol("WM_DELETE_WINDOW", self.finish)
        self.show()

    # helpers
    def h(self, text):
        tk.Label(self.body, text=text, bg=PANEL, fg=CYAN, font=(self.app.F_UI, 15, "bold"), anchor="w"
                 ).pack(fill="x")

    def p(self, text, color=FG, size=10):
        lbl = tk.Label(self.body, text=text, bg=PANEL, fg=color, font=(self.app.F_UI, size), anchor="w",
                       justify="left", wraplength=int(570 * self.app.scale))
        lbl.pack(fill="x", pady=(8, 0))
        return lbl

    def clear(self):
        for w in self.body.winfo_children():
            w.destroy()

    def show(self):
        self.clear()
        page = self.PAGES[self.i]
        getattr(self, "page_" + page)()
        self.lbl_step.configure(text=f"Step {self.i + 1} of {len(self.PAGES)}")
        self.btn_back.configure(state="normal" if self.i else "disabled")
        self.btn_next.configure(text="START" if page == "done" else "NEXT")

    def next(self):
        page = self.PAGES[self.i]
        if page == "money":
            self.save_money()
        if page == "look":
            self.save_look()
        if self.i + 1 >= len(self.PAGES):
            self.finish()
            return
        self.i += 1
        self.show()

    def back(self):
        if self.i:
            self.i -= 1
            self.show()

    def finish(self):
        self.app._save_setting("welcomed", True)
        self.destroy()

    # pages
    def page_welcome(self):
        self.h("Welcome to Starboard")
        self.p("Your companion for everything you do in Star Citizen: where you are and how to get anywhere, mining, "
               "hauling, salvage, bounties and missions, where to buy anything, your ships and your money. One "
               "window instead of a dozen websites.")
        self.p("This guide takes a minute. Everything here can be changed later in SETTINGS, and you can open the "
               "guide again from there.", MUTED, 9)
        self.p(DISCLAIMER, MUTED, 8)

    def page_gamelog(self):
        a = self.app
        self.h("Connect to the game")
        self.p("Starboard reads Star Citizen's own log file while you play. It adds your trades, purchases and "
               "contract payouts to your ledger, tracks bounties and knows where you are. It only reads the file.")
        path = getattr(a, "gl_path", None) if a.gl else None
        self.lbl_gl = self.p(f"Found: {path}" if path else "Not found yet.", GREEN if path else AMBER, 9)
        row = tk.Frame(self.body, bg=PANEL)
        row.pack(fill="x", pady=(8, 0))
        ttk.Button(row, text="FIND IT", command=self.find_log).pack(side="left")
        ttk.Button(row, text="CHOOSE FILE", command=self.choose_log).pack(side="left", padx=6)
        self.p("It is called Game.log, in your StarCitizen\\LIVE folder (for example C:\\Program Files\\Roberts Space "
               "Industries\\StarCitizen\\LIVE).", MUTED, 9)
        self.p("Position: in game, press F9 (or type /showlocation in chat) and Starboard shows where you are, the "
               "closest places and how to get to your target.", FG, 9)

    def find_log(self):
        self.app._gl_start(force_find=True)
        path = getattr(self.app, "gl_path", None) if self.app.gl else None
        self.lbl_gl.configure(text=f"Found: {path}" if path else "Not found. Use CHOOSE FILE.",
                              fg=GREEN if path else AMBER)

    def choose_log(self):
        self.app._gl_choose()
        path = getattr(self.app, "gl_path", None) if self.app.gl else None
        if path:
            self.lbl_gl.configure(text=f"Using: {path}", fg=GREEN)

    def page_money(self):
        self.h("Your money")
        self.p("Type the aUEC balance shown in your mobiGlas (top right). Starboard keeps a ledger from there: every "
               "payout and purchase, profit per session and per hour. Leave it empty to skip.")
        row = tk.Frame(self.body, bg=PANEL)
        row.pack(fill="x", pady=(10, 0))
        tk.Label(row, text="BALANCE", bg=PANEL, fg=MUTED, font=(self.app.F_UI, 8, "bold")).pack(side="left")
        self.v_money = tk.StringVar()
        ttk.Entry(row, textvariable=self.v_money, width=16).pack(side="left", padx=8)

    def save_money(self):
        text = self.v_money.get().strip() if hasattr(self, "v_money") else ""
        v = ledger.parse_amount(text) if text else None
        if v is not None:
            self.app.ledger.set_balance(v)
            self.app._fill_ledger()

    def page_ships(self):
        a = self.app
        self.h("Your ships")
        self.p("Add the ships you own. Hauling then knows your cargo space, and MY SHIPS remembers where each one is "
               "parked. You can add more later in HANGAR.")
        row = tk.Frame(self.body, bg=PANEL)
        row.pack(fill="x", pady=(10, 0))
        self.v_ship = tk.StringVar()
        ships = a.trade.all_ships() if a.trade and a.trade.loaded else []
        self.cb_ship = ttk.Combobox(row, textvariable=self.v_ship, values=ships, width=30)
        self.cb_ship.pack(side="left")
        self.cb_ship.bind("<KeyRelease>", self.filter_ships)
        self._all_ships = ships
        ttk.Button(row, text="ADD", style="Accent.TButton", command=self.add_ship).pack(side="left", padx=6)
        if not ships:
            ttk.Button(row, text="DOWNLOAD SHIP LIST", command=self.dl_ships).pack(side="left")
        owned = ", ".join(a.hangar.label(s) for s in a.hangar.ships)
        self.lbl_owned = self.p(f"In your hangar: {owned}" if owned else "No ships yet.", MUTED, 9)

    def filter_ships(self, _e=None):
        q = self.v_ship.get().lower()
        self.cb_ship.configure(values=[s for s in self._all_ships if q in s.lower()] or self._all_ships)

    def dl_ships(self):
        self.app._haul_download()
        self.lbl_owned.configure(text="Downloading the ship list from UEX; this page refreshes in a few seconds.",
                                 fg=CYAN)
        self.after(8000, lambda: self.winfo_exists() and self.PAGES[self.i] == "ships" and self.show())

    def add_ship(self):
        a = self.app
        name = self.v_ship.get().strip()
        if not name or (self._all_ships and name not in self._all_ships):
            self.lbl_owned.configure(text="Pick a ship from the list.", fg=AMBER)
            return
        e = a.hangar.add(name)
        if len(a.hangar.ships) == 1:
            a._ship_apply(e)
        a._fill_hangar()
        self.v_ship.set("")
        self.lbl_owned.configure(text="In your hangar: " + ", ".join(a.hangar.label(s) for s in a.hangar.ships),
                                 fg=GREEN)

    def page_look(self):
        self.h("Easy to read")
        self.p("Pick a text size and colors that suit you. These apply the next time Starboard starts.")
        st = self.app._settings()
        row = tk.Frame(self.body, bg=PANEL)
        row.pack(fill="x", pady=(10, 0))
        tk.Label(row, text="TEXT SIZE", bg=PANEL, fg=MUTED, font=(self.app.F_UI, 8, "bold")).pack(side="left")
        cur = min(TEXT_SIZES, key=lambda t: abs(t[1] - float(st.get("text_scale", 1.0) or 1.0)))[0]
        self.v_size = tk.StringVar(value=cur)
        ttk.Combobox(row, textvariable=self.v_size, values=[n for n, _ in TEXT_SIZES], state="readonly",
                     width=12).pack(side="left", padx=(6, 16))
        tk.Label(row, text="COLORS", bg=PANEL, fg=MUTED, font=(self.app.F_UI, 8, "bold")).pack(side="left")
        self.v_color = tk.StringVar(value=st.get("color_mode", "Default"))
        ttk.Combobox(row, textvariable=self.v_color, values=COLOR_MODES, state="readonly",
                     width=22).pack(side="left", padx=6)
        self.p("Colorblind modes swap the colors that carry meaning (good, warning, danger) for ones you can tell "
               "apart. High contrast uses black backgrounds and bright text.", MUTED, 9)

    def save_look(self):
        self.app._save_setting("text_scale", dict(TEXT_SIZES).get(self.v_size.get(), 1.0))
        self.app._save_setting("color_mode", self.v_color.get())

    def page_done(self):
        self.h("You are set")
        self.p("Handy keys, also while the game has focus:")
        self.p("F9  where am I (sends /showlocation)\nF8  identify a scanned signature\nCtrl+Shift+S  show or hide "
               "Starboard\nCtrl+Shift+1 to 9, then 0  open the tabs in order: HOME, LIVE, NAVIGATE, MINE, "
               "SALVAGE, HAUL, COMBAT, MISSIONS, SHOP, CRAFT", FG, 10)
        self.p("Start on HOME: the RIGHT NOW card suggests what to do, and each card takes you to the right tab. "
               "Hover over things for help.", MUTED, 9)


class App:
    def __init__(self, root):
        self.root = root
        self.world = core.World()
        self.sigdb = signatures.SignatureDB(self.world.data_dir, self.world.user_dir)
        self.last_scan = None
        self.scan_history = []
        self.reader = None
        self._reader_q = queue.Queue()
        self._last_screen_sig = (None, 0.0)
        self.hk = None
        self._hk_q = queue.Queue()
        self._ui_q = queue.Queue()  # work threads hand UI updates to the main thread through this
        self.repeat_on = False
        self._repeat_job = None
        self.toast = None
        self.sig_prompt = None
        self.here = None
        self.target = None
        self.last_clip = None
        self.system_choice = tk.StringVar(value="Auto")
        self.on_top = tk.BooleanVar(value=True)
        self.filter_text = tk.StringVar()
        self.filter_type = tk.StringVar(value="All types")
        self.ore_body = tk.StringVar()
        self.last_system = "Stanton"
        self.prev_here = None
        self.motion = None
        self.overlay = None
        self.overlay_locked = True
        self.ore_material = tk.StringVar()
        self._finder_map = {}
        self._blink = False
        self._near_map = {}
        self._iid_to_loc = {}

        st0 = self._settings()
        edition.load_fonts(EDITION)
        efonts = EDITION.get("fonts") or {}
        self.F_UI = pick_font(([efonts["ui"]] if efonts.get("ui") else []) +
                              ["Bahnschrift SemiCondensed", "Bahnschrift", "Segoe UI", "DejaVu Sans"], "TkDefaultFont")
        self.F_TITLE = pick_font([efonts["title"]], self.F_UI) if efonts.get("title") else self.F_UI
        if st0.get("font", "Default") != "Default" and st0.get("font") in tkfont.families():
            self.F_UI = st0["font"]
        self.scale = float(st0.get("text_scale", 1.0) or 1.0)
        self.scale = min(1.6, max(0.8, self.scale))
        global CLOCK_12H
        CLOCK_12H = bool(st0.get("clock_12h"))
        self._base_scaling = float(root.tk.call("tk", "scaling"))
        root.tk.call("tk", "scaling", self._base_scaling * self.scale)
        self.reduce_flash = st0.get("reduce_flash", False)
        self.show_tips = st0.get("show_tips", True)
        self.on_top.set(st0.get("on_top", True))
        self.F_MONO = pick_font(["Cascadia Mono", "Consolas", "Lucida Console", "DejaVu Sans Mono"], "TkFixedFont")

        root.title(f"{APP_TITLE} {APP_VERSION}")
        try:
            self._icon = tk.PhotoImage(file=edition.path(EDITION, EDITION.get("icon")) or
                                       os.path.join(core.DATA_DIR, "icon.png"))
            root.iconphoto(True, self._icon)
        except tk.TclError:
            pass
        root.geometry(self._start_geometry(st0))
        root.minsize(int(620 * self.scale), min(int(720 * self.scale), root.winfo_screenheight() - 80))
        root.configure(bg=BG)
        root.attributes("-topmost", self.on_top.get())
        try:
            root.attributes("-alpha", float(st0.get("opacity", 100)) / 100)
        except (tk.TclError, ValueError):
            pass
        self._style()
        self._build()
        self._fill_browse()
        self._refresh_ore_bodies()
        self._fill_types()
        self._fill_nearby()
        self.root.after(POLL_MS, self._poll_clipboard)
        self.root.after(700, self._tick)
        self.root.after(300, self._start_hotkeys)
        self.root.after(1200, self._gl_start)
        self.root.after(100, self._ui_poll)
        self.root.after(20000, self._auto_tick)
        self.root.after(30000, self._bp_first_scan)
        self.root.after(8000, lambda: self._update_check(quiet=True))
        self.root.after(4000, lambda: self._make_shortcut(quiet=True))
        self._empty_texts()
        self._apply_compact()
        if not self._settings().get("welcomed"):
            self.root.after(1800, lambda: WelcomeDialog(self.root, self))

    # ------------------------------------------------------------ look
    def _style(self):
        s = ttk.Style(self.root)
        try:
            s.theme_use("clam")
        except tk.TclError:
            pass
        ui, mono = self.F_UI, self.F_MONO
        s.configure(".", background=BG, foreground=FG, fieldbackground=PANEL, font=(ui, 10),
                    bordercolor=LINE, lightcolor=LINE, darkcolor=LINE, troughcolor=BG)
        s.configure("TFrame", background=BG)
        s.configure("Panel.TFrame", background=PANEL)
        s.configure("TCheckbutton", background=BG, foreground=MUTED, font=(ui, 9),
                    indicatorbackground=PANEL, indicatorforeground=CYAN)
        s.map("TCheckbutton", background=[("active", BG)], foreground=[("active", CYAN)])
        s.configure("Panel.TCheckbutton", background=PANEL, foreground=MUTED, font=(ui, 9),
                    indicatorbackground=BG, indicatorforeground=CYAN)
        s.map("Panel.TCheckbutton", background=[("active", PANEL)], foreground=[("active", CYAN)])
        s.configure("TButton", background=PANEL_HI, foreground=CYAN, font=(ui, 9, "bold"),
                    bordercolor=CYAN_DIM, lightcolor=PANEL_HI, darkcolor=PANEL_HI,
                    borderwidth=1, padding=(10, 5), focuscolor=PANEL_HI, width=-4)
        s.map("TButton", background=[("pressed", CYAN_FAINT), ("active", BTN_HOVER)],
              bordercolor=[("active", CYAN)], foreground=[("active", "#ffffff")])
        s.configure("Accent.TButton", background=ORANGE, foreground=ON_ACCENT, font=(ui, 9, "bold"),
                    bordercolor=ORANGE, lightcolor=ORANGE, darkcolor=ORANGE, borderwidth=1, padding=(10, 5),
                    focuscolor=ORANGE, width=-4)
        s.map("Accent.TButton", background=[("pressed", ACCENT_PRESSED), ("active", ORANGE_HI)],
              bordercolor=[("active", ORANGE_HI)], foreground=[("active", "#000000")],
              lightcolor=[("active", ORANGE_HI)], darkcolor=[("active", ORANGE_HI)])
        s.configure("Small.TButton", background=PANEL_HI, foreground=CYAN, font=(ui, 8, "bold"), padding=(6, 2),
                    bordercolor=CYAN_DIM, lightcolor=PANEL_HI, darkcolor=PANEL_HI)
        s.map("Small.TButton", background=[("pressed", CYAN_FAINT), ("active", BTN_HOVER)])
        s.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 0, 0, 0))
        s.configure("Main.TNotebook", background=BG, borderwidth=0, tabmargins=(0, 0, 0, 0))
        s.layout("Main.TNotebook.Tab", [])
        s.configure("TNotebook.Tab", background=BG, foreground=MUTED, font=(ui, 8, "bold"),
                    padding=(5, 6), bordercolor=LINE, lightcolor=BG, darkcolor=BG)
        s.map("TNotebook.Tab", background=[("selected", PANEL_HI), ("active", PANEL)],
              foreground=[("selected", "#ffffff"), ("active", CYAN)],
              lightcolor=[("selected", CYAN)], bordercolor=[("selected", CYAN_DIM)])
        s.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=FG,
                    rowheight=int(25 * self.scale), borderwidth=0, font=(ui, 10))
        s.configure("Treeview.Heading", background=BAND, foreground=CYAN, relief="flat",
                    font=(ui, 8, "bold"), bordercolor=LINE, lightcolor=BAND, darkcolor=BAND)
        s.map("Treeview.Heading", background=[("active", PANEL_HI)])
        s.map("Treeview", background=[("selected", CYAN_FAINT)], foreground=[("selected", "#ffffff")])
        s.configure("TCombobox", fieldbackground=PANEL, background=PANEL_HI, foreground=CYAN,
                    arrowcolor=CYAN, bordercolor=LINE, lightcolor=PANEL, darkcolor=PANEL, padding=3)
        s.map("TCombobox", fieldbackground=[("readonly", PANEL)], foreground=[("readonly", CYAN)],
              selectbackground=[("readonly", PANEL)], selectforeground=[("readonly", CYAN)],
              bordercolor=[("focus", CYAN_DIM)])
        s.configure("TEntry", fieldbackground=PANEL, foreground=FG, insertcolor=CYAN,
                    bordercolor=LINE, lightcolor=PANEL, darkcolor=PANEL, padding=3)
        s.map("TEntry", bordercolor=[("focus", CYAN_DIM)])
        s.configure("Vertical.TScrollbar", background=LINE, troughcolor=PANEL, arrowcolor=CYAN_DIM,
                    bordercolor=PANEL, lightcolor=LINE, darkcolor=LINE)
        self._round_styles(s)
        self.root.option_add("*TCombobox*Listbox.background", PANEL)
        self.root.option_add("*TCombobox*Listbox.foreground", FG)
        self.root.option_add("*TCombobox*Listbox.selectBackground", CYAN_FAINT)
        self.root.option_add("*TCombobox*Listbox.font", (ui, 10))

    def _round_styles(self, s):
        """Rounded corners for buttons and tabs: ttk draws them from small images and stretches the middle."""
        r = max(6, int(9 * self.scale))
        size = r * 2 + 6
        self._round_imgs = imgs = {}

        def img(key, fill, border, top_only=False):
            if key not in imgs:
                imgs[key] = tk.PhotoImage(data=round_png(size, size, r, fill, border, top_only,
                                                         grow=(int(320 * self.scale), int(56 * self.scale))))
            return imgs[key]
        try:
            for style, (n_f, n_b), (a_f, a_b), (p_f, p_b) in (
                    ("TButton", (PANEL_HI, CYAN_DIM), (BTN_HOVER, CYAN), (CYAN_FAINT, CYAN)),
                    ("Accent.TButton", (ORANGE, ORANGE), (ORANGE_HI, ORANGE_HI), (ACCENT_PRESSED, ACCENT_PRESSED)),
                    ("Small.TButton", (PANEL_HI, CYAN_DIM), (BTN_HOVER, CYAN), (CYAN_FAINT, CYAN))):
                el = style.replace(".", "_") + "_round"
                s.element_create(el, "image", img(el + "n", n_f, n_b),
                                 ("disabled", img(el + "d", PANEL, LINE)),
                                 ("pressed", img(el + "p", p_f, p_b)), ("active", img(el + "a", a_f, a_b)),
                                 border=r + 1, sticky="nsew", width=size, height=size)
                s.layout(style, [(el, {"sticky": "nsew", "children": [
                    ("Button.padding", {"sticky": "nsew", "children": [
                        ("Button.label", {"sticky": "nsew"})]})]})])
                # ttk paints the whole widget in its background first: make that the panel color so the
                # rounded corners blend in, and let the images show hover and press
                s.configure(style, background=PANEL)
                s.map(style, background=[])
            s.element_create("Tab_round", "image", img("tab_n", BG, LINE, True),
                             ("selected", img("tab_s", PANEL_HI, CYAN_DIM, True)),
                             ("active", img("tab_a", PANEL, LINE, True)),
                             border=(r + 1, r + 1, r + 1, 2), sticky="nsew", width=size, height=size)
            s.layout("TNotebook.Tab", [("Tab_round", {"sticky": "nsew", "children": [
                ("Notebook.padding", {"side": "top", "sticky": "nsew", "children": [
                    ("Notebook.label", {"side": "top", "sticky": ""})]})]})])
            s.configure("TNotebook.Tab", padding=(7, 6), background=BG)
            s.map("TNotebook.Tab", background=[])
        except tk.TclError as e:
            hotkeys_win.log(f"rounded styles: {e!r}")  # keep the square look rather than fail

    def _lbl(self, parent, text="", size=10, color=FG, bold=False, mono=False, **kw):
        if kw.get("wraplength"):
            kw["wraplength"] = int(kw["wraplength"] * getattr(self, "scale", 1.0))
        font = (self.F_MONO if mono else self.F_UI, size, "bold" if bold else "normal")
        try:
            bg = parent.cget("bg")
        except tk.TclError:
            bg = PANEL  # ttk frames inside the notebook use the panel color
        return tk.Label(parent, text=text, bg=bg, fg=color, font=font,
                        anchor="w", justify="left", **kw)

    # ------------------------------------------------------------ layout
    def _build(self):
        self._build_scroller()
        self.suggest = Suggest(self.root, self)
        # header bar
        self.header = tk.Canvas(self.body, height=int(HEADER_H * self.scale), bg=BG, highlightthickness=0)
        self.header.pack(fill="x")
        self._hdr_job = None

        def hdr(_e):
            if self._hdr_job:
                self.root.after_cancel(self._hdr_job)
            self._hdr_job = self.root.after(250, self._draw_header)
        self.header.bind("<Configure>", hdr)
        self.tick_box = tk.Frame(self.body, bg=BG)
        self.tick_box.pack(fill="x", padx=14, pady=(2, 0))
        self.tick_market = Ticker(self.tick_box, self, "MARKET", GREEN)
        self.tick_news = Ticker(self.tick_box, self, "NEWS", PURPLE)
        self._ticker_show()
        self.root.after(2500, self._news_refresh)

        bar = tk.Frame(self.body, bg=BG)
        bar.pack(fill="x", padx=14, pady=(2, 8))
        self._lbl(bar, spaced("system"), 8, MUTED, bold=True).pack(side="left")
        cb = ttk.Combobox(bar, textvariable=self.system_choice, width=9, state="readonly",
                          values=["Auto"] + self.world.systems())
        cb.pack(side="left", padx=(8, 14))
        cb.bind("<<ComboboxSelected>>", lambda e: self._recompute())
        b = ttk.Checkbutton(bar, text="ON TOP", variable=self.on_top, command=self._on_top_changed)
        b.pack(side="left")
        self._tip(b, "Keep this window above the game.")
        b = ttk.Button(bar, text="PASTE", command=self._manual_paste)
        b.pack(side="right")
        self._tip(b, "Read a /showlocation result you copied yourself (Starboard normally does this for you).")
        self.btn_lock = ttk.Button(bar, text="UNLOCK", command=self._toggle_lock)
        self.btn_lock.pack(side="right", padx=(0, 6))
        self._tip(self.btn_lock, "UNLOCK lets you drag and resize the in-game overlay. LOCK makes it click-through "
                                 "again.")
        self.btn_overlay = ttk.Button(bar, text="OVERLAY ON", command=self._toggle_overlay)
        self.btn_overlay.pack(side="right", padx=(0, 6))
        self._tip(self.btn_overlay, "A small see-through panel on top of the game with your position, target and "
                                    "timers. Play in Borderless mode for it to show.")
        self.compact = tk.BooleanVar(value=self._settings().get("compact", False))
        self.btn_compact = ttk.Button(bar, text="FULL" if self.compact.get() else "COMPACT",
                                      command=self._toggle_compact)
        self.btn_compact.pack(side="right", padx=(0, 6))
        self._tip(self.btn_compact, "COMPACT folds the position panel into one line, so the tabs below get more "
                                    "room. FULL shows it again.")

        # one-line position strip, shown in compact mode
        self._compact_box = RoundBox(self.body, fill=PANEL, accent=CYAN, radius=14, pad=(8, 3))
        self.compact_bar = self._compact_box
        cb = self._compact_box.inner
        self.lbl_compact = tk.Label(cb, text="NO FIX", bg=PANEL, fg=CYAN, anchor="w",
                                    font=(self.F_UI, 11, "bold"))
        self.lbl_compact.pack(side="left", padx=10, pady=5)
        self.lbl_compact2 = tk.Label(cb, text="", bg=PANEL, fg=FG, anchor="w", justify="left",
                                     font=(self.F_UI, 9))
        self.lbl_compact2.pack(side="left", fill="x", expand=True, padx=(0, 10), pady=3)

        def wrap_strip(_e=None):
            # long hints wrap onto a second line instead of running off the right edge
            room = self.compact_bar.winfo_width() - self.lbl_compact.winfo_reqwidth() - 40
            if room > 100 and self.lbl_compact2.cget("wraplength") != room:
                self.lbl_compact2.configure(wraplength=room)
        self.compact_bar.bind("<Configure>", wrap_strip, add="+")
        self.lbl_compact.bind("<Configure>", wrap_strip, add="+")

        # position card
        card = HudPanel(self.body)
        card.pack(fill="x", padx=12)
        self.pos_card = card
        inner = card.inner
        left = tk.Frame(inner, bg=PANEL)
        left.pack(side="left", fill="both", expand=True)
        self.lbl_kicker = self._lbl(left, spaced("current position"), 8, CYAN_DIM, bold=True)
        self.lbl_kicker.pack(anchor="w")
        self.lbl_where = self._lbl(left, "NO FIX", 22, CYAN, bold=True)
        self.lbl_where.pack(anchor="w", pady=(0, 0))
        self.lbl_sub = self._lbl(left, "TYPE /showlocation IN GAME CHAT", 9, MUTED, bold=True)
        self.lbl_sub.pack(anchor="w", pady=(0, 8))

        grid = tk.Frame(left, bg=PANEL)
        grid.pack(anchor="w", fill="x")
        self.readouts = {}
        for i, key in enumerate(("LAT", "LON", "ALT", "SPEED")):
            cell = tk.Frame(grid, bg=PANEL)
            cell.grid(row=0, column=i, sticky="w", padx=(0, 16))
            self._lbl(cell, key, 7, MUTED, bold=True).pack(anchor="w")
            v = self._lbl(cell, "---", 12, FG, mono=True)
            v.pack(anchor="w")
            self.readouts[key] = v

        self.lbl_near = self._lbl(left, "", 10, FG, wraplength=380)
        self.lbl_near.pack(anchor="w", pady=(10, 0))
        self.lbl_sun = self._lbl(left, "", 9, AMBER, bold=True, wraplength=380)
        self.lbl_sun.pack(anchor="w", pady=(4, 0))
        self.lbl_coords = self._lbl(left, "", 8, MUTED, mono=True)
        self.lbl_coords.pack(anchor="w", pady=(6, 0))

        right = tk.Frame(inner, bg=PANEL)
        right.pack(side="right", anchor="n")
        self.compass = tk.Canvas(right, width=150, height=150, bg=PANEL, highlightthickness=0)
        self.compass.pack()
        self.lbl_comp = self._lbl(right, "NO TARGET", 8, MUTED, bold=True)
        self.lbl_comp.configure(anchor="center", justify="center")
        self.lbl_comp.pack(fill="x")

        # target strip
        tgt = HudPanel(self.body, pad=8, cut=10)
        tgt.pack(fill="x", padx=12, pady=(8, 0))
        self.tgt_card = tgt
        trow = tgt.inner
        self._lbl(trow, spaced("target"), 8, GREEN, bold=True).pack(side="left", anchor="n", padx=(2, 12), pady=(2, 0))
        tcol = tk.Frame(trow, bg=PANEL)
        tcol.pack(side="left", fill="x", expand=True)
        self.lbl_target = self._lbl(tcol, "None set. Double-click a location below.", 10, MUTED,
                                    wraplength=440)
        self.lbl_target.pack(anchor="w", fill="x")
        self.lbl_motion = self._lbl(tcol, "", 9, FG, mono=True)
        self.lbl_motion.pack(anchor="w")
        self.lbl_route = self._lbl(tcol, "", 9, CYAN, wraplength=460)
        self.lbl_route.pack(anchor="w", pady=(2, 0))

        btns = tk.Frame(self.body, bg=BG)
        btns.pack(fill="x", padx=12, pady=8)
        self.hud_btns = btns
        b = ttk.Button(btns, text="SAVE SPOT", style="Accent.TButton", command=self._save_poi)
        b.pack(side="left")
        self._tip(b, "Save where you are right now (a cave, a wreck, a good rock) so you can fly back later.")
        b = ttk.Button(btns, text="LOG FIND", command=self._log_find)
        b.pack(side="left", padx=(6, 0))
        self._tip(b, "Log a mining or salvage find at your position (MINE > LOG).")
        b = ttk.Button(btns, text="CALIBRATE", command=self._calibrate)
        b.pack(side="left", padx=6)
        self._tip(b, "Stand at a known place and press this to correct Starboard's map for that planet or moon.")
        b = ttk.Button(btns, text="CLEAR TARGET", command=self._clear_target)
        b.pack(side="left")
        self._tip(b, "Stop guiding to the current target.")

        nb = ttk.Notebook(self.body, style="Main.TNotebook")
        self.tabbar = TabBar(self.body, self, nb)
        self.tabbar.pack(fill="x", padx=12)
        self.root.after_idle(self.tabbar.draw)
        nb.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.nb = nb
        # activity groups: NAVIGATE and MINE hold their own tabs
        self.nb_nav = ttk.Notebook(nb)
        self.nb_mine = ttk.Notebook(nb)

        f1 = ttk.Frame(self.nb_nav, style="Panel.TFrame", padding=8)
        self.nb_nav.add(f1, text="NEARBY")
        self.tab_near = f1
        flt = tk.Frame(f1, bg=PANEL)
        flt.pack(fill="x", pady=(0, 8))
        self._lbl(flt, "SEARCH", 7, MUTED, bold=True).pack(side="left", padx=(0, 6))
        e = ttk.Entry(flt, textvariable=self.filter_text, width=14)
        e.pack(side="left")
        e.bind("<KeyRelease>", lambda ev: self._fill_nearby())
        self._lbl(flt, "TYPE", 7, MUTED, bold=True).pack(side="left", padx=(10, 6))
        self.type_cb = ttk.Combobox(flt, textvariable=self.filter_type, width=18, state="readonly")
        self.type_cb.pack(side="left")
        self.type_cb.bind("<<ComboboxSelected>>", lambda ev: self._fill_nearby())
        self.near_body = tk.StringVar(value="Where I am")
        self.near_body_cb = ttk.Combobox(flt, textvariable=self.near_body, width=15, state="readonly",
                                         values=["Where I am"] + self._body_choices())
        self.near_body_cb.pack(side="right")
        self.near_body_cb.bind("<<ComboboxSelected>>", lambda ev: (self._fill_types(), self._fill_nearby()))
        self._lbl(flt, "BODY", 7, MUTED, bold=True).pack(side="right", padx=(10, 6))
        self.tree_near = self._tree(f1, [("name", "LOCATION", 230), ("type", "TYPE", 150),
                                         ("dist", "DISTANCE", 90), ("brg", "DIRECTION", 90)])
        self.tree_near.bind("<Double-1>", lambda ev: self._pick_from(self.tree_near))
        self.lbl_near_hint = self._lbl(f1, "Double-click to target. Distance is measured over the surface.", 8, MUTED,
                                       wraplength=640)
        self.lbl_near_hint.pack(anchor="w", pady=(6, 0))

        f9 = ttk.Frame(self.nb_mine, style="Panel.TFrame", padding=8)
        self.nb_mine.add(f9, text="SCAN")
        self.tab_scan = f9
        self._build_scan(f9)

        f6 = ttk.Frame(self.nb_nav, style="Panel.TFrame", padding=8)
        self.nb_nav.add(f6, text="MAP")
        self.tab_map = f6
        self._build_map(f6)

        f2 = ttk.Frame(self.nb_mine, style="Panel.TFrame", padding=8)
        self.nb_mine.add(f2, text="ORES")
        self.tab_ores = f2
        orow = tk.Frame(f2, bg=PANEL)
        orow.pack(fill="x", pady=(0, 8))
        self._lbl(orow, "BODY", 7, MUTED, bold=True).pack(side="left", padx=(0, 6))
        self.ore_cb = ttk.Combobox(orow, textvariable=self.ore_body, width=18, state="readonly")
        self.ore_cb.pack(side="left")
        self.ore_cb.bind("<<ComboboxSelected>>", lambda ev: self._fill_ores())
        self.ore_canvas_holder = f2
        self.tree_ore = self._tree(f2, [("name", "MATERIAL", 170), ("bar", "", 190), ("pct", "SHARE", 70)],
                                   show_tree=True)
        self.lbl_ore_note = self._lbl(f2, "", 8, MUTED, wraplength=520)
        self.lbl_ore_note.pack(anchor="w", pady=(6, 0))

        f5 = ttk.Frame(self.nb_mine, style="Panel.TFrame", padding=8)
        self.nb_mine.add(f5, text="FINDER")
        self.tab_finder = f5
        frow = tk.Frame(f5, bg=PANEL)
        frow.pack(fill="x", pady=(0, 8))
        self._lbl(frow, "MATERIAL", 7, MUTED, bold=True).pack(side="left", padx=(0, 6))
        mats = self.world.materials()
        self.mat_cb = ttk.Combobox(frow, textvariable=self.ore_material, values=mats, width=22, state="readonly")
        self.mat_cb.pack(side="left")
        self.mat_cb.bind("<<ComboboxSelected>>", lambda ev: self._fill_finder())
        self.lbl_finder_best = self._lbl(frow, "", 9, GREEN, bold=True)
        self.lbl_finder_best.pack(side="left", padx=(12, 0))
        self.tree_find = self._tree(f5, [("src", "WHERE", 150), ("sys", "SYSTEM", 70), ("how", "METHOD", 100),
                                         ("share", "SHARE", 60), ("dist", "DISTANCE", 95)])
        self.tree_find.tag_configure("best", foreground=GREEN)
        self.tree_find.bind("<Double-1>", self._finder_open)
        self.lbl_finder_note = self._lbl(f5, "Pick a material. Best places first; when two are equal, the closer one comes first. "
                                             "Double-click a row to see everything mined there.", 8, MUTED, wraplength=520)
        self.lbl_finder_note.pack(anchor="w", pady=(6, 0))
        if "Quantainium" in mats:
            self.ore_material.set("Quantainium")

        f7 = ttk.Frame(self.nb_mine, style="Panel.TFrame", padding=8)
        self.nb_mine.add(f7, text="LOG")
        self.tab_log = f7
        fr2 = ttk.Frame(self.nb_mine, style="Panel.TFrame", padding=8)
        self.tab_refining = fr2
        self._build_log(f7)

        f10 = ttk.Frame(nb, style="Panel.TFrame", padding=8)
        nb.add(f10, text="HAUL")
        self.tab_haul = f10
        self._build_haul(f10)

        f11 = ttk.Frame(nb, style="Panel.TFrame", padding=8)
        nb.add(f11, text="LEDGER")
        self.tab_ledger = f11
        self._build_ledger(f11)
        nb.bind("<<NotebookTabChanged>>", self._tab_changed)

        f3 = ttk.Frame(self.nb_nav, style="Panel.TFrame", padding=8)
        self.nb_nav.add(f3, text="SPACE")
        self.tab_space = f3
        self.tree_space = self._tree(f3, [("name", "NAME", 240), ("type", "TYPE", 140),
                                          ("dist", "DISTANCE", 110)])

        f4 = ttk.Frame(self.nb_nav, style="Panel.TFrame", padding=8)
        self.nb_nav.add(f4, text="STARMAP")
        self.tab_starmap = f4
        self.tree_browse = self._tree(f4, [("name", "NAME", 290), ("type", "TYPE", 160)], show_tree=True)
        self.tree_browse.bind("<Double-1>", lambda ev: self._pick_from(self.tree_browse))
        self.tree_browse.bind("<Button-3>", self._browse_menu)
        self._lbl(f4, "Double-click to target. Right-click for the wiki page, a share code, or to delete "
                      "your own entries.", 8, MUTED).pack(anchor="w", pady=(6, 0))

        self.nb_setup = ttk.Notebook(nb)
        nb.add(self.nb_setup, text="SETTINGS")
        f8 = ttk.Frame(self.nb_setup, style="Panel.TFrame", padding=8)
        self.nb_setup.add(f8, text="MAP DATA")
        self.tab_data = f8
        self._build_data(f8)
        fmd = ttk.Frame(self.nb_setup, style="Panel.TFrame", padding=8)
        self.nb_setup.add(fmd, text="MY DATA")
        self.tab_mydata = fmd
        self._build_mydata(fmd)
        self.nb_setup.bind("<<NotebookTabChanged>>", lambda e: self.nb_setup.select() == str(fmd) and
                           self._md_fill(), add="+")

        self.nb_mine.add(fr2, text="REFINING")
        self._build_refining(fr2)

        flo = ttk.Frame(self.nb_mine, style="Panel.TFrame", padding=8)
        self.nb_mine.add(flo, text="LOADOUT")
        self.tab_loadout = flo
        self._build_loadout(flo)

        fbe = ttk.Frame(self.nb_mine, style="Panel.TFrame", padding=8)
        self.nb_mine.add(fbe, text="BELTS")
        self.tab_belts = fbe
        self._build_belts(fbe)
        self.nb_mine.bind("<<NotebookTabChanged>>", lambda e: self.nb_mine.select() == str(fbe) and
                          self._belt_show(), add="+")
        self.nb_mine.bind("<<NotebookTabChanged>>", lambda e: self.nb_mine.select() == str(flo) and
                          self._tab_lazy(flo), add="+")

        fv = ttk.Frame(nb, style="Panel.TFrame", padding=8)
        nb.add(fv, text="SALVAGE")
        self.tab_salvage = fv
        self._build_salvage(fv)

        fc2 = ttk.Frame(nb, style="Panel.TFrame", padding=8)
        nb.add(fc2, text="COMBAT")
        self.tab_combat = fc2
        self._build_combat(fc2)

        fs = ttk.Frame(nb, style="Panel.TFrame", padding=8)
        nb.add(fs, text="SHOP")
        self.tab_shop = fs
        self._build_shop(fs)

        self.nb_hangar = ttk.Notebook(nb)
        nb.insert(0, self.nb_hangar, text="HANGAR")
        fh = ttk.Frame(self.nb_hangar, style="Panel.TFrame", padding=8)
        self.nb_hangar.add(fh, text="MY SHIPS")
        self.tab_hangar = fh
        self.hangar = hangar.Hangar(self.world.user_dir)
        self._build_hangar(fh)
        fsb = ttk.Frame(self.nb_hangar, style="Panel.TFrame", padding=8)
        self.nb_hangar.add(fsb, text="SHIP BUILDER")
        self.tab_builder = fsb
        self._build_builder(fsb)
        self.nb_hangar.bind("<<NotebookTabChanged>>", lambda e: self.nb_hangar.select() == str(fsb) and
                            self._sb_lazy(), add="+")

        fmi = ttk.Frame(nb, style="Panel.TFrame", padding=8)
        nb.add(fmi, text="MISSIONS")
        self.tab_missions = fmi
        self._build_missions(fmi)
        fcr = ttk.Frame(nb, style="Panel.TFrame", padding=8)
        nb.add(fcr, text="CRAFT")
        self.tab_craft = fcr
        self._build_craft(fcr)
        fev = ttk.Frame(nb, style="Panel.TFrame", padding=8)
        nb.add(fev, text="EVENTS")
        self.tab_events = fev
        self._build_events(fev)

        flv = ttk.Frame(nb, style="Panel.TFrame", padding=8)
        nb.add(flv, text="LIVE")
        self.tab_live = flv
        self._build_live(flv)

        fset = ttk.Frame(self.nb_setup, style="Panel.TFrame", padding=8)
        self.nb_setup.insert(0, fset, text="GENERAL")
        self.tab_settings = fset
        self._build_settings(fset)

        f0 = ttk.Frame(nb, style="Panel.TFrame", padding=8)
        nb.insert(0, f0, text="HOME")
        self.tab_home = f0
        self._build_home(f0)
        # final order of the main tabs
        # getting around | things you do | gear and money | info. Ctrl+Shift+1..9, 0 follow this order.
        for i, (w, text) in enumerate([(f0, "HOME"), (flv, "LIVE"), (self.nb_nav, "NAVIGATE"),
                                       (self.nb_mine, "MINE"), (fv, "SALVAGE"), (f10, "HAUL"), (fc2, "COMBAT"),
                                       (fmi, "MISSIONS"),
                                       (fs, "SHOP"), (fcr, "CRAFT"), (self.nb_hangar, "HANGAR"), (f11, "MONEY"),
                                       (self.tab_events, "EVENTS"), (self.nb_setup, "SETTINGS")]):
            nb.insert(i, w, text=text)
        # MINE in the order of a trip: scan rocks, find where to go, get there, then log, refine; setup last
        for i, w in enumerate([self.tab_scan, self.tab_finder, self.tab_belts, self.tab_ores, self.tab_log,
                               self.tab_refining, self.tab_loadout]):
            self.nb_mine.insert(i, w)
        nb.select(f0)
        if self.compact.get():
            self._apply_compact()

        self._draw_compass(None, None)
        self._fill_finder()

    def _tree(self, parent, cols, show_tree=False):
        frame = tk.Frame(parent, bg=LINE, padx=1, pady=1)
        frame.pack(fill="both", expand=True)
        # small requested height: the table grows to fill the tab, but never pushes the
        # buttons and notes under it out of the window
        tree = ttk.Treeview(frame, columns=[c[0] for c in cols], height=4,
                            show=("tree headings" if show_tree else "headings"))
        if show_tree:
            tree.column("#0", width=22, stretch=False)
        tree._labels = {}
        tree._sort = None
        tree._sort_pending = False
        for key, label, width in cols:
            tree._labels[key] = label
            tree.heading(key, text=label, anchor="w",
                         command=(lambda k=key, t=tree: self._sort_click(t, k)) if label else "")
            tree.column(key, width=width, anchor="w")
        plain_insert = tree.insert

        def insert(*a, **k):  # keep the chosen sort when a table is refilled
            iid = plain_insert(*a, **k)
            if tree._empty_lbl.winfo_ismapped():
                tree._empty_lbl.place_forget()
            if tree._sort and not tree._sort_pending:
                tree._sort_pending = True
                tree.after_idle(lambda: self._apply_sort(tree))
            return iid
        tree.insert = insert
        plain_delete = tree.delete

        def delete(*a, **k):
            plain_delete(*a, **k)
            self._empty_soon(tree)
        tree.delete = delete
        tree.empty_text = ""
        tree._empty_lbl = tk.Label(frame, text="", bg=CARD, fg=MUTED, font=(self.F_UI, 10), justify="center")
        tree._empty_pending = False
        sb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        tree.tag_configure("odd", background=ROW_ALT)
        tree.tag_configure("custom", foreground=AMBER)
        tree.tag_configure("log", foreground=GREEN)
        tree.tag_configure("head", foreground=CYAN, font=(self.F_UI, 9, "bold"))
        tree.tag_configure("mono", font=(self.F_MONO, 10))
        return tree

    def _empty_soon(self, tree):
        if not tree._empty_pending:
            tree._empty_pending = True
            tree.after_idle(lambda: self._empty_check(tree))

    def _empty_check(self, tree):
        tree._empty_pending = False
        lbl = tree._empty_lbl
        if tree.get_children() or not tree.empty_text:
            lbl.place_forget()
            return
        lbl.configure(text=tree.empty_text, wraplength=int(440 * self.scale))
        lbl.place(in_=tree, relx=0.5, rely=0.5, anchor="center")

    def _empty_texts(self):
        texts = {
            "tree_near": "No position yet.\nPress F9 in game (or type /showlocation) to list what is near you.",
            "tree_space": "No position yet.\nPress F9 in game to list the planets, stations and belts around you.",
            "tree_log": "No finds logged yet.\nWhen you find a good deposit, press F9 in game, then LOG FIND.",
            "tree_sig": "Type a signature number above, or press F8 in game while scanning.",
            "tree_routes": "Pick your ship (or type its cargo SCU) above to see the best trade routes.",
            "tree_con": "No hauling contracts yet.\nPress ADD CONTRACT for each one you accept in game.",
            "tree_run": "No run planned.\nDouble-click a trade route, or press PLAN RUN on CONTRACTS.",
            "tree_led": "Nothing in your ledger yet.\nTrades, purchases and contract payouts from the game log land "
                        "here by themselves. You can also add an entry above.",
            "tree_hangar": "Your hangar is empty.\nPress ADD SHIP for each ship you own.",
            "tree_shop": "Type what you want to buy above, or pick a category.",
            "tree_refine": "No refinery jobs.\nPress NEW JOB when you drop ore off at a refinery.",
            "tree_bounty": "No bounties tracked.\nPress ADD BOUNTY when you accept a bounty contract.",
            "tree_glc": "No contracts this session yet.\nThey appear here when you accept them in game.",
            "tree_glf": "Waiting for the game. Start Star Citizen and this fills in as you play.",
            "tree_mi": "Missions are downloading, or nothing matches your filters.",
            "tree_md": "Nothing here yet. Play with the game log on, or press IMPORT OLD GAME LOGS.",
            "tree_find": "Pick a material above to see where it spawns.",
            "tree_ore": "Pick a planet or moon above.",
        }
        for name, text in texts.items():
            t = getattr(self, name, None)
            if t is not None:
                t.empty_text = text
                self._empty_soon(t)

    # ------------------------------------------------------------ sorting
    SORT_DESC_FIRST = {"PROFIT", "SHARE", "CHANCE", "QUALITY", "REWARD", "COST", "SCU", "ON BOARD"}
    SORT_UNITS = {"m": 0.001, "km": 1.0, "Mm": 1e3, "Gm": 1e6, "k": 1e3, "M": 1e6,
                  "h": 1 / 24, "d": 1.0, "min": 1 / 1440, "s": 1 / 86400}
    SORT_MISSING = {"", "-", "--", "---", "?", "n/a"}
    MONTHS = {m: i for i, m in enumerate(("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug",
                                          "Sep", "Oct", "Nov", "Dec"), 1)}

    def _sort_value(self, text):
        """(kind, key): kind 0 = number, 1 = text, None = empty."""
        t = str(text).strip()
        if t.lower() in self.SORT_MISSING:
            return None, None
        m = re.match(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) (\d+)(?: (\d{4}))? (\d+):(\d+)", t)
        if m:  # log dates like "Nov 14 18:05"
            yr = int(m.group(3) or 0)
            return 0, (((yr * 13 + self.MONTHS[m.group(1)]) * 32 + int(m.group(2))) * 24 + int(m.group(4))) * 60 \
                + int(m.group(5))
        m = re.match(r"^[◆~<>≈ ]*([-+]?(?:\d[\d,]*\.?\d*|\.\d+))\s*([A-Za-z]*)", t)
        if m and (not m.group(2) or m.group(2) in self.SORT_UNITS or m.group(2) in ("SCU", "aUEC", "x")):
            try:
                return 0, float(m.group(1).replace(",", "")) * self.SORT_UNITS.get(m.group(2), 1.0)
            except ValueError:
                pass
        t = re.sub(r"^[^0-9A-Za-z]+", "", t).lower()
        return 1, [int(p) if p.isdigit() else p for p in re.split(r"(\d+)", t)]  # natural order

    def _sort_click(self, tree, col):
        if tree._sort and tree._sort[0] == col:
            tree._sort = (col, not tree._sort[1])
        else:
            tree._sort = (col, tree._labels.get(col) in self.SORT_DESC_FIRST)
        for k, label in tree._labels.items():
            if label:
                arrow = ("  ▼" if tree._sort[1] else "  ▲") if k == col else ""
                tree.heading(k, text=label + arrow)
        self._apply_sort(tree)

    def _apply_sort(self, tree):
        tree._sort_pending = False
        if not tree._sort:
            return
        col, desc = tree._sort
        try:
            self._sort_level(tree, "", col, desc)
        except tk.TclError:
            pass

    def _sort_level(self, tree, parent, col, desc):
        items = list(tree.get_children(parent))
        if not items:
            return
        vals = [self._sort_value(tree.set(i, col)) for i in items]
        kinds = {k for k, _ in vals if k is not None}
        numeric = kinds == {0}
        have = [(i, v) for i, v in zip(items, vals) if v[0] is not None]
        empty = [i for i, v in zip(items, vals) if v[0] is None]
        if numeric:
            have.sort(key=lambda x: x[1][1], reverse=desc)
        else:  # mixed: compare everything as text
            have.sort(key=lambda x: (x[1][1] if x[1][0] == 1 else [str(x[1][1])]), reverse=desc)
        order = [i for i, _ in have] + empty  # empty values always last
        for n, item in enumerate(order):
            tree.move(item, parent, n)
            tags = [x for x in tree.item(item, "tags") or () if x != "odd"]
            if n % 2 and "head" not in tags:
                tags.append("odd")
            tree.item(item, tags=tags)
            self._sort_level(tree, item, col, desc)

    # ------------------------------------------------------------ drawing
    @staticmethod
    def _mix(c1, c2, t):
        a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
        b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
        return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(a, b))

    def _header_art(self):
        """The banner picture (data/header_<size>.png) for the current text size, or None."""
        if hasattr(self, "_hdr_art"):
            return self._hdr_art
        self._hdr_art = None
        sizes = [90, 100, 115, 130, 150]
        pct = min(sizes, key=lambda p: abs(p - self.scale * 100))
        path = (edition.path(EDITION, EDITION["art"].format(pct=pct)) if EDITION.get("art") else None) or \
            os.path.join(self.world.data_dir, f"header_{pct}.png")
        try:
            if os.path.isfile(path):
                self._hdr_art = tk.PhotoImage(file=path)
        except tk.TclError:
            self._hdr_art = None
        return self._hdr_art

    def _draw_header_scene(self, c, w, h):
        """The drawn scene, used when the banner picture is missing."""
        px, py, pr = w - 300, h + 118, 150
        for i in range(14):
            t = i / 13
            rr = pr + 14 - i
            c.create_oval(px - rr, py - rr, px + rr, py + rr, outline="",
                          fill=self._mix(PLANET_DARK, PLANET_LIGHT, t * 0.55))
        for i in range(10):
            t = i / 9
            rr = pr - 2 - i * 6
            c.create_oval(px - rr + i * 4, py - rr + i * 3, px + rr + i * 4, py + rr + i * 3, outline="",
                          fill=self._mix("#2a6c9e", "#0c2840", t ** 0.7))
        c.create_arc(px - pr, py - pr, px + pr, py + pr, start=40, extent=100, style="arc",
                     outline="#8fd3ff", width=2)
        # small ringed moon
        mx, my, mr = w - 440, 20, 9
        c.create_oval(mx - mr, my - mr, mx + mr, my + mr, fill="#c98b45", outline="")
        c.create_oval(mx - mr + 3, my - mr + 2, mx + mr, my + mr, fill="#8a5427", outline="")
        c.create_line(mx - 17, my + 5, mx + 17, my - 5, fill="#e7c08a", width=1)
        # a ship heading out, engine trail behind it
        sx, sy = w * 0.47, 40
        for i in range(26):
            t = i / 25
            c.create_line(sx - 12 - i * 6, sy + 1 + i * 0.9, sx - 18 - i * 6, sy + 1 + i * 0.9 + 0.8,
                          fill=self._mix("#7fd4ff", "#0d2a40", t), width=2)
        hull = [sx + 26, sy - 1, sx + 6, sy - 6, sx - 6, sy - 7, sx - 14, sy - 3, sx - 14, sy + 4,
                sx - 4, sy + 6, sx + 10, sy + 5]
        c.create_polygon(hull, fill="#9fb3c4", outline="#dbe8f2")
        c.create_polygon(sx + 4, sy - 5, sx + 12, sy - 3, sx + 4, sy - 2, fill="#4ab8f5", outline="")
        c.create_polygon(sx - 6, sy + 5, sx + 2, sy + 12, sx - 10, sy + 12, fill="#7a8ea0", outline="")
        c.create_oval(sx - 17, sy - 2, sx - 11, sy + 4, fill="#bdf0ff", outline="")

    def _draw_header(self):
        c = self.header
        w, h = c.winfo_width(), int(HEADER_H * self.scale)
        S = self.scale
        if w < 50:
            return
        if getattr(self, "_hdr_w", None) != w:
            self._hdr_w = w
            c.delete("all")
            # sky: deep navy fading to a teal glow near the horizon
            for y in range(0, h, 2):
                c.create_rectangle(0, y, w, y + 2, outline="", fill=self._mix(SKY_TOP, SKY_BOTTOM, y / h))
            rnd = random.Random(42)
            for _ in range(int(w / 3.5)):
                x, y = rnd.uniform(0, w), rnd.uniform(0, h - 4)
                r = rnd.choice((0.6, 0.6, 0.8, 1.2))
                col = self._mix(STAR_DIM, STAR_BRIGHT, rnd.random() ** 1.5)
                c.create_oval(x - r, y - r, x + r, y + r, fill=col, outline="")
            art = self._header_art()
            bw0 = int(174 * S)
            if art is not None:
                c.create_image(w - bw0 - 18, 0, anchor="ne", image=art)
            # nebula haze
            cx = w * 0.55
            for i in (range(9, 0, -1) if art is None else ()):
                rx, ry = 40 + i * 22, 8 + i * 4
                c.create_oval(cx - rx, h * 0.45 - ry, cx + rx, h * 0.45 + ry, outline="",
                              fill=self._mix(BG, HAZE, (10 - i) / 22))
            if art is None:
                self._draw_header_scene(c, w, h)
            # logo plate
            pw = int(286 * S)
            c.create_polygon(0, 0, pw - 24, 0, pw, 24, pw, h - 12, 0, h - 12, fill=PLATE, outline="",
                             stipple="gray75")
            c.create_line(pw, 24, pw - 24, 0, fill=CYAN_DIM)
            c.create_line(0, h - 12, pw, h - 12, pw + 16, h - 2, w, h - 2, fill=CYAN_DIM, width=1)
            c.create_line(pw + 16, h - 2, pw + 134, h - 2, fill=ORANGE, width=2)
            c.create_rectangle(14, 16, 18, int(38 * S), fill=ORANGE, outline="")
            c.create_text(28, 14 * S, anchor="nw", text=APP_TITLE.upper(), fill="#ffffff",
                          font=(self.F_TITLE, 18, "bold"))
            c.create_text(29, 42 * S, anchor="nw", text=spaced(EDITION.get("subtitle") or "star citizen companion"),
                          fill=CYAN,
                          font=(self.F_UI, 7, "bold"))
        c.delete("status")
        live = self.here is not None
        on = self._blink or self.reduce_flash
        dot = (GREEN if on else self._mix(GREEN, "#000000", 0.55)) if live else \
            (AMBER if on else self._mix(AMBER, "#000000", 0.55))
        bw = int(174 * S)
        c.create_polygon(round_points(w - bw - 8, 10, w - 8, 10 + 40 * S, 12), smooth=True, fill=PLATE,
                         outline=LINE, tags="status")
        c.create_oval(w - bw + 2, 10 + 11 * S, w - bw + 10, 10 + 11 * S + 8, fill=dot, outline="", tags="status")
        gs = getattr(self, "gl_session", {}) or {}
        in_game = bool(gs.get("joined") and gs.get("live"))
        if live:
            status, col = "POSITION LOCKED", GREEN
            sub = "LAST FIX  " + clock_str(self.here["time"].astimezone(), "%H:%M:%S")
        elif in_game:
            status, col, sub = "IN GAME", CYAN, "F9 FOR POSITION"
        else:
            status, col, sub = "WAITING FOR GAME", AMBER, "START STAR CITIZEN"
        c.create_text(w - bw + 18, 7 + 10 * S, anchor="nw", text=status, fill=col,
                      font=(self.F_UI, 9, "bold"), tags="status")
        c.create_text(w - bw + 18, 7 + 26 * S, anchor="nw", text=sub, fill=MUTED,
                      font=(self.F_MONO, 8), tags="status")

    def _draw_compass(self, bearing, label, color=GREEN):
        c = self.compass
        c.delete("all")
        cx = cy = 75
        r = 62
        c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=LINE, width=1)
        c.create_oval(cx - r + 10, cy - r + 10, cx + r - 10, cy + r - 10, outline=CYAN_FAINT, width=1)
        for deg in range(0, 360, 10):
            a = math.radians(deg - 90)
            inner = r - (9 if deg % 90 == 0 else 6 if deg % 30 == 0 else 3)
            c.create_line(cx + inner * math.cos(a), cy + inner * math.sin(a),
                          cx + r * math.cos(a), cy + r * math.sin(a),
                          fill=CYAN if deg % 90 == 0 else CYAN_DIM, width=2 if deg % 90 == 0 else 1)
        for deg, t in ((0, "N"), (90, "E"), (180, "S"), (270, "W")):
            a = math.radians(deg - 90)
            rr = r - 20
            c.create_text(cx + rr * math.cos(a), cy + rr * math.sin(a), text=t,
                          fill=CYAN if t == "N" else MUTED, font=(self.F_UI, 8, "bold"))
        if bearing is None:
            c.create_text(cx, cy, text="---", fill=MUTED, font=(self.F_MONO, 12))
            return
        a = math.radians(bearing - 90)
        tip = (cx + (r - 4) * math.cos(a), cy + (r - 4) * math.sin(a))
        base = (cx + 14 * math.cos(a), cy + 14 * math.sin(a))
        c.create_line(*base, *tip, fill=color, width=3, arrow="last", arrowshape=(10, 12, 5))
        c.create_oval(cx - 3, cy - 3, cx + 3, cy + 3, fill=color, outline="")
        c.create_text(cx, cy + 22, text=f"{bearing:03.0f}°", fill=color, font=(self.F_MONO, 11, "bold"))

    def _tick(self):
        self._blink = not self._blink
        self._draw_header()
        self._ticks = getattr(self, "_ticks", 0) + 1
        if self._ticks % 43 == 0:  # about every 30 s: refresh sun countdowns and the night shading
            if self.here and self.here.get("body"):
                b = self.here["body"]
                txt, col = self._sun_text(b, self.here["local"], core.utcnow())
                self.lbl_sun.configure(text=txt, fg=col)
            self._render_route()
            self._draw_map()
        if self.overlay and self.last_scan and SCAN_SHOW_SECONDS <= self._scan_age() < SCAN_SHOW_SECONDS + 1:
            self.overlay.refresh()
        if self.toast and core.utcnow().timestamp() - self.toast[2] > 3:
            self.toast = None
            if self.overlay:
                self.overlay.refresh()
        self.root.after(700, self._tick)

    # ------------------------------------------------------------ input
    def _poll_clipboard(self):
        # On Windows, ask only whether the clipboard changed (almost free) and read it only then;
        # reading it every time can hold up the window for tens of milliseconds.
        if sys.platform.startswith("win"):
            try:
                import ctypes
                seq = ctypes.windll.user32.GetClipboardSequenceNumber()
                if seq == getattr(self, "_clip_seq", None):
                    self.root.after(POLL_MS, self._poll_clipboard)
                    return
                self._clip_seq = seq
            except Exception:  # noqa: BLE001
                pass
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            text = None
        if text and text != self.last_clip:
            self.last_clip = text
            sig = signatures.parse_sig_clip(text)
            if sig is not None:
                self._scan(sig, source="hotkey")
            else:
                g = core.parse_showlocation(text)
                if g:
                    self._update(g)
        self.root.after(POLL_MS, self._poll_clipboard)

    def _manual_paste(self):
        text = simpledialog.askstring(APP_TITLE, "Paste /showlocation text:", parent=self.root)
        if text:
            g = core.parse_showlocation(text)
            if g:
                self._update(g)
            else:
                messagebox.showwarning(APP_TITLE, "Could not find x / y / z coordinates in that text.")

    # ------------------------------------------------------------ update
    def _system_for(self, g):
        choice = self.system_choice.get()
        if choice != "Auto":
            return choice
        return self.world.guess_system(g, self.last_system)

    def _update(self, g, t=None):
        system = self._system_for(g)
        self.last_system = system
        new = self.world.locate(g, t, system)
        self.stale = t is None and self.world.is_stale(self.here, new)
        if self.stale:
            hotkeys_win.log("stale /showlocation: same coordinates as the previous fix")
            self._render()  # keep the last good position, just show the warning
            return
        if t is None and self.here is not None and not self.stale:  # a real new fix, not a recompute
            self.prev_here = self.here
        self.here = new
        self.motion = self.world.motion(self.prev_here, self.here, self.target)
        if t is None:
            try:
                core.append_history(self.world.user_dir, self.here)
            except OSError:
                pass
        self._render()
        if t is None and hasattr(self, "tab_belts"):
            self._belt_after_fix()
        if t is None and getattr(self, "run", None):
            self._run_check()
        if t is None and hasattr(self, "tree_routes") and not self.tree_routes.selection():
            try:
                if self.nb.select() == str(self.tab_haul):
                    self._fill_routes()
            except tk.TclError:
                pass

    def _recompute(self):
        if self.here:
            prev = self.prev_here
            if prev:  # recompute the previous fix too, in case calibration changed
                self.prev_here = self.world.locate(prev["global"], prev["time"], prev["system"])
            self._update(self.here["global"], self.here["time"])

    def _render(self):
        h = self.here
        body = h["body"]
        self._draw_header()
        gx, gy, gz = h["global"]
        if body:
            parts = [body.type]
            if body.type == "Moon" and body.parent:
                parts.append(body.parent)
            parts.append(h["system"])
            if h.get("zone"):
                parts.append(h["zone"])
            alt = h["alt"]
            self.lbl_where.configure(text=body.name.upper())
            self.lbl_sub.configure(text=spaced("  //  ".join(parts)).replace("/ /", "//"))
            self.readouts["LAT"].configure(text=f"{h['lat']:+.4f}°")
            self.readouts["LON"].configure(text=f"{h['lon']:+.4f}°")
            self.readouts["ALT"].configure(text=f"{alt:,.2f} km")
            cal = "CALIBRATED" if h["calibrated"] else "DEFAULT ROTATION"
            near = h["nearby"][0] if h["nearby"] else None
            where = "On the surface." if alt < 2 else f"{core.fmt_km(alt)} above the surface."
            if getattr(self, "stale", False):
                where = ("The game sent the same position as last time, which happens inside some stations. "
                         "Move a little (or step into your ship) and press F9 again.  ")
            if near:
                where += (f"  Closest: {near['loc'].name} ({near['loc'].type}), "
                          f"{core.fmt_km(near['surface'])} {core.compass_word(near['bearing'])}.")
            self.lbl_near.configure(text=where)
            lx, ly, lz = h["local"]
            self.lbl_coords.configure(text=(f"LOCAL  {lx:>12,.3f} {ly:>12,.3f} {lz:>12,.3f} km\n"
                                            f"GLOBAL {gx:>12,.1f} {gy:>12,.1f} {gz:>12,.1f} km\n{cal}"))
        else:
            sp = h["space"][0] if h["space"] else None
            zone = h.get("zone")
            self.lbl_where.configure(text=(zone or "OPEN SPACE").upper())
            self.lbl_sub.configure(text=spaced(h["system"] + " system"))
            for k in self.readouts:
                self.readouts[k].configure(text="---", fg=FG)
            self.lbl_near.configure(text=(f"Nearest: {sp[1]} ({sp[2]}), {core.fmt_km(sp[0])}" if sp else ""))
            self.lbl_coords.configure(text=f"GLOBAL {gx:>12,.1f} {gy:>12,.1f} {gz:>12,.1f} km")
        if body:
            txt, col = self._sun_text(body, h["local"], h["time"])
            self.lbl_sun.configure(text=txt, fg=col)
            if body.rotates and self.map_body.get() != body.name and not self.target:
                self.map_body.set(body.name)
        else:
            self.lbl_sun.configure(text="")
        self._draw_map()
        self._fill_log()
        if self.last_scan and self._scan_age() < SCAN_SHOW_SECONDS:
            self._scan(self.last_scan["value"], source=self.last_scan["source"], record=False)
        m = self.motion
        self.readouts["SPEED"].configure(text=core.fmt_speed(m["speed_ms"]) if m else "---")
        self._render_target()
        self._fill_types()
        self._fill_nearby()
        self._fill_space()
        self._fill_finder()
        if body:
            self.ore_body.set(body.name)
            self._fill_ores()

    def _render_target(self):
        if hasattr(self, "hud_btns"):
            self._apply_compact()
        self._render_target_main()
        self._render_motion()
        self._render_route()
        if self.overlay:
            self.overlay.refresh()

    def _render_target_main(self):
        here = self.here
        if not self.target:
            self.lbl_target.configure(text="None set. Double-click a location below.", fg=MUTED)
            if here and here.get("nearby"):
                n = here["nearby"][0]
                self._draw_compass(n["bearing"], None, CYAN)
                self.lbl_comp.configure(text="CLOSEST POI", fg=CYAN_DIM)
            else:
                self._draw_compass(None, None)
                self.lbl_comp.configure(text="NO TARGET", fg=MUTED)
            return
        loc = self.target
        if not here:
            self.lbl_target.configure(text=f"{loc.name} on {loc.body}. Waiting for a position fix.", fg=FG)
            return
        info = self.world.target_info(here, loc)
        if info["same_body"]:
            self.lbl_target.configure(fg=GREEN, text=(
                f"{loc.name}   {core.fmt_km(info['surface'])}   "
                f"{info['bearing']:03.0f}° {core.compass_word(info['bearing'])}   "
                f"lat {info['lat']:+.3f}  lon {info['lon']:+.3f}"))
            self._draw_compass(info["bearing"], loc.name, GREEN)
            self.lbl_comp.configure(text="DIRECTION TO TARGET", fg=GREEN)
        else:
            self.lbl_target.configure(fg=AMBER, text=(
                f"{loc.name} on {info['body_name']}   {core.fmt_km(info['straight'])} away"))
            self._draw_compass(None, None)
            self.lbl_comp.configure(text="OFF-BODY TARGET", fg=AMBER)

    def _render_route(self):
        loc = self.target
        if not loc:
            self.lbl_route.configure(text="")
            return
        rt = self.world.route(self.here, loc)
        lines = ["› " + st for st in rt["steps"]]
        body = self.world.bodies[loc.body]
        if body.rotates:
            t = self.here["time"] if self.here else core.utcnow()
            txt, _ = self._sun_text(body, loc.local, t, prefix="At target: ")
            if txt:
                lines.append(txt)
        self.lbl_route.configure(text="\n".join(lines))

    def _render_motion(self):
        m = self.motion
        if not m:
            hint = "Run /showlocation again while moving to get speed and ETA." if self.here else ""
            self.lbl_motion.configure(text=hint, fg=MUTED)
            return
        bits = [f"SPD {core.fmt_speed(m['speed_ms'])}"]
        if m["climb_ms"] is not None and abs(m["climb_ms"]) >= 1:
            bits.append(f"VS {m['climb_ms']:+,.0f} m/s")
        if m["closing_ms"] is not None:
            if m["closing_ms"] > 0.5:
                bits.append(f"ETA {core.fmt_duration(m['eta_s'])}")
            else:
                bits.append("MOVING AWAY" if m["closing_ms"] < -0.5 else "NOT CLOSING")
        if m["turn"] is not None:
            bits.append(core.turn_text(m["turn"]).upper())
        away = m["closing_ms"] is not None and m["closing_ms"] < -0.5
        self.lbl_motion.configure(text="   ".join(bits), fg=AMBER if away else FG)

    # ------------------------------------------------------------ overlay
    def _toggle_overlay(self):
        if self.overlay:
            self.overlay.close()
            self.overlay = None
            self.btn_overlay.configure(text="OVERLAY ON")
        else:
            self.overlay = Overlay(self)
            self.overlay.set_locked(self.overlay_locked)
            ov = self.overlay
            ov.after(80, lambda: ov.winfo_exists() and ov.attributes("-alpha", self.overlay_alpha()))
            self.btn_overlay.configure(text="OVERLAY OFF")

    def _toggle_lock(self):
        self.overlay_locked = not self.overlay_locked
        self.btn_lock.configure(text="UNLOCK" if self.overlay_locked else "LOCK")
        if self.overlay:
            self.overlay.set_locked(self.overlay_locked)

    # ------------------------------------------------------------ ore finder
    def _fill_finder(self):
        t = self.tree_find
        t.delete(*t.get_children())
        self._finder_map = {}
        mat = self.ore_material.get()
        if not mat:
            return
        rows = self.world.ore_sources(mat, self.here)
        with_dist = [r for r in rows if r["distance_km"] is not None]
        nearest = min(with_dist, key=lambda r: r["distance_km"]) if with_dist else None
        top = rows[0]["share"] if rows else None
        methods = {"ship": "Ship", "vehicle": "ROC", "hand": "Hand", "harvestable": "Harvest", "log": "Your log"}
        for i, r in enumerate(rows):
            tags = ["odd"] if i % 2 else []
            if r["method"] == "log":
                tags.append("log")
            label = r["source"]
            if r is nearest:
                tags.append("best")
                label = "◆ " + label
            if r["method"] == "log":
                share = f"{r['count']} find{'s' if r['count'] != 1 else ''}"
            else:
                share = "yes" if r["share"] is None else f"{r['share']:g}%"
            if r["distance_km"] is None:
                dist = "other system" if self.here and r["system"] != self.here["system"] else "--"
            else:
                dist = "here" if r["distance_km"] == 0 else core.fmt_km(r["distance_km"])
            iid = t.insert("", "end", tags=tags, values=(label, r["system"], methods.get(r["method"], r["method"]),
                                                         share, dist))
            self._finder_map[iid] = r["source"]
        if nearest:
            self.lbl_finder_best.configure(
                text=f"NEAREST: {nearest['source'].upper()}  "
                     f"({'here' if nearest['distance_km'] == 0 else core.fmt_km(nearest['distance_km'])})")
        elif rows:
            self.lbl_finder_best.configure(text=f"BEST SHARE: {rows[0]['source'].upper()} ({top:g}%)" if top else "")
        else:
            self.lbl_finder_best.configure(text="")

    def _finder_open(self, _ev=None):
        sel = self.tree_find.selection()
        if not sel:
            return
        src = self._finder_map.get(sel[0])
        if src:
            self.ore_body.set(src)
            self._fill_ores()
            self._show(self.tab_ores)

    def _body_choices(self):
        bodies = sorted(self.world.surface_bodies(), key=lambda b: (b.star != "Stanton", b.star, b.name.lower()))
        return [b.name for b in bodies]

    def _near_selected_body(self):
        """The body NEARBY lists: the one you are on, or the one picked in BODY."""
        name = self.near_body.get() if hasattr(self, "near_body") else "Where I am"
        if name == "Where I am":
            return self.here["body"] if self.here and self.here.get("body") else None
        return self.world.bodies.get(name)

    def _fill_types(self):
        body = self._near_selected_body()
        locs = self.world.locations_on(body.name) if body else []
        counts = {}
        for l in locs:
            counts[l.type] = counts.get(l.type, 0) + 1
        types = sorted(counts)
        self.type_cb.configure(values=["All types"] + types)
        if self.filter_type.get() not in ["All types"] + types:
            self.filter_type.set("All types")

    def _fill_nearby(self):
        t = self.tree_near
        t.delete(*t.get_children())
        self._near_map = {}
        body = self._near_selected_body()
        if body is None:
            self.lbl_near_hint.configure(text="Press F9 (or type /showlocation) on a planet or moon, or pick one in "
                                              "BODY to see its locations.", fg=MUTED)
            return
        q = self.filter_text.get().strip().lower()
        ft = self.filter_type.get()
        here = self.here
        on_it = here is not None and here.get("body") is body
        if on_it:
            rows = self.world.locate(here["global"], here["time"], here["system"], max_nearby=100_000)["nearby"]
        else:
            rows = []
            for loc in self.world.locations_on(body.name):
                d = None
                if here and here["system"] == body.star:
                    d = self.world.target_info(here, loc)["straight"]
                rows.append({"loc": loc, "straight": d})
            rows.sort(key=lambda r: (r["straight"] is None, r["straight"] or 0, r["loc"].name.lower()))
        i = 0
        for r in rows:
            loc = r["loc"]
            if q and q not in loc.name.lower():
                continue
            if ft != "All types" and loc.type != ft:
                continue
            tags = ["odd"] if i % 2 else []
            if loc.source in ("custom", "log"):
                tags.append(loc.source)
            if on_it:
                dist, brg = core.fmt_km(r["surface"]), f"{r['bearing']:03.0f}° {core.compass_word(r['bearing'])}"
            else:
                dist, brg = (core.fmt_km(r["straight"]) if r["straight"] is not None else "?"), "QT"
            iid = t.insert("", "end", tags=tags, values=(loc.name, loc.type, dist, brg))
            self._near_map[iid] = loc
            i += 1
        what = f"{i} {ft.lower() if ft != 'All types' else 'location'}{'' if i == 1 else 's'}"
        if ft != "All types" and i != 1 and ft.endswith(("s", "x")):
            what = f"{i} {ft.lower()}"
        if on_it:
            msg = (f"{what} on {body.name}, closest first. Distance is over the surface. "
                   "Double-click one to fly there.")
        else:
            msg = (f"{what} on {body.name}. Distance is straight-line from you. Double-click one to target it; "
                   "the TARGET box shows which orbital marker to quantum to.")
        if ft == "All types" and "Cave" not in self.type_cb.cget("values"):
            msg += (f"  No caves are known on {body.name} yet: run SETTINGS > MAP DATA > CHECK FOR UPDATES with ALSO GET NYX AND CAVES ticked "
                    "to add them, or save the ones you find with SAVE SPOT.")
        if ft == "Cave" and i == 0:
            msg = (f"No caves known on {body.name} yet. Run SETTINGS > MAP DATA > CHECK FOR UPDATES (with ALSO GET NYX AND CAVES ticked) to add "
                   "caves, or save the ones you find with SAVE SPOT.")
        self.lbl_near_hint.configure(text=msg, fg=MUTED)

    def _fill_space(self):
        t = self.tree_space
        t.delete(*t.get_children())
        for i, (d, name, typ) in enumerate(self.here["space"]):
            t.insert("", "end", values=(name, typ, core.fmt_km(d)), tags=("odd",) if i % 2 else ())

    def _refresh_ore_bodies(self):
        names = [b.name for b in sorted(self.world.surface_bodies(), key=lambda b: (b.star, b.name))]
        names += [z for z in self.world.zones() if z not in names]
        self.ore_cb.configure(values=names)
        if names and not self.ore_body.get():
            have = [n for n in names if self.world.ores.get(n)]
            stanton = [b.name for b in self.world.surface_bodies() if b.star == "Stanton" and b.name in have]
            self.ore_body.set((sorted(stanton) or have or names)[0])
            self._fill_ores()

    def _game_mineables(self, name):
        g = getattr(self, "gtext", None)
        lists = g.mineables(name) if g and g.data else None
        if not lists or not (lists[0] or lists[1]):
            return ""
        out = "The game itself lists"
        if lists[0]:
            out += " for ships: " + ", ".join(lists[0])
        if lists[1]:
            out += ("; by hand: " if lists[0] else " by hand: ") + ", ".join(lists[1])
        return out + "."

    def _fill_ores(self):
        t = self.tree_ore
        t.delete(*t.get_children())
        name = self.ore_body.get()
        data = self.world.ores.get(name)
        meta = self.world.ore_meta
        game = self._game_mineables(name)
        if not data and game:
            self.lbl_ore_note.configure(text=f"No Wiki ore shares for {name}. " + game)
            return
        if not data:
            if name in meta.get("_no_surface_mining", []):
                msg = f"{name} has no surface mining (gas giant or city planet). Try its moons or Lagrange belts."
            elif name.startswith("Nyx") or name == "Delamar":
                msg = f"{name} has no surface mining data yet. In Nyx, mine the Glaciem Ring or Keeger Belt."
            else:
                msg = f"No ore data for {name}."
            self.lbl_ore_note.configure(text=msg)
            return
        for key, label in ORE_LABELS:
            items = data.get(key) or []
            if not items:
                continue
            parent = t.insert("", "end", values=(label, "", ""), open=True, tags=("head",))
            for i, (mat, pct) in enumerate(items):
                if pct is None:
                    bar, txt = "", "present"
                else:
                    bar, txt = ("▰" * max(1, round(pct / 5)) if pct > 0 else ""), f"{pct:g}%"
                t.insert(parent, "end", values=(mat, bar, txt), tags=("odd",) if i % 2 else ())
        note = "SHARE is how often you find this material with that kind of mining here. Data: Star Citizen Wiki."
        if name in meta.get("_partial", []):
            note = "Partial data for this body. " + note
        zone = self.world.zones().get(name)
        if zone and zone.get("note"):
            note = zone["note"] + " " + note
        if game:
            note += "  " + game
        self.lbl_ore_note.configure(text=note)

    def _fill_browse(self):
        t = self.tree_browse
        t.delete(*t.get_children())
        self._iid_to_loc = {}
        w = self.world
        for system in w.systems():
            sid = t.insert("", "end", values=(f"{system.upper()} SYSTEM", "Star system"),
                           open=False, tags=("head",))
            planets = [b for b in w.surface_bodies(system) if b.type in ("Planet", "Planetoid")]
            planets.sort(key=lambda b: str(b.ordinal))
            for p in planets:
                pid = t.insert(sid, "end", values=(p.name, f"{p.type}  ·  {len(w.locations_on(p.name))} places"))
                self._add_locs(pid, p.name)
                for m in sorted(w.children(p.name), key=lambda b: str(b.ordinal)):
                    mid = t.insert(pid, "end", values=(m.name, f"Moon  ·  {len(w.locations_on(m.name))} places"))
                    self._add_locs(mid, m.name)
            space = [l for l in w.locations if l.star == system and not w.bodies[l.body].rotates]
            if space:
                xid = t.insert(sid, "end", values=("Deep space", f"{len(space)} places"))
                for l in sorted(space, key=lambda l: l.name):
                    iid = t.insert(xid, "end", values=(l.name, l.type))
                    self._iid_to_loc[iid] = l

    def _add_locs(self, parent_iid, body_name):
        t = self.tree_browse
        for loc in sorted(self.world.locations_on(body_name), key=lambda l: (l.type, l.name)):
            iid = t.insert(parent_iid, "end", values=(loc.name, loc.type),
                           tags=(loc.source,) if loc.source in ("custom", "log") else ())
            self._iid_to_loc[iid] = loc

    # ------------------------------------------------------------ actions
    def _pick_from(self, tree):
        sel = tree.selection()
        if not sel:
            return
        maps = {id(self.tree_near): self._near_map, id(self.tree_log): self._log_map,
                id(getattr(self, "tree_spots", None)): getattr(self, "_spots_map", {}),
                id(getattr(self, "tree_zones", None)): getattr(self, "_zones_map", {})}
        loc = maps.get(id(tree), self._iid_to_loc).get(sel[0])
        if loc:
            self._set_target(loc)

    def _set_target(self, loc):
        self.target = loc
        self.motion = self.world.motion(self.prev_here, self.here, self.target)
        if loc.body in self.world.bodies and self.world.bodies[loc.body].rotates:
            self.map_body.set(loc.body)
        self._render_target()
        self._draw_map()

    def _clear_target(self):
        self.target = None
        self.motion = self.world.motion(self.prev_here, self.here, None)
        self._render_target()
        self._draw_map()

    def _browse_menu(self, ev):
        iid = self.tree_browse.identify_row(ev.y)
        loc = self._iid_to_loc.get(iid)
        if not loc:
            return
        self.tree_browse.selection_set(iid)
        m = tk.Menu(self.root, tearoff=0, bg=PANEL, fg=FG, activebackground=CYAN_FAINT,
                    activeforeground="#ffffff", bd=0)
        m.add_command(label="Set as target", command=lambda: self._pick_from(self.tree_browse))
        if loc.wiki:
            m.add_command(label="Open wiki page", command=lambda: webbrowser.open(loc.wiki))
        if loc.source in ("custom", "log"):
            m.add_command(label="Copy share code", command=lambda: self._copy_codes([loc]))
        if loc.source == "custom":
            m.add_command(label="Delete saved POI", command=lambda: self._delete_custom(loc))
        if loc.source == "log":
            m.add_command(label="Delete logged find", command=lambda: self._delete_custom(loc))
        m.tk_popup(ev.x_root, ev.y_root)

    def _delete_custom(self, loc):
        if messagebox.askyesno(APP_TITLE, f"Delete '{loc.name}'?"):
            if loc.source == "log":
                self.world.delete_log_entry(loc)
            else:
                self.world.delete_custom_poi(loc)
            if self.target is loc:
                self.target = None
            self._fill_browse()
            self._fill_log()
            self._draw_map()
            self._recompute()

    # ------------------------------------------------------------ map
    def _build_map(self, parent):
        top = tk.Frame(parent, bg=PANEL)
        top.pack(fill="x", pady=(0, 6))
        self._lbl(top, "BODY", 7, MUTED, bold=True).pack(side="left", padx=(0, 6))
        self.map_body = tk.StringVar()
        names = [b.name for b in sorted(self.world.surface_bodies(), key=lambda b: (b.star, b.name))]
        self.map_cb = ttk.Combobox(top, textvariable=self.map_body, values=names, width=16, state="readonly")
        self.map_cb.pack(side="left")
        self.map_cb.bind("<<ComboboxSelected>>", lambda e: self._draw_map())
        legend = [("YOU", "#ffffff"), ("QT", CYAN), ("OTHER", CYAN_DIM), ("SAVED", AMBER), ("LOGGED", GREEN)]
        for text, col in legend:
            self._lbl(top, "◆" if text == "LOGGED" else "●", 9, col).pack(side="left", padx=(8, 2))
            self._lbl(top, text, 7, MUTED, bold=True).pack(side="left")
        frame = tk.Frame(parent, bg=LINE, padx=1, pady=1)
        frame.pack(fill="both", expand=True)
        self.map_c = tk.Canvas(frame, bg=PANEL, highlightthickness=0, height=260)
        self.map_c.pack(fill="both", expand=True)
        self.map_c.bind("<Configure>", lambda e: self._draw_map())
        self.map_c.bind("<Motion>", self._map_hover)
        self.map_c.bind("<Button-1>", self._map_click)
        self.lbl_map = self._lbl(parent, "Night side is shaded. Hover a dot for details, click it to set a target.",
                                 8, MUTED, wraplength=540)
        self.lbl_map.pack(anchor="w", pady=(6, 0))
        self._map_marks = []
        if names:
            self.map_body.set("Daymar" if "Daymar" in names else names[0])

    def _map_geom(self):
        W, H = self.map_c.winfo_width(), self.map_c.winfo_height()
        mw = min(W - 8, (H - 8) * 2)
        mh = mw / 2
        return (W - mw) / 2, (H - mh) / 2, mw, mh

    def _map_xy(self, lat, lon):
        ox, oy, mw, mh = self._map_geom()
        return ox + (lon + 180) / 360 * mw, oy + (90 - lat) / 180 * mh

    def _draw_map(self):
        c = self.map_c
        if not hasattr(self, "map_c") or c.winfo_width() < 50:
            return
        c.delete("all")
        self._map_marks = []
        body = self.world.bodies.get(self.map_body.get())
        if not body:
            return
        ox, oy, mw, mh = self._map_geom()
        t = core.utcnow()
        R = body.radius
        sun = self.world.sun_dir_local(body, t) if body.rotates else None
        c.create_rectangle(ox, oy, ox + mw, oy + mh, fill=PANEL_HI, outline=LINE)
        # night shading on a 6 degree grid
        if sun:
            step = 6
            for lat in range(-90, 90, step):
                for lon in range(-180, 180, step):
                    u = core.local_from_lat_lon(lat + step / 2, lon + step / 2, 1.0)
                    d = u[0] * sun[0] + u[1] * sun[1] + u[2] * sun[2]
                    if d < 0.1:
                        col = "#040d15" if d < -0.1 else "#081824"
                        x0, y0 = self._map_xy(lat + step, lon)
                        x1, y1 = self._map_xy(lat, lon + step)
                        c.create_rectangle(x0, y0, x1 + 1, y1 + 1, fill=col, outline="")
        for lat in range(-60, 90, 30):
            x0, y = self._map_xy(lat, -180)
            x1, _ = self._map_xy(lat, 180)
            c.create_line(x0, y, x1, y, fill=CYAN_FAINT if lat == 0 else LINE)
        for lon in range(-150, 180, 30):
            x, y0 = self._map_xy(90, lon)
            _, y1 = self._map_xy(-90, lon)
            c.create_line(x, y0, x, y1, fill=CYAN_FAINT if lon == 0 else LINE)
        for lat in (60, 30, 0, -30, -60):
            x, y = self._map_xy(lat, -180)
            c.create_text(x + 3, y - 1, text=f"{lat:+d}", anchor="sw", fill=MUTED, font=(self.F_MONO, 7))
        c.create_text(ox + mw - 4, oy + 4, anchor="ne", text=body.name.upper(), fill=CYAN,
                      font=(self.F_UI, 11, "bold"))
        # orbital markers
        for name, p in self.world.orbital_markers(body).items():
            la, lo, _ = core.lat_lon_alt(p, R)
            x, y = self._map_xy(la, lo)
            c.create_rectangle(x - 3, y - 3, x + 3, y + 3, outline=MUTED)
            c.create_text(x + 5, y, text=name, anchor="w", fill=MUTED, font=(self.F_UI, 7, "bold"))
        # locations
        for loc in self.world.locations_on(body.name):
            la, lo, _ = core.lat_lon_alt(loc.local, R)
            x, y = self._map_xy(la, lo)
            if loc.source == "custom":
                col, r = AMBER, 3.5
            elif loc.source == "log":
                col, r = GREEN, 3.5
            elif loc.quantum:
                col, r = CYAN, 3
            else:
                col, r = CYAN_DIM, 2.2
            if loc.source == "log":
                c.create_polygon(x, y - r - 1, x + r + 1, y, x, y + r + 1, x - r - 1, y, fill=col, outline="")
            else:
                c.create_oval(x - r, y - r, x + r, y + r, fill=col, outline="")
            self._map_marks.append((x, y, loc))
        # path to target
        here = self.here
        tgt = self.target if self.target and self.target.body == body.name else None
        start = None
        if here and here.get("body") is body:
            start = here["local"]
        elif tgt:
            rt = self.world.route(here, tgt)
            if rt.get("om"):
                start = core.local_from_lat_lon(rt["om"]["lat"], rt["om"]["lon"], R)
        if tgt and start:
            pts = self._great_circle(start, tgt.local)
            prev = None
            for la, lo in pts:
                x, y = self._map_xy(la, lo)
                if prev and abs(x - prev[0]) < mw / 2:
                    c.create_line(prev[0], prev[1], x, y, fill=GREEN, width=2, dash=(4, 3))
                prev = (x, y)
        if tgt:
            la, lo, _ = core.lat_lon_alt(tgt.local, R)
            x, y = self._map_xy(la, lo)
            c.create_oval(x - 8, y - 8, x + 8, y + 8, outline=GREEN, width=2)
        if here and here.get("body") is body:
            x, y = self._map_xy(here["lat"], here["lon"])
            c.create_oval(x - 9, y - 9, x + 9, y + 9, outline="#ffffff", width=1)
            c.create_oval(x - 4, y - 4, x + 4, y + 4, fill="#ffffff", outline="")
            c.create_text(x + 11, y - 9, text="YOU", anchor="w", fill="#ffffff", font=(self.F_UI, 8, "bold"))
        if not body.rotates or body.rate_hours == 0:
            c.create_text(ox + 6, oy + mh - 6, anchor="sw", text="NO DAY CYCLE DATA", fill=MUTED,
                          font=(self.F_UI, 7, "bold"))

    @staticmethod
    def _great_circle(a, b, n=64):
        la, lb = core.vlen(a), core.vlen(b)
        ua = [v / la for v in a]
        ub = [v / lb for v in b]
        dot = max(-1.0, min(1.0, sum(x * y for x, y in zip(ua, ub))))
        om = math.acos(dot)
        pts = []
        for i in range(n + 1):
            f = i / n
            if om < 1e-6:
                v = ua
            else:
                s1 = math.sin((1 - f) * om) / math.sin(om)
                s2 = math.sin(f * om) / math.sin(om)
                v = [s1 * x + s2 * y for x, y in zip(ua, ub)]
            la_, lo_, _ = core.lat_lon_alt(v, 1.0)
            pts.append((la_, lo_))
        return pts

    def _map_pick(self, ev):
        best, bd = None, 10 ** 9
        for x, y, loc in self._map_marks:
            d = (x - ev.x) ** 2 + (y - ev.y) ** 2
            if d < bd:
                best, bd = loc, d
        return best if bd <= 100 else None

    def _map_hover(self, ev):
        loc = self._map_pick(ev)
        if not loc:
            self.lbl_map.configure(text="Night side is shaded. Hover a dot for details, click it to set a target.",
                                   fg=MUTED)
            return
        body = self.world.bodies[loc.body]
        la, lo, _ = core.lat_lon_alt(loc.local, body.radius)
        extra = ""
        if self.here and self.here.get("body") is body:
            d = core.surface_distance(self.here["lat"], self.here["lon"], la, lo, body.radius)
            extra = f"   {core.fmt_km(d)} from you"
        self.lbl_map.configure(text=f"{loc.name}  ({loc.type})   lat {la:+.2f}  lon {lo:+.2f}{extra}", fg=FG)

    def _map_click(self, ev):
        loc = self._map_pick(ev)
        if loc:
            self._set_target(loc)

    # ------------------------------------------------------------ mining log
    def _build_log(self, parent):
        top = tk.Frame(parent, bg=PANEL)
        top.pack(fill="x", pady=(0, 8))
        self._lbl(top, "MATERIAL", 7, MUTED, bold=True).pack(side="left", padx=(0, 6))
        self.log_filter = tk.StringVar(value="All")
        self.log_cb = ttk.Combobox(top, textvariable=self.log_filter, width=18, state="readonly")
        self.log_cb.pack(side="left")
        self.log_cb.bind("<<ComboboxSelected>>", lambda e: self._fill_log())
        ttk.Button(top, text="DELETE", command=self._log_delete_selected).pack(side="right")
        ttk.Button(top, text="COPY CODE", command=self._log_copy_selected).pack(side="right", padx=(6, 0))
        ttk.Button(top, text="LOG FIND HERE", command=self._log_find).pack(side="right", padx=6)
        self.tree_log = self._tree(parent, [("when", "WHEN", 95), ("mat", "MATERIAL", 110), ("q", "QUALITY", 60),
                                            ("body", "WHERE", 90), ("how", "HOW", 60), ("dist", "DISTANCE", 85)])
        self.tree_log.bind("<Double-1>", lambda e: self._pick_from(self.tree_log))
        self.lbl_log = self._lbl(parent, "", 8, MUTED, wraplength=540)
        self.lbl_log.pack(anchor="w", pady=(6, 0))
        self._log_map = {}
        self._fill_log()

    def _fill_log(self):
        if not hasattr(self, "tree_log"):
            return
        t = self.tree_log
        t.delete(*t.get_children())
        self._log_map = {}
        locs = self.world.log_locations()
        mats = sorted({l.entry["material"] for l in locs})
        self.log_cb.configure(values=["All"] + mats)
        f = self.log_filter.get()
        if f != "All" and f not in mats:
            self.log_filter.set("All")
            f = "All"
        here = self.here
        rows = []
        for l in locs:
            e = l.entry
            if f != "All" and e["material"] != f:
                continue
            body = self.world.bodies[l.body]
            dist = None
            if here and here.get("body") is body:
                la, lo, _ = core.lat_lon_alt(l.local, body.radius)
                dist = core.surface_distance(here["lat"], here["lon"], la, lo, body.radius)
            rows.append((dist if dist is not None else float("inf"), e.get("time", ""), l, dist))
        rows.sort(key=lambda r: (r[0], [-ord(ch) for ch in r[1]]))
        methods = {"ship": "Ship", "vehicle": "ROC", "hand": "Hand"}
        for i, (_, _, l, dist) in enumerate(rows):
            e = l.entry
            try:
                when = clock_str(core.dt.datetime.fromisoformat(e["time"]).astimezone(), "%b %d %H:%M")
            except (ValueError, KeyError):
                when = ""
            q = "" if e.get("quality") in (None, "") else str(e["quality"])
            iid = t.insert("", "end", tags=["log"] + (["odd"] if i % 2 else []), values=(
                when, e["material"], q, l.body, methods.get(e.get("method"), e.get("method", "")),
                "--" if dist is None else core.fmt_km(dist)))
            self._log_map[iid] = l
        n = len(locs)
        self.lbl_log.configure(text=(f"{n} logged find{'s' if n != 1 else ''}. Closest first when you are on the same "
                                     "body. Double-click to target. Logged finds also show on the map and in Finder."
                                     if n else "No finds yet. When you find a deposit, run /showlocation, "
                                     "then click LOG FIND."))

    def _log_find(self):
        if not self._need_surface_fix():
            return
        dlg = LogDialog(self.root, self, self.world.materials(), getattr(self, "_last_log", None))
        if not dlg.result:
            return
        mat, method, quality, amount, note = dlg.result
        self._last_log = (mat, method)
        body = self.here["body"]
        self.world.log_find(mat, method, body.name, self.here["local"], quality, amount, note)
        self.mat_cb.configure(values=self.world.materials())
        self._fill_browse()
        self._recompute()

    def _log_copy_selected(self):
        locs = [self._log_map[i] for i in self.tree_log.selection() if i in self._log_map]
        if locs:
            self._copy_codes(locs)

    def _log_delete_selected(self):
        sel = self.tree_log.selection()
        loc = self._log_map.get(sel[0]) if sel else None
        if loc:
            self._delete_custom(loc)

    # ------------------------------------------------------------ day / route text
    def _sun_short(self, body, local, t):
        d = self.world.day_info(body, local, t)
        if d["elev"] is None or not d["cycle"]:
            return ""
        clock = core.fmt_clock(d["solar_time"])
        if d["is_day"]:
            return f"DAY {clock}" + (f" SET {core.fmt_duration((d['set'] - t).total_seconds(), False)}" if d["set"] else "")
        return f"NIGHT {clock}" + (f" RISE {core.fmt_duration((d['rise'] - t).total_seconds(), False)}" if d["rise"] else "")

    def _sun_text(self, body, local, t, prefix=""):
        d = self.world.day_info(body, local, t)
        if d["elev"] is None:
            return "", MUTED
        if not d["cycle"]:
            return f"{prefix}No day/night cycle data for {body.name}.", MUTED
        clock = core.fmt_clock(d["solar_time"])
        def when(x):
            return f"{core.fmt_duration((x - t).total_seconds(), False)} ({clock_str(x.astimezone(), '%H:%M')})"
        if d["is_day"]:
            nxt = f"sunset in {when(d['set'])}" if d["set"] else "sun stays up all cycle"
            return f"{prefix}☀ DAY   local {clock}   sun {d['elev']:.0f}° up   {nxt}", AMBER
        nxt = f"sunrise in {when(d['rise'])}" if d["rise"] else "no sunrise this cycle"
        return f"{prefix}☾ NIGHT   local {clock}   {nxt}", CYAN_DIM


    # ------------------------------------------------------------ scan / signatures
    def _build_scan(self, parent):
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill="x")
        self._lbl(row, "SIGNATURE", 7, MUTED, bold=True).pack(side="left", padx=(0, 6))
        self.sig_var = tk.StringVar()
        e = tk.Entry(row, textvariable=self.sig_var, width=10, bg=BG, fg=CYAN, insertbackground=CYAN,
                     font=(self.F_MONO, 18, "bold"), bd=0, highlightthickness=1, highlightbackground=LINE,
                     highlightcolor=CYAN)
        e.pack(side="left", ipady=2)
        e.bind("<KeyRelease>", lambda ev: self._scan_from_entry(record=ev.keysym == "Return"))
        self.sig_entry = e
        self._lbl(row, "MODE", 7, MUTED, bold=True).pack(side="left", padx=(12, 6))
        self.sig_mode = tk.StringVar(value="Auto")
        cb = ttk.Combobox(row, textvariable=self.sig_mode, values=signatures.MODES, width=13, state="readonly")
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda ev: self._scan_from_entry(record=False))
        ttk.Button(row, text="TEACH", command=self._teach_sig).pack(side="right")
        self.btn_ref = ttk.Button(row, text="TABLE", command=self._toggle_sig_table)
        self.btn_ref.pack(side="right", padx=6)

        card = tk.Frame(parent, bg=PANEL)
        card.pack(fill="x", pady=(8, 4))
        self.lbl_sig_main = self._lbl(card, "Type a signature, or press F8 in game", 16, MUTED, bold=True)
        self.lbl_sig_main.pack(anchor="w")
        self.lbl_sig_detail = self._lbl(card, "Example: 6340 is two Quantainium rocks (2 x 3,170).", 9, MUTED,
                                        wraplength=560)
        self.lbl_sig_detail.pack(anchor="w")

        self.sig_table_mode = False
        self.tree_sig = self._tree(parent, [("what", "COULD BE", 190), ("chance", "CHANCE", 60),
                                            ("info", "DETAILS", 320)])
        self.tree_sig.tag_configure("warn", foreground=AMBER)
        self.tree_sig.tag_configure("best", foreground=GREEN)

        self.lbl_sig_hist = self._lbl(parent, "", 8, MUTED, wraplength=560)
        self.lbl_sig_hist.pack(anchor="w", pady=(6, 2))

        rrow = tk.Frame(parent, bg=PANEL)
        rrow.pack(fill="x", pady=(2, 0))
        self._lbl(rrow, "READ SIGNATURES FROM MY SCREEN (BETA)", 7, CYAN_DIM, bold=True).pack(side="left", padx=(0, 8))
        ttk.Button(rrow, text="SET AREA", command=self._pick_area).pack(side="left")
        self.btn_reader = ttk.Button(rrow, text="START", command=self._toggle_reader)
        self.btn_reader.pack(side="left", padx=6)
        self.lbl_reader = self._lbl(rrow, "", 8, MUTED, wraplength=330)
        self.lbl_reader.pack(side="left", fill="x", expand=True)
        area = self._settings().get("ocr_area")
        self.lbl_reader.configure(text=("Area set. Press START." if area else
                                        "Pick the part of the screen where the signature number shows.")
                                  if ocr_reader.available() else "Windows only.")

    def _scan_age(self):
        if not self.last_scan:
            return 1e9
        return (core.utcnow() - self.last_scan["time"]).total_seconds()

    def _scan_from_entry(self, record):
        digits = "".join(ch for ch in self.sig_var.get() if ch.isdigit())
        if len(digits) < 4:
            if not digits:
                self.lbl_sig_main.configure(text="Type a signature, or press F8 in game", fg=MUTED)
            return
        self._scan(int(digits), source="typed", record=record, from_entry=True)

    def _scan(self, value, source="typed", record=True, from_entry=False):
        res = self.sigdb.identify(value, self.world, self.here, self.sig_mode.get())
        self.last_scan = {"value": value, "results": res, "time": core.utcnow() if record or not self.last_scan
                          else self.last_scan["time"], "source": source}
        if record:
            self.last_scan["time"] = core.utcnow()
        if not from_entry:
            self.sig_var.set(str(value))
        if self.sig_table_mode:
            self._toggle_sig_table()
        t = self.tree_sig
        t.delete(*t.get_children())
        if not res:
            self.lbl_sig_main.configure(text=f"{value:,}: NO MATCH", fg=AMBER)
            self.lbl_sig_detail.configure(fg=MUTED, text="Not a known rock, deposit, harvestable or salvage value. "
                                                         "If you find out what it is, click TEACH so it is "
                                                         "recognized next time.")
        else:
            top = res[0]
            col = RARITY_COLOR.get(top["rarity"], FG) if not top["warn"] else AMBER
            sure = "" if len(res) == 1 or top["score"] >= 75 else "  (probably)"
            self.lbl_sig_main.configure(text=f"{value:,}  =  {top['label'].upper()}{sure}", fg=col)
            self.lbl_sig_detail.configure(text=top["detail"], fg=AMBER if top["warn"] else FG)
            for i, c in enumerate(res):
                tags = ["odd"] if i % 2 else []
                tags.append("warn" if c["warn"] else ("best" if i == 0 else ""))
                t.insert("", "end", values=(c["label"], f"{c['score']}%", c["detail"]), tags=[x for x in tags if x])
        if record:
            self.scan_history = [(value, res[0]["label"] if res else "no match")] + \
                                [h for h in self.scan_history if h[0] != value][:7]
            self.lbl_sig_hist.configure(text="RECENT   " + "   ·   ".join(f"{v:,} {lab}" for v, lab in self.scan_history))
        if self.overlay:
            self.overlay.refresh()

    def _toggle_sig_table(self):
        self.sig_table_mode = not self.sig_table_mode
        self.btn_ref.configure(text="RESULTS" if self.sig_table_mode else "TABLE")
        t = self.tree_sig
        t.delete(*t.get_children())
        if not self.sig_table_mode:
            if self.last_scan:
                self._scan(self.last_scan["value"], self.last_scan["source"], record=False)
            return
        order = {"ship": 0, "vehicle": 1, "hand": 2, "harvestable": 3, "salvage": 4, "custom": 5}
        rows = sorted(self.sigdb.all_entries(), key=lambda e: (order.get(e["category"], 9), e["base"]))
        for i, e in enumerate(rows):
            mult = "  ".join(f"x{n} {e['base'] * n:,}" for n in range(2, min(e.get("max", 1), 6) + 1))
            label = signatures.CATEGORY_LABEL.get(e["category"], "") + (f" · {e['rarity']}" if e.get("rarity") else "")
            t.insert("", "end", values=(f"{e['name']}  {e['base']:,}", label, mult or "single"),
                     tags=("odd",) if i % 2 else ())

    def _teach_sig(self):
        digits = "".join(ch for ch in self.sig_var.get() if ch.isdigit())
        if not digits:
            messagebox.showinfo(APP_TITLE, "Type the signature first, then click TEACH.")
            return
        dlg = TeachDialog(self.root, self, int(digits))
        if dlg.result:
            name, count = dlg.result
            base = self.sigdb.teach(int(digits), name, count)
            messagebox.showinfo(APP_TITLE, f"Saved: {name} = {base:,}" + (f" each ({count} in this scan)." if count > 1 else ".")
                                + "\nIt will be recognized from now on, including groups of it.")
            self._scan(int(digits), record=False)

    # -- screen reader
    def _settings(self):
        try:
            import json
            with open(os.path.join(self.world.user_dir, "settings.json"), encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save_setting(self, key, value):
        import json
        s = self._settings()
        s[key] = value
        os.makedirs(self.world.user_dir, exist_ok=True)
        with open(os.path.join(self.world.user_dir, "settings.json"), "w", encoding="utf-8") as f:
            json.dump(s, f, indent=1)

    def _pick_area(self):
        AreaPicker(self, lambda region: (self._save_setting("ocr_area", region),
                                         self.lbl_reader.configure(text=f"Area {region[2]}x{region[3]} set. "
                                                                        "Press START.", fg=MUTED)))

    def _toggle_reader(self):
        if self.reader and self.reader.running:
            self.reader.stop()
            self.btn_reader.configure(text="START")
            self.lbl_reader.configure(text="Stopped.", fg=MUTED)
            return
        if not ocr_reader.available():
            messagebox.showinfo(APP_TITLE, "The screen reader uses text recognition built into Windows, so it "
                                           "only works on Windows 10 or 11.")
            return
        area = self._settings().get("ocr_area")
        if not area:
            messagebox.showinfo(APP_TITLE, "Click SET AREA first and drag a box around where the signature "
                                           "number appears on your screen.")
            return
        self.reader = ocr_reader.ScreenReader(self.world.user_dir, lambda k, t: self._reader_q.put((k, t)))
        try:
            self.reader.start(area)
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Could not start the screen reader.\n{e}")
            return
        self.btn_reader.configure(text="STOP")
        self.lbl_reader.configure(text="Starting...", fg=MUTED)
        self.root.after(250, self._poll_reader)

    def _poll_reader(self):
        while not self._reader_q.empty():
            kind, text = self._reader_q.get()
            if kind == "READY":
                self.lbl_reader.configure(text="Reading. Point the area at a signature.", fg=GREEN)
            elif kind == "ERR":
                self.lbl_reader.configure(text=f"Error: {text[:120]}", fg=AMBER)
            elif kind == "STOPPED":
                self.btn_reader.configure(text="START")
            elif kind == "OCR":
                self._handle_ocr(text)
        if self.reader and (self.reader.running or not self._reader_q.empty()):
            self.root.after(250, self._poll_reader)

    def _handle_ocr(self, text):
        nums = signatures.numbers_in_text(text)
        raw = text.split(" || ")[0].strip() or text.replace(" || ", " ").strip()
        seen = f"Sees: {', '.join(f'{v:,}' for v in nums[:3])}" if nums else \
            (f"Sees: {raw[:60]}" if raw else "Sees: nothing")
        self.lbl_reader.configure(text=seen, fg=MUTED)
        # take a number only once two reads in a row agree, so a one-off misread is ignored
        prev, self._ocr_prev = getattr(self, "_ocr_prev", set()), set(nums)
        for v in nums:
            if v not in prev:
                continue
            res = self.sigdb.identify(v, self.world, self.here, self.sig_mode.get(), limit=1)
            if res and res[0]["exact"]:
                last_v, last_t = self._last_screen_sig
                now = core.utcnow().timestamp()
                if v != last_v or now - last_t > 10:
                    self._last_screen_sig = (v, now)
                    self._scan(v, source="screen")
                return

    # ------------------------------------------------------------ built-in hotkeys
    def _repeat_seconds(self):
        try:
            return max(3, min(300, int(float(self.repeat_secs.get()))))
        except (ValueError, AttributeError):
            return 10

    def _hk_say(self, text, ok=True):
        stamp = clock_str(core.dt.datetime.now(), "%H:%M:%S")
        if hasattr(self, "lbl_hk"):
            self.lbl_hk.configure(text=f"{stamp}  {text}", fg=GREEN if ok else AMBER)
        self.toast = (text, ok, core.utcnow().timestamp())
        if self.overlay:
            self.overlay.refresh()

    def _start_hotkeys(self):
        if not hotkeys_win.available():
            self.lbl_hk.configure(text="Built-in hotkeys work on Windows only.", fg=MUTED)
            return
        if self.btn_admin and hotkeys_win.is_admin():
            self.btn_admin.configure(text="ADMIN ✓", state="disabled")
        if not self.hk_enabled.get():
            self.lbl_hk.configure(text="Hotkeys are off.", fg=MUTED)
            return
        if not hotkeys_win.claim_hotkeys():
            if not getattr(self, "_hk_wait_logged", False):
                hotkeys_win.log("another Starboard owns the hotkeys; waiting")
                self._hk_wait_logged = True
            self.lbl_hk.configure(fg=AMBER, text="Another Starboard window is open and handles F8, F9 and F10. "
                                                 "Close it and the hotkeys move to this window.")
            if getattr(self, "_hk_retry", None):
                self.root.after_cancel(self._hk_retry)
            self._hk_retry = self.root.after(3000, self._hk_try_again)
            return
        self._hk_actions = {}
        for action, spec in self._hotkey_map().items():
            parsed = hotkeys_win.parse_hotkey(spec)
            if parsed and parsed[2] not in ("F8", "F9", "F10"):
                self._hk_actions[spec] = action
        self.hk = hotkeys_win.HotkeyListener(["F8", "F9", "F10"] + list(self._hk_actions),
                                             lambda k: self._hk_q.put(k))
        failed = self.hk.start()
        hotkeys_win.log(f"hotkeys started, failed={failed}, admin={hotkeys_win.is_admin()}")
        admin = "Running as administrator." if hotkeys_win.is_admin() else \
            "Not running as administrator: if F9 shows 'sent' but nothing types in game, click ADMIN."
        if failed:
            self.lbl_hk.configure(fg=AMBER, text=f"The keyboard watcher could not start for {', '.join(failed)}, so "
                                                 "Starboard cannot see "
                                                 "the F-keys. Try restarting Starboard. " + admin)
        else:
            self.lbl_hk.configure(fg=MUTED, text="Ready. Press F9 in game; this line shows what happened. " + admin)
        self.root.after(100, self._poll_hotkeys)
        self.root.after(2000, self._check_game_elevation)

    def _hk_try_again(self):
        self._hk_retry = None
        if self.hk is None and self.hk_enabled.get():
            self._start_hotkeys()

    def _check_game_elevation(self):
        """Warn when the game runs as administrator but this app does not: Windows then
        keeps hotkeys and typed keys away from the game."""
        if not self.hk:
            return
        exe = self._settings().get("game_exe", "StarCitizen.exe")
        pid = hotkeys_win.find_process(exe)
        elevated = hotkeys_win.process_elevated(pid) if pid else None
        if pid and elevated and not hotkeys_win.is_admin():
            if not getattr(self, "_elev_warned", False):
                hotkeys_win.log("Star Citizen is elevated and Starboard is not")
                self._elev_warned = True
            self._hk_say("Star Citizen is running as administrator, so Windows blocks the hotkeys. "
                         "Click ADMIN (and tick 'always start as administrator').", False)
        self.root.after(10000, self._check_game_elevation)

    def _hotkeys_toggled(self):
        self._save_setting("hotkeys_enabled", self.hk_enabled.get())
        if self.hk:
            self.hk.stop()
            self.hk = None
        if self.repeat_on:
            self._toggle_repeat()
        if self.hk_enabled.get():
            self._start_hotkeys()
        else:
            self.lbl_hk.configure(text="Hotkeys are off.", fg=MUTED)

    def _poll_hotkeys(self):
        while not self._hk_q.empty():
            key = self._hk_q.get()
            if isinstance(key, tuple):  # result from a send thread
                self._hk_say(*key)
                continue
            if key == "F8":
                self._hk_signature()
            elif key == "F9":
                self._hk_showlocation(manual=True)
            elif key == "F10":
                self._toggle_repeat()
            elif key in getattr(self, "_hk_actions", {}):
                self._hotkey_action(self._hk_actions[key])
        if self.hk:
            self.root.after(100, self._poll_hotkeys)

    # Ctrl+Shift+number opens the tab in that place on the tab bar (0 is the tenth)
    TAB_ORDER = ["HOME", "LIVE", "NAVIGATE", "MINE", "SALVAGE", "HAUL", "COMBAT", "MISSIONS", "SHOP", "CRAFT",
                 "HANGAR", "MONEY", "EVENTS", "SETTINGS"]
    HOTKEY_ACTIONS = [("toggle", "Show or hide Starboard", "Ctrl+Shift+S")] + [
        (name, f"Open {name}", f"Ctrl+Shift+{(i + 1) % 10}" if i < 10 else "") for i, name in enumerate(TAB_ORDER)]
    OLD_HOTKEY_DEFAULTS = {"HOME": "Ctrl+Shift+1", "LIVE": "Ctrl+Shift+2", "NAVIGATE": "Ctrl+Shift+3",
                           "MINE": "Ctrl+Shift+4", "HAUL": "Ctrl+Shift+5", "COMBAT": "Ctrl+Shift+6",
                           "SHOP": "Ctrl+Shift+7", "MONEY": "Ctrl+Shift+8", "HANGAR": "Ctrl+Shift+9"}

    def _hotkey_map(self):
        saved = dict(self._settings().get("hotkeys_map") or {})
        if saved and self._settings().get("hotkeys_layout", 1) < 2:
            # keys still on the old defaults follow the new tab order; keys you changed stay
            saved = {a: v for a, v in saved.items() if self.OLD_HOTKEY_DEFAULTS.get(a) != v}
            self._save_setting("hotkeys_map", saved)
            self._save_setting("hotkeys_layout", 2)
        out = {a: saved.get(a, d) for a, _label, d in self.HOTKEY_ACTIONS}
        taken = {v for a, v in out.items() if a in saved and v}  # a key you set wins over a default
        return {a: ("" if (a not in saved and v in taken) else v) for a, v in out.items()}

    def _tab_hotkey(self, name):
        return self._hotkey_map().get(name, "")

    def _hotkey_action(self, action):
        r = self.root
        if action == "toggle":
            if r.state() in ("withdrawn", "iconic"):
                r.deiconify()
                r.lift()
                r.attributes("-topmost", True)
                if not self.on_top.get():
                    r.after(200, lambda: r.attributes("-topmost", False))
            else:
                r.withdraw()
            return
        tabs = {"HOME": self.tab_home, "LIVE": self.tab_live, "NAVIGATE": self.tab_near, "MINE": self.tab_scan,
                "SALVAGE": self.tab_salvage, "HAUL": self.tab_haul, "COMBAT": self.tab_combat,
                "MISSIONS": self.tab_missions, "SHOP": self.tab_shop, "CRAFT": self.tab_craft,
                "HANGAR": self.tab_hangar, "MONEY": self.tab_ledger, "EVENTS": self.tab_events,
                "SETTINGS": self.tab_settings}
        if action in tabs:
            if r.state() in ("withdrawn", "iconic"):
                r.deiconify()
            r.lift()
            self._show(tabs[action])

    def _game_active(self):
        name = hotkeys_win.foreground_process_name()
        return name.lower() == self._settings().get("game_exe", "StarCitizen.exe").lower(), name

    def _hk_showlocation(self, manual=False):
        active, name = self._game_active()
        if not active:
            if manual:
                self._hk_say(f"F9 received, but the active window is {name or 'unknown'}, not Star Citizen.", False)
            return
        st = self._settings()
        wait, delay = st.get("chat_open_ms", 250) / 1000, st.get("key_delay_ms", 30) / 1000

        def work():
            n = hotkeys_win.send_chat_command("/showlocation", wait, delay, delay)
            hotkeys_win.log(f"/showlocation sent, {n} key events accepted")
            if n == 0:
                self._hk_q.put(("Windows blocked the keys. Click RESTART AS ADMIN in SETTINGS > MAP DATA.", False))
            elif manual:
                self._hk_q.put(("F9: /showlocation sent.", True))

        threading.Thread(target=work, daemon=True).start()

    def _toggle_repeat(self):
        self.repeat_on = not self.repeat_on
        if self._repeat_job:
            self.root.after_cancel(self._repeat_job)
            self._repeat_job = None
        if self.repeat_on:
            self._hk_say(f"F10: auto-repeat ON, every {self._repeat_seconds()} s.")
            self._repeat_tick()
        else:
            self._hk_say("F10: auto-repeat OFF.")

    def _repeat_tick(self):
        if not self.repeat_on:
            return
        self._hk_showlocation(manual=False)
        self._repeat_job = self.root.after(self._repeat_seconds() * 1000, self._repeat_tick)

    def _hk_signature(self):
        active, name = self._game_active()
        game = hotkeys_win.foreground_window() if active else None
        if self.sig_prompt:
            self.sig_prompt.destroy()
        self.sig_prompt = SigPrompt(self, game)

    def _restart_admin(self):
        if hotkeys_win.relaunch_as_admin():
            if self.hk:
                self.hk.stop()
            if self.reader:
                self.reader.stop()
            self.root.after(300, self.root.destroy)

    # ------------------------------------------------------------ data tab
    # ------------------------------------------------------------ hauling
    HAUL_SKIP_TYPES = {"Cave", "Landmark", "Racetrack", "Ruins", "Shipwreck", "CommArray", "Asteroid cluster",
                       "Planetary alignment facility", "Orbital laser platform"}
    ARRIVE_KM = {"City": 15.0, "Landing zone": 15.0, "Space station": 8.0, "Space Station": 8.0,
                 "Asteroid base": 6.0, "Distribution center": 3.0}

    def _build_haul(self, parent):
        st = self._settings()
        self.haul_ship = tk.StringVar(value=st.get("haul_ship", ""))
        self.haul_scu = tk.StringVar(value=str(st.get("haul_scu", "")))
        self.haul_budget = tk.StringVar(value=str(st.get("haul_budget", "")))
        self.root.after(500, lambda: (self.haul_scu.trace_add("write", lambda *a: self._haul_changed()),
                                      self.haul_budget.trace_add("write", lambda *a: self._haul_changed())))
        top = tk.Frame(parent, bg=PANEL)
        top.pack(fill="x", pady=(0, 4))
        self._lbl(top, "SHIP", 7, MUTED, bold=True).pack(side="left", padx=(0, 6))
        self.ship_cb = ttk.Combobox(top, textvariable=self.haul_ship, width=24)
        self.ship_cb.pack(side="left")
        self.ship_cb.bind("<KeyRelease>", self._ship_filter)
        self.ship_cb.bind("<<ComboboxSelected>>", self._ship_picked)
        self._lbl(top, "SCU", 7, MUTED, bold=True).pack(side="left", padx=(10, 4))
        e = ttk.Entry(top, textvariable=self.haul_scu, width=6)
        e.pack(side="left")
        e.bind("<FocusOut>", lambda ev: self._haul_save())
        self._lbl(top, "BUDGET", 7, MUTED, bold=True).pack(side="left", padx=(10, 4))
        e = ttk.Entry(top, textvariable=self.haul_budget, width=9)
        e.pack(side="left")
        e.bind("<FocusOut>", lambda ev: self._haul_save())
        self.btn_prices = ttk.Button(top, text="UPDATE PRICES", command=self._haul_download)
        self.btn_prices.pack(side="right")
        self.lbl_haul = self._lbl(parent, "Loading trade data...", 8, MUTED, wraplength=640)
        self.lbl_haul.pack(anchor="w", pady=(0, 6))

        hnb = ttk.Notebook(parent)
        hnb.pack(fill="both", expand=True)
        self.haul_nb = hnb

        # -- trade routes
        fr = ttk.Frame(hnb, style="Panel.TFrame", padding=6)
        hnb.add(fr, text="ROUTES")
        row = tk.Frame(fr, bg=PANEL)
        row.pack(fill="x", pady=(0, 6))
        self.route_system = tk.StringVar(value="Current")
        self.route_comm = tk.StringVar(value="All")
        self.route_near = tk.StringVar(value="Anywhere")
        self._lbl(row, "SYSTEM", 7, MUTED, bold=True).pack(side="left", padx=(0, 4))
        cb = ttk.Combobox(row, textvariable=self.route_system, state="readonly", width=9,
                          values=["Current"] + self.world.systems())
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda ev: self._fill_routes())
        self._lbl(row, "COMMODITY", 7, MUTED, bold=True).pack(side="left", padx=(10, 4))
        self.comm_cb = ttk.Combobox(row, textvariable=self.route_comm, state="readonly", width=16, values=["All"])
        self.comm_cb.pack(side="left")
        self.comm_cb.bind("<<ComboboxSelected>>", lambda ev: self._fill_routes())
        self._lbl(row, "START", 7, MUTED, bold=True).pack(side="left", padx=(10, 4))
        cb = ttk.Combobox(row, textvariable=self.route_near, state="readonly", width=11,
                          values=["Anywhere", "Where I am", "Under 1 Gm", "Under 5 Gm", "Under 20 Gm"])
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda ev: self._fill_routes())
        self.tree_routes = self._tree(fr, [("c", "COMMODITY", 88), ("buy", "BUY AT", 102), ("sell", "SELL AT", 102),
                                           ("qty", "SCU", 40), ("inv", "COST", 56), ("pro", "PROFIT", 56),
                                           ("dist", "TRIP", 70), ("from", "TO START", 70), ("age", "PRICE AGE", 50)])
        self.tree_routes.tag_configure("old", foreground=MUTED)
        self.tree_routes.bind("<<TreeviewSelect>>", self._route_selected)
        self.tree_routes.bind("<Double-1>", self._route_start)
        self.lbl_route_info = self._lbl(fr, "Double-click a route to start it as a run.", 8, MUTED, wraplength=640)
        self.lbl_route_info.pack(anchor="w", pady=(6, 0))
        self._route_map = {}

        # -- contracts
        fc = ttk.Frame(hnb, style="Panel.TFrame", padding=6)
        hnb.add(fc, text="CONTRACTS")
        row = tk.Frame(fc, bg=PANEL)
        row.pack(fill="x", pady=(0, 6))
        ttk.Button(row, text="ADD CONTRACT", style="Accent.TButton", command=self._contract_add).pack(side="left")
        ttk.Button(row, text="EDIT", command=self._contract_edit).pack(side="left", padx=6)
        ttk.Button(row, text="ON / OFF", command=self._contract_toggle).pack(side="left")
        ttk.Button(row, text="REMOVE", command=self._contract_remove).pack(side="left", padx=6)
        ttk.Button(row, text="PLAN RUN", style="Accent.TButton", command=self._contract_plan).pack(side="right")
        b = ttk.Button(row, text="PLAN TRIP", style="Accent.TButton", command=self._trip_plan)
        b.pack(side="right", padx=(0, 6))
        self._tip(b, "One trip for everything: your active contracts, refinery jobs ready to collect, and the best "
                     "trade you can fit on the way with the cargo space left over.")
        self.tree_con = self._tree(fc, [("what", "CONTRACT  /  LEG", 330), ("scu", "SCU", 60),
                                        ("reward", "REWARD", 90), ("st", "STATUS", 70)], show_tree=True)
        self.tree_con.tag_configure("off", foreground=MUTED)
        self.tree_con.bind("<Double-1>", lambda ev: self._contract_edit())
        self.lbl_con = self._lbl(fc, "", 8, MUTED, wraplength=640)
        self.lbl_con.pack(anchor="w", pady=(6, 0))

        # -- live run
        fl = ttk.Frame(hnb, style="Panel.TFrame", padding=6)
        hnb.add(fl, text="RUN")
        self.lbl_run = self._lbl(fl, "", 10, CYAN, bold=True, wraplength=640)
        self.lbl_run.pack(anchor="w", pady=(0, 4))
        row = tk.Frame(fl, bg=PANEL)
        row.pack(fill="x", pady=(0, 6))
        ttk.Button(row, text="BACK", command=lambda: self._run_step(-1)).pack(side="left")
        ttk.Button(row, text="NEXT STOP", command=lambda: self._run_step(1)).pack(side="left", padx=6)
        ttk.Button(row, text="TARGET STOP", command=self._run_target).pack(side="left")
        ttk.Button(row, text="END RUN", command=self._run_end).pack(side="right")
        self.run_auto = tk.BooleanVar(value=st.get("run_auto", True))
        ttk.Checkbutton(row, text="AUTO NEXT WHEN I LEAVE", variable=self.run_auto, style="Panel.TCheckbutton",
                        command=lambda: self._save_setting("run_auto", self.run_auto.get())
                        ).pack(side="left", padx=10)
        self.tree_run = self._tree(fl, [("n", "#", 30), ("place", "STOP", 140), ("todo", "TO DO", 300),
                                        ("load", "ON BOARD", 80), ("st", "STATUS", 62)])
        self.tree_run.tag_configure("now", foreground=GREEN)
        self.tree_run.tag_configure("done", foreground=MUTED)
        self.tree_run.bind("<Double-1>", self._run_jump)
        self._lbl(fl, "The current stop is your target. Press F9 at each stop; the app marks it arrived and moves "
                      "on when you leave. Double-click a stop to jump to it.", 8, MUTED, wraplength=640
                  ).pack(anchor="w", pady=(6, 0))

        self.trade = None
        self._haul_q = None
        self.contracts = hauling.Contracts(self.world)
        self.run = self._run_load()
        self._fill_contracts()
        self._fill_run()
        self.root.after(1200, lambda: threading.Thread(target=self._haul_load_bg, daemon=True).start())
        self.root.after(300, self._haul_poll)

    # -- trade data loading and download
    def _haul_load_bg(self):
        try:
            td = hauling.TradeData(self.world, self.world.user_dir)
            self._haul_ready = ("loaded", td)
        except Exception as e:
            self._haul_ready = ("error", f"{e.__class__.__name__}: {e}")

    def _haul_poll(self):
        ready = getattr(self, "_haul_ready", None)
        if ready is None:
            self.root.after(300, self._haul_poll)
            return
        self._haul_ready = None
        kind, val = ready
        if kind == "error":
            self.lbl_haul.configure(text=f"Could not read the trade data ({val}). Click UPDATE PRICES.", fg=AMBER)
            return
        self.trade = val
        self._haul_after_load()

    def _haul_after_load(self):
        td = self.trade
        try:
            self._market_refresh()
        except Exception as e:  # noqa: BLE001
            hotkeys_win.log(f"market ticker: {e}")
        names = td.ship_names()
        self._ships_all = names
        self.ship_cb.configure(values=names)
        self.comm_cb.configure(values=["All"] + td.commodities())
        self._haul_status()
        self._fill_routes()
        self._search_index = None
        if hasattr(self, "tree_hangar"):
            self._fill_hangar()
        if hasattr(self, "tree_shop"):
            self.shopdata = None
            self._shop_list()
        if hasattr(self, "tree_salv"):
            self._fill_salvage()

    def _haul_status(self, extra=""):
        td = self.trade
        if not td or not td.loaded:
            self.lbl_haul.configure(fg=AMBER, text="No trade data yet. Click UPDATE PRICES to download prices, "
                                                   "terminals and ships from UEX (free, about 10 seconds).")
            return
        age = td.age_minutes()
        matched = sum(1 for t in td.terminals.values() if t.loc is not None)
        when = ("just now" if age is not None and age < 2 else
                f"{age:.0f} min ago" if age is not None and age < 90 else
                f"{age / 60:.1f} h ago" if age is not None else "at an unknown time")
        old = age is not None and age > hauling.CACHE_TTL / 60
        self.lbl_haul.configure(fg=AMBER if old else MUTED, text=(
            f"Prices from UEX, updated {when}.{' Press UPDATE PRICES for fresh ones.' if old else ''}  "
            f"{extra}").strip())

    def _haul_download(self):
        if self._haul_q is not None:
            return
        self.btn_prices.configure(state="disabled")
        self.lbl_haul.configure(text="Downloading from UEX...", fg=CYAN)
        q = queue.Queue()
        self._haul_q = q
        user_dir, world = self.world.user_dir, self.world

        def work():
            try:
                counts = hauling.download(user_dir, log=lambda m: q.put(("log", m)))
                q.put(("done", (counts, hauling.TradeData(world, user_dir))))
            except Exception as e:
                q.put(("error", f"{e.__class__.__name__}: {e}"))

        threading.Thread(target=work, daemon=True).start()
        self.root.after(200, self._haul_dl_poll)

    def _haul_dl_poll(self):
        q, finished = self._haul_q, None
        while q and not q.empty():
            kind, val = q.get()
            if kind == "log":
                self.lbl_haul.configure(text=val, fg=CYAN)
            else:
                finished = (kind, val)
        if not finished:
            self.root.after(200, self._haul_dl_poll)
            return
        self._haul_q = None
        self.btn_prices.configure(state="normal")
        kind, val = finished
        if kind == "error":
            hotkeys_win.log(f"UEX download failed: {val}")
            self.lbl_haul.configure(text=f"Download failed, your old data is kept. ({val})", fg=AMBER)
            return
        self.trade = val[1]
        self._haul_after_load()

    # -- ship, hold and budget
    def _ship_filter(self, ev):
        if ev.keysym in ("Up", "Down", "Return", "Escape", "Tab"):
            return
        text = self.haul_ship.get().lower()
        allv = getattr(self, "_ships_all", [])
        self.ship_cb.configure(values=[n for n in allv if text in n.lower()] or allv)

    def _ship_default_scu(self, label):
        over = self._settings().get("scu_overrides", {})
        if label in over:
            return float(over[label])
        v = self.trade.ship(label) if self.trade else None
        return float(v["scu"]) if v else None

    def _ship_picked(self, _ev=None):
        if self.trade:
            scu = self._ship_default_scu(self.haul_ship.get())
            if scu is not None:
                self._picking = True
                self.haul_scu.set(f"{scu:g}")
        self.ship_cb.configure(values=getattr(self, "_ships_all", []))
        self._haul_save()
        self._fill_routes()

    def _haul_save(self):
        self._save_setting("haul_ship", self.haul_ship.get().strip())
        self._save_setting("haul_scu", self.haul_scu.get().strip())
        self._save_setting("haul_budget", self.haul_budget.get().strip())
        self._fill_contracts()

    def _haul_changed(self):
        if getattr(self, "_haul_job", None):
            self.root.after_cancel(self._haul_job)
        self._haul_job = self.root.after(600, self._haul_apply)

    def _haul_apply(self):
        self._haul_job = None
        if getattr(self, "_picking", False):
            self._picking = False
        elif self.trade:  # typed SCU for a ship setup: remember it for that setup
            label, v = self.haul_ship.get().strip(), self.trade.ship(self.haul_ship.get().strip())
            scu = self._haul_scu()
            if v and scu > 0:
                over = self._settings().get("scu_overrides", {})
                if abs(scu - float(v["scu"])) < 0.01:
                    over.pop(label, None)
                else:
                    over[label] = scu
                self._save_setting("scu_overrides", over)
        self._haul_save()
        self._fill_routes()

    def _haul_scu(self):
        try:
            return max(0.0, float(self.haul_scu.get().replace(",", "")))
        except ValueError:
            return 0.0

    def _haul_budget(self):
        txt = self.haul_budget.get().replace(",", "").strip().lower()
        try:
            mult = 1_000_000 if txt.endswith("m") else 1000 if txt.endswith("k") else 1
            return float(txt.rstrip("mk")) * mult if txt else None
        except ValueError:
            return None

    # -- trade routes
    @staticmethod
    def _money(v):
        v = float(v)
        if abs(v) >= 1_000_000:
            return f"{v / 1_000_000:.2f}M"
        if abs(v) >= 10_000:
            return f"{v / 1000:.1f}k"
        return f"{v:,.0f}"

    @staticmethod
    def _short_km(d):
        if d is None:
            return "?"
        if d >= 100_000:
            return f"{d / 1e6:.2f} Gm"
        return core.fmt_km(d)

    def _fill_routes(self):
        if not hasattr(self, "tree_routes"):
            return
        t = self.tree_routes
        t.delete(*t.get_children())
        self._route_map = {}
        td = self.trade
        if not td or not td.loaded:
            return
        scu = self._haul_scu()
        if scu <= 0:
            self.lbl_route_info.configure(text="Pick your ship (or type its SCU) to see routes.", fg=AMBER)
            return
        system = self.route_system.get()
        system = self.last_system if system == "Current" else system
        comm = self.route_comm.get()
        mode = self.route_near.get()
        near = {"Under 1 Gm": 1e6, "Under 5 Gm": 5e6, "Under 20 Gm": 2e7}.get(mode)
        here = self.here if self.here and self.here["system"] == system else None
        if (near or mode == "Where I am") and not here:
            self.lbl_route_info.configure(text=f"START needs a /showlocation fix in {system} (press F9).", fg=AMBER)
            return
        local = td.terminals_here(here) if here else []
        local_ids = {t.id for t in local}
        if mode == "Where I am" and not local_ids:
            self.lbl_route_info.configure(fg=AMBER, text=(
                f"No trade terminals within {hauling.HERE_KM:g} km of your last fix. Press F9 at the terminal."))
            return
        rows = td.routes(scu, budget=self._haul_budget(), system=system, here=here,
                         commodity=None if comm == "All" else comm, from_here_km=near,
                         buy_at=local_ids if mode == "Where I am" else None)
        for i, r in enumerate(rows):
            iid = str(i)
            self._route_map[iid] = r
            age = r["age_days"]
            tags = ["odd"] if i % 2 else []
            if age is not None and age > hauling.STALE_PRICE_DAYS:
                tags.append("old")
            fmt = self._short_km
            t.insert("", "end", iid=iid, tags=tags, values=(
                clip_text(r["commodity"], 13), clip_text(r["buy"].name, 15), clip_text(r["sell"].name, 15), r["qty"],
                self._money(r["invest"]), self._money(r["profit"]), fmt(r["distance"]), fmt(r["from_here"]),
                "?" if age is None else (f"{age * 24:.0f}h" if age < 1 else f"{age:.0f}d")))
        names_here = ", ".join(sorted({t.name for t in local if any(
            p.get("id_terminal") == t.id for p in td.prices)})) if local else ""
        if mode == "Where I am":
            sold = td.sold_at(local_ids)
            what = ", ".join(sorted({c for c, *_ in sold})) or "nothing (no prices reported)"
            if rows:
                self.lbl_route_info.configure(fg=MUTED, text=(
                    f"Buying at {names_here}. For sale here: {what}. Click a row for details, double-click "
                    "to start it as a run."))
            else:
                self.lbl_route_info.configure(fg=AMBER, text=(
                    f"{names_here or 'The terminals here'} sell {what}, but no buyer pays more in {system} "
                    "with these filters."))
        elif rows:
            hint = (f"You are at {names_here}: set START to WHERE I AM to see what you can haul from here.  "
                    if names_here and mode == "Anywhere" else "")
            self.lbl_route_info.configure(fg=CYAN if hint else MUTED, text=hint + (
                f"{len(rows)} routes in {system} for {scu:g} SCU, best profit first. Click a row for details, "
                "double-click to start it as a run. Grey rows have prices older than a week."))
        else:
            self.lbl_route_info.configure(fg=AMBER, text=f"No profitable routes found in {system} with these filters.")

    def _route_selected(self, _ev=None):
        sel = self.tree_routes.selection()
        r = self._route_map.get(sel[0]) if sel else None
        if not r:
            return
        a, b = r["buy"], r["sell"]
        lim = {"stock": "the terminal's stock", "demand": "what the buyer wants", "budget": "your budget"}
        why = (" Limited by " + " and ".join(lim[x] for x in r["limits"]) + ".") if r["limits"] else ""
        def where(t):
            out = t.place + (f" ({t.body.name})" if t.body and t.body.name != t.place else "")
            return out + (f", {t.name}" if t.name and t.name != t.place else "")
        self.lbl_route_info.configure(fg=FG, text=(
            f"Buy {r['qty']} SCU {r['commodity']} at {where(a)} for {r['price_buy']:,.2f}/SCU. "
            f"Sell at {where(b)} for {r['price_sell']:,.2f}/SCU.  "
            f"Cost {r['invest']:,.0f} aUEC, profit {r['profit']:,.0f} aUEC "
            f"({r['margin']:,.2f}/SCU).{why}"))

    def _stop_from_terminal(self, t, actions):
        loc = t.loc
        return {"name": loc.name if loc else t.place, "body": loc.body if loc else (t.body.name if t.body else ""),
                "type": loc.type if loc else "", "terminal": t.name, "actions": actions}

    def _route_start(self, _ev=None):
        sel = self.tree_routes.selection()
        r = self._route_map.get(sel[0]) if sel else None
        if not r:
            return
        what = f"{r['qty']} SCU {r['commodity']}"
        term = lambda t: f" ({t.name})" if t.name and t.name != t.place else ""
        stops = [self._stop_from_terminal(r["buy"], [f"BUY {what} at {r['price_buy']:,.2f}{term(r['buy'])}"]),
                 self._stop_from_terminal(r["sell"], [f"SELL {what} at {r['price_sell']:,.2f}{term(r['sell'])}"])]
        stops[0]["load_after"], stops[1]["load_after"] = r["qty"], 0
        stops[0]["ledger"] = [{"kind": ledger.EXPENSE, "category": "Trade purchase", "amount": r["invest"],
                               "note": f"Bought {what} at {r['buy'].name}"}]
        stops[1]["ledger"] = [{"kind": ledger.INCOME, "category": "Trade sale", "amount": r["qty"] * r["price_sell"],
                               "note": f"Sold {what} at {r['sell'].name}"}]
        self._run_begin(f"{r['commodity']}: {r['buy'].place} to {r['sell'].place}, "
                        f"profit {r['profit']:,.0f} aUEC", stops, r["distance"])

    # -- contracts
    def _haul_places(self):
        """Location choices for contract legs: label -> Location."""
        out = {}
        for l in self.world.locations:
            if l.type in self.HAUL_SKIP_TYPES:
                continue
            out[f"{l.name} · {l.body}"] = l
        return out

    def _fill_contracts(self):
        if not hasattr(self, "tree_con"):
            return
        t = self.tree_con
        t.delete(*t.get_children())
        total_scu, total_reward, n_on = 0.0, 0.0, 0
        for c in self.contracts.items:
            on = c.get("active", True)
            scu = sum(float(l["scu"]) for l in c["legs"])
            if on:
                n_on += 1
                total_scu += scu
                total_reward += float(c.get("reward") or 0)
            iid = "c" + c["id"]
            t.insert("", "end", iid=iid, open=True, tags=([] if on else ["off"]) + ["head"],
                     values=(c["title"], f"{scu:g}", f"{float(c.get('reward') or 0):,.0f}",
                             "DONE" if c.get("done") else "ON" if on else "OFF"))
            for i, l in enumerate(c["legs"]):
                what = f"{l['pickup']['name']}  >  {l['dropoff']['name']}"
                if l.get("commodity"):
                    what += f"   ({l['commodity']})"
                t.insert(iid, "end", iid=f"{iid}:{i}", tags=[] if on else ["off"],
                         values=(what, f"{float(l['scu']):g}", "", ""))
        cap = self._haul_scu()
        if not self.contracts.items:
            self.lbl_con.configure(fg=MUTED, text="Add the hauling contracts you accepted in game. PLAN RUN "
                                                  "orders every pickup and drop-off for the shortest trip that fits "
                                                  "your hold, starting from where you are.")
            return
        msg = f"{n_on} active contracts, {total_scu:g} SCU in total, {total_reward:,.0f} aUEC reward."
        if cap:
            msg += f"  Your hold: {cap:g} SCU."
            if total_scu > cap:
                msg += " Not everything fits at once; the plan will deliver some cargo before picking up more."
        self.lbl_con.configure(fg=MUTED, text=msg)

    def _contract_selected(self):
        sel = self.tree_con.selection()
        if not sel:
            return None
        cid = sel[0].split(":")[0][1:]
        return next((c for c in self.contracts.items if c["id"] == cid), None)

    def _contract_add(self, existing=None):
        dlg = ContractDialog(self.root, self, self._haul_places(), existing)
        if not dlg.result:
            return
        title, reward, legs = dlg.result
        if existing:
            existing.update(title=title, reward=reward, legs=legs)
            self.contracts.save()
        else:
            self.contracts.add(title, reward, legs)
        self._fill_contracts()

    def _contract_edit(self):
        c = self._contract_selected()
        if c:
            self._contract_add(c)

    def _contract_toggle(self):
        c = self._contract_selected()
        if c:
            c["active"] = not c.get("active", True)
            c.pop("done", None)
            self.contracts.save()
            self._fill_contracts()

    def _contract_remove(self):
        c = self._contract_selected()
        if c and messagebox.askyesno(APP_TITLE, f"Remove the contract \"{c['title']}\"?"):
            self.contracts.remove(c["id"])
            self._fill_contracts()

    def _contract_plan(self):
        legs = []
        for leg in self.contracts.active_legs():
            p = hauling.find_location(self.world, leg["pickup"]["name"], leg["pickup"].get("body"))
            d = hauling.find_location(self.world, leg["dropoff"]["name"], leg["dropoff"].get("body"))
            if not p or not d:
                messagebox.showwarning(APP_TITLE, f"Could not find a stop of \"{leg['contract']}\" any more "
                                                  "(maybe after a data update). Edit the contract and pick it again.")
                return
            legs.append(dict(leg, pickup=p, dropoff=d, scu=float(leg["scu"])))
        if not legs:
            messagebox.showinfo(APP_TITLE, "There are no active contracts to plan.")
            return
        cap = self._haul_scu()
        if cap <= 0:
            messagebox.showinfo(APP_TITLE, "Pick your ship or type its SCU first, so the plan knows what fits.")
            return
        legs = hauling.split_legs(legs, cap)
        start = self.here["global"] if self.here else None
        if self.here and legs and self.here["system"] != legs[0]["pickup"].star:
            start = None
        self.root.configure(cursor="watch")
        self.root.update_idletasks()
        try:
            stops = hauling.plan_run(self.world, legs, cap, start=start)
        finally:
            self.root.configure(cursor="")
        if not stops:
            messagebox.showwarning(APP_TITLE, "No order of stops fits these contracts in your hold. Turn some "
                                              "contracts off and plan again.")
            return
        out, total, last_drop = [], 0.0, {}
        for n, s in enumerate(stops):
            total += s.get("leg_km") or 0
            for kind, li in s["actions"]:
                if kind == "dropoff":
                    last_drop[legs[li]["cid"]] = n
            out.append({"name": s["loc"].name, "body": s["loc"].body, "type": s["loc"].type,
                        "actions": hauling.describe_actions(s, legs), "load_after": s["load_after"],
                        "leg_km": s.get("leg_km")})
        for c in self.contracts.items:
            if c["id"] in last_drop:
                st = out[last_drop[c["id"]]]
                st.setdefault("ledger", []).append({"kind": ledger.INCOME, "category": "Contract payout",
                                                    "amount": float(c.get("reward") or 0), "note": c["title"]})
                st.setdefault("completes", []).append(c["id"])
        reward = sum(float(c.get("reward") or 0) for c in self.contracts.items if c.get("active", True))
        self._run_begin(f"{len({l['cid'] for l in legs})} contracts, {len(out)} stops, "
                        f"reward {reward:,.0f} aUEC", out, total)

    # -- one trip for everything (HAUL > CONTRACTS > PLAN TRIP)
    def _trip_plan(self):
        import time as _t
        cap = self._haul_scu()
        if cap <= 0:
            messagebox.showinfo(APP_TITLE, "Pick your ship or type its SCU first (HAUL), so the trip knows what fits.")
            return
        when = core.utcnow()
        legs = []
        for leg in self.contracts.active_legs():
            p = hauling.find_location(self.world, leg["pickup"]["name"], leg["pickup"].get("body"))
            d = hauling.find_location(self.world, leg["dropoff"]["name"], leg["dropoff"].get("body"))
            if p and d:
                legs.append(dict(leg, pickup=p, dropoff=d, scu=float(leg["scu"])))
        stops = []  # each: {"loc", "actions": [str], "load": scu on board after the stop, "ledger": []}
        if legs:
            legs = hauling.split_legs(legs, cap)
            start = self.here["global"] if self.here and self.here["system"] == legs[0]["pickup"].star else None
            planned = hauling.plan_run(self.world, legs, cap, start=start) or []
            last_drop = {}
            for n, st in enumerate(planned):
                for kind, li in st["actions"]:
                    if kind == "dropoff":
                        last_drop[legs[li]["cid"]] = n
                stops.append({"loc": st["loc"], "actions": list(hauling.describe_actions(st, legs)),
                              "load": st["load_after"], "ledger": [], "completes": []})
            for c in self.contracts.items:
                if c["id"] in last_drop:
                    st = stops[last_drop[c["id"]]]
                    st["ledger"].append({"kind": ledger.INCOME, "category": "Contract payout",
                                         "amount": float(c.get("reward") or 0), "note": c["title"]})
                    st["completes"].append(c["id"])

        def pos(loc):
            try:
                return self.world.location_global(loc, when)
            except Exception:
                return None

        def km(a, b):
            pa, pb = pos(a), pos(b)
            return core.vlen(core.vsub(pa, pb)) if pa is not None and pb is not None else 1e12

        # refinery jobs ready (or ready within the hour): add a pickup where it costs the least detour
        refined = 0
        for j in (self.refine.open_jobs() if hasattr(self, "refine") else []):
            if self.refine.left(j) > 3600:
                continue
            loc = self._find_place(j.get("refinery") or "")
            if not loc:
                continue
            act = "COLLECT refined ore (refinery job)"
            same = next((x for x in stops if x["loc"] is loc), None)
            refined += 1
            if same:
                same["actions"].append(act)
                continue
            new = {"loc": loc, "actions": [act], "load": 0, "ledger": [], "completes": []}
            if not stops:
                stops.append(new)
                continue
            best, at = None, len(stops)
            here_loc = None
            for i in range(len(stops) + 1):
                a = stops[i - 1]["loc"] if i > 0 else here_loc
                b = stops[i]["loc"] if i < len(stops) else None
                extra = (km(a, loc) if a else 0) + (km(loc, b) if b else 0) - (km(a, b) if a and b else 0)
                if best is None or extra < best:
                    best, at = extra, i
            new["load"] = stops[at - 1]["load"] if at > 0 else 0
            stops.insert(at, new)
        if not stops:
            messagebox.showinfo(APP_TITLE, "Nothing to plan yet: add hauling contracts (ADD CONTRACT) or refinery "
                                           "jobs (MINE > REFINING). For a trade on its own, use ROUTES.")
            return

        # the best trade that fits on the way, with the space left over
        trade = None
        td = self.trade
        if td and td.loaded and len(stops) > 1:
            by_loc = {}
            for t in td.terminals.values():
                if t.loc is not None:
                    by_loc.setdefault(id(t.loc), []).append(t.id)
            for i in range(len(stops) - 1):
                ids = by_loc.get(id(stops[i]["loc"]))
                if not ids:
                    continue
                free = cap
                for j in range(i + 1, len(stops)):
                    free = min(free, cap - stops[j - 1]["load"])
                    if free < 1:
                        break
                    sell_ids = set(by_loc.get(id(stops[j]["loc"])) or [])
                    if not sell_ids:
                        continue
                    for r in td.routes(free, buy_at=set(ids), limit=1000, per_pair=1000):
                        if r["sell"].id in sell_ids and r["profit"] > 0 and \
                                (trade is None or r["profit"] > trade[2]["profit"]):
                            trade = (i, j, r)
        if trade:
            i, j, r = trade
            qty = r["qty"]
            stops[i]["actions"].append(f"BUY {qty:g} SCU {r['commodity']} (trade)")
            stops[i]["ledger"].append({"kind": ledger.EXPENSE, "category": "Trade purchase", "amount": r["invest"],
                                       "note": f"Bought {qty:g} SCU {r['commodity']} at {r['buy'].name}"})
            stops[j]["actions"].append(f"SELL {qty:g} SCU {r['commodity']} (trade)")
            stops[j]["ledger"].append({"kind": ledger.INCOME, "category": "Trade sale",
                                       "amount": r["invest"] + r["profit"],
                                       "note": f"Sold {qty:g} SCU {r['commodity']} at {r['sell'].name}"})
            for k in range(i, j):
                stops[k]["load"] += qty

        out, total, prev = [], 0.0, None
        for st in stops:
            leg_km = km(prev, st["loc"]) / 1 if prev is not None else None
            if leg_km and leg_km > 1e11:
                leg_km = None
            total += leg_km or 0
            o = {"name": st["loc"].name, "body": st["loc"].body, "type": st["loc"].type,
                 "actions": st["actions"], "load_after": st["load"], "leg_km": leg_km}
            if st["ledger"]:
                o["ledger"] = st["ledger"]
            if st["completes"]:
                o["completes"] = st["completes"]
            out.append(o)
            prev = st["loc"]
        bits = []
        n_con = len({l["cid"] for l in legs})
        if n_con:
            bits.append(f"{n_con} contract{'s' if n_con != 1 else ''}")
        if refined:
            bits.append(f"{refined} refinery pickup{'s' if refined != 1 else ''}")
        if trade:
            bits.append(f"trade {trade[2]['commodity']} +{ledger.short_money(trade[2]['profit'])}")
        self._run_begin("Trip: " + ", ".join(bits) + f", {len(out)} stops", out, total)
        if not trade and len(stops) > 1:
            self._hk_say("No trade fits on this trip's route with the space left over", ok=False)

    # -- live run
    def _run_path(self):
        return os.path.join(self.world.user_dir, "run.json")

    def _run_load(self):
        try:
            import json
            with open(self._run_path(), encoding="utf-8") as f:
                r = json.load(f)
            if r.get("stops") and not r.get("touched"):
                r["touched"] = os.path.getmtime(self._run_path())
            return r if r.get("stops") else None
        except Exception:
            return None

    def _run_save(self):
        import json
        try:
            if self.run:
                self.run["touched"] = time.time()
                with open(self._run_path(), "w", encoding="utf-8") as f:
                    json.dump(self.run, f, indent=1)
            elif os.path.exists(self._run_path()):
                os.remove(self._run_path())
        except OSError:
            pass

    def _run_begin(self, title, stops, total_km):
        if self.run and self.run["i"] < len(self.run["stops"]) and not messagebox.askyesno(
                APP_TITLE, "Replace the run you are on with this one?"):
            return
        self.run = {"title": title, "stops": stops, "i": 0, "arrived": False, "total_km": total_km}
        self._run_save()
        self._fill_run()
        self._run_target()
        self._show(self.tab_haul)
        self.haul_nb.select(2)

    def _run_stop(self):
        r = self.run
        if not r or r["i"] >= len(r["stops"]):
            return None
        return r["stops"][r["i"]]

    def _run_loc(self, stop):
        if not stop:
            return None
        loc = hauling.find_location(self.world, stop["name"], stop.get("body") or None)
        if loc is None and self.trade:
            loc = self.trade.extra_locations.get((stop["name"], stop.get("body")))
        return loc

    def _fill_run(self):
        if not hasattr(self, "tree_run"):
            return
        t = self.tree_run
        t.delete(*t.get_children())
        r = self.run
        if not r:
            self.lbl_run.configure(text="NO RUN.  Double-click a trade route or plan your contracts.", fg=MUTED)
            return
        n = len(r["stops"])
        if r["i"] >= n:
            head = "RUN COMPLETE.  " + r["title"]
        else:
            head = f"STOP {r['i'] + 1} OF {n}.  " + r["title"]
        if r.get("total_km"):
            head += f".  Total {core.fmt_km(r['total_km'])}"
        self.lbl_run.configure(text=head, fg=GREEN if r["i"] >= n else CYAN)
        for i, s in enumerate(r["stops"]):
            if i < r["i"]:
                state, tag = "DONE", "done"
            elif i == r["i"]:
                state, tag = ("HERE" if r.get("arrived") else "NEXT"), "now"
            else:
                state, tag = "", ""
            la = s.get("load_after")
            t.insert("", "end", iid=str(i), tags=[tag] if tag else [], values=(
                i + 1, clip_text(s["name"], 22), "   ".join(s["actions"]),
                "" if la is None else f"{la:g} SCU", state))
        if r["i"] < n:
            t.see(str(r["i"]))

    def _run_target(self):
        stop = self._run_stop()
        loc = self._run_loc(stop)
        if loc:
            self._set_target(loc)
        elif stop:
            self._hk_say(f"{stop['name']}: not on the map", ok=False)

    def _run_finish_stop(self, stop):
        """A stop is done: log its money and close finished contracts (once)."""
        if stop.get("logged"):
            return
        stop["logged"] = True
        if self.ledger_auto.get():
            for item in stop.get("ledger", []):
                if self._gl_covers(item["category"]):
                    continue  # the game log already put the exact amount in the ledger
                self._ledger_log(item["kind"], item["category"], item["amount"], item["note"])
        done = stop.get("completes", [])
        if done:
            for c in self.contracts.items:
                if c["id"] in done:
                    c["active"], c["done"] = False, True
            self.contracts.save()
            self._fill_contracts()

    def _run_step(self, delta):
        r = self.run
        if not r:
            return
        new_i = max(0, min(len(r["stops"]), r["i"] + delta))
        for k in range(r["i"], new_i):  # stops you moved past are done
            self._run_finish_stop(r["stops"][k])
        r["i"] = new_i
        r["arrived"] = False
        self._run_save()
        self._fill_run()
        stop = self._run_stop()
        if stop:
            self._run_target()
            self._hk_say(f"Next stop: {stop['name']}")
        else:
            self._clear_target()
            self._hk_say("Run complete")

    def _run_jump(self, _ev=None):
        sel = self.tree_run.selection()
        if sel and self.run:
            self._run_step(int(sel[0]) - self.run["i"])

    def _run_end(self):
        if self.run and messagebox.askyesno(APP_TITLE, "End this run?"):
            self.run = None
            self._run_save()
            self._fill_run()
            self._clear_target()
            if self.overlay:
                self.overlay.refresh()

    def _run_check(self):
        """Called on every new position: mark arrival, and move on after leaving."""
        stop = self._run_stop()
        loc = self._run_loc(stop)
        if not loc or not self.here:
            return
        if self.here["system"] != loc.star:
            return
        d = self.world.target_info(self.here, loc)["straight"]
        radius = 60.0 if loc.source == "uex" else self.ARRIVE_KM.get(loc.type, 3.0)
        r = self.run
        if d <= radius:
            if not r.get("arrived"):
                r["arrived"] = True
                self._hk_say(f"Arrived: {stop['name']}")
                self._run_save()
                self._fill_run()
        elif r.get("arrived") and d > radius * 1.5 and self.run_auto.get():
            self._run_step(1)

    # ------------------------------------------------------------ ledger
    def _build_ledger(self, parent):
        self.ledger = ledger.Ledger(self.world.user_dir)
        st = self._settings()
        top = tk.Frame(parent, bg=PANEL)
        top.pack(fill="x", pady=(0, 6))
        bal = tk.Frame(top, bg=PANEL)
        bal.pack(side="left")
        self._lbl(bal, spaced("balance"), 7, MUTED, bold=True).pack(anchor="w")
        self.lbl_balance = self._lbl(bal, "---", 18, CYAN, bold=True, mono=True)
        self.lbl_balance.pack(anchor="w")
        tot = tk.Frame(top, bg=PANEL)
        tot.pack(side="left", padx=(24, 0))
        prow = tk.Frame(tot, bg=PANEL)
        prow.pack(anchor="w")
        self.ledger_period = tk.StringVar(value=st.get("ledger_period", "Today"))
        cb = ttk.Combobox(prow, textvariable=self.ledger_period, values=ledger.PERIODS, state="readonly", width=12)
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: (self._save_setting("ledger_period", self.ledger_period.get()),
                                                    self._fill_ledger()))
        trow = tk.Frame(tot, bg=PANEL)
        trow.pack(anchor="w", pady=(4, 0))
        self.lbl_led = {}
        for key, label, col in (("income", "IN", GREEN), ("spent", "OUT", AMBER), ("net", "NET", CYAN)):
            self._lbl(trow, label, 7, MUTED, bold=True).pack(side="left", padx=(0, 4))
            v = self._lbl(trow, "0", 11, col, bold=True, mono=True)
            v.pack(side="left", padx=(0, 14))
            self.lbl_led[key] = v
        ttk.Button(top, text="SET BALANCE", command=self._ledger_set_balance).pack(side="right", anchor="n")

        add = tk.Frame(parent, bg=PANEL)
        add.pack(fill="x", pady=(0, 4))
        self.led_kind = tk.StringVar(value=ledger.EXPENSE)
        self.led_cat = tk.StringVar(value="Trade purchase")
        self.led_amount = tk.StringVar()
        self.led_note = tk.StringVar()
        cb = ttk.Combobox(add, textvariable=self.led_kind, values=[ledger.EXPENSE, ledger.INCOME],
                          state="readonly", width=8)
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: self._ledger_kind_changed())
        self.led_cat_cb = ttk.Combobox(add, textvariable=self.led_cat, width=17, values=ledger.EXPENSE_CATEGORIES)
        self.led_cat_cb.pack(side="left", padx=(4, 0))
        self._lbl(add, "aUEC", 7, MUTED, bold=True).pack(side="left", padx=(8, 4))
        e1 = ttk.Entry(add, textvariable=self.led_amount, width=10)
        e1.pack(side="left")
        self._lbl(add, "NOTE", 7, MUTED, bold=True).pack(side="left", padx=(8, 4))
        e2 = ttk.Entry(add, textvariable=self.led_note, width=18)
        e2.pack(side="left", fill="x", expand=True)
        for e in (e1, e2):
            e.bind("<Return>", lambda ev: self._ledger_add())
        ttk.Button(add, text="ADD", style="Accent.TButton", command=self._ledger_add).pack(side="right", padx=(6, 0))
        self.lbl_led_msg = self._lbl(parent, "", 8, MUTED, wraplength=640)
        self.lbl_led_msg.pack(anchor="w", pady=(0, 4))

        self.tree_led = self._tree(parent, [("when", "WHEN", 92), ("cat", "CATEGORY", 122), ("amt", "AMOUNT", 84),
                                            ("bal", "BALANCE", 84), ("note", "NOTE", 150), ("where", "WHERE", 90)])
        self.tree_led.tag_configure("inc", foreground=GREEN)
        self.tree_led.tag_configure("exp", foreground=AMBER)
        self.tree_led.tag_configure("adj", foreground=CYAN_DIM)
        self.tree_led.tag_configure("est", foreground=MUTED)
        self.tree_led.bind("<Double-1>", lambda e: self._ledger_edit())
        bot = tk.Frame(parent, bg=PANEL)
        bot.pack(fill="x", pady=(6, 0))
        ttk.Button(bot, text="EDIT", command=self._ledger_edit).pack(side="left")
        ttk.Button(bot, text="DELETE", command=self._ledger_delete).pack(side="left", padx=6)
        ttk.Button(bot, text="EXPORT FOR EXCEL", command=self._ledger_export).pack(side="left")
        ttk.Button(bot, text="SESSIONS", command=self._sessions_window).pack(side="left", padx=6)
        self.ledger_auto = tk.BooleanVar(value=st.get("ledger_auto", True))
        ttk.Checkbutton(bot, text="LOG HAULING RUNS AUTOMATICALLY", variable=self.ledger_auto,
                        style="Panel.TCheckbutton",
                        command=lambda: self._save_setting("ledger_auto", self.ledger_auto.get())
                        ).pack(side="right")
        self.lbl_led_cats = self._lbl(parent, "", 8, MUTED, wraplength=640)
        self.lbl_led_cats.pack(anchor="w", pady=(6, 0))
        self._fill_ledger()

    def _where_text(self):
        h = self.here
        if not h:
            return ""
        if h.get("body") and h.get("nearby"):
            n = h["nearby"][0]
            if n["surface"] < 30 and h.get("alt", 99) < 30:
                return n["loc"].name
        if h.get("body"):
            return h["body"].name
        sp = h.get("space")
        if sp and sp[0][0] < 100:
            return sp[0][1]
        return h.get("zone") or h.get("system", "")

    def _ledger_kind_changed(self):
        cats = ledger.INCOME_CATEGORIES if self.led_kind.get() == ledger.INCOME else ledger.EXPENSE_CATEGORIES
        self.led_cat_cb.configure(values=cats)
        if self.led_cat.get() not in cats:
            self.led_cat.set(cats[0])

    def _ledger_add(self):
        amt = ledger.parse_amount(self.led_amount.get())
        if amt is None or amt == 0:
            self.lbl_led_msg.configure(text="Type an amount, for example 12500, 12.5k or 1.2m.", fg=AMBER)
            return
        kind = self.led_kind.get()
        if amt < 0:  # a minus sign means spending, whatever the type box says
            kind, amt = ledger.EXPENSE, -amt
            self.led_kind.set(kind)
        cat = self.led_cat.get().strip() or ("Other income" if kind == ledger.INCOME else "Other expense")
        e = self.ledger.add(kind, cat, amt, note=self.led_note.get().strip(), where=self._where_text())
        self.led_amount.set("")
        self.led_note.set("")
        self.lbl_led_msg.configure(fg=GREEN if kind == ledger.INCOME else AMBER,
                                   text=f"Added {ledger.money(e['amount'], True)} aUEC, {cat}.")
        self._fill_ledger()

    def _ledger_log(self, kind, category, amount, note, estimate=True, source="run", where=None, when=None):
        """Entry made by the app (hauling runs, the game log); shown with ≈ until you edit it."""
        if not amount:
            return None
        e = self.ledger.add(kind, category, amount, note=note, where=self._where_text() if where is None else where,
                            estimate=estimate, source=source, when=when)
        self._fill_ledger()
        self._hk_say(f"Ledger {ledger.short_money(e['amount'])}: {category}", ok=kind == ledger.INCOME)
        return e

    def _fill_ledger(self):
        if not hasattr(self, "tree_led"):
            return
        L = self.ledger
        bal = L.balance()
        if L.has_balance():
            self.lbl_balance.configure(text=ledger.money(bal), fg=CYAN if bal >= 0 else RED)
        else:
            self.lbl_balance.configure(text=ledger.money(bal) + "*" if L.entries else "NOT SET", fg=MUTED)
        period = self.ledger_period.get()
        tot = L.totals(period)
        self.lbl_led["income"].configure(text=ledger.short_money(tot["income"]))
        self.lbl_led["spent"].configure(text=ledger.short_money(tot["spent"]))
        self.lbl_led["net"].configure(text=("+" if tot["net"] >= 0 else "") + ledger.short_money(tot["net"]),
                                      fg=GREEN if tot["net"] >= 0 else RED)
        t = self.tree_led
        t.delete(*t.get_children())
        start = L.period_start(period)
        rows = [(e, b) for e, b in L.running() if e["time"] >= start]
        for i, (e, b) in enumerate(reversed(rows)):
            tag = {"Income": "inc", "Expense": "exp"}.get(e["kind"], "adj")
            tags = [tag] + (["odd"] if i % 2 else [])
            if e.get("estimate"):
                tags.append("est")
            when = clock_str(core.dt.datetime.fromtimestamp(e["time"]), "%b %d %H:%M")
            amt = ("≈ " if e.get("estimate") else "") + ledger.money(e["amount"], True)
            t.insert("", "end", iid=str(e["id"]), tags=tags,
                     values=(when, e["category"], amt, ledger.money(b), e.get("note", ""), e.get("where", "")))
        cats = L.by_category(period)
        earn = sorted(((v, c) for (k, c), v in cats.items() if k == ledger.INCOME), reverse=True)[:3]
        spend = sorted(((-v, c) for (k, c), v in cats.items() if k == ledger.EXPENSE), reverse=True)[:3]
        parts = []
        if earn:
            parts.append("Most earned: " + ", ".join(f"{c} {ledger.short_money(v)}" for v, c in earn) + ".")
        if spend:
            parts.append("Most spent: " + ", ".join(f"{c} {ledger.short_money(v)}" for v, c in spend) + ".")
        n_est = sum(1 for e, _ in rows if e.get("estimate"))
        if n_est:
            parts.append(f"{n_est} entries marked ≈ were filled in from a run; double-click to fix the amount.")
        if not L.has_balance():
            parts.append("Click SET BALANCE and type what your wallet shows, so the balance matches the game.")
        if not L.entries:
            parts = ["Log every purchase and payout here: pick Expense or Income, a category, the amount, and press "
                     "Enter. Hauling runs add their buys, sales and contract rewards for you."] + parts[-1:]
        self.lbl_led_cats.configure(text="  ".join(parts))

    def _ledger_selected(self):
        sel = self.tree_led.selection()
        return self.ledger.get(int(sel[0])) if sel else None

    def _ledger_edit(self):
        e = self._ledger_selected()
        if not e:
            return
        dlg = LedgerDialog(self.root, self, e)
        if dlg.result:
            self.ledger.update(e["id"], **dlg.result)
            self._fill_ledger()
            if e.get("ref") and hasattr(self, "mydata"):
                # you corrected a contract payout: remember what this contract really pays
                self.mydata.learn_reward(e["ref"], e.get("ref_title", ""), abs(float(e["amount"])))

    def _ledger_delete(self):
        e = self._ledger_selected()
        if e and messagebox.askyesno(APP_TITLE, f"Delete this entry ({ledger.money(e['amount'], True)} aUEC, "
                                                f"{e['category']})?"):
            self.ledger.delete(e["id"])
            self._fill_ledger()

    def _ledger_set_balance(self):
        cur = self.ledger.balance()
        txt = simpledialog.askstring(APP_TITLE, "What does your in-game wallet show right now? (aUEC)",
                                     initialvalue=f"{cur:.0f}" if self.ledger.has_balance() else "",
                                     parent=self.root)
        if txt is None:
            return
        amt = ledger.parse_amount(txt)
        if amt is None:
            messagebox.showwarning(APP_TITLE, "That is not a number.")
            return
        e = self.ledger.set_balance(amt, where=self._where_text())
        if e is None:
            self.lbl_led_msg.configure(text="Your ledger already matches your wallet.", fg=GREEN)
        else:
            self.lbl_led_msg.configure(fg=CYAN, text=(
                f"Balance set to {ledger.money(amt)} aUEC." if e["category"] == "Starting balance" else
                f"Balance corrected by {ledger.money(e['amount'], True)} aUEC (something was not logged)."))
        self._fill_ledger()

    def _ledger_export(self):
        path = filedialog.asksaveasfilename(parent=self.root, defaultextension=".csv",
                                            initialfile="sc_ledger.csv", filetypes=[("CSV", "*.csv")])
        if path:
            self.ledger.export_csv(path)
            self.lbl_led_msg.configure(text=f"Exported {len(self.ledger.entries)} entries.", fg=GREEN)

    # ------------------------------------------------------------ home
    def _build_home(self, parent):
        srow = tk.Frame(parent, bg=PANEL)
        srow.pack(fill="x", pady=(0, 4))
        self._lbl(srow, "SEARCH", 7, MUTED, bold=True).pack(side="left", padx=(0, 6))
        self.home_q = tk.StringVar()
        e = ttk.Entry(srow, textvariable=self.home_q)
        e.pack(side="left", fill="x", expand=True)
        e.bind("<KeyRelease>", self._home_search_key)
        e.bind("<Return>", lambda ev: self._home_open())
        self.home_hint = self._lbl(srow, "places, planets, ships, items, cargo, ores", 8, MUTED)
        self.home_hint.pack(side="left", padx=(8, 0))

        self.home_mid = tk.Frame(parent, bg=PANEL)
        self.home_mid.pack(fill="x")
        self.home_cards = tk.Frame(self.home_mid, bg=PANEL)
        self.home_cards.pack(fill="x")
        for c in range(3):
            self.home_cards.columnconfigure(c, weight=1, uniform="c")
        go = self._home_go
        now = RoundBox(self.home_cards, accent=ORANGE, pad=(8, 4))
        now.grid(row=0, column=0, columnspan=3, sticky="nsew", pady=(0, 3))
        ni = now.inner
        tk.Label(ni, text="RIGHT NOW", bg=CARD, fg="#ffffff", font=(self.F_UI, 11, "bold")).pack(side="left",
                                                                                               anchor="n")
        self.lbl_now = tk.Label(ni, text="", bg=CARD, fg=FG, font=(self.F_UI, 8), anchor="w", justify="left",
                                wraplength=int(620 * self.scale))
        self.lbl_now.pack(side="left", fill="x", expand=True, padx=(10, 0))
        self.lbl_now.bind("<Configure>", lambda e: self.lbl_now.configure(wraplength=max(120, e.width - 6)))
        self._now_cache = {}
        cards = [  # same order as the tabs
            ("NAVIGATE", "Find a place and fly there: nearby spots, maps, caves",
             [("NEARBY", lambda: go("near")), ("MAP", lambda: go("map")), ("CAVES", self._home_caves)]),
            ("MINE", "Identify rocks, find ores, get into belts, refine",
             [("SCAN", lambda: go("scan")), ("FINDER", lambda: go("finder")), ("BELTS", lambda: go("belts")),
              ("REFINING", lambda: go("refining"))]),
            ("SALVAGE", "Where the wrecks are, and where to sell salvage for the most",
             [("SPOTS", lambda: go("salvage", 0)), ("SELL", lambda: go("salvage", 1))]),
            ("HAUL", "Trade routes, contracts, runs", [("ROUTES", lambda: go("haul", 0)),
                                                       ("CONTRACTS", lambda: go("haul", 1)),
                                                       ("RUN", lambda: go("haul", 2))]),
            ("COMBAT", "Bounty contracts, payouts, and where security and outlaws are",
             [("BOUNTIES", lambda: go("combat", 0)), ("ZONES", lambda: go("combat", 1))]),
            ("MISSIONS", "Contracts, the blueprints they give, and this season's events",
             [("MISSIONS", lambda: go("missions")), ("CRAFT", lambda: go("craft")),
              ("EVENTS", lambda: go("events"))]),
            ("SHOP", "Where to buy anything, rent ships, refuel and refine",
             [("SHOP", lambda: go("shop")), ("FUEL", lambda: self._shop_category(shop.FUEL)),
              ("YIELDS", lambda: self._shop_category(shop.REFINING))]),
            ("HANGAR", "Your ships, and a builder to plan their loadouts",
             [("MY SHIPS", lambda: go("hangar")), ("BUILDER", lambda: go("builder")),
              ("FIND MY SHIP", self._ship_find)]),
            ("MONEY", "Your balance and every payout", [("LEDGER", lambda: go("ledger"))]),
        ]
        self.home_status = {}
        accents = {"NAVIGATE": CYAN, "MINE": ORANGE, "HAUL": GREEN, "MISSIONS": PURPLE, "SHOP": AMBER,
                   "MONEY": GREEN, "HANGAR": CYAN, "COMBAT": RED, "SALVAGE": TEAL}
        for i, (title, desc, btns) in enumerate(cards):
            card = RoundBox(self.home_cards, accent=accents.get(title, CYAN), pad=(8, 4))
            col = i % 3
            card.grid(row=i // 3 + 1, column=col, sticky="nsew", padx=(0 if col == 0 else 3, 0 if col == 2 else 3),
                      pady=3)
            inner = card.inner
            head = tk.Frame(inner, bg=CARD)
            head.pack(fill="x")
            t = tk.Label(head, text=title, bg=CARD, fg="#ffffff", font=(self.F_UI, 11, "bold"))
            t.pack(side="left")
            self._tip(t, desc)
            acc = accents.get(title, CYAN)
            card.bind("<Enter>", lambda e, c=card, a=acc: c.set_border(a))
            card.bind("<Leave>", lambda e, c=card: c.set_border(LINE))
            st = tk.Label(inner, text="", bg=CARD, fg=FG, font=(self.F_UI, 8), anchor="nw", justify="left",
                          wraplength=int(225 * self.scale), height=2)
            st.pack(fill="x", pady=(0, 2))
            self.home_status[title] = st
            br = tk.Frame(inner, bg=CARD)
            br.pack(fill="x")
            for label, cmd in btns:
                ttk.Button(br, text=label, command=cmd, width=-4, style="Small.TButton").pack(side="left",
                                                                                           padx=(0, 3))
        # latest from the game: the last things the game log saw, so HOME feels alive while you play
        feed = RoundBox(self.home_cards, accent=GREEN, pad=(8, 5))
        feed.grid(row=4, column=0, columnspan=3, sticky="nsew", pady=(3, 0))
        fi = feed.inner
        fh = tk.Frame(fi, bg=CARD)
        fh.pack(fill="x")
        tk.Label(fh, text="LATEST FROM THE GAME", bg=CARD, fg="#ffffff", font=(self.F_UI, 11, "bold")).pack(side="left")
        ttk.Button(fh, text="OPEN LIVE", style="Small.TButton", width=-4,
                   command=lambda: self._home_go("live")).pack(side="right")
        self.home_feed = []
        for _i in range(5):
            r = tk.Frame(fi, bg=CARD)
            r.pack(fill="x")
            a = tk.Label(r, text="", bg=CARD, fg=MUTED, font=(self.F_MONO, 9), width=6, anchor="w")
            a.pack(side="left")
            b = tk.Label(r, text="", bg=CARD, fg=CYAN, font=(self.F_UI, 9, "bold"), width=12, anchor="w")
            b.pack(side="left")
            c = tk.Label(r, text="", bg=CARD, fg=FG, font=(self.F_UI, 9), anchor="w")
            c.pack(side="left", fill="x", expand=True)
            self.home_feed.append((a, b, c))
        self.home_results = tk.Frame(self.home_mid, bg=PANEL)
        self.tree_search = self._tree(self.home_results, [("kind", "WHAT", 90), ("name", "NAME", 250),
                                                          ("detail", "DETAILS", 270)])
        self.tree_search.configure(height=12)
        self.tree_search.bind("<Double-1>", lambda ev: self._home_open())
        self.tree_search.bind("<Return>", lambda ev: self._home_open())
        self._lbl(self.home_results, "Double-click a result. Places become your target; planets open in NEARBY; "
                                     "cargo opens trade routes; ores open the finder; items and ships show where to "
                                     "buy them. Press Esc to go back.", 8, MUTED, wraplength=640
                  ).pack(anchor="w", pady=(4, 0))
        e.bind("<Escape>", lambda ev: (self.home_q.set(""), self._home_search_key()))
        self._search_index = None
        self._search_map = {}

        self._lbl(parent, "Type in SEARCH to find anything: a place to fly to, a planet, a ship, cargo or an ore. "
                          "Or pick what you want to do above.", 8, MUTED, wraplength=640).pack(anchor="w", pady=(8, 0))
        self.root.after_idle(self._refresh_home)
        self.root.after(1500, self._home_tick)

    def _build_hangar(self, parent):
        hh = tk.Frame(parent, bg=PANEL)
        hh.pack(fill="x", pady=(0, 4))
        self._lbl(hh, spaced("my hangar"), 9, CYAN, bold=True).pack(side="left")
        self.lbl_active_ship = self._lbl(hh, "", 9, GREEN, bold=True)
        self.lbl_active_ship.pack(side="left", padx=(12, 0))
        hb = tk.Frame(parent, bg=PANEL)
        hb.pack(fill="x", pady=(0, 4))
        ttk.Button(hb, text="ADD SHIP", style="Accent.TButton", command=self._ship_add).pack(side="left")
        ttk.Button(hb, text="EDIT", command=self._ship_edit).pack(side="left", padx=4)
        ttk.Button(hb, text="REMOVE", command=self._ship_remove).pack(side="left")
        ttk.Button(hb, text="FLYING THIS", command=self._ship_activate).pack(side="left", padx=(12, 4))
        ttk.Button(hb, text="PARKED HERE", command=self._ship_parked_here).pack(side="left")
        ttk.Button(hb, text="FIND MY SHIP", command=self._ship_find).pack(side="left", padx=4)
        b = ttk.Button(hb, text="LOADOUT", command=self._sb_open_from_hangar)
        b.pack(side="left")
        self._tip(b, "Open the selected ship in SHIP BUILDER with its loadout.")
        self.tree_hangar = self._tree(parent, [("ship", "SHIP", 160), ("setup", "SETUP", 150), ("role", "ROLE", 130),
                                               ("scu", "SCU", 50), ("crew", "CREW", 45), ("parked", "PARKED AT", 120),
                                               ("build", "LOADOUT", 110)])
        self.tree_hangar.tag_configure("now", foreground=GREEN)
        self.tree_hangar.bind("<Double-1>", lambda ev: self._ship_activate())
        self.lbl_hangar = self._lbl(parent, "", 8, MUTED, wraplength=640)
        self.lbl_hangar.pack(anchor="w", pady=(4, 0))
        self._fill_hangar()

    def _show(self, frame):
        """Bring a tab to the front, opening its activity group first."""
        parent = frame.master
        if parent is not self.nb:
            self.nb.select(parent)
            parent.select(frame)
        else:
            self.nb.select(frame)

    def _home_go(self, where, sub=None):
        tabs = {"near": self.tab_near, "map": self.tab_map, "space": self.tab_space, "scan": self.tab_scan,
                "ores": self.tab_ores, "finder": self.tab_finder, "log": self.tab_log, "haul": self.tab_haul,
                "starmap": self.tab_starmap, "ledger": self.tab_ledger, "data": self.tab_data,
                "hangar": self.tab_hangar, "shop": self.tab_shop, "salvage": self.tab_salvage,
                "refining": self.tab_refining, "combat": self.tab_combat, "live": self.tab_live,
                "loadout": self.tab_loadout, "missions": self.tab_missions, "settings": self.tab_settings,
                "craft": self.tab_craft, "builder": self.tab_builder, "events": self.tab_events,
                "belts": self.tab_belts}
        self._show(tabs[where])
        if where == "haul" and sub is not None:
            self.haul_nb.select(sub)
        if where == "combat" and sub is not None:
            self.nb_combat.select(sub)
            if sub == 1:
                self._fill_zones()
        if where == "salvage" and sub is not None:
            self.nb_salv.select(sub)
            if sub == 0:  # SPOTS
                self._fill_salv_spots()

    def _home_caves(self):
        self.near_body.set("Where I am")
        self._fill_types()
        if "Cave" in self.type_cb.cget("values"):
            self.filter_type.set("Cave")
        self._fill_nearby()
        self._home_go("near")

    def _home_tick(self):
        try:
            self._refresh_compact()
            self._refine_tick()
            self._refresh_home()
        except Exception as e:  # never let a status line break the app
            hotkeys_win.log(f"home refresh: {e}")
        self.root.after(2000, self._home_tick)

    def _home_now(self):
        """Up to three things worth doing right now, from what Starboard knows."""
        lines = []
        S = getattr(self, "gl_session", {})
        place = self._where_text() if self.here else ""
        if S.get("joined") and S.get("place"):
            place = S["place"]
        ready = [j for j in self.refine.open_jobs() if self.refine.left(j) <= 0] if hasattr(self, "refine") else []
        if ready:
            lines.append(f"{len(ready)} refinery job{'s' if len(ready) != 1 else ''} ready at "
                         f"{ready[0].get('refinery', 'the refinery')}.")
        c = self._now_cache
        if time.time() - c.get("t", 0) > 60:
            c.clear()
            c["t"] = time.time()
            td = self.trade
            try:
                if td and td.loaded and self.here and self._haul_scu() > 0:
                    local = {t.id for t in td.terminals_here(self.here)}
                    if local:
                        r = td.routes(self._haul_scu(), budget=self._haul_budget(), system=self.here["system"],
                                      here=self.here, buy_at=local, limit=1)
                        if r:
                            r = r[0]
                            c["trade"] = (f"Best trade from here: {r['commodity']} to {r['sell'].name}, about "
                                          f"{ledger.short_money(r['profit'])} profit for your "
                                          f"{self._haul_scu():g} SCU.")
            except Exception as e:
                hotkeys_win.log(f"right now trade: {e}")
            system = (self.here or {}).get("system") or self.last_system
            ms = [m for m in getattr(self, "mi_rows", []) if system in m["systems"] and not m["illegal"]
                  and (m.get("reward_max") or m.get("reward_min"))]
            if ms:
                top = max(ms, key=lambda m: m.get("reward_max") or m.get("reward_min") or 0)
                c["mission"] = (f"{len(ms)} legal paid missions in {system}; best listed: {top['title']} "
                                f"({self._mi_reward(top)}).")
        if c.get("trade"):
            lines.append(c["trade"])
        active = [x for x in getattr(self, "gl_contracts", {}).values() if x.get("state") in ("Accepted", "Shared")]
        if active:
            lines.append(f"{len(active)} contract{'s' if len(active) != 1 else ''} in progress: {active[0]['title']}.")
        elif c.get("mission"):
            lines.append(c["mission"])
        if not lines:
            if place:
                lines.append(f"You are at {place}. Pick a card below to plan what to do.")
            else:
                lines.append("Start Star Citizen and press F9 in game: Starboard then suggests trades, missions and "
                             "more for where you are.")
        if S.get("armistice"):
            lines.insert(0, "In an armistice zone.")
        return "\n".join(lines[:3])

    def _refresh_home_feed(self):
        rows = getattr(self, "home_feed", None)
        if not rows:
            return
        feed = [f for f in getattr(self, "gl_feed", []) if f[1] not in ("GAME",)][-len(rows):][::-1]
        if not feed:
            rows[0][0].configure(text="")
            rows[0][1].configure(text="")
            rows[0][2].configure(text="Nothing yet. Start Star Citizen: trades, contracts, purchases and where you "
                                      "are show up here as you play.", fg=MUTED)
            for a, b, c in rows[1:]:
                for w in (a, b, c):
                    w.configure(text="")
            return
        for i, (a, b, c) in enumerate(rows):
            if i < len(feed):
                ts, what, detail, tag = feed[i]
                a.configure(text=clock_str(time.localtime(ts), "%H:%M"))
                b.configure(text=str(what)[:12], fg={"hi": GREEN, "warn": AMBER, "bad": RED}.get(tag, CYAN))
                c.configure(text=clip_text(str(detail), 110), fg=FG)
            else:
                for w in (a, b, c):
                    w.configure(text="")

    def _refresh_home(self):
        self._refresh_home_feed()
        st, h = self.home_status, self.here
        if hasattr(self, "lbl_now"):
            try:
                self.lbl_now.configure(text=self._home_now())
            except Exception as e:
                hotkeys_win.log(f"right now: {e}")
        # navigate
        if self.target and h:
            info = self.world.target_info(h, self.target)
            d = info.get("surface") if info.get("same_body") else info.get("straight")
            nav = f"Target: {self.target.name}, {core.fmt_km(d) if d is not None else '?'} away."
        elif h:
            nav = f"You are near {self._where_text() or h.get('system', '')}. Pick a place to fly to."
        else:
            nav = "Press F9 in game (or type /showlocation) to get your position."
        st["NAVIGATE"].configure(text=nav)
        # mine
        scan = self.last_scan if self.last_scan and self._scan_age() < 600 else None
        if scan:
            res = scan.get("results") or []
            what = res[0].get("label") or res[0].get("name") if res else "no match"
            st["MINE"].configure(text=f"Last scan {scan.get('value', '')}: {what}.")
        elif self.refine.open_jobs():
            R = self.refine
            nxt = min(R.open_jobs(), key=R.ready_at)
            left = R.left(nxt)
            ready = sum(1 for j in R.open_jobs() if R.left(j) <= 0)
            st["MINE"].configure(text=f"{ready} refinery job{'s' if ready != 1 else ''} ready to collect." if ready
                                 else f"Refinery: next job ready in {refining.fmt_duration(left)} at "
                                      f"{nxt.get('refinery', '')}.")
        elif h and h.get("body"):
            st["MINE"].configure(text=f"Press F8 when you scan a signature on {h['body'].name}.")
        else:
            st["MINE"].configure(text="Press F8 when you scan a signature to see what it is.")
        # haul
        r = self.run
        if r and r["i"] < len(r["stops"]):
            s = r["stops"][r["i"]]
            st["HAUL"].configure(text=f"Run: stop {r['i'] + 1} of {len(r['stops'])}, {s['name']}.")
        else:
            n = len([c for c in self.contracts.items if c.get("active", True)])
            scu = self._haul_scu()
            st["HAUL"].configure(text=(f"{n} active contract{'s' if n != 1 else ''}. " if n else "") +
                                 (f"Hold: {scu:g} SCU." if scu else "Pick the ship you are flying below."))
        # missions: what is on this season
        try:
            import datetime as _dt
            today = _dt.date.today()
            ev = [e for e in events.in_window(events.load(core.DATA_DIR)) if e["end"] >= today]
            cur = next((e for e in ev if e["start"] <= today), None)
            nxt = next((e for e in ev if e["start"] > today), None)
            if cur:
                st["MISSIONS"].configure(text=f"On now: {cur['name']}, until {cur['end'].strftime('%b %d')}.")
            elif nxt:
                st["MISSIONS"].configure(text=f"Next event: {nxt['name']}, {events.when(nxt).title()}"
                                              + ("" if nxt.get("status") == "confirmed" else " (expected)") + ".")
            else:
                st["MISSIONS"].configure(text="Find contracts and the blueprints they give.")
        except Exception:  # noqa: BLE001
            st["MISSIONS"].configure(text="Find contracts and the blueprints they give.")
        # money
        L = self.ledger
        tot = L.totals("Today")
        bal = ledger.money(L.balance()) + " aUEC" if L.has_balance() else "not set yet"
        st["MONEY"].configure(text=f"Balance {bal}. Today {'+' if tot['net'] >= 0 else ''}"
                                   f"{ledger.short_money(tot['net'])}.")
        # shop
        sd = self.shopdata if self.shopdata and self.shopdata.loaded else None
        st["SHOP"].configure(text=f"{len(sd.products):,} items, ships and services with prices." if sd else
                             "Prices load with the trade data from UEX.")
        # combat
        bs = self.bounties.stats(ledger.Ledger.period_start("Today"))
        if h and h["system"] in combat.LAWLESS_SYSTEMS:
            ctext = f"{h['system']} is lawless: anyone can attack you."
        else:
            ctext = ""
        st["COMBAT"].configure(text=(f"{bs['active']} active bounties. Today {bs['done']} done, "
                                     f"{ledger.short_money(bs['earned'])} aUEC. " if bs["active"] or bs["done"]
                                     else "Track bounty contracts and find security or outlaw places. ") + ctext)
        # salvage
        best = None
        if self.trade and self.trade.loaded:
            for p in self.trade.prices:
                if p.get("commodity_name") == "Recycled Material Composite":
                    t = self.trade.terminals.get(p.get("id_terminal"))
                    v = hauling._num(p.get("price_sell"))
                    if t and t.system == self.last_system and v > 0 and (best is None or v > best[1]):
                        best = (t, v)
        st["SALVAGE"].configure(text=f"RMC sells best at {best[0].name}: {best[1]:,.0f}/SCU." if best else
                                "Sell prices load with the trade data from UEX.")
        # hangar
        a = self.hangar.active_ship()
        if a:
            scu = self._ship_scu(a)
            park = (a.get("parked") or {}).get("name")
            st["HANGAR"].configure(text=f"Flying {self.hangar.label(a)}" + (f", {scu:g} SCU" if scu else "") + "."
                                   + (f" Parked at {park}." if park else ""))
        else:
            st["HANGAR"].configure(text="Add the ships you own, once. Hauling and the rest use them.")

    # -- search
    def _build_search_index(self):
        idx = []
        for b in self.world.bodies.values():
            idx.append(("Planet" if b.type == "Planet" else b.type or "Body", b.name, f"{b.star}", ("body", b.name)))
        for l in self.world.locations:
            idx.append(("Place", l.name, f"{l.type} on {l.body}", ("loc", l)))
        for m in self.world.materials():
            idx.append(("Ore", m, "where to mine it", ("ore", m)))
        if self.trade and self.trade.loaded:
            for c in self.trade.commodities():
                idx.append(("Cargo", c, "trade routes", ("comm", c)))
            sd = self._shop_ready()
            if sd:
                for (kind, name), p in sd.products.items():
                    if kind == "item":
                        idx.append(("Item", name, f"{p.category}, {len(p.offers)} shops", ("shop", (kind, name))))
                    elif kind == "fuel":
                        idx.append(("Fuel", name, f"{len(p.offers)} stations", ("shop", (kind, name))))
            for sname in self.trade.all_ships():
                info = self.trade.ship_info(sname) or {}
                idx.append(("Ship", sname, ", ".join(info.get("roles", [])[:3]) or info.get("maker", ""),
                            ("ship", sname)))
        for b in (getattr(self, "bp_rows", None) or []):
            idx.append(("Blueprint", b["name"], b["type"], ("bp", b["uuid"])))
        self._search_index = idx

    def _home_search_key(self, ev=None):
        if ev is not None and ev.keysym in ("Return", "Up", "Down"):
            if ev.keysym == "Down" and self.tree_search.get_children():
                self.tree_search.focus_set()
                first = self.tree_search.get_children()[0]
                self.tree_search.selection_set(first)
                self.tree_search.focus(first)
            return
        q = self.home_q.get().strip().lower()
        if not q:
            self.home_results.pack_forget()
            self.home_cards.pack(fill="x")
            self.home_hint.configure(text="places, planets, ships, items, cargo, ores")
            return
        if self._search_index is None:
            self._build_search_index()
        words = q.split()
        hits = []
        for kind, name, detail, act in self._search_index:
            n = name.lower()
            if all(w in n or w in detail.lower() for w in words):
                score = (0 if n.startswith(q) else 1 if q in n else 2, len(name))
                hits.append((score, kind, name, detail, act))
        hits.sort(key=lambda x: x[0])
        t = self.tree_search
        t.delete(*t.get_children())
        self._search_map = {}
        for i, (_, kind, name, detail, act) in enumerate(hits[:80]):
            iid = t.insert("", "end", tags=["odd"] if i % 2 else [], values=(kind, name, detail))
            self._search_map[iid] = act
        self.home_cards.pack_forget()
        self.home_results.pack(fill="x")
        self.home_hint.configure(text=f"{len(hits)} found" + (", showing 80" if len(hits) > 80 else ""))

    def _home_open(self):
        sel = self.tree_search.selection()
        if not sel:
            kids = self.tree_search.get_children()
            sel = kids[:1]
        act = self._search_map.get(sel[0]) if sel else None
        if not act:
            return
        kind, val = act
        if kind == "loc":
            self._set_target(val)
            self._hk_say(f"Target: {val.name}")
        elif kind == "body":
            self.near_body.set(val)
            self._fill_types()
            self.filter_type.set("All types")
            self._fill_nearby()
            self._home_go("near")
        elif kind == "ore":
            self.ore_material.set(val)
            self._fill_finder()
            self._home_go("finder")
        elif kind == "comm":
            self.route_comm.set(val)
            self.route_near.set("Anywhere")
            self._fill_routes()
            self._home_go("haul", 0)
        elif kind == "shop":
            self._shop_show(*val)
        elif kind == "bp":
            self._craft_open(("bp", val))
        elif kind == "ship":
            if not (self._shop_show("buy", val) or self._shop_show("rent", val)):
                self._ship_add(preset=val)

    # -- hangar
    def _ship_scu(self, s):
        if not self.trade:
            return None
        if s.get("setup"):
            v = self._ship_default_scu(s["setup"])
            if v is not None:
                return v
        info = self.trade.ship_info(s["ship"])
        return info["scu"] if info else None

    def _fill_hangar(self):
        t = self.tree_hangar
        t.delete(*t.get_children())
        H = self.hangar
        for i, s in enumerate(H.ships):
            info = self.trade.ship_info(s["ship"]) if self.trade else None
            now = s["id"] == H.active
            scu = self._ship_scu(s)
            setup = s.get("setup") or ""
            if setup.startswith(s["ship"]):
                setup = setup[len(s["ship"]):].strip(" +()") or "Standard"
            parked = s.get("parked") or {}
            tags = (["now"] if now else []) + (["odd"] if i % 2 else [])
            t.insert("", "end", iid=s["id"], tags=tags, values=(
                ("★ " if now else "") + H.label(s), setup or "Standard",
                ", ".join((info or {}).get("roles", [])[:3]) or ("?" if not info else ""),
                "" if scu is None else f"{scu:g}", (info or {}).get("crew", ""),
                parked.get("name", ""), (s.get("build") or {}).get("name", "Stock")))
        a = H.active_ship()
        self.lbl_active_ship.configure(text=f"FLYING: {H.label(a)}" if a else "")
        if not H.ships:
            self.lbl_hangar.configure(text="Add the ships you own. The one you mark FLYING THIS sets your cargo hold "
                                           "for hauling, and PARKED HERE remembers where you left each ship.")
        else:
            self.lbl_hangar.configure(text="Double-click a ship to fly it. PARKED HERE saves where you left the "
                                           "selected ship (press F9 first); FIND MY SHIP points you back to it.")

    def _ship_selected(self):
        sel = self.tree_hangar.selection()
        return self.hangar.get(sel[0]) if sel else self.hangar.active_ship()

    def _need_ships(self):
        if self.trade and self.trade.loaded and self.trade.all_ships():
            return True
        messagebox.showinfo(APP_TITLE, "The ship list comes from UEX. Downloading it now; try again in a few "
                                       "seconds.")
        self._haul_download()
        return False

    def _ship_add(self, preset=None, existing=None):
        if not self._need_ships():
            return
        dlg = ShipDialog(self.root, self, preset=preset, existing=existing)
        if not dlg.result:
            return
        if existing:
            self.hangar.update(existing["id"], **dlg.result)
        else:
            e = self.hangar.add(**dlg.result)
            if len(self.hangar.ships) == 1:
                self._ship_apply(e)
        if existing and existing["id"] == self.hangar.active:
            self._ship_apply(existing)
        self._fill_hangar()

    def _ship_edit(self):
        s = self._ship_selected()
        if s:
            self._ship_add(existing=s)

    def _ship_remove(self):
        s = self._ship_selected()
        if s and messagebox.askyesno(APP_TITLE, f"Remove {self.hangar.label(s)} from your hangar?"):
            self.hangar.remove(s["id"])
            self._fill_hangar()

    def _ship_apply(self, s):
        """Make this the ship you are flying: hauling uses its hold."""
        label = s.get("setup") or s["ship"]
        self.haul_ship.set(label)
        scu = self._ship_scu(s)
        self._picking = True
        self.haul_scu.set("" if scu is None else f"{scu:g}")
        self._haul_save()
        self._fill_routes()

    def _ship_activate(self):
        s = self._ship_selected()
        if not s:
            return
        self.hangar.set_active(s["id"])
        self._ship_apply(s)
        self._fill_hangar()
        self._hk_say(f"Flying: {self.hangar.label(s)}")

    def _ship_parked_here(self):
        s = self._ship_selected()
        if not s:
            return
        if not self.here:
            messagebox.showinfo(APP_TITLE, "Press F9 in game first, so the app knows where you are.")
            return
        best, best_d = None, None
        body = self.here.get("body")
        cands = self.world.locations_on(body.name) if body else self.world.locations
        for l in cands:
            if l.star != self.here["system"]:
                continue
            d = self.world.target_info(self.here, l)["straight"]
            if best_d is None or d < best_d:
                best, best_d = l, d
        if best is None or best_d > 10:
            messagebox.showinfo(APP_TITLE, "You are not at a known landing zone, station or outpost. Press F9 at "
                                           "the hangar or pad where the ship is, then try again.")
            return
        self.hangar.update(s["id"], parked={"name": best.name, "body": best.body})
        self._fill_hangar()
        self._hk_say(f"{self.hangar.label(s)} parked at {best.name}")

    def _ship_find(self):
        s = self._ship_selected()
        p = (s or {}).get("parked")
        if not p:
            messagebox.showinfo(APP_TITLE, "That ship has no parking spot saved. Use PARKED HERE when you leave it.")
            return
        loc = hauling.find_location(self.world, p["name"], p.get("body"))
        if loc:
            self._set_target(loc)
            self._hk_say(f"Target: {self.hangar.label(s)} at {loc.name}")

    # ------------------------------------------------------------ shop
    def _build_shop(self, parent):
        self.shopdata = None
        self._shop_product = None
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill="x", pady=(0, 6))
        self._lbl(row, "SEARCH", 7, MUTED, bold=True).pack(side="left", padx=(0, 6))
        self.shop_q = tk.StringVar()
        e = ttk.Entry(row, textvariable=self.shop_q, width=18)
        e.pack(side="left")
        e.bind("<KeyRelease>", lambda ev: self._shop_list_later())
        self._lbl(row, "CATEGORY", 7, MUTED, bold=True).pack(side="left", padx=(10, 6))
        self.shop_cat = tk.StringVar(value="All")
        self.shop_cat_cb = ttk.Combobox(row, textvariable=self.shop_cat, state="readonly", width=22, values=["All"])
        self.shop_cat_cb.pack(side="left")
        self.shop_cat_cb.bind("<<ComboboxSelected>>", lambda ev: self._shop_list())
        self.shop_sys = tk.StringVar(value="Current")
        cb = ttk.Combobox(row, textvariable=self.shop_sys, state="readonly", width=9,
                          values=["Current", "All"] + self.world.systems())
        cb.pack(side="right")
        cb.bind("<<ComboboxSelected>>", lambda ev: (self._shop_list(), self._shop_detail_fill()))
        self._lbl(row, "SYSTEM", 7, MUTED, bold=True).pack(side="right", padx=(10, 6))

        self.shop_listf = tk.Frame(parent, bg=PANEL)
        self.shop_listf.pack(fill="both", expand=True)
        self.tree_shop = self._tree(self.shop_listf, [("name", "ITEM", 230), ("cat", "CATEGORY", 170),
                                                      ("best", "BEST PRICE", 95), ("at", "AT", 150),
                                                      ("n", "SHOPS", 50)])
        self.tree_shop.bind("<Double-1>", lambda ev: self._shop_open())
        self.tree_shop.bind("<Return>", lambda ev: self._shop_open())
        self.lbl_shop = self._lbl(self.shop_listf, "", 8, MUTED, wraplength=660)
        self.lbl_shop.pack(anchor="w", pady=(6, 0))

        self.shop_detf = tk.Frame(parent, bg=PANEL)
        top = tk.Frame(self.shop_detf, bg=PANEL)
        top.pack(fill="x", pady=(0, 6))
        ttk.Button(top, text="BACK", command=self._shop_back).pack(side="left")
        self.lbl_shop_title = self._lbl(top, "", 11, CYAN, bold=True)
        self.lbl_shop_title.pack(side="left", padx=(10, 0))
        self.btn_shop_hangar = ttk.Button(top, text="ADD TO HANGAR", command=self._shop_to_hangar)
        ttk.Button(top, text="FLY TO SHOP", style="Accent.TButton", command=self._shop_target).pack(side="right")
        self.tree_offers = self._tree(self.shop_detf, [("shop", "SHOP", 190), ("place", "PLACE", 170),
                                                       ("price", "PRICE", 95), ("dist", "DISTANCE", 90),
                                                       ("age", "PRICE AGE", 60)])
        self.tree_offers.tag_configure("best", foreground=GREEN)
        self.tree_offers.tag_configure("old", foreground=MUTED)
        self.tree_offers.bind("<Double-1>", lambda ev: self._shop_target())
        self.lbl_shop_det = self._lbl(self.shop_detf, "", 8, MUTED, wraplength=660)
        self.lbl_shop_det.pack(anchor="w", pady=(6, 0))
        self._shop_job = None
        self._shop_map, self._offer_map = {}, {}
        self._shop_list()

    def _shop_ready(self):
        if self.trade and self.trade.loaded:
            if self.shopdata is None or self.shopdata.trade is not self.trade:
                self.shopdata = shop.ShopData(self.trade)
                self.shop_cat_cb.configure(values=["All"] + self.shopdata.categories())
        return self.shopdata if self.shopdata and self.shopdata.loaded else None

    def _shop_system(self):
        s = self.shop_sys.get()
        if s == "Current":
            return self.last_system
        return None if s == "All" else s

    def _shop_list_later(self):
        if self._shop_job:
            self.root.after_cancel(self._shop_job)
        self._shop_job = self.root.after(250, self._shop_list)

    def _shop_value(self, p, v):
        if p.kind == "refine":
            return f"{v:+.0f}%"
        return ledger.money(v)

    def _shop_list(self):
        self._shop_job = None
        t = self.tree_shop
        t.delete(*t.get_children())
        self._shop_map = {}
        sd = self._shop_ready()
        if not sd:
            self.lbl_shop.configure(fg=AMBER, text="Shop prices come from UEX. Open HAUL and click UPDATE PRICES "
                                                   "(or wait for the first download), then come back.")
            return
        q = self.shop_q.get().strip()
        cat = self.shop_cat.get()
        if not q and cat == "All":
            self.lbl_shop.configure(fg=MUTED, text=(
                f"{len(sd.products):,} items, ships and services with prices. Type what you want to buy, or pick a "
                "category (Ships to buy, Ships to rent, Fuel, Refinery yields, armor, weapons and more). "
                "Double-click a result to see every shop that has it and how far each one is."))
            return
        hits = sd.search(q, None if cat == "All" else cat, self._shop_system())
        hits.sort(key=lambda h: (not h[0].name.lower().startswith(q.lower()), h[0].name.lower()))
        for i, (p, offers) in enumerate(hits[:400]):
            best = (max if p.kind == "refine" else min)(offers, key=lambda o: o[1])
            iid = t.insert("", "end", tags=["odd"] if i % 2 else [], values=(
                p.name, p.category, self._shop_value(p, best[1]), clip_text(best[0].name, 24), len(offers)))
            self._shop_map[iid] = p
        where = self._shop_system() or "all systems"
        self.lbl_shop.configure(fg=MUTED if hits else AMBER, text=(
            f"{len(hits)} found in {where}" + (", showing 400" if len(hits) > 400 else "") +
            ". Double-click one to see every shop that has it." if hits else
            f"Nothing found in {where}. Try another word, or set SYSTEM to All."))

    def _shop_open(self, product=None):
        if product is None:
            sel = self.tree_shop.selection()
            product = self._shop_map.get(sel[0]) if sel else None
        if not product:
            return
        self._shop_product = product
        self.shop_listf.pack_forget()
        self.shop_detf.pack(fill="both", expand=True)
        self._shop_detail_fill()

    def _shop_back(self):
        self._shop_product = None
        self.shop_detf.pack_forget()
        self.shop_listf.pack(fill="both", expand=True)

    def _shop_detail_fill(self):
        p = self._shop_product
        if not p:
            return
        t = self.tree_offers
        t.delete(*t.get_children())
        self._offer_map = {}
        system = self._shop_system()
        here = self.here
        offers = [o for o in p.offers if not system or o[0].system == system]
        rows = []
        for term, value, age in offers:
            d = self.trade.distance_from(here, term) if here and here["system"] == term.system else None
            rows.append((term, value, age, d))
        best_v = (max if p.kind == "refine" else min)((r[1] for r in rows), default=None)
        if here and any(r[3] is not None for r in rows):
            rows.sort(key=lambda r: (r[3] is None, r[3] or 0))
            order = "closest first"
        else:
            rows.sort(key=lambda r: -r[1] if p.kind == "refine" else r[1])
            order = "best first"
        for i, (term, value, age, d) in enumerate(rows):
            tags = ["odd"] if i % 2 else []
            if value == best_v:
                tags.append("best")
            elif age is not None and age > hauling.STALE_PRICE_DAYS:
                tags.append("old")
            place = term.place + (f" ({term.body.name})" if term.body and term.body.name not in term.place
                                  and term.body.type != "Star" else "")
            iid = t.insert("", "end", tags=tags, values=(
                clip_text(term.name, 30), clip_text(place, 28), self._shop_value(p, value),
                self._short_km(d) if d is not None else "?",
                "?" if age is None else (f"{age * 24:.0f}h" if age < 1 else f"{age:.0f}d")))
            self._offer_map[iid] = term
        if p.kind == "item" and hasattr(self, "mydata"):
            for i, (place, unit, ts) in enumerate(self.mydata.item_prices(p.name)[:5]):
                age = (time.time() - ts) / 86400
                t.insert("", "end", tags=("mine",), values=(
                    "YOU PAID", clip_text(place or "?", 28), self._shop_value(p, unit or 0), "",
                    f"{age * 24:.0f}h" if age < 1 else f"{age:.0f}d"))
        t.tag_configure("mine", foreground=PURPLE)
        kind_word = {"item": "Price", "buy": "Price to buy", "rent": "Rental price", "fuel": "Price per SCU",
                     "refine": "Yield bonus"}[p.kind]
        self.lbl_shop_title.configure(text=f"{p.name}  ·  {p.category}")
        if p.kind in ("buy", "rent"):
            self.btn_shop_hangar.pack(side="right", padx=(0, 6))
        else:
            self.btn_shop_hangar.pack_forget()
        extra = ""
        if p.kind == "refine" and self.shopdata.methods:
            m = sorted(self.shopdata.methods, key=lambda x: -_num0(x.get("rating_yield")))
            extra = "  Refining methods with the best yield: " + ", ".join(
                f"{x.get('name')}" for x in m[:3]) + "."
        self.lbl_shop_det.configure(text=(
            f"{len(rows)} shops in {system or 'all systems'}, {order}. {kind_word} in {cw('green')} is the best. "
            "Double-click a shop to fly there. Prices are reported by players to UEX; grey rows are more than a "
            "week old." + extra))

    def _shop_target(self):
        sel = self.tree_offers.selection()
        term = self._offer_map.get(sel[0]) if sel else None
        if not term:
            return
        loc = term.loc
        if loc is None and term.body is not None:
            messagebox.showinfo(APP_TITLE, f"{term.name} is at {term.place}, which is not on the map yet. "
                                           f"Quantum to {term.body.name} and look for it there.")
            return
        if loc:
            self._set_target(loc)
            self._hk_say(f"Target: {term.name}")

    def _shop_to_hangar(self):
        p = self._shop_product
        if p and p.kind in ("buy", "rent"):
            self._ship_add(preset=p.name)

    def _shop_show(self, kind, name):
        sd = self._shop_ready()
        p = sd.find(kind, name) if sd else None
        self._show(self.tab_shop)
        if p:
            self.shop_sys.set("All")
            self._shop_open(p)
        return p is not None

    def _shop_category(self, cat):
        self._shop_back()
        self._show(self.tab_shop)
        if self._shop_ready() and cat in self.shopdata.categories():
            self.shop_cat.set(cat)
        self.shop_q.set("")
        self._shop_list()

    # ------------------------------------------------------------ refining jobs
    def _build_refining(self, parent):
        self.refine = refining.RefineJobs(self.world.user_dir)
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill="x", pady=(0, 6))
        ttk.Button(row, text="NEW JOB", command=self._refine_add).pack(side="left")
        ttk.Button(row, text="EDIT", command=self._refine_edit).pack(side="left", padx=4)
        ttk.Button(row, text="COLLECTED", command=self._refine_collect).pack(side="left")
        ttk.Button(row, text="REMOVE", command=self._refine_remove).pack(side="left", padx=4)
        ttk.Button(row, text="FLY TO REFINERY", style="Accent.TButton", command=self._refine_target).pack(side="right")
        self.refine_show_done = tk.BooleanVar(value=False)
        ttk.Checkbutton(row, text="SHOW COLLECTED", variable=self.refine_show_done, style="Panel.TCheckbutton",
                        command=self._fill_refining).pack(side="right", padx=10)
        self.tree_refine = self._tree(parent, [("ref", "REFINERY", 150), ("ores", "ORES", 210),
                                               ("method", "METHOD", 100), ("left", "READY IN", 80),
                                               ("at", "READY AT", 80), ("st", "STATUS", 70)])
        self.tree_refine.tag_configure("ready", foreground=GREEN)
        self.tree_refine.tag_configure("done", foreground=MUTED)
        self.tree_refine.bind("<Double-1>", lambda ev: self._refine_edit())
        self.lbl_refine = self._lbl(parent, "", 8, MUTED, wraplength=660)
        self.lbl_refine.pack(anchor="w", pady=(6, 0))
        self._fill_refining()

    def _fill_refining(self):
        if not hasattr(self, "tree_refine"):
            return
        t = self.tree_refine
        sel = t.selection()
        t.delete(*t.get_children())
        R, now = self.refine, time.time()
        jobs = R.jobs if self.refine_show_done.get() else R.open_jobs()
        for i, j in enumerate(sorted(jobs, key=lambda j: (j.get("collected", False), R.ready_at(j)))):
            left = R.left(j, now)
            if j.get("collected"):
                st, tag, ltxt = "COLLECTED", "done", ""
            elif left <= 0:
                st, tag, ltxt = "READY", "ready", "now"
            else:
                st, tag, ltxt = "REFINING", "", refining.fmt_duration(left)
            at = clock_str(time.localtime(R.ready_at(j)), "%a %H:%M")
            t.insert("", "end", iid=j["id"], tags=[tag] + (["odd"] if i % 2 else []), values=(
                clip_text(j.get("refinery", ""), 24), clip_text(R.ores_text(j), 36), j.get("method", ""), ltxt, at, st))
        for s in sel:
            if t.exists(s):
                t.selection_set(s)
        n_ready = sum(1 for j in R.open_jobs() if R.left(j, now) <= 0)
        if not R.jobs:
            msg = ("Add each refinery work order when you drop ore off: the refinery, the ores, the method and the time "
                   "the terminal shows. The app counts down and tells you (also in the overlay) when it is ready.")
        else:
            msg = (f"{len(R.open_jobs())} job{'s' if len(R.open_jobs()) != 1 else ''} waiting"
                   + (f", {n_ready} ready to collect" if n_ready else "") +
                   ". Mark a job COLLECTED once you pick it up. Double-click to edit.")
        self.lbl_refine.configure(text=msg, fg=GREEN if n_ready else MUTED)

    def _refine_tick(self):
        if not hasattr(self, "refine"):
            return
        for j in self.refine.newly_ready():
            self._alert("refinery", "Refinery job ready", f"Your ore is refined at {j.get('refinery', 'the refinery')}."
                        " Pick it up there.")
        try:
            on = self.nb.select() == str(self.nb_mine) and self.nb_mine.select() == str(self.tab_refining)
        except tk.TclError:
            on = False
        if on:
            self._fill_refining()

    def _refine_selected(self):
        sel = self.tree_refine.selection()
        return self.refine.get(sel[0]) if sel else None

    def _refine_add(self, existing=None):
        if not (self.trade and self.trade.loaded):
            messagebox.showinfo(APP_TITLE, "The refinery list comes with the UEX trade data. Downloading it now; "
                                           "try again in a few seconds.")
            self._haul_download()
            return
        dlg = RefineDialog(self.root, self, existing)
        if not dlg.result:
            return
        data, log_cost = dlg.result
        if existing:
            self.refine.update(existing["id"], **data)
        else:
            self.refine.add(**data)
            if log_cost and data.get("cost"):
                self._ledger_log(ledger.EXPENSE, "Refining", data["cost"],
                                 f"Refinery job at {data['refinery']}: {refining.RefineJobs.ores_text(data)}",
                                 estimate=False, source="refining")
        self._fill_refining()

    def _refine_edit(self):
        j = self._refine_selected()
        if j:
            self._refine_add(j)

    def _refine_collect(self):
        j = self._refine_selected()
        if j:
            self.refine.update(j["id"], collected=True, notified=True)
            self._fill_refining()
            self._hk_say("Collected. Sell it from HAUL or log the sale in MONEY.")

    def _refine_remove(self):
        j = self._refine_selected()
        if j and messagebox.askyesno(APP_TITLE, f"Remove the job at {j.get('refinery', '')}?"):
            self.refine.remove(j["id"])
            self._fill_refining()

    def _refine_target(self):
        j = self._refine_selected()
        if not j:
            return
        p = j.get("place") or {}
        loc = hauling.find_location(self.world, p.get("name", ""), p.get("body")) if p else None
        if loc is None and self.trade:
            loc = self.trade.extra_locations.get((p.get("name"), p.get("body")))
        if loc:
            self._set_target(loc)
            self._hk_say(f"Target: {loc.name}")
        else:
            messagebox.showinfo(APP_TITLE, f"{j.get('refinery', '')} is not on the map yet.")

    def _refineries(self):
        """Refinery terminal name -> Terminal."""
        out = {}  # one entry per station, preferring the terminal UEX has yields for
        sd = self._shop_ready()
        if sd:
            for (kind, _name), p in sd.products.items():
                if kind == "refine":
                    for term, _v, _a in p.offers:
                        out.setdefault(term.place or term.name, term)
        for t in self.trade.terminals.values():
            if t.name.lower().startswith("refinery") and t.available:
                out.setdefault(t.place or t.name, t)
        return out

    # ------------------------------------------------------------ salvage
    SALVAGE_CARGO = ("Recycled Material Composite", "Construction Materials", "Scrap")
    SALVAGE_TYPES = {"Scrapyard", "Salvage Yard", "Shipwreck", "Derelict Settlement", "Derelict settlement",
                     "Crash site", "Crash Site"}

    def _build_salvage(self, parent):
        nb2 = ttk.Notebook(parent)
        nb2.pack(fill="both", expand=True)
        self.nb_salv = nb2
        fs = ttk.Frame(nb2, style="Panel.TFrame", padding=6)
        nb2.add(fs, text="SELL")
        row = tk.Frame(fs, bg=PANEL)
        row.pack(fill="x", pady=(0, 6))
        self._lbl(row, "CARGO", 7, MUTED, bold=True).pack(side="left", padx=(0, 6))
        self.salv_cargo = tk.StringVar(value=self.SALVAGE_CARGO[0])
        cb = ttk.Combobox(row, textvariable=self.salv_cargo, state="readonly", width=28, values=self.SALVAGE_CARGO)
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: self._fill_salvage())
        self._lbl(row, "SCU", 7, MUTED, bold=True).pack(side="left", padx=(10, 6))
        self.salv_scu = tk.StringVar(value=str(self._settings().get("salv_scu", "")))
        e = ttk.Entry(row, textvariable=self.salv_scu, width=7)
        e.pack(side="left")
        e.bind("<KeyRelease>", lambda ev: self._fill_salvage())
        self.salv_sys = tk.StringVar(value="Current")
        cb = ttk.Combobox(row, textvariable=self.salv_sys, state="readonly", width=9,
                          values=["Current", "All"] + self.world.systems())
        cb.pack(side="right")
        cb.bind("<<ComboboxSelected>>", lambda e: self._fill_salvage())
        self._lbl(row, "SYSTEM", 7, MUTED, bold=True).pack(side="right", padx=(10, 6))
        self.tree_salv = self._tree(fs, [("term", "SELL AT", 170), ("place", "PLACE", 160), ("price", "PER SCU", 75),
                                         ("value", "YOU GET", 90), ("dist", "DISTANCE", 85), ("age", "PRICE AGE", 60)])
        self.tree_salv.tag_configure("best", foreground=GREEN)
        self.tree_salv.tag_configure("old", foreground=MUTED)
        self.tree_salv.bind("<Double-1>", lambda ev: self._salv_target())
        brow = tk.Frame(fs, bg=PANEL)
        brow.pack(fill="x", pady=(6, 0))
        ttk.Button(brow, text="FLY THERE", command=self._salv_target).pack(side="left")
        ttk.Button(brow, text="LOG SALE", command=self._salv_log).pack(side="left", padx=6)
        self.lbl_salv = self._lbl(fs, "", 8, MUTED, wraplength=660)
        self.lbl_salv.pack(anchor="w", pady=(6, 0))
        self._salv_map = {}

        fp = ttk.Frame(nb2, style="Panel.TFrame", padding=6)
        nb2.add(fp, text="SPOTS")
        self.tab_salv_spots = fp
        nb2.insert(0, fp)  # find wrecks first, sell after
        row = tk.Frame(fp, bg=PANEL)
        row.pack(fill="x", pady=(0, 6))
        self.salv_scope = tk.StringVar(value="This system")
        cb = ttk.Combobox(row, textvariable=self.salv_scope, state="readonly", width=14,
                          values=["This body", "This system", "All systems"])
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: self._fill_salv_spots())
        self.tree_spots = self._tree(fp, [("name", "PLACE", 230), ("type", "TYPE", 150), ("body", "ON", 110),
                                          ("dist", "DISTANCE", 90)])
        self.tree_spots.bind("<Double-1>", lambda ev: self._pick_from(self.tree_spots))
        self.lbl_spots = self._lbl(fp, "", 8, MUTED, wraplength=660)
        self.lbl_spots.pack(anchor="w", pady=(6, 0))
        nb2.bind("<<NotebookTabChanged>>", lambda e: self._fill_salv_spots())
        self._fill_salvage()

    def _salv_scu_value(self):
        try:
            return max(0.0, float(self.salv_scu.get().replace(",", "")))
        except ValueError:
            return 0.0

    def _fill_salvage(self):
        if not hasattr(self, "tree_salv"):
            return
        t = self.tree_salv
        t.delete(*t.get_children())
        self._salv_map = {}
        self._save_setting("salv_scu", self.salv_scu.get().strip())
        td = self.trade
        if not (td and td.loaded):
            self.lbl_salv.configure(fg=AMBER, text="Salvage prices come from UEX. Open HAUL and click UPDATE PRICES.")
            return
        cargo = self.salv_cargo.get()
        sysname = self.salv_sys.get()
        system = self.last_system if sysname == "Current" else (None if sysname == "All" else sysname)
        scu = self._salv_scu_value()
        here, now = self.here, time.time()
        rows = []
        for p in td.prices:
            if p.get("commodity_name") != cargo:
                continue
            price = hauling._num(p.get("price_sell"))
            term = td.terminals.get(p.get("id_terminal"))
            if price <= 0 or term is None or not term.available or (system and term.system != system):
                continue
            demand = hauling._num(p.get("scu_sell") or p.get("scu_sell_stock"))
            d = td.distance_from(here, term) if here and here["system"] == term.system else None
            age = (now - hauling._num(p.get("date_modified"))) / 86400 if p.get("date_modified") else None
            rows.append((term, price, demand, d, age))
        if not rows:
            self.lbl_salv.configure(fg=AMBER, text=f"No terminal buys {cargo} in {system or 'any system'} right now.")
            return
        best = max(r[1] for r in rows)
        rows.sort(key=lambda r: -r[1])
        for i, (term, price, demand, d, age) in enumerate(rows):
            tags = ["odd"] if i % 2 else []
            if price == best:
                tags.append("best")
            elif age is not None and age > hauling.STALE_PRICE_DAYS:
                tags.append("old")
            value = ledger.money(scu * price) if scu else ""
            place = term.place + (f" ({term.body.name})" if term.body and term.body.name not in term.place
                                  and term.body.type != "Star" else "")
            iid = t.insert("", "end", tags=tags, values=(
                clip_text(term.name, 26), clip_text(place, 26), f"{price:,.0f}", value,
                self._short_km(d) if d is not None else "?",
                "?" if age is None else (f"{age * 24:.0f}h" if age < 1 else f"{age:.0f}d")))
            self._salv_map[iid] = (term, price)
        self.lbl_salv.configure(fg=MUTED, text=(
            f"{len(rows)} terminals buy {cargo} in {system or 'all systems'}, best price first ({cw('green')}). "
            + ("Type your SCU to see what you get. " if not scu else "")
            + "Double-click to fly there. LOG SALE adds the sale to your ledger. Click a column to sort by "
              "distance."))

    def _salv_target(self):
        sel = self.tree_salv.selection()
        hit = self._salv_map.get(sel[0]) if sel else None
        if hit and hit[0].loc:
            self._set_target(hit[0].loc)
            self._hk_say(f"Target: {hit[0].name}")
        elif hit:
            messagebox.showinfo(APP_TITLE, f"{hit[0].name} is not on the map yet.")

    def _salv_log(self):
        sel = self.tree_salv.selection()
        hit = self._salv_map.get(sel[0]) if sel else None
        scu = self._salv_scu_value()
        guess = f"{scu * hit[1]:.0f}" if hit and scu else ""
        txt = simpledialog.askstring(APP_TITLE, "How much did you get for the salvage? (aUEC)", initialvalue=guess,
                                     parent=self.root)
        amt = ledger.parse_amount(txt) if txt else None
        if not amt:
            return
        where = hit[0].name if hit else ""
        self.ledger.add(ledger.INCOME, "Salvage sale", amt,
                        note=f"{scu:g} SCU {self.salv_cargo.get()}" + (f" at {where}" if where else ""),
                        where=self._where_text())
        self._fill_ledger()
        self._hk_say(f"Ledger +{ledger.short_money(amt)}: Salvage sale", ok=True)

    def _fill_salv_spots(self):
        if not hasattr(self, "tree_spots"):
            return
        t = self.tree_spots
        t.delete(*t.get_children())
        self._spots_map = {}
        h = self.here
        scope = self.salv_scope.get()
        body = h.get("body") if h else None
        out = []
        for l in self.world.locations:
            n = l.name.lower()
            if not (l.type in self.SALVAGE_TYPES or "wreck" in n or "crash" in n or "derelict" in n
                    or "salvage" in n or "scrapyard" in n):
                continue
            if scope == "This body" and (not body or l.body != body.name):
                continue
            if scope == "This system" and h and l.star != h["system"]:
                continue
            d = None
            if h and l.star == h["system"]:
                info = self.world.target_info(h, l)
                d = info.get("surface") if info.get("same_body") else info.get("straight")
            out.append((l, d))
        out.sort(key=lambda x: (x[1] is None, x[1] or 0, x[0].name))
        for i, (l, d) in enumerate(out):
            iid = t.insert("", "end", tags=["odd"] if i % 2 else [], values=(
                l.name, l.type, l.body, core.fmt_km(d) if d is not None else "?"))
            self._spots_map[iid] = l
        if scope == "This body" and not body:
            msg = "Press F9 on a planet or moon to see the salvage spots there."
        else:
            msg = (f"{len(out)} scrapyards, salvage yards, wrecks and derelicts, closest first. Double-click one to "
                   "fly there. SETTINGS > MAP DATA > CHECK FOR UPDATES adds more.")
        self.lbl_spots.configure(text=msg)

    # ------------------------------------------------------------ combat
    def _build_combat(self, parent):
        self.bounties = combat.Bounties(self.world.user_dir)
        nb2 = ttk.Notebook(parent)
        nb2.pack(fill="both", expand=True)
        self.nb_combat = nb2
        fb = ttk.Frame(nb2, style="Panel.TFrame", padding=6)
        nb2.add(fb, text="BOUNTIES")
        row = tk.Frame(fb, bg=PANEL)
        row.pack(fill="x", pady=(0, 6))
        ttk.Button(row, text="ADD BOUNTY", style="Accent.TButton", command=self._bounty_add).pack(side="left")
        ttk.Button(row, text="EDIT", command=self._bounty_edit).pack(side="left", padx=4)
        ttk.Button(row, text="DONE", command=lambda: self._bounty_finish("Done")).pack(side="left")
        ttk.Button(row, text="FAILED", command=lambda: self._bounty_finish("Failed")).pack(side="left", padx=4)
        ttk.Button(row, text="REMOVE", command=self._bounty_remove).pack(side="left")
        ttk.Button(row, text="FLY TO", style="Accent.TButton", command=self._bounty_target).pack(side="right")
        row2 = tk.Frame(fb, bg=PANEL)
        row2.pack(fill="x", pady=(0, 6))
        st = self._settings()
        self.bounty_show = tk.StringVar(value="Active")
        cb = ttk.Combobox(row2, textvariable=self.bounty_show, state="readonly", width=10,
                          values=["Active", "Done", "Failed", "All"])
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: self._fill_bounties())
        self.bounty_ledger = tk.BooleanVar(value=st.get("bounty_ledger", True))
        ttk.Checkbutton(row2, text="ADD PAYOUTS TO MY LEDGER", variable=self.bounty_ledger,
                        style="Panel.TCheckbutton",
                        command=lambda: self._save_setting("bounty_ledger", self.bounty_ledger.get())
                        ).pack(side="left", padx=10)
        self.tree_bounty = self._tree(fb, [("target", "TARGET", 170), ("rank", "RANK", 60), ("reward", "REWARD", 90),
                                           ("where", "WHERE", 170), ("st", "STATUS", 70), ("when", "WHEN", 90)])
        self.tree_bounty.tag_configure("done", foreground=GREEN)
        self.tree_bounty.tag_configure("failed", foreground=MUTED)
        self.tree_bounty.bind("<Double-1>", lambda ev: self._bounty_edit())
        self.lbl_bounty = self._lbl(fb, "", 8, MUTED, wraplength=660)
        self.lbl_bounty.pack(anchor="w", pady=(6, 0))

        fz = ttk.Frame(nb2, style="Panel.TFrame", padding=6)
        nb2.add(fz, text="ZONES")
        self.tab_zones = fz
        row = tk.Frame(fz, bg=PANEL)
        row.pack(fill="x", pady=(0, 6))
        self._lbl(row, "SHOW", 7, MUTED, bold=True).pack(side="left", padx=(0, 6))
        self.zone_kind = tk.StringVar(value="All")
        cb = ttk.Combobox(row, textvariable=self.zone_kind, state="readonly", width=22,
                          values=["All"] + list(combat.ZONES))
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: self._fill_zones())
        self.zone_scope = tk.StringVar(value="This system")
        cb = ttk.Combobox(row, textvariable=self.zone_scope, state="readonly", width=12,
                          values=["This body", "This system", "All systems"])
        cb.pack(side="left", padx=(8, 0))
        cb.bind("<<ComboboxSelected>>", lambda e: self._fill_zones())
        self.tree_zones = self._tree(fz, [("name", "PLACE", 220), ("zone", "GROUP", 150), ("type", "TYPE", 130),
                                          ("dist", "DISTANCE", 90)])
        self.tree_zones.tag_configure("sec", foreground=GREEN)
        self.tree_zones.tag_configure("out", foreground=RED)
        self.tree_zones.tag_configure("hid", foreground=AMBER)
        self.tree_zones.bind("<Double-1>", lambda ev: self._pick_from(self.tree_zones))
        self.lbl_zones = self._lbl(fz, "", 8, MUTED, wraplength=660)
        self.lbl_zones.pack(anchor="w", pady=(6, 0))
        self._zones_map = {}
        nb2.bind("<<NotebookTabChanged>>", lambda e: self._fill_zones())
        self._fill_bounties()

    def _fill_bounties(self):
        if not hasattr(self, "tree_bounty"):
            return
        t = self.tree_bounty
        t.delete(*t.get_children())
        show = self.bounty_show.get()
        items = [b for b in self.bounties.items if show == "All" or b["status"] == show]
        items.sort(key=lambda b: -(b.get("finished") or b.get("added") or 0))
        for i, b in enumerate(items):
            tag = {"Done": "done", "Failed": "failed"}.get(b["status"], "")
            when = clock_str(time.localtime(b.get("finished") or b.get("added") or 0), "%b %d %H:%M")
            where = (b.get("place") or {}).get("name") or b.get("where_text", "")
            t.insert("", "end", iid=b["id"], tags=([tag] if tag else []) + (["odd"] if i % 2 else []), values=(
                b.get("target", ""), b.get("rank", ""), ledger.money(float(b.get("reward") or 0)), clip_text(where, 26),
                b["status"].upper(), when))
        today = ledger.Ledger.period_start("Today")
        s_all, s_today = self.bounties.stats(), self.bounties.stats(today)
        if not self.bounties.items:
            msg = ("Add each bounty contract you accept: the target, its risk rank, the reward and where it is. "
                   "Mark it DONE when you collect, and the payout goes into your ledger.")
        else:
            msg = (f"{s_all['active']} active. Today: {s_today['done']} done, "
                   f"{ledger.short_money(s_today['earned'])} aUEC. All time: {s_all['done']} done, "
                   f"{s_all['failed']} failed, {ledger.short_money(s_all['earned'])} aUEC earned"
                   + (f", {ledger.short_money(s_all['average'])} per bounty." if s_all["done"] else "."))
        self.lbl_bounty.configure(text=msg)

    def _bounty_selected(self):
        sel = self.tree_bounty.selection()
        return self.bounties.get(sel[0]) if sel else None

    def _bounty_add(self, existing=None):
        dlg = BountyDialog(self.root, self, self._haul_places(), existing)
        if not dlg.result:
            return
        if existing:
            self.bounties.update(existing["id"], **dlg.result)
        else:
            self.bounties.add(**dlg.result)
        self.bounty_show.set("Active" if not existing else self.bounty_show.get())
        self._fill_bounties()

    def _bounty_edit(self):
        b = self._bounty_selected()
        if b:
            self._bounty_add(b)

    def _bounty_finish(self, status):
        b = self._bounty_selected()
        if not b:
            return
        was_done = b["status"] == "Done"
        self.bounties.update(b["id"], status=status, finished=time.time())
        if status == "Done" and not was_done and self.bounty_ledger.get() and float(b.get("reward") or 0) > 0:
            self._ledger_log(ledger.INCOME, "Bounty", float(b["reward"]),
                             f"{b.get('rank', '')} {b.get('target', '')}".strip(), estimate=False, source="bounty")
        elif status == "Done":
            self._hk_say(f"Bounty done: {b.get('target', '')}", ok=True)
        self._fill_bounties()

    def _bounty_remove(self):
        b = self._bounty_selected()
        if b and messagebox.askyesno(APP_TITLE, f"Remove the bounty on {b.get('target', '')}?"):
            self.bounties.remove(b["id"])
            self._fill_bounties()

    def _bounty_target(self):
        b = self._bounty_selected()
        p = (b or {}).get("place")
        loc = hauling.find_location(self.world, p["name"], p.get("body")) if p else None
        if loc:
            self._set_target(loc)
            self._hk_say(f"Target: {loc.name}")
        elif b:
            messagebox.showinfo(APP_TITLE, "This bounty has no place on the map. Edit it and pick where the "
                                           "target is, or use the marker the contract gives you in game.")

    def _fill_zones(self):
        if not hasattr(self, "tree_zones"):
            return
        t = self.tree_zones
        t.delete(*t.get_children())
        self._zones_map = {}
        h = self.here
        body = h.get("body") if h else None
        scope, kind = self.zone_scope.get(), self.zone_kind.get()
        out = []
        for l in self.world.locations:
            z = combat.zone_of(l)
            if not z or (kind != "All" and z != kind):
                continue
            if scope == "This body" and (not body or l.body != body.name):
                continue
            if scope == "This system" and h and l.star != h["system"]:
                continue
            d = None
            if h and l.star == h["system"]:
                info = self.world.target_info(h, l)
                d = info.get("surface") if info.get("same_body") else info.get("straight")
            out.append((l, z, d))
        out.sort(key=lambda x: (x[2] is None, x[2] or 0, x[0].name))
        tags = {"Security": "sec", "Outlaw stations": "out", "Outlaw hideouts": "hid"}
        for i, (l, z, d) in enumerate(out[:500]):
            iid = t.insert("", "end", tags=([tags[z]] if z in tags else []) + (["odd"] if i % 2 else []), values=(
                l.name, z, l.type, core.fmt_km(d) if d is not None else "?"))
            self._zones_map[iid] = l
        lawless = h and h["system"] in combat.LAWLESS_SYSTEMS
        msg = (f"{len(out)} places, closest first. " + (combat.ZONES[kind] + " " if kind != "All" else
               f"{cw('green', True)}: security. {cw('red', True)}: outlaw stations. {cw('amber', True)}: outlaw hideouts. ") +
               "Double-click one to fly there.")
        if lawless:
            msg = f"{h['system']} has no UEE law: anyone can attack you anywhere. " + msg
        if scope == "This body" and not body:
            msg = "Press F9 on a planet or moon to see the places there."
        self.lbl_zones.configure(text=msg, fg=AMBER if lawless else MUTED)

    def _toggle_compact(self):
        self.compact.set(not self.compact.get())
        self._save_setting("compact", self.compact.get())
        self._apply_compact()

    def _apply_compact(self):
        """The big position panel only shows when you asked for it AND there is a position to show.
        Until then a one-line strip says what to do, so the tabs get the room."""
        full = not self.compact.get() and bool(getattr(self, "here", None))
        has_target = bool(getattr(self, "target", None))
        state = (full, has_target)
        self.btn_compact.configure(text="COMPACT" if not self.compact.get() else "FULL")
        if getattr(self, "_hud_state", None) == state:
            self._refresh_compact()
            return
        self._hud_state = state
        for w in (self.pos_card, self.compact_bar, self.tgt_card):
            w.pack_forget()
        if full:
            self.pos_card.pack(fill="x", padx=12, before=self.hud_btns)
        else:
            self.compact_bar.pack(fill="x", padx=12, before=self.hud_btns)
        if has_target:
            self.tgt_card.pack(fill="x", padx=12, pady=(8, 0), before=self.hud_btns)
        self._refresh_compact()

    def _refresh_compact(self):
        if getattr(self, "_hud_state", (True,))[0]:
            return
        where = self.lbl_where.cget("text")
        gp = getattr(self, "gl_session", {}).get("place")
        if where == "NO FIX" and not self.here:
            self.lbl_compact.configure(text=gp.upper() if gp else "WHERE AM I?")
            self.lbl_compact2.configure(text=(
                "Press F9 in game (or type /showlocation in chat) to get your exact position."
                + ("" if self.target else "  Double-click any place below to set it as your target.")))
            return
        self.lbl_compact.configure(text=where)
        bits = []
        if getattr(self, "gl_session", {}).get("armistice"):
            bits.append("ARMISTICE")
        if self.here:
            b = self.here.get("body")
            bits.append(f"{b.type} · {self.here['system']}" if b else self.here.get("system", ""))
            alt = self.readouts["ALT"].cget("text")
            if alt and alt != "---":
                bits.append(f"alt {alt}")
            near = self._where_text()
            if near and near != where.title() and near.upper() != where:
                bits.append(f"near {near}")
            spd = self.readouts["SPEED"].cget("text")
            if spd and spd != "---":
                bits.append(spd)
        self.lbl_compact2.configure(text="   ".join(b for b in bits if b))

    def _ui(self, fn):
        """Run fn on the UI thread (safe to call from any thread)."""
        self._ui_q.put(fn)

    def _ui_poll(self):
        try:
            while True:
                fn = self._ui_q.get_nowait()
                try:
                    fn()
                except Exception as e:
                    hotkeys_win.log(f"ui call error: {e!r}")
        except queue.Empty:
            pass
        self.root.after(100, self._ui_poll)  # keep polling

    # ------------------------------------------------------------ alerts
    ILLEGAL = ("Altruciatoxin", "E'tam", "Freeze", "Gasping Weevil Eggs", "Maze", "Neon", "SLAM", "WiDoW")
    ALERT_KINDS = [("refinery", "Refinery job ready"), ("contract", "Contract completed or failed"),
                   ("illegal", "Illegal cargo when you enter a new jurisdiction"),
                   ("servers", "Game servers go down or come back")]

    def _illegal_cargo(self):
        cargo = (getattr(self, "gl_session", {}) or {}).get("cargo") or {}
        bad = {c.lower() for c in self.ILLEGAL}
        return {k: v for k, v in cargo.items() if v > 0 and k.lower() in bad}

    def _alert_cfg(self):
        c = self._settings().get("alerts") or {}
        out = {k: c.get(k, True) for k, _l in self.ALERT_KINDS}
        out["sound"] = c.get("sound", True)
        out["popup"] = c.get("popup", True)
        return out

    def _alert(self, kind, title, text, bad=False):
        """A heads-up: a small window in the corner of the screen, a sound, and the overlay message."""
        cfg = self._alert_cfg()
        self._hk_say(f"{title}: {text}", ok=not bad)
        if not cfg.get(kind, True):
            return
        hotkeys_win.log(f"alert {kind}: {title}")
        if cfg.get("sound"):
            try:
                if sys.platform.startswith("win"):
                    import winsound
                    winsound.MessageBeep(winsound.MB_ICONEXCLAMATION if bad else winsound.MB_ICONASTERISK)
                else:
                    self.root.bell()
            except Exception:
                pass
        if cfg.get("popup"):
            self._alert_popup(title, text, bad)

    def _alert_popup(self, title, text, bad=False):
        w = tk.Toplevel(self.root)
        w.overrideredirect(True)
        try:
            w.attributes("-topmost", True)
            w.attributes("-alpha", 0.95)
        except tk.TclError:
            pass
        col = RED if bad else CYAN
        key = "#010203"
        w.configure(bg=key)
        try:
            if sys.platform.startswith("win"):
                w.attributes("-transparentcolor", key)  # so the rounded corners show the game behind
        except tk.TclError:
            pass
        rb = RoundBox(w, fill=PANEL, border=col, accent=col, radius=14, pad=(14, 10))
        rb.pack()
        box = rb.inner
        tk.Label(box, text=APP_TITLE.upper() + "  ·  " + title.upper(), bg=PANEL, fg=col,
                 font=(self.F_UI, 10, "bold"), anchor="w").pack(anchor="w")
        tk.Label(box, text=text, bg=PANEL, fg=FG, font=(self.F_UI, 10), justify="left", anchor="w",
                 wraplength=int(340 * self.scale)).pack(anchor="w", pady=(3, 0))
        rb.update_idletasks()
        rb.configure(width=box.winfo_reqwidth() + 2 * 14 + 4)
        w.update_idletasks()
        sw, sh = w.winfo_screenwidth(), w.winfo_screenheight()
        stack = len([x for x in getattr(self, "_alert_wins", []) if x.winfo_exists()])
        x = sw - w.winfo_reqwidth() - 24
        y = sh - (w.winfo_reqheight() + 12) * (stack + 1) - 60
        w.geometry(f"+{x}+{max(10, y)}")
        self._alert_wins = [x for x in getattr(self, "_alert_wins", []) if x.winfo_exists()] + [w]
        for wd in (w, rb, box) + tuple(box.winfo_children()):
            wd.bind("<Button-1>", lambda e: w.destroy())
        w.after(9000, lambda: w.winfo_exists() and w.destroy())

    def _alerts_save(self):
        cfg = {k: v.get() for k, v in self.alert_vars.items()}
        self._save_setting("alerts", cfg)

    def _alert_test(self):
        self._alert("refinery", "Test alert", "This is how Starboard tells you something needs your attention. "
                                              "Click it to close it.")

    # ------------------------------------------------------------ automatic updates
    AUTO_SOURCES = [("prices", "Prices", 3), ("missions", "Missions", 24),
                    ("blueprints", "Blueprints", 24), ("parts", "Ship parts", 168),
                    ("mining", "Mining gear", 168), ("map", "Map", 168)]
    AUTO_CHOICES = [("Every hour", 1), ("Every 3 hours", 3), ("Every 12 hours", 12), ("Every day", 24),
                    ("Every week", 168), ("Off", 0)]

    def _auto_cfg(self):
        return self._settings().get("auto_update") or {}

    def _auto_label(self, hours):
        return next((n for n, h in self.AUTO_CHOICES if h == hours), "Every day")

    def _auto_save(self):
        cfg = {"on": self.auto_on.get()}
        for key, v in self.auto_vars.items():
            cfg[key] = dict(self.AUTO_CHOICES).get(v.get(), 24)
        self._save_setting("auto_update", cfg)
        self._auto_status()

    def _auto_age(self, key):
        """When this source was last downloaded (epoch seconds, 0 if never)."""
        import json
        try:
            if key == "prices":
                with open(os.path.join(self.world.user_dir, "uex", "info.json"), encoding="utf-8") as f:
                    return float(json.load(f).get("downloaded") or 0)
            if key == "missions":
                return float(getattr(self, "_mi_fetched", 0) or 0)
            if key == "mining":
                return float(getattr(self, "_lo_fetched", 0) or 0)
            if key == "blueprints":
                return float(getattr(self, "_bp_fetched", 0) or 0)
            if key == "parts":
                return float(getattr(self, "_sb_fetched", 0) or 0)
            if key == "map":
                v = data_update.read_info(self.world.data_dir).get("checked")
                return core.dt.datetime.fromisoformat(v).timestamp() if v else 0
        except Exception:
            return 0
        return 0

    def _auto_busy(self, key):
        return {"prices": getattr(self, "_haul_q", None) is not None, "missions": getattr(self, "mi_loading", False),
                "mining": getattr(self, "lo_loading", False), "blueprints": getattr(self, "bp_loading", False),
                "parts": getattr(self, "sb_loading", False),
                "map": getattr(self, "_update_q", None) is not None}.get(key, False)

    def _auto_run(self, key):
        hotkeys_win.log(f"auto update: {key}")
        if key == "prices":
            self._haul_download()
        elif key == "missions":
            self._mi_fetch()
        elif key == "mining":
            self._lo_fetch()
        elif key == "blueprints":
            self._bp_fetch()
        elif key == "parts":
            self._sb_fetch()
        elif key == "map":
            self._start_update()

    def _auto_tick(self, force=False):
        cfg = self._auto_cfg()
        started = []
        if force or cfg.get("on", True):
            for key, _label, default in self.AUTO_SOURCES:
                hours = cfg.get(key, default)
                if self._auto_busy(key) or (not force and not hours):
                    continue
                if force or time.time() - self._auto_age(key) > hours * 3600:
                    try:
                        self._auto_run(key)
                        started.append(key)
                    except Exception as e:
                        hotkeys_win.log(f"auto update {key} failed to start: {e!r}")
                    if not force:
                        break  # one at a time; the next is checked on the next round
        self._auto_status(started)
        if not force:
            self.root.after(10 * 60 * 1000, self._auto_tick)

    def _auto_status(self, started=()):
        if not hasattr(self, "auto_lbls"):
            return
        for key, lb in self.auto_lbls.items():
            t = self._auto_age(key)
            if key in started or self._auto_busy(key):
                text, col = "updating now...", CYAN
            elif not t:
                text, col = "not downloaded yet", AMBER
            else:
                age = (time.time() - t) / 3600
                text = f"updated {age:.0f} h ago" if age < 48 else f"updated {age / 24:.0f} days ago"
                col = MUTED
            lb.configure(text=text, fg=col)

    # ------------------------------------------------------------ my data (SETTINGS > MY DATA)
    MD_VIEWS = ["Commodity prices", "Shop purchases", "Places visited", "Contracts"]

    def _build_mydata(self, parent):
        if not hasattr(self, "mydata"):
            self.mydata = mydata.MyData(self.world.user_dir)
        top = tk.Frame(parent, bg=PANEL)
        top.pack(fill="x")
        self._lbl(top, "SHOW", 7, MUTED, bold=True).pack(side="left")
        self.md_view = tk.StringVar(value=self.MD_VIEWS[0])
        cb = ttk.Combobox(top, textvariable=self.md_view, values=self.MD_VIEWS, state="readonly", width=18)
        cb.pack(side="left", padx=6)
        cb.bind("<<ComboboxSelected>>", lambda e: self._md_fill())
        ttk.Button(top, text="IMPORT OLD GAME LOGS", command=self._md_import).pack(side="right")
        gt = tk.Frame(parent, bg=PANEL)
        gt.pack(fill="x", pady=(6, 0))
        self._lbl(gt, "GAME TEXT", 7, MUTED, bold=True).pack(side="left")
        ttk.Button(gt, text="READ AGAIN", command=lambda: self._gt_load(force=True)).pack(side="right")
        ttk.Button(gt, text="PICK FILE", command=self._gt_pick).pack(side="right", padx=(0, 4))
        self.lbl_gt = self._lbl(gt, "", 8, MUTED, wraplength=560)
        self.lbl_gt.pack(side="left", padx=8)
        self.lbl_md = self._lbl(parent, "", 8, MUTED, wraplength=740)
        self.lbl_md.pack(anchor="w", pady=(4, 4))
        self.tree_md = self._tree(parent, [("a", "", 190), ("b", "", 90), ("c", "", 170), ("d", "", 100),
                                           ("e", "", 100), ("f", "", 70)])
        self.tree_md.tag_configure("up", foreground=GREEN)
        self.tree_md.tag_configure("down", foreground=AMBER)
        self._lbl(parent, "Starboard builds this from your own play: what you paid and got, where you went, the "
                          "contracts you took and what they paid. It fills gaps in the other data and never leaves "
                          "your PC.", 8, MUTED, wraplength=740).pack(anchor="w", pady=(4, 0))
        self._md_importing = False
        self._gt_status()

    def _md_uex_price(self, name, place, side):
        """UEX's current price for a commodity at the terminal that matches a place you traded at."""
        td = self.trade
        if not td or not td.loaded or not name or not place:
            return None
        sp = mydata.squash(place)
        ids = {t.id for t in td.terminals.values() if sp and (sp in mydata.squash(t.name) or
                                                              sp in mydata.squash(getattr(t, "place", "")))}
        if not ids:
            return None
        key = "price_buy" if side == "buy" else "price_sell"
        vals = [_num0(r.get(key)) for r in td.prices if r.get("id_terminal") in ids
                and (r.get("commodity_name") or "").lower() == name.lower() and _num0(r.get(key)) > 0]
        return sum(vals) / len(vals) if vals else None

    def _md_fill(self):
        t = self.tree_md
        t.delete(*t.get_children())
        view = self.md_view.get()
        heads = {"Commodity prices": ("COMMODITY", "BUY / SELL", "PLACE", "YOUR PRICE", "UEX PRICE", "WHEN"),
                 "Shop purchases": ("ITEM", "", "PLACE", "YOU PAID (EACH)", "", "SEEN"),
                 "Places visited": ("PLACE", "BODY", "", "VISITS", "", "LAST"),
                 "Contracts": ("CONTRACT", "STATUS", "TAKEN AT", "PAID", "", "WHEN")}[view]
        for col, h in zip("abcdef", heads):
            t.heading(col, text=h)

        def age(ts):
            a = (time.time() - (ts or 0)) / 86400
            return f"{a * 24:.0f}h" if a < 1 else f"{a:.0f}d"
        rows = 0
        if view == "Commodity prices":
            for nm, kind, place, body, unit, qty, ts, n in self.mydata.price_rows("commodity"):
                side = kind.split("_")[-1]
                uex = self._md_uex_price(nm, place, side)
                tag = ""
                if uex and unit:
                    better = unit < uex if side == "buy" else unit > uex
                    tag = "up" if better else "down"
                t.insert("", "end", tags=(tag,) if tag else (), values=(
                    nm if len(nm) < 30 else nm[:8] + "...", side.upper(), place or "?",
                    f"{unit:,.0f}" if unit else "?", f"{uex:,.0f}" if uex else "-", age(ts)))
                rows += 1
        elif view == "Shop purchases":
            for nm, kind, place, body, unit, qty, ts, n in self.mydata.price_rows("item"):
                t.insert("", "end", values=(nm, "", place or "?", f"{unit:,.0f}" if unit else "?", "", age(ts)))
                rows += 1
        elif view == "Places visited":
            for nm, body, visits, last in self.mydata.places():
                t.insert("", "end", values=(nm, body or "", "", visits, "", age(last)))
                rows += 1
        else:
            for title, state, place, acc, reward, dfn in self.mydata.missions():
                t.insert("", "end", values=(title or "?", state or "", place or "?",
                                            ledger.money(reward) if reward else "-", "", age(acc)))
                rows += 1
        c = self.mydata.counts()
        self.lbl_md.configure(text=(
            f"Saved so far: {c['prices']} prices, {c['places']} places, {c['missions']} contracts, "
            f"{c['rewards']} contract payouts, {c['imported']} old game logs read."
            + ("  Green: you did better than UEX's price today; amber: worse." if view == "Commodity prices"
               else "")))

    def _md_import(self):
        if self._md_importing:
            return
        import glob
        folder = None
        gp = getattr(self, "gl_path", None)
        if gp:
            cand = os.path.join(os.path.dirname(gp), "logbackups")
            if os.path.isdir(cand):
                folder = cand
        if not folder:
            folder = filedialog.askdirectory(title="Pick Star Citizen's logbackups folder (next to Game.log)")
        if not folder:
            return
        paths = sorted(glob.glob(os.path.join(folder, "*.log")))
        if not paths:
            messagebox.showinfo(APP_TITLE, "No .log files in that folder.")
            return
        self._md_importing = True
        self.lbl_md.configure(text=f"Reading {len(paths)} old game logs...", fg=CYAN)
        names = dict(self.gl_store.get("guid", {}))

        def work():
            try:
                done, before, after = mydata.import_logs(
                    self.mydata, paths, gamelog.parse, names,
                    lambda i, n: self._ui(lambda: self.lbl_md.configure(text=f"Reading old game logs: {i} of {n}...",
                                                                        fg=CYAN)))
                msg = (f"Read {done} new log{'s' if done != 1 else ''}: +{after['prices'] - before['prices']} prices, "
                       f"+{after['places'] - before['places']} places, +{after['missions'] - before['missions']} "
                       "contracts.")
            except Exception as e:
                msg = f"Import stopped: {e}"

            def fin():
                self._md_importing = False
                self.gl_store["guid"].update(names)
                self._md_fill()
                self.lbl_md.configure(text=msg + "  " + self.lbl_md.cget("text"), fg=GREEN)
            self._ui(fin)
        threading.Thread(target=work, daemon=True).start()

    # ------------------------------------------------------------ mining loadout (MINE > LOADOUT)
    LO_SHIPS = [("Prospector", [1], "Arbor MH1"), ("MOLE", [2, 2, 2], "Arbor MH2"), ("Golem", [1], "Pitman"),
                ("ROC / ROC-DS", [0], "Arbor MHV"), ("Any size 1 laser", [1], None), ("Any size 2 laser", [2], None)]
    LO_NONE = "(none)"

    def _build_loadout(self, parent):
        st = self._settings()
        self.lo_cache = wikidata.Cache(self.world.user_dir, "mining")
        self.lo_items = []
        self.lo_loading = False
        top = tk.Frame(parent, bg=PANEL)
        top.pack(fill="x")
        self._lbl(top, "SHIP", 7, MUTED, bold=True).pack(side="left")
        self.lo_ship = tk.StringVar(value=st.get("lo_ship", "Prospector"))
        cb = ttk.Combobox(top, textvariable=self.lo_ship, state="readonly", width=16,
                          values=[s[0] for s in self.LO_SHIPS])
        cb.pack(side="left", padx=(6, 12))
        cb.bind("<<ComboboxSelected>>", lambda e: self._lo_ship_changed(reset=True))
        self.lo_active = tk.BooleanVar(value=st.get("lo_active", True))
        ttk.Checkbutton(top, text="COUNT ACTIVE MODULES", variable=self.lo_active, style="Panel.TCheckbutton",
                        command=lambda: (self._save_setting("lo_active", self.lo_active.get()), self._lo_calc())
                        ).pack(side="left")
        ttk.Button(top, text="UPDATE", command=lambda: self._lo_fetch(force=True)).pack(side="right")
        self.lbl_lo = self._lbl(parent, "", 8, MUTED, wraplength=740)
        self.lbl_lo.pack(anchor="w", pady=(4, 2))
        self.lo_grid = tk.Frame(parent, bg=PANEL)
        self.lo_grid.pack(fill="x", pady=(2, 4))
        self.lo_rows = []
        g = tk.Frame(parent, bg=PANEL)
        g.pack(fill="x", pady=(0, 4))
        self._lbl(g, "GADGET", 7, MUTED, bold=True).pack(side="left")
        self.lo_gadget = tk.StringVar(value=self.LO_NONE)
        self.lo_gadget_cb = ttk.Combobox(g, textvariable=self.lo_gadget, state="readonly", width=22)
        self.lo_gadget_cb.pack(side="left", padx=6)
        self.lo_gadget_cb.bind("<<ComboboxSelected>>", lambda e: self._lo_calc())
        self._lbl(g, "Gadgets go on the rock, so they count for every laser.", 8, MUTED).pack(side="left", padx=6)
        rk = tk.Frame(parent, bg=PANEL)
        rk.pack(fill="x", pady=(0, 4))
        self._lbl(rk, "ROCK", 7, MUTED, bold=True).pack(side="left")
        self.lo_rock = {}
        for key, label, w in (("mass", "MASS", 9), ("res", "RESISTANCE %", 5), ("inst", "INSTABILITY", 5)):
            self._lbl(rk, label, 7, MUTED, bold=True).pack(side="left", padx=(10, 4))
            v = tk.StringVar()
            e = ttk.Entry(rk, textvariable=v, width=w)
            e.pack(side="left")
            e.bind("<KeyRelease>", lambda ev: self._lo_crack())
            self.lo_rock[key] = v
        self._tip(rk, "Type what your mining scanner shows for the rock: its mass, resistance and instability. "
                      "Starboard tells you if your lasers can break it and which gadget would help.")
        self.lbl_lo_crack = self._lbl(parent, "Type a rock's mass and resistance from your mining scanner to see if "
                                              "you can break it.", 9, MUTED, wraplength=740)
        self.lbl_lo_crack.pack(anchor="w", pady=(0, 4))
        self.tree_lo = self._tree(parent, [("stat", "STAT", 170), ("l1", "LASER 1", 150), ("l2", "LASER 2", 150),
                                           ("l3", "LASER 3", 150)])
        self.tree_lo.tag_configure("good", foreground=GREEN)
        self.tree_lo.tag_configure("bad", foreground=AMBER)
        self.tree_lo.tag_configure("head", foreground=CYAN)
        self.lbl_lo_cost = self._lbl(parent, "", 8, FG, wraplength=740)
        self.lbl_lo_cost.pack(anchor="w", pady=(6, 0))
        self._lbl(parent, "Stats from the Star Citizen Wiki (api.star-citizen.wiki), prices from UEX. Percentages "
                          "add up the way the game does. Lower resistance, instability, inert and overcharge are better.", 8,
                  MUTED, wraplength=740).pack(anchor="w", pady=(2, 0))
        self._lo_load()

    def _lo_load(self):
        c = self.lo_cache.load()
        if c and c.get("rows"):
            self.lo_items = wikidata.clean_mining(c["rows"])
            self._lo_fetched = c.get("fetched", 0)
            age = (time.time() - c.get("fetched", 0)) / 86400
            self.lbl_lo.configure(text=f"{sum(1 for r in self.lo_items if r['kind'] == 'laser')} lasers, "
                                       f"{sum(1 for r in self.lo_items if r['kind'] == 'module')} modules, "
                                       f"{sum(1 for r in self.lo_items if r['kind'] == 'gadget')} gadget(s) "
                                       f"({age_words(age)}).", fg=MUTED)
            self._lo_ship_changed(reset=False)
            if age > 14:
                self._lo_fetch()
        else:
            self.lbl_lo.configure(text="Downloading mining gear from the Star Citizen Wiki the first time you open "
                                       "this tab (about half a minute).", fg=AMBER)

    def _lo_fetch(self, force=False):
        if self.lo_loading:
            return
        self.lo_loading = True
        self.lbl_lo.configure(text="Downloading mining lasers, modules and gadgets...", fg=CYAN)

        def work():
            try:
                rows = wikidata.fetch_mining(self.lo_cache, lambda p: self._ui(
                    lambda: self.lbl_lo.configure(text=f"Downloading: {p}", fg=CYAN)))
                err = None if rows else "the Wiki sent no mining items"
            except Exception as e:
                rows, err = None, str(e)

            def done():
                self.lo_loading = False
                if err:
                    self.lbl_lo.configure(text=f"Could not download mining gear ({err}). Check your internet and "
                                               "press UPDATE.", fg=AMBER)
                    return
                self._lo_load()
            self._ui(done)
        import threading as _t
        _t.Thread(target=work, daemon=True).start()

    def _lo_lasers_for(self, size):
        ship = self.lo_ship.get()
        out = []
        for r in self.lo_items:
            if r["kind"] != "laser" or int(r.get("size") or 0) != size:
                continue
            golem = "golem" in r["class"].lower() or r["name"].lower().startswith("pitman")
            if (ship == "Golem") != golem:
                continue
            if size == 0 and (r.get("power_max") or 0) < 500:
                continue  # hand-held tools
            out.append(r)
        return sorted(out, key=lambda r: r["name"])

    def _lo_by_name(self, kind, name):
        return next((r for r in self.lo_items if r["kind"] == kind and r["name"] == name), None)

    def _lo_ship_changed(self, reset=False):
        self._save_setting("lo_ship", self.lo_ship.get())
        for w in self.lo_grid.winfo_children():
            w.destroy()
        self.lo_rows = []
        sizes, stock = next(((s[1], s[2]) for s in self.LO_SHIPS if s[0] == self.lo_ship.get()), ([1], None))
        saved = {} if reset else (self._settings().get("lo_setup") or {}).get(self.lo_ship.get(), {})
        mods = sorted(r["name"] for r in self.lo_items if r["kind"] == "module")
        for i, size in enumerate(sizes):
            lasers = self._lo_lasers_for(size)
            names = [r["name"] for r in lasers]
            self._lbl(self.lo_grid, f"LASER {i + 1}", 7, MUTED, bold=True).grid(row=i, column=0, sticky="w",
                                                                              padx=(0, 6), pady=2)
            v = tk.StringVar()
            pick = (saved.get("lasers") or [None] * 3)[i] if saved else None
            if pick not in names:
                pick = next((n for n in names if stock and n.lower().startswith(stock.lower())), names[0] if names
                            else "")
            v.set(pick)
            cb = ttk.Combobox(self.lo_grid, textvariable=v, values=names, state="readonly", width=26)
            cb.grid(row=i, column=1, sticky="w", pady=2)
            mvars, mcbs = [], []
            for j in range(3):
                mv = tk.StringVar(value=((saved.get("modules") or [[]] * 3)[i][j:j + 1] or [self.LO_NONE])[0]
                                  if saved and i < len(saved.get("modules") or []) else self.LO_NONE)
                mcb = ttk.Combobox(self.lo_grid, textvariable=mv, values=[self.LO_NONE] + mods, state="readonly",
                                   width=15)
                mcb.grid(row=i, column=2 + j, sticky="w", padx=(6, 0), pady=2)
                mcb.bind("<<ComboboxSelected>>", lambda e: self._lo_calc())
                mvars.append(mv)
                mcbs.append(mcb)
            cb.bind("<<ComboboxSelected>>", lambda e, k=i: self._lo_laser_changed(k))
            self.lo_rows.append({"laser": v, "mods": mvars, "mcbs": mcbs})
            self._lo_laser_changed(i, calc=False)
        gadgets = sorted(r["name"] for r in self.lo_items if r["kind"] == "gadget")
        self.lo_gadget_cb.configure(values=[self.LO_NONE] + gadgets)
        g = saved.get("gadget") if saved else None
        self.lo_gadget.set(g if g in gadgets else self.LO_NONE)
        self._lo_calc()

    def _lo_laser_changed(self, i, calc=True):
        row = self.lo_rows[i]
        laser = self._lo_by_name("laser", row["laser"].get())
        slots = (laser or {}).get("slots", 0)
        for j, (mv, mcb) in enumerate(zip(row["mods"], row["mcbs"])):
            if j < slots:
                mcb.grid()
            else:
                mv.set(self.LO_NONE)
                mcb.grid_remove()
        if calc:
            self._lo_calc()

    def _lo_calc(self):
        t = self.tree_lo
        t.delete(*t.get_children())
        if not self.lo_items or not self.lo_rows:
            self.lbl_lo_cost.configure(text="")
            return
        gadget = self._lo_by_name("gadget", self.lo_gadget.get())
        stats, picks = [], []
        for row in self.lo_rows:
            laser = self._lo_by_name("laser", row["laser"].get())
            mods = [self._lo_by_name("module", m.get()) for m in row["mods"] if m.get() != self.LO_NONE]
            picks.append((laser, mods))
            stats.append(wikidata.loadout_stats(laser, mods, gadget, self.lo_active.get()))
        self._save_setting("lo_setup", {**(self._settings().get("lo_setup") or {}), self.lo_ship.get(): {
            "lasers": [r["laser"].get() for r in self.lo_rows],
            "modules": [[m.get() for m in r["mods"]] for r in self.lo_rows], "gadget": self.lo_gadget.get()}})
        n = len(stats)

        def cells(f):
            vals = [f(s) if s else "" for s in stats]
            return tuple(vals + [""] * (3 - n))

        rows = [("Mining power", lambda s: f"{s['power_min']:,.0f} - {s['power_max']:,.0f}", ""),
                ("Extraction power", lambda s: f"{s['extract']:,.0f}", ""),
                ("Optimal / max range", lambda s: f"{s['opt_range'] or 0:g} / {s['max_range'] or 0:g} m", "")]
        keys = []
        for s in stats:
            for k in (s or {}).get("mods", {}):
                if k not in keys:
                    keys.append(k)
        keys.sort(key=lambda k: wikidata.MOD_ORDER.index(k) if k in wikidata.MOD_ORDER else 99)
        for i, (label, f, tag) in enumerate(rows):
            t.insert("", "end", values=(label,) + cells(f), tags=("head",) + (("odd",) if i % 2 else ()))
        for i, k in enumerate(keys):
            vals = []
            good = 0
            for s in stats:
                v = (s or {}).get("mods", {}).get(k)
                if v is None or abs(v) < 0.05:
                    vals.append("0%" if s else "")
                    continue
                vals.append(f"{v:+.0f}%")
                better = (v < 0) if k in wikidata.LOWER_BETTER else (v > 0)
                good += 1 if better else -1
            tag = "good" if good > 0 else "bad" if good < 0 else ""
            t.insert("", "end", values=(wikidata.MOD_LABELS.get(k, k.replace("_", " ").capitalize()),) +
                     tuple(vals + [""] * (3 - n)), tags=tuple(x for x in (tag, "odd" if (i + 3) % 2 else "") if x))
        # module notes
        notes = []
        for laser, mods in picks:
            for m in mods:
                if m and m.get("active"):
                    bits = [f"{m['charges']:g} uses" if m.get("charges") else "",
                            f"{m['duration']:g} s each" if m.get("duration") else ""]
                    notes.append(f"{m['name']} is active: {', '.join(b for b in bits if b)}".rstrip(": "))
        # cost from UEX
        sd = self._shop_ready() if hasattr(self, "shopdata") and getattr(self, "trade", None) else None
        total, missing, where = 0.0, [], []
        names = [l["name"] for l, _ in picks if l] + [m["name"] for _, ms in picks for m in ms if m] + \
            ([gadget["name"]] if gadget else [])
        for nm in names:
            p = None
            if sd:
                p = sd.find("item", nm) or next((q for (k, qn), q in sd.products.items()
                                                 if k == "item" and qn.lower() == nm.lower()), None)
            b = p.best() if p else None
            if b:
                total += b[1]
                where.append(f"{nm} {ledger.short_money(b[1])} at {getattr(b[0], 'name', '?')}")
            else:
                missing.append(nm)
        text = f"Cost: {ledger.money(total)} aUEC" if total else \
            ("Cost: UEX prices not loaded yet (HAUL > UPDATE PRICES)" if sd is None else
             "Cost: UEX has no prices for these parts")
        if where:
            text += "   ·   Cheapest: " + "; ".join(dict.fromkeys(where))
        if missing and total:
            text += "   ·   Not sold or no price: " + ", ".join(dict.fromkeys(missing))
        if notes:
            text += "\n" + "   ·   ".join(notes)
        self.lbl_lo_cost.configure(text=text)
        for i in range(3):
            t.heading(f"l{i + 1}", text=f"LASER {i + 1}" if i < n else "")
        self._lo_picks = picks
        self._lo_crack()

    def _lo_crack(self):
        if not hasattr(self, "lbl_lo_crack"):
            return

        def num(v):
            try:
                return float(str(v).replace(",", "").replace("%", "").strip())
            except ValueError:
                return None
        mass, res, inst = (num(self.lo_rock[k].get()) for k in ("mass", "res", "inst"))
        picks = getattr(self, "_lo_picks", [])
        if not mass or res is None or not picks or not any(l for l, _m in picks):
            self.lbl_lo_crack.configure(text="Type a rock's mass and resistance from your mining scanner to see if "
                                             "you can break it.", fg=MUTED)
            return
        if res <= 1 and "." in self.lo_rock["res"].get():
            res *= 100  # typed 0.35 instead of 35
        active = self.lo_active.get()
        cur_g = self._lo_by_name("gadget", self.lo_gadget.get())

        def share_with(gadget):
            stats = [wikidata.loadout_stats(l, m, gadget, active) for l, m in picks if l]
            return wikidata.crack(stats, mass, res), stats

        (share, need, eff), stats = share_with(cur_g)
        lasers = len([1 for l, _m in picks if l])
        if share >= 1:
            throttle = min(100, 100 / share)
            text = (f"YES, you can break it. You need about {throttle:.0f}% of your laser power"
                    + (" across your lasers" if lasers > 1 else "") + f" (needs {need:,.0f}, rock resistance "
                    f"{eff:.0f}% after your gear).")
            color = GREEN if share >= 1.15 else AMBER
            if share < 1.15:
                text += " It is close: go slowly."
        else:
            text = (f"NO, not with this setup: you bring {share * 100:.0f}% of the power it needs ({need:,.0f} "
                    f"needed, rock resistance {eff:.0f}% after your gear).")
            color = RED
            better = []
            for g in (r for r in self.lo_items if r["kind"] == "gadget"):
                (sh, _n, _e), _s = share_with(g)
                if sh >= 1:
                    better.append((sh, g["name"]))
            if better:
                better.sort(reverse=True)
                text += " A gadget makes it breakable: " + ", ".join(f"{n} ({s * 100:.0f}%)" for s, n in better[:3]) \
                    + "."
            elif lasers == 1:
                text += " Try a stronger laser, a resistance module, or a second ship."
        if inst is not None and stats and stats[0]:
            k = 1 + stats[0]["mods"].get("laser_instability", 0) / 100
            text += f" Instability with your gear: {inst * k:.0f}" + (" (wild: keep the beam steady)." if inst * k > 50
                                                                         else ".")
        text += "  Estimate from the community formula; mining is not exact."
        self.lbl_lo_crack.configure(text=text, fg=color)

    # ------------------------------------------------------------ missions (MISSIONS tab)
    def _build_missions(self, parent):
        self.mi_cache = wikidata.Cache(self.world.user_dir, "missions")
        self.mi_rows = []
        self.mi_loading = False
        self._mi_map = {}
        self._mi_detail = {}
        top = tk.Frame(parent, bg=PANEL)
        top.pack(fill="x")
        self._lbl(top, "FIND", 7, MUTED, bold=True).pack(side="left")
        self.mi_q = tk.StringVar()
        e = ttk.Entry(top, textvariable=self.mi_q, width=14)
        e.pack(side="left", padx=(6, 8))
        e.bind("<KeyRelease>", lambda ev: self._mi_fill_later())
        self.mi_type = tk.StringVar(value="All types")
        self.mi_type_cb = ttk.Combobox(top, textvariable=self.mi_type, state="readonly", width=16)
        self.mi_type_cb.pack(side="left")
        self.mi_sys = tk.StringVar(value="All systems")
        self.mi_sys_cb = ttk.Combobox(top, textvariable=self.mi_sys, state="readonly", width=10)
        self.mi_sys_cb.pack(side="left", padx=6)
        self.mi_legal = tk.StringVar(value="Legal and illegal")
        lc = ttk.Combobox(top, textvariable=self.mi_legal, state="readonly", width=13,
                          values=["Legal and illegal", "Legal only", "Illegal only"])
        lc.pack(side="left")
        for w in (self.mi_type_cb, self.mi_sys_cb, lc):
            w.bind("<<ComboboxSelected>>", lambda ev: self._mi_fill())
        ttk.Button(top, text="UPDATE", command=lambda: self._mi_fetch(force=True)).pack(side="right")
        b = ttk.Button(top, text="BLUEPRINTS", command=self._mi_to_craft)
        b.pack(side="right", padx=(0, 6))
        self._tip(b, "Open the selected mission in CRAFT: the blueprints it gives, its faction and what you need.")
        self.tree_mi = self._tree(parent, [("title", "MISSION", 250), ("type", "TYPE", 110), ("giver", "GIVER", 140),
                                           ("sys", "SYSTEMS", 90), ("reward", "REWARD", 90), ("rank", "RANK", 45)])
        self.tree_mi.tag_configure("illegal", foreground=RED)
        self.tree_mi.tag_configure("bp", foreground=PURPLE)
        self.tree_mi.bind("<<TreeviewSelect>>", lambda ev: self._mi_show())
        self.tree_mi.bind("<Double-1>", lambda ev: self._mi_open())
        self.lbl_mi = self._lbl(parent, "", 8, MUTED, wraplength=740)
        self.lbl_mi.pack(anchor="w", pady=(4, 0))
        self.lbl_mi_det = self._lbl(parent, "", 9, FG, wraplength=740)
        self.lbl_mi_det.pack(anchor="w", pady=(2, 0))
        self._mi_job = None
        c = self.mi_cache.load()
        if c and c.get("rows"):
            self.mi_rows = [wikidata.tidy_mission(m) for m in c["rows"]]
            self._mi_after_load(c.get("fetched", 0))
        else:
            self.lbl_mi.configure(text="Open this tab to download every mission from the Star Citizen Wiki.",
                                  fg=MUTED)

    def _mi_after_load(self, fetched):
        types = sorted({m["type"] for m in self.mi_rows if m["type"]})
        systems = sorted({s for m in self.mi_rows for s in m["systems"]})
        self.mi_type_cb.configure(values=["All types"] + types)
        self.mi_sys_cb.configure(values=["All systems"] + systems)
        self._mi_fetched = fetched
        self._mi_fill()
        if hasattr(self, "bp_rows"):
            self._bp_index()
        if (time.time() - fetched) / 86400 > 3:
            self._mi_fetch()

    def _mi_fetch(self, force=False):
        if self.mi_loading:
            return
        self.mi_loading = True
        self.lbl_mi.configure(text="Downloading missions from the Star Citizen Wiki...", fg=CYAN)

        def work():
            try:
                rows = wikidata.fetch_missions(self.mi_cache, lambda n: self._ui(
                    lambda: self.lbl_mi.configure(text=f"Downloading missions: {n}...", fg=CYAN)))
                err = None if rows else "the Wiki sent no missions"
            except Exception as e:
                rows, err = None, str(e)

            def done():
                self.mi_loading = False
                if err:
                    self.lbl_mi.configure(text=f"Could not download missions ({err}). Press UPDATE to try again.",
                                          fg=AMBER)
                    return
                self.mi_rows = rows
                self._mi_after_load(time.time())
            self._ui(done)
        import threading as _t
        _t.Thread(target=work, daemon=True).start()

    def _mi_fill_later(self):
        if self._mi_job:
            self.root.after_cancel(self._mi_job)
        self._mi_job = self.root.after(250, self._mi_fill)

    def _mi_reward(self, m):
        lo, hi = m.get("reward_min"), m.get("reward_max")
        if not lo and not hi and hasattr(self, "mydata"):
            mine = self.mydata.reward(m.get("uuid"))
            if mine:
                return f"{ledger.short_money(mine)} (you)"
        if lo and hi and hi > lo:
            return f"{ledger.short_money(lo)}-{ledger.short_money(hi)}"
        if lo or hi:
            return ledger.short_money(lo or hi)
        if m.get("scrip"):
            return f"{m['scrip']:g} scrip"
        return ""

    def _mi_fill(self):
        self._mi_job = None
        t = self.tree_mi
        t.delete(*t.get_children())
        self._mi_map = {}
        q = self.mi_q.get().strip().lower()
        typ, sysf, legal = self.mi_type.get(), self.mi_sys.get(), self.mi_legal.get()
        n = 0
        for m in self.mi_rows:
            if typ != "All types" and m["type"] != typ:
                continue
            if sysf != "All systems" and sysf not in m["systems"]:
                continue
            if legal == "Legal only" and m["illegal"] or legal == "Illegal only" and not m["illegal"]:
                continue
            if q and q not in f"{m['title']} {m['giver']} {m['type']}".lower():
                continue
            if n >= 1500:
                break
            tags = ["illegal"] if m["illegal"] else ["bp"] if m.get("has_bp") else []
            if n % 2:
                tags.append("odd")
            iid = t.insert("", "end", values=(m["title"], m["type"], m["giver"], ", ".join(m["systems"]),
                                              self._mi_reward(m), f"{m['rank']:g}" if m.get("rank") is not None
                                              else ""), tags=tuple(tags))
            self._mi_map[iid] = m
            n += 1
        age = (time.time() - getattr(self, "_mi_fetched", time.time())) / 86400
        self.lbl_mi.configure(text=f"{n} of {len(self.mi_rows)} missions"
                                   + (" (first 1,500 shown; narrow it down)" if n >= 1500 else "")
                                   + f". Red: illegal. Purple: gives a blueprint. Click one for details, double-click "
                                     f"for its Wiki page. Data: Star Citizen Wiki, {age_words(age)}.",
                              fg=MUTED)

    def _mi_selected(self):
        sel = self.tree_mi.selection()
        return self._mi_map.get(sel[0]) if sel else None

    def _mi_show(self):
        m = self._mi_selected()
        if not m:
            return
        bits = [m["type"], m["giver"], ", ".join(m["systems"])]
        rew = self._mi_reward(m)
        bits.append(f"pays {rew}" if rew else "reward not listed on the Wiki")
        if not m["systems"]:
            bits.append("system not listed")
        if m.get("minutes"):
            bits.append(f"about {m['minutes']:g} min")
        if m.get("players"):
            bits.append(f"{m['players']:g} player" + ("s" if m["players"] != 1 else ""))
        if m.get("shareable"):
            bits.append("shareable")
        if m.get("danger"):
            bits.append(m["danger"])
        if m.get("rep"):
            bits.append(f"+{m['rep']:,.0f} rep")
        if m.get("standing"):
            bits.append(f"needs {m['standing']}")
        text = "   ·   ".join(b for b in bits if b)
        det = self._mi_detail.get(m["uuid"])
        if det:
            text += "\n\n" + det
        self.lbl_mi_det.configure(text=text)
        if m["uuid"] not in self._mi_detail:
            self._mi_detail[m["uuid"]] = ""

            def work(uuid=m["uuid"]):
                try:
                    d = wikidata.fetch_mission_detail(uuid)
                    desc = wikidata.clean_text(d.get("description") or "")
                    locs = []
                    ml = d.get("merged_locations")
                    if isinstance(ml, dict):
                        for v in ml.values():
                            for loc in (v or [])[:8]:
                                nm = loc.get("name") if isinstance(loc, dict) else str(loc)
                                if nm and nm not in locs:
                                    locs.append(nm)
                    bp = d.get("blueprints") or []
                    bpn = [b.get("name") for b in bp if isinstance(b, dict) and b.get("name")][:6]
                    out = (desc[:600] + ("..." if len(desc) > 600 else "")) if desc else ""
                    if locs:
                        out += ("\n" if out else "") + "Where: " + ", ".join(locs[:10])
                    if bpn:
                        out += ("\n" if out else "") + "Blueprints: " + ", ".join(bpn)
                except Exception:
                    out = ""

                def done():
                    self._mi_detail[uuid] = out
                    if self._mi_selected() and self._mi_selected()["uuid"] == uuid:
                        self._mi_show()
                self._ui(done)
            import threading as _t
            _t.Thread(target=work, daemon=True).start()

    def _mi_open(self):
        m = self._mi_selected()
        if m and m.get("web"):
            webbrowser.open(m["web"])

    # ------------------------------------------------------------ ship builder (HANGAR > SHIP BUILDER)
    def _build_builder(self, parent):
        self.sb_cache = wikidata.Cache(self.world.user_dir, "shipparts")
        self.sb_parts, self.sb_loading, self.sb_ship, self.sb_fit = {}, False, None, {}
        self.sb_slot_map, self.sb_part_map, self.sb_sel_slot, self.sb_sel_part = {}, {}, None, None
        self.sb_builds_path = os.path.join(self.world.user_dir, "builds.json")
        top = tk.Frame(parent, bg=PANEL)
        top.pack(fill="x")
        self._lbl(top, "SHIP", 7, MUTED, bold=True).pack(side="left")
        self.sb_name = tk.StringVar()
        self.sb_ship_cb = ttk.Combobox(top, textvariable=self.sb_name, width=30)
        self.sb_ship_cb.pack(side="left", padx=6)
        self.sb_ship_cb.bind("<<ComboboxSelected>>", lambda e: self._sb_load_ship())
        self.sb_ship_cb.bind("<Return>", lambda e: self._sb_load_ship())
        self.sb_ship_cb.bind("<KeyRelease>", self._sb_ship_filter)
        b = ttk.Button(top, text="STOCK", command=self._sb_stock)
        b.pack(side="left")
        self._tip(b, "Put every slot back to the parts the ship comes with.")
        ttk.Button(top, text="UPDATE PARTS", command=lambda: self._sb_fetch(force=True)).pack(side="right")
        b = ttk.Button(top, text="SHOPPING LIST", style="Accent.TButton", command=self._sb_shopping)
        b.pack(side="right", padx=6)
        self._tip(b, "Every part you changed: where to buy it for the least, or the blueprint to craft it.")
        self.sb_build = tk.StringVar()
        self.sb_build_cb = ttk.Combobox(top, textvariable=self.sb_build, state="readonly", width=22)
        self.sb_build_cb.pack(side="right")
        self.sb_build_cb.bind("<<ComboboxSelected>>", lambda e: self._sb_open_build())
        b = ttk.Button(top, text="DELETE", command=self._sb_delete_build)
        b.pack(side="right", padx=(6, 0))
        self._tip(b, "Delete the build picked in My builds.")
        ttk.Button(top, text="SAVE BUILD", command=self._sb_save_build).pack(side="right", padx=6)
        tools = tk.Frame(parent, bg=PANEL)
        tools.pack(fill="x", pady=(4, 0))
        for text, cmd, tip in (
                ("COMPARE", self._sb_compare, "Compare this build with the one picked in My builds."),
                ("PUT ON MY SHIP", self._sb_to_hangar, "Make this the loadout of this ship in MY SHIPS."),
                ("SHARE CODE", self._sb_share, "Copy a code for this build to paste in Discord."),
                ("LOAD CODE", self._sb_load_code, "Paste a build code someone shared.")):
            b = ttk.Button(tools, text=text, command=cmd, style="Small.TButton")
            b.pack(side="left", padx=(0, 4))
            self._tip(b, tip)
        self.lbl_sb = self._lbl(parent, "", 8, MUTED, wraplength=900)
        self.lbl_sb.pack(anchor="w", pady=(4, 4))

        # totals strip
        totbox = RoundBox(parent, pad=(4, 2))
        totbox.pack(fill="x", pady=(0, 6))
        tot = totbox.inner
        self.sb_tot = {}
        for i, (key, label) in enumerate([("dps", "DPS"), ("alpha", "ALPHA"), ("missiles", "MISSILES"),
                                          ("shield", "SHIELD HP"), ("regen", "SHIELD REGEN"),
                                          ("power", "POWER USE"), ("cool", "COOLING"), ("qt", "QUANTUM"),
                                          ("sig", "PARTS EM / IR"),
                                          ("cost", "COST TO CHANGE")]):
            f = tk.Frame(tot, bg=CARD)
            f.grid(row=0, column=i, sticky="w", padx=(10, 8), pady=4)
            self._sb_tot_cells = getattr(self, "_sb_tot_cells", []) + [f]
            tk.Label(f, text=label, bg=CARD, fg=MUTED, font=(self.F_UI, 7, "bold")).pack(anchor="w")
            v = tk.Label(f, text="-", bg=CARD, fg=FG, font=(self.F_UI, 11, "bold"))
            v.pack(anchor="w")
            d = tk.Label(f, text="", bg=CARD, fg=MUTED, font=(self.F_UI, 7))
            d.pack(anchor="w")
            self.sb_tot[key] = (v, d)
        tot._cols = None

        def wrap_totals(e):
            # as many per row as fit; the rest wrap onto the next row
            cell = max(c.winfo_reqwidth() for c in self._sb_tot_cells) + 18
            cols = max(1, min(len(self._sb_tot_cells), (e.width - 8) // cell))
            if cols != tot._cols:
                tot._cols = cols
                for n, c in enumerate(self._sb_tot_cells):
                    c.grid_configure(row=n // cols, column=n % cols)
        tot.bind("<Configure>", wrap_totals, add="+")  # keep RoundBox's own resize handler

        pw = ttk.PanedWindow(parent, orient="horizontal")
        pw.pack(fill="both", expand=True)
        left = tk.Frame(pw, bg=PANEL)
        right = tk.Frame(pw, bg=PANEL)
        pw.add(left, weight=1)
        pw.add(right, weight=1)
        self.tree_sb = self._tree(left, [("slot", "SLOT", 150), ("size", "SIZE", 40), ("part", "FITTED", 170),
                                         ("stat", "STAT", 120)])
        self.tree_sb.tag_configure("changed", foreground=ORANGE)
        self.tree_sb.tag_configure("locked", foreground=MUTED)
        self.tree_sb.bind("<<TreeviewSelect>>", lambda e: self._sb_slot_select())
        self.tree_sb.empty_text = "Pick a ship above."
        frow = tk.Frame(right, bg=PANEL)
        frow.pack(fill="x", pady=(0, 4))
        self._lbl(frow, "CLASS", 7, MUTED, bold=True).pack(side="left")
        self.sb_cls = tk.StringVar(value="All")
        cb = ttk.Combobox(frow, textvariable=self.sb_cls, state="readonly", width=12,
                          values=["All", "Military", "Stealth", "Civilian", "Industrial", "Competition"])
        cb.pack(side="left", padx=(6, 0))
        cb.bind("<<ComboboxSelected>>", lambda e: self._sb_fill_parts())
        self._tip(cb, "\n".join(f"{k}: {v}" for k, v in shipbuild.CLASS_INFO.items()) + "\n" + shipbuild.GRADE_INFO)
        self._lbl(frow, "Lower EM / IR = harder to spot. Stealth in purple.", 8, MUTED).pack(
            side="left", padx=(10, 0))
        self.tree_sbp = self._tree(right, [("name", "PART", 160), ("size", "SIZE", 36), ("cls", "CLASS", 80),
                                           ("grade", "GRADE", 46), ("stat", "STAT", 110),
                                           ("sig", "EM · IR", 110), ("price", "PRICE", 66), ("get", "GET IT", 76)])
        self.tree_sbp.tag_configure("stealth", foreground=PURPLE)
        self.tree_sbp.tag_configure("fitted", foreground=GREEN)
        self.tree_sbp.tag_configure("nosale", foreground=MUTED)
        self.tree_sbp.bind("<<TreeviewSelect>>", lambda e: self._sb_part_select())
        self.tree_sbp.bind("<Double-1>", lambda e: self._sb_fit_selected())
        self.tree_sbp.empty_text = "Click a slot on the left to see every part that fits it."
        row = tk.Frame(right, bg=PANEL)
        row.pack(fill="x", pady=(4, 0))
        ttk.Button(row, text="FIT THIS PART", style="Accent.TButton", command=self._sb_fit_selected).pack(side="left")
        ttk.Button(row, text="STOCK PART", command=self._sb_stock_slot).pack(side="left", padx=6)
        self.btn_sb_rack = ttk.Button(row, text="CHANGE RACK", command=self._sb_rack_toggle, state="disabled")
        self.btn_sb_rack.pack(side="left")
        self._tip(self.btn_sb_rack, "For missiles: switch the list between missiles and the missile racks that fit "
                                    "this hardpoint. A different rack can carry more, or bigger, missiles.")
        box = tk.Frame(right, bg=LINE, padx=1, pady=1)
        box.pack(fill="both", expand=True, pady=(6, 0))
        t = tk.Text(box, bg=CARD, fg=FG, wrap="word", relief="flat", padx=10, pady=8, cursor="arrow", height=10,
                    font=(self.F_UI, 9), insertwidth=0)
        t.pack(fill="both", expand=True)
        for tag, conf in (("h1", dict(font=(self.F_UI, 12, "bold"), foreground="#ffffff")),
                          ("h2", dict(font=(self.F_UI, 9, "bold"), foreground=ORANGE, spacing1=6)),
                          ("muted", dict(foreground=MUTED)), ("small", dict(font=(self.F_UI, 8), foreground=MUTED)),
                          ("good", dict(foreground=GREEN)), ("bad", dict(foreground=RED)),
                          ("warn", dict(foreground=AMBER)), ("bold", dict(font=(self.F_UI, 9, "bold"))),
                          ("link", dict(foreground=CYAN, underline=True))):
            t.tag_configure(tag, **conf)
        t.tag_bind("link", "<Enter>", lambda e: t.configure(cursor="hand2"))
        t.tag_bind("link", "<Leave>", lambda e: t.configure(cursor="arrow"))
        t.bind("<Key>", lambda e: "break")
        self.sb_text = t
        self._lbl(parent, "Totals assume everything is switched on, so use them to compare builds. Data: Star "
                          "Citizen Wiki (parts and slots) and UEX (where to buy).", 8, MUTED,
                  wraplength=900).pack(anchor="w", pady=(4, 0))
        c = self.sb_cache.load()
        if c and c.get("rows"):
            self.sb_parts = {p["uuid"]: p for p in c["rows"]}
            self._sb_fetched = c.get("fetched", 0)
            if not any("em" in p for p in c["rows"]):
                self._sb_refetch = True  # saved before parts had EM / IR: download them again
        self._sb_builds_refresh()
        self._sb_status()

    def _sb_lazy(self):
        if (not self.sb_parts or getattr(self, "_sb_refetch", False)) and not self.sb_loading:
            self._sb_refetch = False
            self._sb_fetch()
        if not getattr(self, "crafting", None):
            if self.bp_rows:
                self._bp_index()
            elif not self.bp_loading:
                self._bp_fetch()  # so parts can link to their blueprints
        if not self.sb_ship_cb.cget("values"):
            self._sb_ship_list()
        if not self.sb_ship:
            last = self._settings().get("sb_last")
            if last and last.get("ship"):
                self.sb_name.set(last["ship"])
                self._sb_load_ship(fit=last.get("fit") or {})
            else:
                a = self.hangar.active_ship()
                if a:
                    self.sb_name.set(a["ship"])
                    self._sb_load_ship()

    def _sb_ship_list(self):
        td = self.trade
        names = []
        if td and td.loaded:
            for v in td.vehicles_raw:
                if hauling._num(v.get("is_concept")) or hauling._num(v.get("is_addon")):
                    continue
                if not hauling._num(v.get("is_spaceship")) and not hauling._num(v.get("is_ground_vehicle")):
                    continue
                names.append(v.get("name") or "")
        self._sb_all_ships = sorted({n for n in names if n})
        self.sb_ship_cb.configure(values=self._sb_all_ships)

    def _sb_ship_filter(self, ev):
        if ev.keysym in ("Return", "Up", "Down", "Escape"):
            return
        q = self.sb_name.get().lower()
        allv = getattr(self, "_sb_all_ships", [])
        self.sb_ship_cb.configure(values=[n for n in allv if q in n.lower()] or allv)

    def _sb_status(self, text=None, col=MUTED):
        if text:
            self.lbl_sb.configure(text=text, fg=col)
            return
        if self.sb_loading:
            return
        n = len(self.sb_parts)
        if not n:
            self.lbl_sb.configure(text="Ship parts are not downloaded yet. They download the first time you open "
                                       "this tab (or press UPDATE PARTS).", fg=AMBER)
        elif not self.sb_ship:
            self.lbl_sb.configure(text=f"{n} ship parts ready ({age_words((time.time() - self._sb_fetched) / 86400)})."
                                       " Pick a ship to start.", fg=MUTED)

    def _sb_fetch(self, force=False):
        if self.sb_loading:
            return
        self.sb_loading = True
        self._sb_status("Downloading ship parts from the Star Citizen Wiki (a few minutes the first time)...", CYAN)

        def work():
            try:
                rows = shipbuild.fetch_parts(self.sb_cache, lambda m: self._ui(
                    lambda: self._sb_status(f"Downloading ship parts: {m}...", CYAN)))
                err = None if rows else "the Wiki sent no parts"
            except Exception as e:
                rows, err = None, str(e)

            def done():
                self.sb_loading = False
                if err:
                    self._sb_status(f"Could not download ship parts ({err}). Press UPDATE PARTS to try again.", AMBER)
                    return
                self.sb_parts = {p["uuid"]: p for p in rows}
                self._sb_fetched = time.time()
                self._sb_status()
                if self.sb_ship:
                    self._sb_refresh()
            self._ui(done)
        threading.Thread(target=work, daemon=True).start()

    def _sb_load_ship(self, fit=None):
        name = self.sb_name.get().strip()
        if not name:
            return
        uuid = None
        td = self.trade
        if td and td.loaded:
            v = next((v for v in td.vehicles_raw if name in (v.get("name"), v.get("name_full"))), None)
            if v:
                uuid, name = v.get("uuid") or None, v.get("name") or name
        self._sb_status(f"Loading {name} from the Star Citizen Wiki...", CYAN)

        def work():
            try:
                ship = shipbuild.fetch_ship(self.world.user_dir, uuid, name)
                err = None if ship and ship["slots"] else "the Wiki has no slots for this ship yet"
            except Exception as e:
                ship, err = None, str(e)

            def done():
                if err:
                    self._sb_status(f"Could not load {name} ({err}).", AMBER)
                    return
                ship["display"] = name
                self.sb_ship = ship
                use = fit
                if use is None:
                    mine = self._sb_hangar_ship(name)
                    if mine and (mine.get("build") or {}).get("fit"):
                        use = mine["build"]["fit"]
                        self._hk_say(f"Loaded your {name}'s loadout: {mine['build'].get('name', '')}")
                self.sb_fit = dict(use or {})
                self.sb_sel_slot = None
                self.sb_rack_mode = False
                self.tree_sbp.delete(*self.tree_sbp.get_children())
                self.tree_sbp.empty_text = "Click a slot on the left to see every part that fits it."
                self._empty_soon(self.tree_sbp)
                self._sb_refresh()
                self._sb_remember()
            self._ui(done)
        threading.Thread(target=work, daemon=True).start()

    def _sb_part(self, slot):
        return shipbuild.fitted_part(slot, self.sb_fit, self.sb_parts)

    def _sb_changed(self, x):
        rk = shipbuild.rack_key(x)
        return (x["id"] in self.sb_fit and self.sb_fit[x["id"]] != x["stock"]) or \
            (rk in self.sb_fit and self.sb_fit[rk] != x.get("rack_stock"))

    def _sb_refresh(self):
        ship = self.sb_ship
        if not ship:
            return
        t = self.tree_sb
        keep = self.sb_sel_slot
        t.delete(*t.get_children())
        self.sb_slot_map = {}
        groups = {}
        for typ, label in shipbuild.GROUPS:
            ss = [x for x in ship["slots"] if x["type"] == typ]
            if ss:
                groups[typ] = t.insert("", "end", values=(label, "", "", ""), open=True, tags=("head",))
        for x in ship["slots"]:
            parent = groups.get(x["type"])
            if parent is None:
                continue
            p = self._sb_part(x)
            size = f"S{x['max']}" if x["min"] == x["max"] else f"S{x['min']}-{x['max']}"
            name = p["name"] if p else "(empty: pick a part)"
            if x["type"] == "Missile":
                n, lo, hi = shipbuild.missile_room(x, self.sb_fit, self.sb_parts)
                size = f"{n} x S{hi}"
                rack = shipbuild.rack_of(x, self.sb_fit, self.sb_parts)
                if rack:
                    name += f"  ({rack['name']})"
            changed = self._sb_changed(x)
            tags = ["changed"] if changed else (["locked"] if not x.get("editable") else [])
            iid = t.insert(parent, "end", tags=tags, values=(
                x["label"], size, name, shipbuild.key_stat(p) if p else ""))
            self.sb_slot_map[iid] = x
            if keep and keep["id"] == x["id"]:
                t.selection_set(iid)
                t.see(iid)
        self._sb_totals()
        n_changed = sum(1 for x in ship["slots"] if self._sb_changed(x))
        self._sb_status(f"{ship['display']}: {len(ship['slots'])} slots you can change, {n_changed} changed "
                        "(orange). Click a slot, then double-click a part to fit it.", MUTED)

    def _sb_totals(self):
        ship = self.sb_ship
        parts = self.sb_parts
        now = shipbuild.totals(ship, self.sb_fit, parts)
        stock = shipbuild.totals(ship, {}, parts)
        cost, unsold = shipbuild.cost(ship, self.sb_fit, parts)

        def put(key, text, delta=None, more_is_better=True, fmt="{:+,.0f}", warn=False):
            v, d = self.sb_tot[key]
            v.configure(text=text, fg=AMBER if warn else FG)
            if delta:
                good = (delta > 0) == more_is_better
                d.configure(text=fmt.format(delta) + " vs stock", fg=GREEN if good else RED)
            else:
                d.configure(text="stock" if delta == 0 else "", fg=MUTED)
        put("dps", f"{now['dps']:,.0f}", now["dps"] - stock["dps"])
        put("alpha", f"{now['alpha']:,.0f}", now["alpha"] - stock["alpha"])
        put("missiles", f"{now['missiles']} ({now['missile_dmg'] / 1000:,.1f}k)",
            now["missile_dmg"] - stock["missile_dmg"])
        put("shield", f"{now['shield_hp']:,.0f}", now["shield_hp"] - stock["shield_hp"])
        put("regen", f"{now['shield_regen']:,.0f}/s", now["shield_regen"] - stock["shield_regen"])
        over = now["power_made"] and now["power_used"] > now["power_made"] and \
            stock["power_used"] <= stock["power_made"]
        put("power", f"{now['power_used']:g} of {now['power_made']:g}", now["power_used"] - stock["power_used"],
            more_is_better=False, fmt="{:+g}", warn=over)
        put("cool", f"{now['coolant']:g}", now["coolant"] - stock["coolant"], fmt="{:+g}")
        put("qt", f"{now['qt_speed'] / 1e6:,.0f} Mm/s" if now["qt_speed"] else "-",
            (now["qt_speed"] - stock["qt_speed"]) / 1e6, fmt="{:+,.0f} Mm/s")
        if now["em"] or now["ir"]:
            v, d = self.sb_tot["sig"]
            v.configure(text=f"{shipbuild.short_num(now['em'])} / {shipbuild.short_num(now['ir'])}", fg=FG)
            de, di = now["em"] - stock["em"], now["ir"] - stock["ir"]
            if de or di:
                d.configure(text=f"{de:+,.0f} / {di:+,.0f} vs stock",
                            fg=GREEN if (de + di) < 0 else RED)  # lower is stealthier
            else:
                d.configure(text="stock", fg=MUTED)
        v, d = self.sb_tot["cost"]
        v.configure(text=f"{cost:,.0f} aUEC" if cost else "-", fg=FG)
        d.configure(text=(f"{len(unsold)} not sold anywhere" if unsold else ""), fg=AMBER)

    def _sb_slot_select(self):
        sel = self.tree_sb.selection()
        slot = self.sb_slot_map.get(sel[0]) if sel else None
        if not slot:
            return
        if not self.sb_sel_slot or self.sb_sel_slot["id"] != slot["id"]:
            self.sb_rack_mode = False
        self.sb_sel_slot = slot
        self.btn_sb_rack.configure(state="normal" if slot["type"] == "Missile" and slot.get("rack_stock") else
                                   "disabled", text="MISSILES" if self.sb_rack_mode else "CHANGE RACK")
        self._sb_fill_parts()
        p = self._sb_part(slot)
        if p:
            self._sb_info(p)

    def _sb_fill_parts(self):
        slot = self.sb_sel_slot
        t = self.tree_sbp
        t.delete(*t.get_children())
        self.sb_part_map = {}
        if not slot:
            return
        if getattr(self, "sb_rack_mode", False) and slot["type"] == "Missile":
            target = shipbuild.rack_slot(slot)
            cur = self.sb_fit.get(target["id"], slot.get("rack_stock"))
            cands = [p for p in self.sb_parts.values() if shipbuild.fits(p, target)]
        else:
            target = slot
            cp = self._sb_part(slot)
            cur = cp["uuid"] if cp else None
            cands = [p for p in self.sb_parts.values() if shipbuild.fits(p, slot, self.sb_fit, self.sb_parts)]
        slot = target
        key = {"WeaponGun": "dps", "Missile": "damage", "Shield": "hp", "PowerPlant": "segments",
               "Cooler": "coolant", "QuantumDrive": "speed", "MissileLauncher": "count"}.get(slot["type"], "size")
        cands.sort(key=lambda p: -(p.get(key) or 0))
        want = self.sb_cls.get() if hasattr(self, "sb_cls") else "All"
        if want != "All":
            cands = [p for p in cands if p.get("cls") == want or p["uuid"] == cur]
        for i, p in enumerate(cands):
            how = [w for w, ok in (("Buy", p["buy"]), ("Craft", p["bp"] or p["craftable"]),
                                   ("Loot", p["lootable"])) if ok]
            tags = (["fitted"] if p["uuid"] == cur else ["stealth"] if p.get("cls") == "Stealth" else []) + \
                ([] if how else ["nosale"]) + (["odd"] if i % 2 else [])
            iid = t.insert("", "end", tags=tags, values=(
                p["name"], f"S{p['size']}", p.get("cls") or "-", p.get("grade") or "-", shipbuild.key_stat(p),
                shipbuild.sig_text(p) or "-",
                f"{p['buy'][0]['price']:,.0f}" if p["buy"] else "-", ", ".join(how) or "Not sold"))
            self.sb_part_map[iid] = p
        t.empty_text = ("No parts in the list fit this slot." if self.sb_parts else
                        "Ship parts are still downloading...")
        self._empty_soon(t)
        if not slot.get("editable"):
            self._sb_status(f"{slot['label']} is fixed on this ship in the game data, so it may not be "
                            "swappable. You can still try parts here.", AMBER)

    def _sb_part_select(self):
        sel = self.tree_sbp.selection()
        p = self.sb_part_map.get(sel[0]) if sel else None
        if p:
            self.sb_sel_part = p
            self._sb_info(p)

    def _sb_fit_selected(self):
        slot, p = self.sb_sel_slot, self.sb_sel_part
        if not slot or not p:
            return
        if getattr(self, "sb_rack_mode", False) and slot["type"] == "Missile":
            rs = shipbuild.rack_slot(slot)
            if not shipbuild.fits(p, rs):
                return
            if p["uuid"] == slot.get("rack_stock"):
                self.sb_fit.pop(rs["id"], None)
            else:
                self.sb_fit[rs["id"]] = p["uuid"]
            # a new rack can take a different missile size: drop a missile that no longer fits
            mine = self.sb_parts.get(self.sb_fit.get(slot["id"]))
            if mine and not shipbuild.fits(mine, slot, self.sb_fit, self.sb_parts):
                self.sb_fit.pop(slot["id"], None)
            self.sb_rack_mode = False
            self.btn_sb_rack.configure(text="CHANGE RACK")
        else:
            if not shipbuild.fits(p, slot, self.sb_fit, self.sb_parts):
                return
            if p["uuid"] == slot["stock"]:
                self.sb_fit.pop(slot["id"], None)
            else:
                self.sb_fit[slot["id"]] = p["uuid"]
        self._sb_refresh()
        self._sb_fill_parts()
        self._sb_remember()

    def _sb_rack_toggle(self):
        slot = self.sb_sel_slot
        if not slot or slot["type"] != "Missile":
            return
        self.sb_rack_mode = not getattr(self, "sb_rack_mode", False)
        self.btn_sb_rack.configure(text="MISSILES" if self.sb_rack_mode else "CHANGE RACK")
        self._sb_fill_parts()

    def _sb_stock_slot(self):
        if self.sb_sel_slot:
            self.sb_fit.pop(self.sb_sel_slot["id"], None)
            self.sb_fit.pop(shipbuild.rack_key(self.sb_sel_slot), None)
            self._sb_refresh()
            self._sb_fill_parts()
            self._sb_remember()

    def _sb_stock(self):
        self.sb_fit = {}
        self._sb_refresh()
        self._sb_fill_parts()
        self._sb_remember()

    def _sb_remember(self):
        if self.sb_ship:
            self._save_setting("sb_last", {"ship": self.sb_ship.get("display"), "fit": self.sb_fit})

    # -- where to get a part
    def _sb_bp_for(self, p):
        C = getattr(self, "crafting", None)
        if not C:
            return None
        for uid in p.get("bp") or []:
            if uid in C.bps:
                return C.bps[uid]
        return C.by_name.get(p["name"].lower())

    def _sb_buy_lines(self, p, limit=6):
        for b in p["buy"][:limit]:
            self._w("•  ")
            loc = self._find_place(b["place"]) if b["place"] else None
            if loc:
                self._link(b["terminal"] or b["place"], lambda l=loc: (self._set_target(l),
                                                                       self._hk_say(f"Target: {l.name}")))
            else:
                self._w(b["terminal"] or b["place"] or "?")
            where = ", ".join(x for x in (b["place"] if b["place"] not in (b["terminal"] or "") else "",
                                          b["body"], b["system"]) if x)
            self._w(f"  {where}" if where else "", "muted")
            self._w(f"  {b['price']:,.0f} aUEC\n", "bold")

    def _sb_info(self, p):
        self._bp_begin(self.sb_text)
        self._w(p["name"] + "\n", "h1")
        bits = [shipbuild.TYPE_WORD.get(p["type"], p["type"]), f"size {p['size']}",
                f"grade {p['grade']}" if p["grade"] else "", p["cls"], p["maker"]]
        self._w("  ·  ".join(b for b in bits if b) + "\n", "muted")
        t = p["type"]
        if t == "WeaponGun":
            stats = [("DPS", f"{p.get('dps', 0):,.0f}"), ("Alpha", f"{p.get('alpha', 0):,.0f}"),
                     ("Fire rate", f"{p.get('rpm', 0):,.0f} rpm"), ("Range", f"{p.get('range', 0):,.0f} m"),
                     ("Damage", p.get("dmg_type", "")), ("Ammo", f"{p.get('ammo', 0):,.0f}" if p.get("ammo") else "")]
        elif t == "Missile":
            stats = [("Damage", f"{p.get('damage', 0):,.0f}"), ("Tracks", p.get("signal", "")),
                     ("Lock time", f"{p.get('lock', 0):g} s"), ("Speed", f"{p.get('speed', 0):,.0f} m/s")]
        elif t == "Shield":
            stats = [("Shield HP", f"{p.get('hp', 0):,.0f}"), ("Regen", f"{p.get('regen', 0):,.0f}/s"),
                     ("Regen delay", f"{p.get('delay', 0):g} s"), ("Physical absorb", f"{p.get('phys', 0):g}%")]
        elif t == "PowerPlant":
            stats = [("Power made", f"{p.get('segments', 0):g}")]
        elif t == "Cooler":
            stats = [("Cooling", f"{p.get('coolant', 0):g}")]
        else:
            stats = [("Speed", f"{p.get('speed', 0) / 1e6:,.0f} Mm/s"), ("Cooldown", f"{p.get('cooldown', 0):g} s"),
                     ("Fuel use", f"{p.get('fuel', 0):g}")]
        if p.get("power") and t != "PowerPlant":
            stats.append(("Power use", f"{p['power']:g}"))
        self._w("   ".join(f"{a}: {b}" for a, b in stats if b) + "\n")
        more = [("EM signature", shipbuild.short_num(p.get("em")) if p.get("em") else ""),
                ("IR signature", shipbuild.short_num(p.get("ir")) if p.get("ir") else ""),
                ("Health", f"{p.get('health', 0):,.0f}" if p.get("health") else ""),
                ("Distortion limit", f"{p.get('distortion', 0):,.0f}" if p.get("distortion") else "")]
        if any(b for _a, b in more):
            self._w("   ".join(f"{a}: {b}" for a, b in more if b) + "\n", "muted")
        if p.get("cls") in shipbuild.CLASS_INFO:
            self._w(f"{p['cls'].upper()}: ", "good" if p["cls"] == "Stealth" else "bold")
            self._w(shipbuild.CLASS_INFO[p["cls"]] + "\n", "muted")
        if p.get("grade"):
            self._w(f"GRADE {p['grade']}: ", "bold")
            self._w(shipbuild.GRADE_INFO + "\n", "muted")
        self._w("BUY IT\n", "h2")
        if p["buy"]:
            self._sb_buy_lines(p)
            self._w("Click a shop to set it as your target. Prices from UEX.\n", "small")
        else:
            self._w("No shop sells it (according to UEX).\n", "muted")
        self._w("CRAFT IT\n", "h2")
        b = self._sb_bp_for(p)
        if b:
            owned = b["name"].lower() in self._bp_owned()
            self._link(f"Blueprint: {b['name']}", lambda u=b["uuid"]: self._craft_open(("bp", u)))
            self._w("  (you own it)\n" if owned else "  shows the contracts that give it and the materials\n",
                    "good" if owned else "muted")
        elif p["craftable"] or p["bp"]:
            self._w("It can be crafted. Open CRAFT once blueprints have downloaded to see how.\n", "muted")
        else:
            self._w("No blueprint for it.\n", "muted")
        if p["lootable"]:
            self._w("It can also be found as loot.\n", "muted")
        if p.get("web"):
            self._link("Open on the Star Citizen Wiki", lambda u=p["web"]: webbrowser.open(u))
            self._w("\n")
        self.sb_text.configure(state="disabled")

    def _sb_shopping(self):
        ship = self.sb_ship
        if not ship:
            return
        self._bp_begin(self.sb_text)
        self._w(f"SHOPPING LIST: {ship['display']}\n", "h1")
        changed = []
        for x in ship["slots"]:
            rk = shipbuild.rack_key(x)
            if self.sb_fit.get(rk) not in (None, x.get("rack_stock")):
                changed.append((dict(x, label=x["label"] + " rack", type="MissileLauncher"),
                                self.sb_parts.get(self.sb_fit[rk])))
            if self.sb_fit.get(x["id"], x["stock"]) != x["stock"]:
                changed.append((x, self.sb_parts.get(self.sb_fit[x["id"]])))
        if not changed:
            self._w("Nothing changed from stock yet. Fit some parts first.\n", "muted")
            self.sb_text.configure(state="disabled")
            return
        total = 0
        for x, p in changed:
            if not p:
                continue
            n = shipbuild.missile_room(x, self.sb_fit, self.sb_parts)[0] if x["type"] == "Missile" else 1
            self._w(f"\n{x['label']}: ", "bold")
            self._w(f"{n} x " if n > 1 else "")
            self._link(p["name"], lambda q=p: self._sb_info(q))
            self._w("\n")
            if p["buy"]:
                b0 = p["buy"][0]
                total += b0["price"] * n
                self._w(f"   Cheapest: {b0['terminal']}", "")
                self._w(f"  {b0['place']}, {b0['system']}" if b0["place"] else "", "muted")
                self._w(f"  {b0['price'] * n:,.0f} aUEC\n", "bold")
            bp = self._sb_bp_for(p)
            if bp:
                self._w("   Or craft it: ")
                self._link(bp["name"], lambda u=bp["uuid"]: self._craft_open(("bp", u)))
                self._w("\n")
            if not p["buy"] and not bp:
                self._w("   Not sold and no blueprint: loot or reward only.\n", "warn")
        self._w(f"\nTotal to buy everything: {total:,.0f} aUEC\n", "h2")
        self.sb_text.configure(state="disabled")

    # -- compare, hangar, share
    def _sb_hangar_ship(self, name):
        td = self.trade
        names = {name.lower()}
        if td and td.loaded:
            v = next((v for v in td.vehicles_raw if name in (v.get("name"), v.get("name_full"))), None)
            if v:
                names |= {(v.get("name") or "").lower(), (v.get("name_full") or "").lower()}
        mine = [x for x in self.hangar.ships if (x.get("ship") or "").lower() in names]
        a = self.hangar.active_ship()
        return a if a in mine else (mine[0] if mine else None)

    def _sb_to_hangar(self):
        if not self.sb_ship:
            return
        name = self.sb_ship["display"]
        mine = self._sb_hangar_ship(name)
        if not mine:
            if messagebox.askyesno(APP_TITLE, f"There is no {name} in MY SHIPS yet. Add it now with this loadout?"):
                mine = self.hangar.add(name)
            if not mine:
                return
        label = self.sb_build.get()
        bname = label.split(" (")[0] if label not in ("My builds", "No saved builds yet") else "Custom"
        self.hangar.update(mine["id"], build={"name": bname, "fit": dict(self.sb_fit)})
        self._fill_hangar()
        self._hk_say(f"{self.hangar.label(mine)} now uses this loadout")

    def _sb_open_from_hangar(self):
        s = self._ship_selected()
        if not s:
            messagebox.showinfo(APP_TITLE, "Click a ship first.")
            return
        self._show(self.tab_builder)
        self._sb_lazy()
        self.sb_name.set(s["ship"])
        b = s.get("build") or {}
        self._sb_load_ship(fit=b.get("fit") if b else None)

    def _sb_compare(self):
        if not self.sb_ship:
            return
        label = self.sb_build.get()
        other = next((b for b in self._sb_builds() if f"{b['name']} ({b['ship']})" == label), None)
        stock_only = other is None or other["ship"] != self.sb_ship["display"]
        fit_b = {} if stock_only else (other.get("fit") or {})
        name_b = "Stock" if stock_only else other["name"]
        a = shipbuild.totals(self.sb_ship, self.sb_fit, self.sb_parts)
        b = shipbuild.totals(self.sb_ship, fit_b, self.sb_parts)
        ca, _ = shipbuild.cost(self.sb_ship, self.sb_fit, self.sb_parts)
        cb, _ = shipbuild.cost(self.sb_ship, fit_b, self.sb_parts)
        t = self._bp_begin(self.sb_text)
        t.configure(tabs=(int(170 * self.scale), int(300 * self.scale), int(430 * self.scale)))
        self._w(f"COMPARE: {self.sb_ship['display']}\n", "h1")
        if stock_only and other is not None:
            self._w(f"'{other['name']}' is for the {other['ship']}, so this compares with the stock ship.\n",
                    "warn")
        elif other is None:
            self._w("Pick a saved build in My builds to compare with it. For now this compares with stock.\n",
                    "muted")
        self._w("\tON SCREEN\t" + name_b.upper() + "\tDIFFERENCE\n", "bold")
        rows = [("DPS", "dps", True, "{:,.0f}"), ("Alpha", "alpha", True, "{:,.0f}"),
                ("Missile damage", "missile_dmg", True, "{:,.0f}"), ("Missiles", "missiles", True, "{:,.0f}"),
                ("Shield HP", "shield_hp", True, "{:,.0f}"), ("Shield regen", "shield_regen", True, "{:,.0f}"),
                ("Power use", "power_used", False, "{:g}"), ("Power made", "power_made", True, "{:g}"),
                ("Cooling", "coolant", True, "{:g}"), ("Quantum Mm/s", "qt_speed", True, "{:,.0f}")]
        for label_, key, more_better, fmt in rows:
            va, vb = a[key], b[key]
            if key == "qt_speed":
                va, vb = va / 1e6, vb / 1e6
            d = va - vb
            self._w(f"{label_}\t{fmt.format(va)}\t{fmt.format(vb)}\t")
            if abs(d) < 1e-9:
                self._w("same\n", "muted")
            else:
                self._w(("+" if d > 0 else "") + fmt.format(d) + "\n", "good" if (d > 0) == more_better else "bad")
        self._w(f"Cost to change\t{ca:,.0f}\t{cb:,.0f}\n")
        self.sb_text.configure(state="disabled")

    def _sb_share(self):
        if not self.sb_ship:
            return
        code = shipbuild.build_code(self.sb_ship["display"], self.sb_fit)
        self.root.clipboard_clear()
        self.root.clipboard_append(code)
        self._bp_begin(self.sb_text)
        self._w("BUILD CODE COPIED\n", "h1")
        self._w("Paste it anywhere (Discord, a note). Anyone with Starboard can open it with LOAD CODE.\n\n",
                "muted")
        self._w(code + "\n")
        self.sb_text.configure(state="disabled")
        self._hk_say("Build code copied")

    def _sb_load_code(self):
        code = simpledialog.askstring(APP_TITLE, "Paste a Starboard build code (it starts with SB1:):",
                                      parent=self.root)
        if not code:
            return
        try:
            ship, fit = shipbuild.read_code(code)
        except ValueError as e:
            messagebox.showinfo(APP_TITLE, f"That code did not work: {e}.")
            return
        self.sb_name.set(ship)
        self._sb_load_ship(fit=fit)

    # -- saved builds
    def _sb_builds(self):
        import json
        try:
            with open(self.sb_builds_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _sb_builds_refresh(self):
        self.sb_build_cb.configure(values=[f"{b['name']} ({b['ship']})" for b in self._sb_builds()] or
                                   ["No saved builds yet"])
        self.sb_build.set("My builds")

    def _sb_save_build(self):
        import json
        if not self.sb_ship:
            return
        name = simpledialog.askstring(APP_TITLE, "Name this build:", parent=self.root)
        if not name:
            return
        builds = [b for b in self._sb_builds() if not (b["name"] == name and b["ship"] == self.sb_ship["display"])]
        builds.append({"name": name, "ship": self.sb_ship["display"], "fit": self.sb_fit, "saved": time.time()})
        self._sb_write_builds(builds)
        self._sb_builds_refresh()
        self._hk_say(f"Build saved: {name}")

    def _sb_write_builds(self, builds):
        import json
        tmp = self.sb_builds_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(builds, f, indent=1)
        os.replace(tmp, self.sb_builds_path)

    def _sb_delete_build(self):
        label = self.sb_build.get()
        builds = self._sb_builds()
        b = next((b for b in builds if f"{b['name']} ({b['ship']})" == label), None)
        if not b:
            messagebox.showinfo(APP_TITLE, "Pick the build to delete in My builds first.")
            return
        if not messagebox.askyesno(APP_TITLE, f"Delete the build '{b['name']}' for the {b['ship']}?\n\n"
                                              "This cannot be undone. The ship on screen stays as it is."):
            return
        self._sb_write_builds([x for x in builds if x is not b])
        self._sb_builds_refresh()
        self._hk_say(f"Build deleted: {b['name']}")

    def _sb_open_build(self):
        label = self.sb_build.get()
        b = next((b for b in self._sb_builds() if f"{b['name']} ({b['ship']})" == label), None)
        if b:
            self.sb_name.set(b["ship"])
            self._sb_load_ship(fit=b.get("fit") or {})

    # ------------------------------------------------------------ crafting (CRAFT)
    BP_SHOW = ["All", "Not owned yet", "I own", "From contracts", "Known from the start"]

    def _build_craft(self, parent):
        self.bp_cache = wikidata.Cache(self.world.user_dir, "blueprints")
        self.bp_rows, self.crafting, self.bp_loading = [], None, False
        self.bp_hist, self.bp_page, self.bp_map = [], None, {}
        self.bp_detail, self.bp_mdetail, self._bp_job = {}, {}, None
        if not hasattr(self, "mydata"):
            self.mydata = mydata.MyData(self.world.user_dir)
        top = tk.Frame(parent, bg=PANEL)
        top.pack(fill="x")
        self._lbl(top, "FIND", 7, MUTED, bold=True).pack(side="left")
        self.bp_q = tk.StringVar()
        e = ttk.Entry(top, textvariable=self.bp_q, width=18)
        e.pack(side="left", padx=6)
        self.bp_q.trace_add("write", lambda *a: self._bp_fill_later())
        self.bp_type = tk.StringVar(value="All types")
        self.bp_type_cb = ttk.Combobox(top, textvariable=self.bp_type, state="readonly", width=16)
        self.bp_type_cb.pack(side="left")
        self.bp_show = tk.StringVar(value="All")
        sc = ttk.Combobox(top, textvariable=self.bp_show, state="readonly", width=17, values=self.BP_SHOW)
        sc.pack(side="left", padx=6)
        for w in (self.bp_type_cb, sc):
            w.bind("<<ComboboxSelected>>", lambda ev: self._bp_fill())
        ttk.Button(top, text="UPDATE", command=lambda: self._bp_fetch(force=True)).pack(side="right")
        self.btn_plan = ttk.Button(top, text="MY PLAN", style="Accent.TButton",
                                   command=lambda: self._bp_go(("plan", "")))
        self.btn_plan.pack(side="right", padx=(0, 6))
        self._tip(self.btn_plan, "Your crafting plan: the blueprints you want to make, every material they need "
                                 "together, what you already have and where to get the rest.")
        b = ttk.Button(top, text="FIND MY BLUEPRINTS", command=self._bp_scan_logs)
        b.pack(side="right", padx=(0, 6))
        self._tip(b, "Read your game logs for every 'Received Blueprint' message, so Starboard knows which "
                     "blueprints you already have. New ones are added by themselves while you play.")
        self.lbl_bp = self._lbl(parent, "", 8, MUTED, wraplength=900)
        self.lbl_bp.pack(anchor="w", pady=(4, 4))

        pw = ttk.PanedWindow(parent, orient="horizontal")
        pw.pack(fill="both", expand=True)
        left = tk.Frame(pw, bg=PANEL)
        right = tk.Frame(pw, bg=PANEL)
        pw.add(left, weight=2)
        pw.add(right, weight=3)
        self.tree_bp = self._tree(left, [("name", "BLUEPRINT", 210), ("type", "TYPE", 110), ("how", "HOW TO GET IT", 120)])
        self.tree_bp.tag_configure("own", foreground=GREEN)
        self.tree_bp.tag_configure("free", foreground=CYAN)
        self.tree_bp.tag_configure("none", foreground=MUTED)
        self.tree_bp.bind("<<TreeviewSelect>>", lambda ev: self._bp_select())
        self.tree_bp.empty_text = "Downloading blueprints from the Star Citizen Wiki..."
        nav = tk.Frame(right, bg=PANEL)
        nav.pack(fill="x", padx=(8, 0))
        self.btn_bp_back = ttk.Button(nav, text="BACK", command=self._bp_back, state="disabled")
        self.btn_bp_back.pack(side="left")
        self.lbl_bp_crumb = self._lbl(nav, "", 8, MUTED)
        self.lbl_bp_crumb.pack(side="left", padx=8)
        box = tk.Frame(right, bg=LINE, padx=1, pady=1)
        box.pack(fill="both", expand=True, padx=(8, 0), pady=(4, 0))
        t = tk.Text(box, bg=CARD, fg=FG, wrap="word", relief="flat", padx=12, pady=10, cursor="arrow",
                    font=(self.F_UI, 10), insertwidth=0, spacing1=1, spacing3=1)
        sb = ttk.Scrollbar(box, orient="vertical", command=t.yview)
        t.configure(yscrollcommand=sb.set)
        t.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        t.tag_configure("h1", font=(self.F_UI, 16, "bold"), foreground="#ffffff", spacing3=2)
        t.tag_configure("h2", font=(self.F_UI, 10, "bold"), foreground=ORANGE, spacing1=12, spacing3=3)
        t.tag_configure("muted", foreground=MUTED)
        t.tag_configure("small", font=(self.F_UI, 8), foreground=MUTED)
        t.tag_configure("good", foreground=GREEN)
        t.tag_configure("bad", foreground=RED)
        t.tag_configure("warn", foreground=AMBER)
        t.tag_configure("bold", font=(self.F_UI, 10, "bold"))
        t.tag_configure("link", foreground=CYAN, underline=True)
        t.tag_configure("step", font=(self.F_UI, 10, "bold"), foreground=CYAN)
        t.tag_bind("link", "<Enter>", lambda e: t.configure(cursor="hand2"))
        t.tag_bind("link", "<Leave>", lambda e: t.configure(cursor="arrow"))
        t.bind("<Key>", lambda e: "break" if e.keysym not in ("Up", "Down", "Prior", "Next", "c") else None)
        self.bp_text = t
        self._plan_save() if os.path.exists(os.path.join(self.world.user_dir, "craft_plan.json")) else None
        c = self.bp_cache.load()
        if c and c.get("rows"):
            self.bp_rows = c["rows"]
            self._bp_fetched = c.get("fetched", 0)
            self._bp_index()
        else:
            self._bp_page_welcome()

    # -- data
    def _bp_fetch(self, force=False):
        if self.bp_loading:
            return
        self.bp_loading = True
        self.lbl_bp.configure(text="Downloading blueprints from the Star Citizen Wiki...", fg=CYAN)

        def work():
            try:
                rows = crafting.fetch_blueprints(self.bp_cache, lambda n: self._ui(
                    lambda: self.lbl_bp.configure(text=f"Downloading blueprints: {n}...", fg=CYAN)))
                err = None if rows else "the Wiki sent no blueprints"
            except Exception as e:
                rows, err = None, str(e)

            def done():
                self.bp_loading = False
                if err:
                    self.lbl_bp.configure(text=f"Could not download blueprints ({err}). Press UPDATE to try again.",
                                          fg=AMBER)
                    self.tree_bp.empty_text = "No blueprints yet. Press UPDATE."
                    self._empty_soon(self.tree_bp)
                    return
                self.bp_rows = rows
                self._bp_fetched = time.time()
                self._search_index = None
                self._bp_index()
            self._ui(done)
        threading.Thread(target=work, daemon=True).start()

    def _bp_owned(self):
        return {r[0].lower() for r in self.mydata.q("SELECT name FROM blueprints")}

    def _bp_index(self):
        if not self.bp_rows:
            return
        self.crafting = crafting.Crafting(self.bp_rows, self.mi_rows or [])
        if (not self.mi_rows or "bps" not in self.mi_rows[0]) and not getattr(self, "_bp_mi_asked", False):
            self._bp_mi_asked = True  # old mission list without blueprint links: download it again once
            self._mi_fetch(force=True)
        self.bp_type_cb.configure(values=["All types"] + self.crafting.types())
        self._bp_fill()
        if self.bp_page:
            self._bp_render()
        else:
            self._bp_page_welcome()

    def _bp_fill_later(self):
        if self._bp_job:
            self.root.after_cancel(self._bp_job)
        self._bp_job = self.root.after(250, self._bp_fill)

    def _bp_how(self, b, owned):
        if b["name"].lower() in owned:
            return "YOU OWN IT", "own"
        if b["default"]:
            return "From the start", "free"
        n = len(self.crafting.missions_for(b)) or b.get("missions_count") or 0
        if n:
            return f"{n} contract{'s' if n != 1 else ''}", ""
        return "No contract listed", "none"

    def _bp_fill(self):
        self._bp_job = None
        t = self.tree_bp
        t.delete(*t.get_children())
        self.bp_map = {}
        if not self.crafting:
            return
        owned = self._bp_owned()
        rows = self.crafting.search(self.bp_q.get(), self.bp_type.get(), self.bp_show.get(), owned)
        for i, b in enumerate(rows[:2000]):
            how, tag = self._bp_how(b, owned)
            tags = [x for x in (tag, "odd" if i % 2 else "") if x]
            iid = t.insert("", "end", tags=tags, values=(b["name"], b["type"], how))
            self.bp_map[iid] = b["uuid"]
        t.empty_text = "No blueprints match. Clear FIND or change the filters."
        linked = sum(1 for b in self.crafting.bps.values() if self.crafting.missions_for(b))
        mis_note = "" if (self.mi_rows and "bps" in self.mi_rows[0]) else \
            "  Missions are updating so blueprints can be linked to their contracts..."
        age = (time.time() - getattr(self, "_bp_fetched", time.time())) / 86400
        self.lbl_bp.configure(fg=MUTED, text=(
            f"{len(rows)} of {len(self.crafting.bps)} blueprints. You own {len(owned)}. {linked} are linked to the "
            f"contracts that give them. Click one to see how to get it and what it takes to craft. Data: "
            f"Star Citizen Wiki, {age_words(age)}." + mis_note))

    def _bp_first_scan(self):
        """Blueprints you already own are in your old game logs: read them once, in the background."""
        try:
            if self._settings().get("bp_scanned") or self._bp_owned():
                return
            if getattr(self, "gl_path", None) or self._settings().get("gl_path"):
                hotkeys_win.log("first blueprint scan")
                self._bp_scan_logs(quiet=True)
        except Exception as e:
            hotkeys_win.log(f"first blueprint scan: {e!r}")

    def _bp_scan_logs(self, quiet=False):
        import glob
        gp = getattr(self, "gl_path", None) or self._settings().get("gl_path")
        paths = []
        if gp:
            paths.append(gp)
            folder = os.path.join(os.path.dirname(gp), "logbackups")
            paths += sorted(glob.glob(os.path.join(folder, "*.log")))
        if len(paths) <= 1 and not quiet:
            folder = filedialog.askdirectory(title="Pick Star Citizen's logbackups folder (next to Game.log)")
            if folder:
                paths += sorted(glob.glob(os.path.join(folder, "*.log")))
        if not paths:
            return
        if quiet:
            self._save_setting("bp_scanned", True)
        else:
            self.lbl_bp.configure(text=f"Reading {len(paths)} game logs for blueprints...", fg=CYAN)
        rx = re.compile(r"^<([0-9T:\-.]+)Z?>.*Received Blueprint:\s*([^\"]+?)\s*:?\s*\"")

        def work():
            found = {}
            for path in paths:
                try:
                    with open(path, encoding="utf-8", errors="replace") as f:
                        for line in f:
                            if "Received Blueprint" not in line:
                                continue
                            m = rx.search(line)
                            if m:
                                name = gamelog.clean_title(m.group(2))
                                try:
                                    ts = core.dt.datetime.fromisoformat(m.group(1)[:19]).replace(
                                        tzinfo=core.dt.timezone.utc).timestamp()
                                except ValueError:
                                    ts = time.time()
                                found[name] = min(ts, found.get(name, ts))
                except OSError:
                    continue

            def fin():
                before = len(self._bp_owned())
                for name, ts in found.items():
                    self.mydata.own_blueprint(name, ts)
                after = len(self._bp_owned())
                self._bp_fill()
                self.lbl_bp.configure(text=f"Found {len(found)} blueprints in your game logs ({after - before} new). "
                                           f"You own {after}. New ones are added by themselves while you play.",
                                      fg=GREEN)
                if self.bp_page:
                    self._bp_render()
            self._ui(fin)
        threading.Thread(target=work, daemon=True).start()

    # -- navigation
    def _craft_open(self, page):
        self._show(self.tab_craft)
        if not self.bp_rows and not self.bp_loading:
            self._bp_fetch()
        self._bp_go(page)

    def _mi_to_craft(self):
        m = self._mi_selected()
        if not m:
            messagebox.showinfo(APP_TITLE, "Click a mission first.")
            return
        self._craft_open(("mis", m["uuid"]))

    def _bp_select(self):
        sel = self.tree_bp.selection()
        uid = self.bp_map.get(sel[0]) if sel else None
        if uid and self.bp_page != ("bp", uid):
            self._bp_go(("bp", uid))

    def _bp_go(self, page, push=True):
        if push and self.bp_page and self.bp_page != page:
            self.bp_hist.append(self.bp_page)
            del self.bp_hist[:-50]
        self.bp_page = page
        self.btn_bp_back.configure(state="normal" if self.bp_hist else "disabled")
        self._bp_render()

    def _bp_back(self):
        if self.bp_hist:
            self.bp_page = self.bp_hist.pop()
            self.btn_bp_back.configure(state="normal" if self.bp_hist else "disabled")
            self._bp_render()

    # -- page writing helpers
    def _bp_begin(self, t=None):
        t = t or self.bp_text
        self._tw = t
        t.configure(state="normal")
        t.delete("1.0", "end")
        self._bp_links = 0
        return t

    def _w(self, text, *tags):
        getattr(self, "_tw", self.bp_text).insert("end", text, tags)

    def _link(self, text, fn, *tags):
        self._bp_links += 1
        tag = f"L{self._bp_links}"
        t = getattr(self, "_tw", self.bp_text)
        t.insert("end", text, ("link", tag) + tags)
        t.tag_bind(tag, "<Button-1>", lambda e: fn())

    def _plink(self, text, page, *tags):
        self._link(text, lambda: self._bp_go(page), *tags)

    def _bp_page_welcome(self):
        t = self._bp_begin()
        self._w("CRAFTING\n", "h1")
        self._w("Everything from a blueprint to a finished item, linked together.\n\n", "muted")
        steps = [("1. Pick a blueprint", "on the left (or type in FIND)."),
                 ("2. Get the blueprint", "from the contracts that give it: their faction, legal or illegal, "
                                          "and the reputation you need."),
                 ("3. Gather the materials", "click a material to see where it is mined and where to buy it."),
                 ("4. Refine", "the material page shows the refineries with the best yield."),
                 ("5. Craft", "at a fabricator once you have the blueprint and the materials.")]
        for a, b in steps:
            self._w(a, "step")
            self._w("  " + b + "\n")
        self._w("\nEvery blue underlined name is a link. BACK goes to the page before.\n", "muted")
        if not self.bp_rows:
            self._w("\nBlueprints are downloading from the Star Citizen Wiki...\n", "warn")
        t.configure(state="disabled")
        self.lbl_bp_crumb.configure(text="")

    def _bp_render(self):
        self._tw = self.bp_text
        kind, key = self.bp_page
        if not self.crafting:
            self._bp_page_welcome()
            return
        try:
            {"bp": self._bp_page_bp, "mat": self._bp_page_mat, "mis": self._bp_page_mis,
             "fac": self._bp_page_fac, "plan": self._bp_page_plan}[kind](key)
        except Exception as e:
            hotkeys_win.log(f"craft page {kind} {key}: {e!r}")
            t = self._bp_begin()
            self._w(f"Could not show this page ({e}).", "warn")
        self.bp_text.configure(state="disabled")
        self.bp_text.yview_moveto(0)

    def _legal_tag(self, m):
        if m.get("illegal"):
            self._w("ILLEGAL", "bad", "bold")
        else:
            self._w("LEGAL", "good", "bold")

    def _rep_text(self, m):
        name = (m.get("standing") or "").strip()
        rep = m.get("min_rep")
        if not name:
            return "any standing"
        return name + (f" ({rep:,.0f} rep)" if isinstance(rep, (int, float)) and rep > 0 else "")

    def _mat_short(self, name):
        rows = self.world.ore_sources(name, self.here)
        if not rows:
            return ""
        near = [r for r in rows if r["distance_km"] is not None]
        r = min(near, key=lambda r: r["distance_km"]) if near else rows[0]
        how = {"ship": "ship mining", "vehicle": "ROC mining", "hand": "hand mining",
               "harvestable": "harvesting", "log": "your log"}.get(r["method"], r["method"])
        share = "" if r["share"] is None else f" {r['share']:g}%"
        where = ("nearest: " if near else "best: ") + r["source"]
        return f"{where} ({how}{share})"

    def _refine_offers(self, name):
        sd = self._shop_ready()
        if not sd:
            return None, []
        for oname in crafting.ore_name(name)[1:] + (name,):
            p = sd.find("refine", oname)
            if p and p.offers:
                offers = sorted(p.offers, key=lambda o: -(o[1] or 0))
                return oname, offers
        return None, []

    def _buy_offers(self, name):
        td = self.trade
        if not td or not td.loaded:
            return []
        out = []
        for r in td.prices:
            if (r.get("commodity_name") or "").lower() == name.lower() and _num0(r.get("price_buy")) > 0:
                term = td.terminals.get(r.get("id_terminal"))
                if term:
                    out.append((term, _num0(r.get("price_buy"))))
        return sorted(out, key=lambda x: x[1])

    def _place_of(self, term):
        parts = []
        place = (term.place or "").split(" (")[0]
        if place and place.lower() not in term.name.lower():
            parts.append(place)
        if term.body and term.body.type != "Star" and term.body.name not in " ".join(parts + [term.name]):
            parts.append(term.body.name)
        parts.append(term.system)
        return "  ·  ".join(parts)

    # -- pages
    def _bp_page_bp(self, uid):
        C = self.crafting
        b = C.bps.get(uid)
        t = self._bp_begin()
        if not b:
            self._w("Blueprint not found. Press UPDATE.", "warn")
            return
        self.lbl_bp_crumb.configure(text="BLUEPRINT")
        owned = b["name"].lower() in self._bp_owned()
        self._w(b["name"] + "\n", "h1")
        sub = b["sub"] if b["sub"] and b["sub"].upper() not in ("UNDEFINED", "UNKNOWN") else ""
        bits = [x for x in (b["type"], sub if sub and sub not in b["type"] else "",
                            f"grade {b['grade']}" if b["grade"] else "",
                            f"crafting takes {b['time']}" if b["time"] else "") if x]
        self._w("  ·  ".join(bits) + "\n", "muted")
        if owned:
            self._w("You have this blueprint.\n", "good", "bold")
        elif b["default"]:
            self._w("Every player has this blueprint from the start.\n", "good")
        else:
            self._w("You do not have this blueprint yet.\n", "warn")
        inplan = next((x for x in self._plan()["items"] if x["uuid"] == uid), None)
        if inplan:
            self._w(f"In your crafting plan (x{inplan['qty']}).  ", "good")
            self._plink("Open my plan", ("plan", ""))
        else:
            self._link("+ Add to my crafting plan", lambda: self._plan_add(uid))
        self._w("\n")

        # 1. getting the blueprint
        self._w("1  GET THE BLUEPRINT\n", "h2")
        det = self.bp_detail.get(uid)
        if uid not in self.bp_detail and not b["default"]:
            self._bp_load_detail(uid)
        if b["default"]:
            self._w("Nothing to do: every player has it from the start.\n")
        else:
            entries = self._bp_contracts(b, det)
            if not entries:
                if det is None and b.get("missions_count"):
                    self._w(f"Loading the {b['missions_count']} contract(s) that give it...\n", "muted")
                else:
                    self._w("The Wiki does not list a contract that gives this blueprint yet.\n", "muted")
            else:
                known = [e for e in entries if e["m"]]
                legal = [e for e in known if not e["m"].get("illegal")]
                facs = sorted({e["fac"] for e in entries})
                self._w(f"Complete any one of these {len(entries)} contract{'s' if len(entries) != 1 else ''} "
                        f"from {len(facs)} faction{'s' if len(facs) != 1 else ''}. ", "muted")
                if known:
                    self._w(f"{len(legal)} legal, {len(known) - len(legal)} illegal.\n", "muted")
                else:
                    self._w("\n")
                if known:
                    pick = min(legal or known, key=lambda e: (e["m"].get("min_rep") or 0, e["m"].get("rank") or 0, e["m"]["title"]))
                    self._w("Easiest: ", "bold")
                    self._plink(pick["m"]["title"], ("mis", pick["m"]["uuid"]))
                    self._w(f"  ({pick['fac']}, {'legal' if not pick['m'].get('illegal') else 'illegal'}, "
                            f"needs {self._rep_text(pick['m'])})\n")
                for fac in sorted(facs, key=lambda f: (all((e["m"] or {}).get("illegal") for e in entries
                                                           if e["fac"] == f), f)):
                    group = [e for e in entries if e["fac"] == fac]
                    self._w("\n")
                    if fac != "Unknown":
                        self._plink(fac, ("fac", fac), "bold")
                    else:
                        self._w("Faction not listed", "bold")
                    self._w(f"   {len(group)} contract{'s' if len(group) != 1 else ''}\n", "small")
                    for e in sorted(group, key=lambda e: ((e["m"] or {}).get("min_rep") or 0, (e["m"] or {}).get("rank") or 0, e["title"])):
                        m = e["m"]
                        self._w("  •  ")
                        if m:
                            self._plink(m["title"], ("mis", m["uuid"]))
                        else:
                            self._w(e["title"])
                        if isinstance(e["chance"], (int, float)) and e["chance"] < 1:
                            self._w(f"   {e['chance'] * 100:.0f}% chance", "warn")
                        self._w("\n")
                        if not m:
                            continue
                        self._w("       ")
                        self._legal_tag(m)
                        self._w(f"  ·  needs {self._rep_text(m)}", "")
                        bits = [m.get("type") or ""]
                        if m.get("systems"):
                            bits.append(", ".join(m["systems"]))
                        rew = self._mi_reward(m)
                        if rew:
                            bits.append(rew)
                        if m.get("rep"):
                            bits.append(f"+{m['rep']:g} rep")
                        if m.get("minutes"):
                            bits.append(f"{m['minutes']:g} min")
                        if m.get("shareable"):
                            bits.append("shareable")
                        self._w("  ·  " + "  ·  ".join(x for x in bits if x) + "\n", "muted")

        # 2. materials
        self._w("2  GATHER THE MATERIALS\n", "h2")
        if not b["ingredients"]:
            self._w("The Wiki lists no materials.\n", "muted")
        for i in b["ingredients"]:
            amt = f"{i['scu']:g} SCU" if i.get("scu") else (f"{i['qty']:g} x" if i.get("qty") else "")
            self._w(f"{amt:>9}  ", "bold")
            self._plink(i["name"], ("mat", i["name"]))
            short = self._mat_short(i["name"])
            if short:
                self._w("   " + short, "muted")
            self._w("\n")

        # 3. refine
        self._w("3  REFINE THE ORE\n", "h2")
        any_ref = False
        for i in b["ingredients"]:
            oname, offers = self._refine_offers(i["name"])
            if offers:
                any_ref = True
                term, val, _age = offers[0]
                self._w("•  ")
                self._plink(i["name"], ("mat", i["name"]))
                self._w(f": best yield at {term.name}  ")
                self._w(self._place_of(term) + "  ", "muted")
                self._w(f"{val:+g}%\n", "good" if (val or 0) > 0 else "muted")
        if not any_ref:
            self._w("None of these need refining, or UEX has no refinery yields for them "
                    "(download prices in HAUL).\n", "muted")
        else:
            self._w("Hand-mined gems (Hadanite, Dolivine, Aphorite...) go straight into crafting.\n", "small")

        # 4. craft
        self._w("4  CRAFT IT\n", "h2")
        sp = next((p for p in getattr(self, "sb_parts", {}).values() if p["name"].lower() == b["name"].lower()), None)
        if sp and sp["buy"]:
            b0 = sp["buy"][0]
            self._w("Or skip crafting and buy it: ", "muted")
            self._w(f"{b0['terminal']}, {b0['price']:,.0f} aUEC", "bold")
            self._w(f" (cheapest of {len(sp['buy'])} shops)\n" if len(sp["buy"]) > 1 else "\n", "muted")
        self._w("With the blueprint and the materials, use a fabricator" +
                (f" (about {b['time']})." if b["time"] else ".") + "\n")
        if b["dismantle"]:
            self._w("Dismantling it gives back: " + ", ".join(
                f"{d['scu']:g} SCU {d['name']}" if d.get("scu") else d["name"] for d in b["dismantle"]) + "\n",
                "small")
        self._w("\n")
        if b.get("web"):
            self._link("Open on the Star Citizen Wiki", lambda u=b["web"]: webbrowser.open(u))
        self._w("    Data: api.star-citizen.wiki" + (f", {b['version']}" if b.get("version") else "") + "\n",
                "small")

    def _bp_contracts(self, b, det):
        """Every contract that can give a blueprint: from the mission list, plus any the Wiki's blueprint
        page names that the list did not link. Each: {m (mission or None), title, fac, chance}."""
        C = self.crafting
        out, seen = [], set()
        um = (det or {}).get("unlocking_missions") or []
        chance_by_uuid, chance_by_title = {}, {}
        for u in um:
            mt = re.search(r"/missions/([0-9a-f-]{36})", u.get("web_url") or "")
            if mt:
                chance_by_uuid[mt.group(1)] = u.get("chance")
            chance_by_title[(u.get("title") or "").lower()] = u.get("chance")
        for m in C.missions_for(b):
            seen.add(m["uuid"])
            out.append({"m": m, "title": m["title"], "fac": m.get("faction") or m.get("giver") or "Unknown",
                        "chance": chance_by_uuid.get(m["uuid"], chance_by_title.get(m["title"].lower()))})
        by_slug = {m.get("web", "").rstrip("/").rsplit("/", 1)[-1]: m for m in C.missions.values() if m.get("web")}
        for u in um:
            mt = re.search(r"/missions/([0-9a-f-]{36})", u.get("web_url") or "")
            slug = (u.get("web_url") or "").rstrip("/").rsplit("/", 1)[-1]
            m = C.missions.get(mt.group(1)) if mt else by_slug.get(slug)
            if m and m["uuid"] in seen:
                continue
            if m:
                seen.add(m["uuid"])
                out.append({"m": m, "title": m["title"], "fac": m.get("faction") or m.get("giver") or "Unknown",
                            "chance": u.get("chance")})
            else:
                title = re.sub(r"\[(\w+)\]", lambda x: x.group(1).lower() + " varies" if x.group(1) == "Location"
                               else x.group(1), u.get("title") or "?")
                out.append({"m": None, "title": title, "fac": "Unknown", "chance": u.get("chance")})
        return out

    # -- crafting plan (CRAFT > MY PLAN)
    def _plan(self):
        import json
        if getattr(self, "_plan_cache", None) is None:
            try:
                with open(os.path.join(self.world.user_dir, "craft_plan.json"), encoding="utf-8") as f:
                    self._plan_cache = json.load(f)
            except Exception:
                self._plan_cache = {}
            self._plan_cache.setdefault("items", [])
            self._plan_cache.setdefault("have", {})
        return self._plan_cache

    def _plan_save(self):
        import json
        p = os.path.join(self.world.user_dir, "craft_plan.json")
        with open(p + ".tmp", "w", encoding="utf-8") as f:
            json.dump(self._plan(), f, indent=1)
        os.replace(p + ".tmp", p)
        n = sum(x["qty"] for x in self._plan()["items"])
        if hasattr(self, "btn_plan"):
            self.btn_plan.configure(text=f"MY PLAN ({n})" if n else "MY PLAN")

    def _plan_add(self, uid, qty=1):
        P = self._plan()
        x = next((x for x in P["items"] if x["uuid"] == uid), None)
        if x:
            x["qty"] = max(0, x["qty"] + qty)
            if not x["qty"]:
                P["items"].remove(x)
        elif qty > 0:
            P["items"].append({"uuid": uid, "qty": qty})
        self._plan_save()
        b = self.crafting.bps.get(uid) if self.crafting else None
        if qty > 0 and b:
            self._hk_say(f"Added to your plan: {b['name']}")
        self._bp_render()

    def _plan_set_have(self, name, unit):
        cur = self._plan()["have"].get(name, 0)
        txt = simpledialog.askstring(APP_TITLE, f"How much {name} do you have? ({unit})",
                                     initialvalue=f"{cur:g}", parent=self.root)
        if txt is None:
            return
        try:
            v = max(0.0, float(txt.replace(",", "").strip() or 0))
        except ValueError:
            return
        self._plan()["have"][name] = v
        self._plan_save()
        self._bp_render()

    def _plan_needs(self):
        """{material: {"need", "unit", "kind", "for": [blueprint names]}} for everything in the plan."""
        need = {}
        for x in self._plan()["items"]:
            b = self.crafting.bps.get(x["uuid"]) if self.crafting else None
            if not b:
                continue
            for i in b["ingredients"]:
                amt = (i.get("scu") or i.get("qty") or 0) * x["qty"]
                d = need.setdefault(i["name"], {"need": 0, "unit": "SCU" if i.get("scu") else "pieces",
                                                "kind": i["kind"], "for": []})
                d["need"] += amt
                if b["name"] not in d["for"]:
                    d["for"].append(b["name"])
        return need

    def _bp_page_plan(self, _key):
        C = self.crafting
        P = self._plan()
        self._bp_begin()
        self.lbl_bp_crumb.configure(text="MY PLAN")
        self._w("MY CRAFTING PLAN\n", "h1")
        if not P["items"]:
            self._w("Nothing in your plan yet. Open a blueprint and press + Add to my crafting plan. "
                    "Add as many as you like: the plan adds up every material they need together.\n", "muted")
            return
        owned = self._bp_owned()
        self._w("1  WHAT YOU WANT TO MAKE\n", "h2")
        missing_bp = []
        for x in list(P["items"]):
            b = C.bps.get(x["uuid"])
            if not b:
                continue
            self._w("•  ")
            self._link(" - ", lambda u=x["uuid"]: self._plan_add(u, -1), "bold")
            self._w(f" {x['qty']} x ", "bold")
            self._link(" + ", lambda u=x["uuid"]: self._plan_add(u, 1), "bold")
            self._w("  ")
            self._plink(b["name"], ("bp", b["uuid"]))
            if b["name"].lower() in owned or b["default"]:
                self._w("   blueprint: you have it\n", "good")
            else:
                missing_bp.append(b)
                self._w("   blueprint: not yet\n", "warn")
        if missing_bp:
            self._w("2  GET THESE BLUEPRINTS FIRST\n", "h2")
            for b in missing_bp:
                entries = self._bp_contracts(b, self.bp_detail.get(b["uuid"]))
                known = [e for e in entries if e["m"]]
                legal = [e for e in known if not e["m"].get("illegal")]
                self._w("•  ")
                self._plink(b["name"], ("bp", b["uuid"]))
                if known:
                    pick = min(legal or known, key=lambda e: (e["m"].get("min_rep") or 0, e["m"].get("rank") or 0))
                    self._w(": ")
                    self._plink(pick["m"]["title"], ("mis", pick["m"]["uuid"]))
                    self._w(f" ({pick['fac']}, needs {self._rep_text(pick['m'])})\n", "muted")
                else:
                    self._w(": open it to see the contracts that give it\n", "muted")
        needs = self._plan_needs()
        have = P["have"]
        self._w(("3" if missing_bp else "2") + "  MATERIALS FOR EVERYTHING\n", "h2")
        self._w("Click HAVE to type how much you already have. Green means you have enough.\n", "small")
        left_total = 0
        for name in sorted(needs, key=lambda n: -max(0, needs[n]["need"] - have.get(n, 0))):
            d = needs[name]
            h = have.get(name, 0)
            left = max(0.0, d["need"] - h)
            done = left <= 1e-9
            unit = d["unit"]
            fmt = (lambda v: f"{v:,.2f}".rstrip("0").rstrip(".")) if unit == "SCU" else (lambda v: f"{v:,.0f}")
            self._w("✓  " if done else "•  ", "good" if done else "")
            self._plink(name, ("mat", name), "bold")
            self._w(f"   need {fmt(d['need'])} {unit}, ")
            self._link(f"have {fmt(h)}", lambda n=name, u=unit: self._plan_set_have(n, u))
            if done:
                self._w("   enough\n", "good")
                continue
            left_total += left if unit == "SCU" else 0
            self._w(f",  still need {fmt(left)} {unit}\n", "warn")
            hint = self._mat_short(name)
            if hint:
                self._w(f"       mine it: {hint}\n", "muted")
            oname, offers = self._refine_offers(name)
            if offers:
                term, val, _age = offers[0]
                self._w(f"       refine at: {term.name} ({val:+g}% yield)\n", "muted")
            buys = self._buy_offers(name)
            if buys:
                term, price = buys[0]
                self._w(f"       or buy it: {term.name}, {price:,.0f} aUEC/SCU (about "
                        f"{price * left:,.0f} for what you still need)\n", "muted")
        self._w(("4" if missing_bp else "3") + "  CRAFT\n", "h2")
        if left_total <= 1e-9 and not missing_bp:
            self._w("You have every blueprint and enough of every material. Head to a fabricator.\n", "good")
        else:
            parts = []
            if missing_bp:
                parts.append(f"{len(missing_bp)} blueprint{'s' if len(missing_bp) != 1 else ''} to get")
            if left_total > 1e-9:
                parts.append(f"{left_total:,.2f} SCU of materials to gather".replace(".00 ", " "))
            self._w("Still to do: " + " and ".join(parts) + ".\n", "muted")
        self._w("\n")
        self._link("Clear the plan", self._plan_clear)
        self._w("   (keeps what you have)\n", "small")

    def _plan_clear(self):
        if messagebox.askyesno(APP_TITLE, "Remove every blueprint from your crafting plan?"):
            self._plan()["items"] = []
            self._plan_save()
            self._bp_render()

    def _bp_load_detail(self, uid):
        self.bp_detail[uid] = None  # loading

        def work():
            try:
                d = crafting.fetch_blueprint_detail(uid)
            except Exception as e:
                hotkeys_win.log(f"blueprint detail {uid}: {e!r}")
                d = {}

            def fin():
                self.bp_detail[uid] = d or {}
                if self.bp_page == ("bp", uid):
                    self._bp_render()
            self._ui(fin)
        threading.Thread(target=work, daemon=True).start()

    def _bp_page_mat(self, name):
        C = self.crafting
        t = self._bp_begin()
        self.lbl_bp_crumb.configure(text="MATERIAL")
        users = C.materials.get(name, [])
        self._w(name + "\n", "h1")
        self._w(f"Used in {len(users)} blueprint{'s' if len(users) != 1 else ''}.\n", "muted")

        self._w("WHERE TO FIND IT\n", "h2")
        rows = self.world.ore_sources(name, self.here)
        if rows:
            how = {"ship": "ship mining", "vehicle": "ROC mining", "hand": "hand mining",
                   "harvestable": "harvest", "log": "your log"}
            for r in rows[:10]:
                self._w("•  ")
                self._link(r["source"], lambda s=r["source"]: self._bp_open_body(s))
                share = "" if r["share"] is None else f"  {r['share']:g}% of deposits"
                if r["method"] == "log":
                    share = f"  {r.get('count', 0)} of your finds"
                dist = ""
                if r["distance_km"] is not None:
                    dist = "  ·  here" if r["distance_km"] == 0 else f"  ·  {core.fmt_km(r['distance_km'])} away"
                self._w(f"  ({r['system']}, {how.get(r['method'], r['method'])}){share}{dist}\n", "muted")
            if len(rows) > 10:
                self._w(f"   and {len(rows) - 10} more places.  ", "small")
            self._link("Open in MINE > FINDER", lambda: self._bp_open_finder(name))
            self._w("\n")
        else:
            self._w("Starboard has no spawn data for it. ", "muted")
            self._link("Search the Wiki", lambda: webbrowser.open(
                "https://starcitizen.tools/index.php?search=" + name.replace(" ", "+")))
            self._w("\n")
        g = getattr(self, "gtext", None)
        if g and g.data:
            places = []
            for body in self.world.bodies.values():
                lists = g.mineables(body.name)
                if lists and any(name.lower() in x.lower() for x in lists[0] + lists[1]):
                    places.append(body.name)
            if places:
                self._w("The game itself lists it on: " + ", ".join(sorted(places)[:14]) + "\n", "small")

        self._w("WHERE TO REFINE IT\n", "h2")
        oname, offers = self._refine_offers(name)
        if offers:
            self._w(f"Refining {oname}, best yield first:\n", "muted")
            for term, val, _age in offers[:6]:
                self._w("•  " + term.name + "  ")
                self._w(self._place_of(term), "muted")
                self._w(f"  {val:+g}% yield\n", "good" if (val or 0) > 0 else ("bad" if (val or 0) < 0 else "muted"))
            self._link("All refinery yields for it", lambda o=oname: self._shop_show("refine", o))
            self._w("  ·  ")
            self._link("Track a refinery job", lambda: self._home_go("refining"))
            self._w("\n")
        else:
            self._w("No refinery yields for it (a gem or item goes straight into crafting, or UEX has no data).\n",
                    "muted")

        self._w("OR BUY IT\n", "h2")
        buys = self._buy_offers(name)
        if buys:
            for term, price in buys[:5]:
                self._w("•  " + term.name + "  ")
                self._w(self._place_of(term), "muted")
                self._w(f"  {price:,.0f} aUEC/SCU\n", "bold")
        else:
            self._w("No terminal sells it (according to UEX).\n", "muted")

        self._w("USED IN\n", "h2")
        owned = self._bp_owned()
        for b in sorted(users, key=lambda b: (b["name"].lower() not in owned, b["name"]))[:80]:
            amt = next((i for i in b["ingredients"] if i["name"] == name), {})
            q = f"{amt['scu']:g} SCU" if amt.get("scu") else (f"{amt['qty']:g} x" if amt.get("qty") else "")
            self._w("•  ")
            self._plink(b["name"], ("bp", b["uuid"]))
            self._w(f"  {q}" + ("  (you own it)" if b["name"].lower() in owned else "") + "\n", "muted")
        if len(users) > 80:
            self._w(f"   and {len(users) - 80} more. Type {name} in FIND to see them all.\n", "small")

    def _bp_open_body(self, src):
        self.ore_body.set(src)
        self._fill_ores()
        self._show(self.tab_ores)

    def _bp_open_finder(self, name):
        self.ore_material.set(name)
        self._fill_finder()
        self._show(self.tab_finder)

    def _bp_page_mis(self, uid):
        C = self.crafting
        m = C.missions.get(uid)
        t = self._bp_begin()
        self.lbl_bp_crumb.configure(text="CONTRACT")
        if not m:
            self._w("This contract is not in the mission list yet. Missions may still be downloading.\n", "warn")
            return
        self._w(m["title"] + "\n", "h1")
        self._w("  ·  ".join(x for x in (m.get("type"), m.get("giver")) if x) + "\n", "muted")
        self._w("Faction  ", "bold")
        fac = m.get("faction") or m.get("giver") or "Unknown"
        self._plink(fac, ("fac", fac))
        self._w("    ")
        self._legal_tag(m)
        self._w("\nYou need  ", "bold")
        need = self._rep_text(m)
        dd = self.bp_mdetail.get(uid) or {}
        mn = ((dd.get("reputation_prerequisite") or {}).get("min_standing") or {})
        if mn.get("name") and "placeholder" not in mn["name"].lower():
            rep_n = mn.get("min_reputation")
            need = mn["name"] + (f" ({rep_n:,} rep)" if isinstance(rep_n, (int, float)) and rep_n > 0 else "")
        self._w(need + (f" with {fac}" if need != "any standing" else "") + "\n")
        bits = []
        if m.get("systems"):
            bits.append("in " + ", ".join(m["systems"]))
        rew = self._mi_reward(m)
        if rew:
            bits.append("pays " + rew)
        if m.get("rep"):
            bits.append(f"+{m['rep']:g} reputation")
        if m.get("minutes"):
            bits.append(f"about {m['minutes']:g} min")
        if m.get("shareable"):
            bits.append("can be shared")
        if bits:
            self._w("  ·  ".join(bits) + "\n", "muted")

        self._w("BLUEPRINTS IT CAN GIVE\n", "h2")
        owned = self._bp_owned()
        bps = C.blueprints_of(m)
        if not bps:
            self._w("None.\n", "muted")
        for b in bps:
            self._w("•  ")
            if b.get("uuid"):
                self._plink(b["name"], ("bp", b["uuid"]))
            else:
                self._w(b["name"])
            if b["name"].lower() in owned:
                self._w("  (you own it)", "good")
            self._w("\n")

        d = self.bp_mdetail.get(uid)
        if d is None and uid not in self.bp_mdetail:
            self._bp_load_mission(uid)
        if d:
            pools = d.get("blueprints") or []
            chances = [p.get("drop_chance_percent") for p in pools if isinstance(p, dict)]
            if chances and any(c is not None and c < 100 for c in chances):
                self._w("Chance of a blueprint: " + ", ".join(f"{c:g}%" for c in chances if c is not None) + "\n",
                        "warn")
            pre = []
            for g in d.get("prerequisite_groups") or []:
                for pm in (g or {}).get("missions") or []:
                    if isinstance(pm, dict) and pm.get("title"):
                        pre.append(pm)
            if pre:
                self._w("DO FIRST\n", "h2")
                self._w("This contract unlocks after one of these:\n", "muted")
                for pm in pre[:12]:
                    self._w("•  ")
                    if pm.get("uuid") in C.missions:
                        self._plink(pm["title"], ("mis", pm["uuid"]))
                    else:
                        self._w(pm["title"])
                    self._w("\n")
            rp = d.get("reputation_prerequisite") or {}
            mn, mx = rp.get("min_standing") or {}, rp.get("max_standing") or {}
            if mn.get("name") and "placeholder" not in mn["name"].lower():
                self._w("REPUTATION\n", "h2")
                self._w(f"Offered from {mn['name']} ({mn.get('min_reputation', 0):,} rep)")
                if mx.get("name") and "placeholder" not in mx["name"].lower():
                    self._w(f" up to {mx['name']}")
                self._w(f" with {rp.get('faction') or fac}.\n")
            locs = wikidata.mission_locations(d)
            if locs:
                self._w("WHERE\n", "h2")
                for name in locs[:8]:
                    loc = self._find_place(name)
                    self._w("•  ")
                    if loc:
                        self._link(name, lambda l=loc: (self._set_target(l), self._hk_say(f"Target: {l.name}")))
                        self._w("  (click to set as target)", "small")
                    else:
                        self._w(name)
                    self._w("\n")
            desc = wikidata.clean_text(d.get("description") or "")
            if desc:
                self._w("BRIEFING\n", "h2")
                self._w(desc[:900] + ("..." if len(desc) > 900 else "") + "\n", "muted")
        elif uid in self.bp_mdetail:
            self._w("\nLoading details from the Wiki...\n", "small")
        self._w("\n")
        self._link("Show in MISSIONS", lambda: self._bp_show_mission(m))
        if m.get("web"):
            self._w("    ")
            self._link("Open on the Star Citizen Wiki", lambda u=m["web"]: webbrowser.open(u))
        self._w("\n")

    def _bp_load_mission(self, uid):
        self.bp_mdetail[uid] = None

        def work():
            try:
                d = wikidata.fetch_mission_detail(uid)
            except Exception as e:
                hotkeys_win.log(f"mission detail {uid}: {e!r}")
                d = {}

            def fin():
                self.bp_mdetail[uid] = d or {}
                if self.bp_page == ("mis", uid):
                    self._bp_render()
            self._ui(fin)
        threading.Thread(target=work, daemon=True).start()

    def _bp_show_mission(self, m):
        self.mi_q.set(m["title"])
        self.mi_type.set("All types")
        self.mi_sys.set("All systems")
        self.mi_legal.set("Legal and illegal")
        self._mi_fill()
        self._show(self.tab_missions)
        for iid, mm in self._mi_map.items():
            if mm is m or mm.get("uuid") == m["uuid"]:
                self.tree_mi.selection_set(iid)
                self.tree_mi.see(iid)
                break

    def _bp_page_fac(self, fac):
        C = self.crafting
        t = self._bp_begin()
        self.lbl_bp_crumb.configure(text="FACTION")
        ms = C.factions.get(fac, [])
        self._w(fac + "\n", "h1")
        legal = sum(1 for m in ms if not m.get("illegal"))
        self._w(f"{len(ms)} contracts from this faction can give blueprints: {legal} legal, "
                f"{len(ms) - legal} illegal.\n", "muted")
        self._w("CONTRACTS, LOWEST REPUTATION FIRST\n", "h2")
        for m in sorted(ms, key=lambda m: (m.get("min_rep") or 0, m.get("rank") or 0, m["title"])):
            self._w("•  ")
            self._plink(m["title"], ("mis", m["uuid"]))
            self._w("  ")
            self._legal_tag(m)
            self._w(f"  ·  needs {self._rep_text(m)}  ·  {len(m.get('bps') or [])} blueprint(s)\n", "muted")
        self._w("BLUEPRINTS FROM THIS FACTION\n", "h2")
        owned = self._bp_owned()
        bps = C.faction_blueprints(fac)
        for b in sorted(bps, key=lambda b: b["name"])[:150]:
            self._w("•  ")
            self._plink(b["name"], ("bp", b["uuid"]))
            self._w(f"  {b['type']}" + ("  (you own it)" if b["name"].lower() in owned else "") + "\n", "muted")
        if len(bps) > 150:
            self._w(f"   and {len(bps) - 150} more.\n", "small")

    def _tab_lazy(self, tab):
        """Download data the first time a tab that needs it is opened."""
        if tab is getattr(self, "tab_craft", None):
            if not self.bp_rows:
                self._bp_fetch()
            if not self.mi_rows or "bps" not in self.mi_rows[0]:
                self._mi_fetch(force=True)
        if tab is getattr(self, "tab_missions", None) and not self.mi_rows:
            self._mi_fetch()
        if tab is getattr(self, "tab_loadout", None) and not self.lo_items:
            self._lo_fetch()

    # ------------------------------------------------------------ live (Game.log)
    def _build_live(self, parent):
        import json
        st = self._settings()
        self.gl = None
        self.gl_q = queue.Queue()
        self.gl_lookups = gamelog.Lookups(self.world.user_dir)
        self.gl_store_path = os.path.join(self.world.user_dir, "gamelog.json")
        try:
            with open(self.gl_store_path, encoding="utf-8") as f:
                self.gl_store = json.load(f)
        except Exception:
            self.gl_store = {}
        self.gl_store.setdefault("logged", [])
        self.gl_store.setdefault("last_ts", None)
        self.gl_store.setdefault("guid", {})
        self.gl_store.setdefault("sessions", [])
        if not hasattr(self, "mydata"):
            self.mydata = mydata.MyData(self.world.user_dir)
        self.gl_rec = mydata.Recorder(self.mydata, self.gl_store["guid"])
        self.gl_session = {"handle": None, "geid": None, "place": None, "body": None, "armistice": False,
                           "ship": None, "joined": None, "jur": None, "live": False}
        self.gl_contracts = {}
        self.gl_feed = []
        self.gl_shop_stock = {}
        self.gl_pending = None
        self._gl_dirty = False

        top = tk.Frame(parent, bg=PANEL)
        top.pack(fill="x")
        self.lbl_gl = tk.Label(top, text="GAME LOG: STARTING", bg=PANEL, fg=CYAN, font=(self.F_UI, 12, "bold"),
                               anchor="w")
        self.lbl_gl.pack(side="left")
        self.gl_on = tk.BooleanVar(value=st.get("gl_enabled", True))
        ttk.Checkbutton(top, text="READ GAME LOG", variable=self.gl_on, style="Panel.TCheckbutton",
                        command=self._gl_toggled).pack(side="right")
        ttk.Button(top, text="CHOOSE FILE", command=self._gl_choose).pack(side="right", padx=6)
        ttk.Button(top, text="FIND", command=lambda: self._gl_start(force_find=True)).pack(side="right")
        ttk.Button(top, text="SESSIONS", command=self._sessions_window).pack(side="right", padx=(0, 6))
        self.lbl_gl2 = self._lbl(parent, "", 9, FG, wraplength=740)
        self.lbl_gl2.pack(anchor="w", pady=(2, 0))
        self.lbl_gl_path = self._lbl(parent, "", 7, MUTED, wraplength=740)
        self.lbl_gl_path.pack(anchor="w")

        opts = tk.Frame(parent, bg=PANEL)
        opts.pack(fill="x", pady=(4, 2))
        self._lbl(opts, "ADD TO MONEY BY ITSELF", 7, MUTED, bold=True).pack(side="left", padx=(0, 8))
        self.gl_opt = {}
        for key, label, default in (("gl_trades", "TRADES", True), ("gl_shopping", "SHOP BUYS", True),
                                    ("gl_contracts", "CONTRACT PAYOUTS", True),
                                    ("gl_bounties", "BOUNTIES", True), ("gl_ship", "MY SHIP", True)):
            v = tk.BooleanVar(value=st.get(key, default))
            self.gl_opt[key] = v
            cb = ttk.Checkbutton(opts, text=label, variable=v, style="Panel.TCheckbutton",
                                 command=lambda k=key, var=v: self._save_setting(k, var.get()))
            cb.pack(side="left", padx=(0, 10))
        self._tip(opts, "What Starboard does with the game log: put commodity trades, shop purchases and contract "
                        "payouts in your ledger with the exact amounts, add bounty contracts to COMBAT, and switch "
                        "MY SHIPS to the ship you are flying (when it is in your hangar).")

        self._section(parent, "contracts this session", ORANGE)
        self.tree_glc = self._tree(parent, [("title", "CONTRACT", 330), ("st", "STATUS", 90), ("reward", "REWARD", 100),
                                            ("when", "TIME", 80)])
        self.tree_glc.master.pack_configure(expand=False)
        self.tree_glc.bind("<<TreeviewSelect>>", lambda ev: self._gl_contract_show())
        crow = tk.Frame(parent, bg=PANEL)
        crow.pack(fill="x", pady=(4, 0))
        self.lbl_glc = self._lbl(crow, "Click a contract for its details from the Star Citizen Wiki.", 8, MUTED,
                                 wraplength=560)
        self.lbl_glc.pack(side="left", fill="x", expand=True)
        ttk.Button(crow, text="WIKI", command=self._gl_contract_wiki).pack(side="right")
        ttk.Button(crow, text="I WAS PAID", command=self._gl_contract_paid).pack(side="right", padx=(4, 0))
        ttk.Button(crow, text="FLY TO", style="Accent.TButton", command=self._gl_contract_fly).pack(side="right",
                                                                                                    padx=4)
        self.tree_glc.tag_configure("done", foreground=GREEN)
        self.tree_glc.tag_configure("failed", foreground=MUTED)
        self._section(parent, "activity", CYAN)
        self.tree_glf = self._tree(parent, [("when", "TIME", 70), ("what", "WHAT", 120), ("detail", "DETAILS", 420)])
        self.tree_glf.configure(height=7)
        for tag, col in (("in", GREEN), ("out", AMBER), ("warn", RED), ("dim", MUTED), ("hi", CYAN)):
            self.tree_glf.tag_configure(tag, foreground=col)
        self._lbl(parent, "Starboard reads Star Citizen's own Game.log; it never touches the game. Money it adds to "
                          "the ledger is marked GAME in the note column, and contract rewards come from the Star "
                          "Citizen Wiki, so check them in your mobiGlas.", 8, MUTED,
                  wraplength=740).pack(anchor="w", pady=(4, 0))

    def _gl_save(self):
        import json
        try:
            self.gl_store["logged"] = self.gl_store["logged"][-3000:]
            tmp = self.gl_store_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.gl_store, f)
            os.replace(tmp, self.gl_store_path)
        except OSError:
            pass

    def _gl_toggled(self):
        self._save_setting("gl_enabled", self.gl_on.get())
        if self.gl_on.get():
            self._gl_start()
        else:
            self._gl_stop()
            self.lbl_gl.configure(text="GAME LOG: OFF", fg=MUTED)

    def _gl_choose(self):
        path = filedialog.askopenfilename(title="Pick Star Citizen's Game.log", filetypes=[("Game log", "*.log")])
        if path:
            self._save_setting("gl_path", path)
            self._gl_start()

    def _gl_stop(self):
        if self.gl:
            self.gl.stop()
            self.gl = None

    def _gl_start(self, force_find=False):
        if not hasattr(self, "gl_on"):
            return
        self._gl_stop()
        if not self.gl_on.get():
            self.lbl_gl.configure(text="GAME LOG: OFF", fg=MUTED)
            return
        path = None if force_find else self._settings().get("gl_path")
        if not path or not os.path.isfile(path):
            found = gamelog.find_logs()
            path = found[0][0] if found else None
            if force_find and path:
                self._save_setting("gl_path", path)
        if not path:
            self.lbl_gl.configure(text="GAME LOG: NOT FOUND", fg=AMBER)
            self.lbl_gl2.configure(text="Starboard could not find Star Citizen's Game.log. Click CHOOSE FILE and pick "
                                        "Game.log in your StarCitizen\\LIVE folder (for example C:\\Program Files\\"
                                        "Roberts Space Industries\\StarCitizen\\LIVE).", fg=FG)
            return
        self.gl_path = path
        self._gt_load()
        self.lbl_gl_path.configure(text=path)
        self.lbl_gl.configure(text="GAME LOG: READING", fg=CYAN)
        self.gl = gamelog.Watcher(path, lambda e, live: self.gl_q.put(("ev", e, live)),
                                  lambda st: self.gl_q.put(("st", st)))
        self.gl.start()
        if not getattr(self, "_gl_polling", False):
            self._gl_polling = True
            self.root.after(250, self._gl_poll)

    # ------------------------------------------------------------ the game's own text
    def _gt_dirs(self):
        out = []
        gp = getattr(self, "gl_path", None) or self._settings().get("gl_path")
        if gp:
            out.append(os.path.dirname(gp))
        for root in gamelog.candidate_dirs():
            d = os.path.join(root, "LIVE")
            if os.path.isdir(d) and d not in out:
                out.append(d)
        return out

    def _gt_load(self, force=False):
        """Names of items, ships, places and contracts from the game itself (a text mod, or Data.p4k)."""
        if not hasattr(self, "gtext"):
            self.gtext = gametext.GameText(self.world.user_dir)
        chosen = self._settings().get("gametext_path")
        dirs = self._gt_dirs()
        if not force and self.gtext.load_cached(dirs, chosen):
            gamelog.TEXT = self.gtext
            self._gt_status()
            return
        if getattr(self, "_gt_loading", False):
            return
        self._gt_loading = True
        self._gt_status()

        def work():
            if force:
                try:
                    os.remove(self.gtext.cache_path)
                except OSError:
                    pass
            ok = self.gtext.load(dirs, chosen, log=hotkeys_win.log)

            def fin():
                self._gt_loading = False
                if ok:
                    gamelog.TEXT = self.gtext
                self._gt_status()
            self._ui(fin)
        threading.Thread(target=work, daemon=True).start()

    def _gt_status(self):
        if not hasattr(self, "lbl_gt"):
            return
        g = getattr(self, "gtext", None)
        if getattr(self, "_gt_loading", False):
            self.lbl_gt.configure(text="Reading the game's text... (only after a game patch, it takes a moment)",
                                  fg=CYAN)
        elif g and g.data:
            c = g.counts()
            src = {"mod": "your text mod (for example StarStrings)", "p4k": "the game's Data.p4k",
                   "file": "the file you picked", "cache": "the last copy Starboard saved"}.get(g.kind, g.kind)
            self.lbl_gt.configure(text=(
                f"Using {src}: {c.get('items', 0):,} item names, {c.get('vehicles', 0):,} ships, "
                f"{c.get('places', 0):,} places, {c.get('titles', 0):,} contract titles. {g.source}"), fg=GREEN)
        else:
            why = f" ({g.error})" if g and g.error else ""
            self.lbl_gt.configure(text=(
                "Not found yet" + why + ". Starboard looks in your StarCitizen\\LIVE folder (next to Game.log). "
                "Press PICK FILE to choose global.ini or Data.p4k yourself."), fg=AMBER)

    def _gt_pick(self):
        p = filedialog.askopenfilename(title="Pick global.ini (text mod) or Data.p4k (in StarCitizen\\LIVE)",
                                       filetypes=[("Game text", "*.ini *.p4k"), ("All", "*.*")])
        if p:
            self._save_setting("gametext_path", p)
            self._gt_load(force=True)

    def _gl_poll(self):
        n = 0
        try:
            while n < 3000:
                item = self.gl_q.get_nowait()
                n += 1
                try:
                    if item[0] == "ev":
                        self._gl_event(item[1], item[2])
                    elif item[0] == "st":
                        self._gl_status(item[1])
                    elif item[0] == "call":
                        item[1]()
                except Exception as e:
                    hotkeys_win.log(f"game log event error: {e!r}")
        except queue.Empty:
            pass
        if self._gl_dirty:
            self._gl_dirty = False
            self._gl_refresh()
            self._gl_save()
            try:
                self.gl_rec.flush()
            except Exception:
                pass
        self.root.after(250 if n < 3000 else 20, self._gl_poll)

    def _gl_status(self, st):
        if st == "caught up":
            self.gl_session["live"] = True
            if self.gl_store.get("last_ts") is None:
                # first time: start counting from here, never import older sessions
                self.gl_store["last_ts"] = getattr(self, "_gl_max_seen", 0) or time.time()
        elif st == "new session":
            self.gl_contracts.clear()
            self.gl_feed.clear()
            self.gl_session.update(place=None, body=None, armistice=False, joined=None, jur=None)
        elif st == "missing":
            self.gl_session["live"] = False
        self._gl_dirty = True

    def _gl_covers(self, category):
        """True when the game log is reading and already logs this kind of money."""
        if not (self.gl and self.gl_session.get("live") and self.gl_session.get("joined")):
            return False
        o = self.gl_opt
        return (category in ("Trade purchase", "Trade sale") and o["gl_trades"].get()) or \
            (category == "Contract payout" and o["gl_contracts"].get())

    def _gl_feed(self, ts, what, detail, tag=""):
        self.gl_feed.append((ts, what, detail, tag))
        del self.gl_feed[:-400]
        self._gl_dirty = True

    def _gl_fresh(self, ev, live):
        """Should this event change your data? New lines always; while catching up, only lines
        written after the last one Starboard handled (so a restart does not miss or repeat money)."""
        last = self.gl_store.get("last_ts")
        return live or (last is not None and ev["ts"] > last)

    def _gl_once(self, key):
        if key in self.gl_store["logged"]:
            return False
        self.gl_store["logged"].append(key)
        return True

    @staticmethod
    def _gl_shop(name):
        n = re.sub(r"^(SCShop_|TDD_)", "", name or "")
        n = re.sub(r"[-_]?SCShop[-_]?\d*$|[-_]\d+$", "", n)
        n = re.sub(r"_(m|s|l)_store$", "", n)
        return gamelog.split_words(n) if n else "TDD" if name.startswith("TDD") else name

    def _gl_event(self, ev, live):
        try:
            self.gl_rec.feed(ev)
        except Exception as e:
            hotkeys_win.log(f"my data: {e!r}")
        S = self.gl_session
        t = ev["type"]
        fresh = self._gl_fresh(ev, live)
        ts = ev["ts"]
        if t == "handle":
            S["handle"] = ev["handle"]
            if ev.get("geid"):
                S["geid"] = ev["geid"]
        elif t == "join":
            S["joined"] = ts
            self._gl_feed(ts, "SERVER", f"Joined {ev.get('shard') or 'a server'}", "hi")
            ss = self.gl_store["sessions"]
            if ss and ss[-1].get("end") is None and ts - ss[-1]["start"] < 6 * 3600:
                pass  # changing servers inside one play session
            elif not any(abs(x["start"] - ts) < 1 for x in ss):
                ss.append({"start": ts, "end": None})
                del ss[:-200]
        elif t == "quit":
            S["joined"] = None
            self._gl_feed(ts, "GAME", "Game closed", "dim")
            ss = self.gl_store["sessions"]
            if ss and ss[-1].get("end") is None and ts >= ss[-1]["start"]:
                ss[-1]["end"] = ts
        elif t == "location":
            if S["handle"] and ev["player"] != S["handle"]:
                pass
            elif ev["name"] != S["place"]:
                S["place"], S["body"] = ev["name"], ev["body"]
                self._gl_feed(ts, "LOCATION", ev["name"] + (f" ({ev['body']})" if ev["body"] else ""), "hi")
        elif t == "armistice":
            if ev["on"] != S["armistice"]:
                S["armistice"] = ev["on"]
                self._gl_feed(ts, "ARMISTICE", "Entered armistice zone: combat prohibited" if ev["on"] else
                              "Left armistice zone: combat caution",
                              "" if ev["on"] else "out")
        elif t == "jurisdiction":
            if ev["name"] != S["jur"]:
                S["jur"] = ev["name"]
                self._gl_feed(ts, "JURISDICTION", f"Entered {ev['name']} jurisdiction", "dim")
                hot = self._illegal_cargo()
                if hot and live:
                    self._alert("illegal", f"{ev['name']} jurisdiction",
                                "You are carrying " + ", ".join(f"{v:g} SCU {k}" for k, v in hot.items()) +
                                ". Security can scan you here.", bad=True)
        elif t == "contract":
            self._gl_contract(ev, fresh)
        elif t == "contract_def":
            c = self.gl_contracts.setdefault(ev["mission"], {"title": "", "state": "", "ts": ts})
            c["code"] = ev.get("contract")
            if c.get("def") != ev["definition"]:
                c["def"] = ev["definition"]
                c["generator"] = ev["generator"]
                self._gl_lookup_reward(ev["mission"])
        elif t == "contract_end":
            c = self.gl_contracts.get(ev["mission"])
            if c and ev["how"] in ("Fail", "Abandon", "Abandoned") and c.get("state") in ("Accepted", "Shared", ""):
                self._gl_contract({"type": "contract", "state": "Failed" if ev["how"] == "Fail" else "Abandoned",
                                   "title": c.get("title", ""), "mission": ev["mission"], "ts": ts}, fresh)
        elif t == "shop_stock":
            stock = self.gl_shop_stock.get(ev["shop"])
            if not stock or ts - stock[0] > 30:
                stock = (ts, set())
                self.gl_shop_stock[ev["shop"]] = stock
            stock[1].add(ev["commodity"])
        elif t == "trade":
            self._gl_trade(ev, fresh)
        elif t == "purchase":
            self._gl_purchase(ev, fresh)
        elif t == "tx_error":
            p = self.gl_pending
            if p and 0 <= ts - p["ts"] < 10:
                if p.get("entry"):
                    self.ledger.delete(p["entry"])
                    self._fill_ledger()
                self._gl_feed(ts, "SHOP", f"Purchase failed ({ev['text']}): {p['what']}", "warn")
                self.gl_pending = None
        elif t == "ship":
            label = f"{ev['maker']} {ev['model']}".strip()
            if label != S["ship"]:
                S["ship"] = label
                self._gl_feed(ts, "SHIP", label, "dim")
                if fresh and self.gl_opt["gl_ship"].get():
                    self._gl_match_ship(ev)
        elif t == "destroyed":
            me = S["handle"] and ev["killer"] == S["handle"]
            mine = S["geid"] and S["geid"] in (ev["owner"], ev["driver"])
            if me and not mine:
                self._gl_feed(ts, "KILL", f"You destroyed a {ev['ship']} ({ev['reason'].lower()})", "in")
            elif mine:
                self._gl_feed(ts, "SHIP LOST", f"Your {ev['ship']} was destroyed ({ev['reason'].lower()})", "warn")
        elif t == "kill":
            if S["handle"] and S["handle"] in (ev["victim"], ev["killer"]):
                if ev["victim"] == S["handle"]:
                    self._gl_feed(ts, "DEATH", f"Killed by {ev['killer']} ({ev['weapon']})", "warn")
                else:
                    self._gl_feed(ts, "KILL", f"You killed {ev['victim']} ({ev['weapon']})", "in")
        elif t == "incap":
            self._gl_feed(ts, "DOWN", "You were incapacitated", "warn")
        elif t == "blueprint":
            self._gl_feed(ts, "BLUEPRINT", ev["item"], "in")
        elif t == "earned":
            self._gl_feed(ts, "REWARD", ev["item"], "in")
        elif t == "notice":
            self._gl_feed(ts, "NOTICE", ev["text"], "dim")
        last = self.gl_store.get("last_ts")
        if live or last is not None:
            self.gl_store["last_ts"] = max(ts, last or 0)
        else:
            self._gl_max_seen = max(ts, getattr(self, "_gl_max_seen", 0))
        self._gl_dirty = True

    def _gl_contract_sel(self):
        sel = self.tree_glc.selection()
        if not sel:
            return None
        title = self.tree_glc.item(sel[0])["values"][0]
        return next((c for c in self.gl_contracts.values() if c.get("title") == title), None)

    def _gl_contract_show(self):
        c = self._gl_contract_sel()
        if not c:
            return
        info = c.get("info") or {}
        bits = [c.get("kind") or info.get("type", ""), info.get("giver", ""),
                f"reward {self._gl_reward_text(c)}"]
        if info.get("locations"):
            bits.append("where: " + ", ".join(info["locations"][:6]))
        if not c.get("def"):
            bits.append("no Wiki match yet (the game names the contract once you get its first objective)")
        text = "   ·   ".join(b for b in bits if b)
        g = getattr(self, "gtext", None)
        if g and g.data and c.get("code"):
            _title, brief = g.contract(c["code"])
            if brief:
                brief = re.sub(r"~mission\((\w+)\)", r"[\1]", brief)
                text += "\n\nBRIEFING (from the game): " + re.sub(r"\n{2,}", "\n", brief)[:700]
        self.lbl_glc.configure(text=text, fg=FG)

    def _find_place(self, name):
        """A location in Starboard's map for a place name from another source (exact, then loose)."""
        n = (name or "").strip().lower()
        if not n:
            return None
        exact = next((l for l in self.world.locations if l.name.lower() == n), None)
        if exact:
            return exact

        def squash(x):
            return re.sub(r"[^a-z0-9]", "", x.lower())
        sn = squash(n)
        return next((l for l in self.world.locations if squash(l.name) == sn), None) or \
            next((l for l in self.world.locations if len(sn) > 4 and sn in squash(l.name)), None)

    def _gl_contract_fly(self):
        c = self._gl_contract_sel()
        locs = ((c or {}).get("info") or {}).get("locations") or []
        for nm in locs:
            loc = self._find_place(nm)
            if loc:
                self._set_target(loc)
                self._hk_say(f"Target: {loc.name}")
                return
        messagebox.showinfo(APP_TITLE, "This contract has no place Starboard knows on the map. Use the marker the "
                                       "contract gives you in game." if c else "Click a contract first.")

    def _gl_contract_paid(self):
        """Type what a contract really paid: it goes in the ledger and Starboard remembers it for next time."""
        c = self._gl_contract_sel()
        if not c:
            messagebox.showinfo(APP_TITLE, "Click a contract first.")
            return
        txt = simpledialog.askstring(APP_TITLE, f"How much did '{c['title']}' pay you? (aUEC, as shown in your "
                                                "mobiGlas)", parent=self.root)
        amount = ledger.parse_amount(txt) if txt else None
        if not amount or amount <= 0:
            return
        mid = next((k for k, v in self.gl_contracts.items() if v is c), None)
        logged = [e for e in self.ledger.entries if e.get("ref") and e.get("ref") == c.get("def")
                  and abs(e["time"] - c["ts"]) < 120]
        if logged:
            self.ledger.update(logged[-1]["id"], amount=amount)
            self._fill_ledger()
        else:
            e = self._ledger_log(ledger.INCOME, "Bounty" if self._gl_is_bounty(c) else "Contract payout", amount,
                                 f"GAME {c['title']}", estimate=False, source="gamelog",
                                 where=self.gl_session.get("place") or "", when=c["ts"])
            if e and c.get("def"):
                e["ref"], e["ref_title"] = c["def"], c["title"]
                self.ledger.save()
            if mid:
                self._gl_once(f"pay:{mid}")
        if c.get("def"):
            self.mydata.learn_reward(c["def"], c["title"], amount)
        c["reward"], c["reward_mine"] = amount, True
        self._gl_dirty = True
        self._hk_say(f"Saved: {c['title']} pays {ledger.short_money(amount)}")

    def _gl_contract_wiki(self):
        c = self._gl_contract_sel()
        web = ((c or {}).get("info") or {}).get("web")
        if web:
            webbrowser.open(web)

    # ------------------------------------------------------------ sessions
    ACTIVITY = {"Trade sale": "Hauling", "Trade purchase": "Hauling", "Mining sale": "Mining", "Refining": "Mining",
                "Salvage sale": "Salvage", "Bounty": "Combat", "Ammunition": "Combat", "Contract payout": "Contracts",
                "Mission reward": "Contracts"}

    def _session_stats(self, start, end):
        end = end or time.time()
        es = [e for e in self.ledger.entries if e["kind"] != ledger.ADJUST and start <= e["time"] <= end]
        inc = sum(e["amount"] for e in es if e["amount"] > 0)
        out = -sum(e["amount"] for e in es if e["amount"] < 0)
        hours = max((end - start) / 3600, 1e-6)
        by = {}
        for e in es:
            k = self.ACTIVITY.get(e["category"], "Other")
            by[k] = by.get(k, 0) + e["amount"]
        return {"entries": len(es), "income": inc, "spent": out, "net": inc - out, "hours": hours,
                "per_hour": (inc - out) / hours, "by": by}

    def _sessions(self):
        """Play sessions from the game log; without it, ledger entries grouped by 2 hour gaps."""
        ss = [dict(x) for x in self.gl_store.get("sessions", []) if x.get("start")] if hasattr(self, "gl_store") \
            else []
        if ss:
            for i, x in enumerate(ss):
                if x.get("end") is None:
                    nxt = ss[i + 1]["start"] if i + 1 < len(ss) else None
                    x["end"] = nxt if nxt else (time.time() if self.gl_session.get("joined") else None)
                    if x["end"] is None:
                        last = [e["time"] for e in self.ledger.entries if e["time"] >= x["start"]]
                        x["end"] = max(last) if last else x["start"] + 60
            return ss, "game"
        times = sorted(e["time"] for e in self.ledger.entries if e["kind"] != ledger.ADJUST)
        out = []
        for t in times:
            if out and t - out[-1]["end"] < 7200:
                out[-1]["end"] = t
            else:
                out.append({"start": t, "end": t})
        for x in out:
            x["end"] = max(x["end"], x["start"] + 900)
        return out, "ledger"

    def _sessions_window(self):
        w = tk.Toplevel(self.root)
        w.title(f"{APP_TITLE}: sessions")
        w.configure(bg=PANEL)
        w.geometry(f"{int(760 * self.scale)}x{int(420 * self.scale)}")
        try:
            w.attributes("-topmost", self.on_top.get())
        except tk.TclError:
            pass
        frame = tk.Frame(w, bg=PANEL, padx=10, pady=10)
        frame.pack(fill="both", expand=True)
        ss, src = self._sessions()
        tree = self._tree(frame, [("when", "STARTED", 120), ("len", "LENGTH", 70), ("in", "EARNED", 90),
                                  ("out", "SPENT", 90), ("net", "NET", 90), ("ph", "PER HOUR", 90),
                                  ("best", "MOST FROM", 150)])
        tree.tag_configure("pos", foreground=GREEN)
        tree.tag_configure("neg", foreground=AMBER)
        self._sess_tree = tree
        shown = 0
        for x in reversed(ss[-60:]):
            st = self._session_stats(x["start"], x["end"])
            if not st["entries"]:
                continue
            best = max(st["by"].items(), key=lambda kv: kv[1]) if st["by"] else ("", 0)
            h = st["hours"]
            tree.insert("", "end", tags=("pos" if st["net"] >= 0 else "neg",) + (("odd",) if shown % 2 else ()),
                        values=(clock_str(time.localtime(x["start"]), "%a %d %b %H:%M"),
                                f"{int(h)}h {int(h * 60) % 60:02d}m", ledger.money(st["income"]),
                                ledger.money(st["spent"]), ("+" if st["net"] >= 0 else "") + ledger.money(st["net"]),
                                ledger.short_money(st["per_hour"]) if h >= 0.25 else "-",
                                f"{best[0]} {ledger.short_money(best[1])}" if best[0] else ""))
            shown += 1
        note = ("Sessions come from the game log (each time you started playing)." if src == "game" else
                "No game sessions recorded yet, so these group your ledger entries: a gap of two hours starts a "
                "new one.")
        self._lbl(frame, f"{shown} sessions with money in them. {note} Per hour counts the whole session, "
                         "not only the time you were earning.", 8, MUTED, wraplength=700).pack(anchor="w", pady=(6, 0))
        ttk.Button(frame, text="CLOSE", command=w.destroy).pack(anchor="e", pady=(6, 0))
        return w

    def _gl_reward_text(self, c):
        r = c.get("reward")
        if r is None:
            return "looking up" if c.get("def") else "?"
        return ledger.money(r) if r else "none"

    def _gl_lookup_reward(self, mid):
        c = self.gl_contracts.get(mid)
        if not c or not c.get("def"):
            return

        def done(value):
            def apply():
                cc = self.gl_contracts.get(mid)
                if cc is None:
                    return
                cc["reward"] = float((value or {}).get("reward") or 0) if value else 0
                mine = self.mydata.reward(cc.get("def"))
                if mine:
                    cc["reward"], cc["reward_mine"] = float(mine), True
                cc["kind"] = (value or {}).get("type", "")
                cc["info"] = value or {}
                if cc.get("await_pay"):
                    cc.pop("await_pay")
                    self._gl_pay(mid)
                self._gl_dirty = True
            self.gl_q.put(("call", apply))
        self.gl_lookups.lookup("mission", c["def"], done)

    @staticmethod
    def _gl_is_bounty(c):
        text = f"{c.get('title', '')} {c.get('kind', '')} {c.get('generator', '')}".lower()
        return "bounty" in text

    @staticmethod
    def _gl_rank(title):
        t = title.upper()
        for code, words in (("ERT", "EXTREME"), ("VHRT", "VERY HIGH"), ("HRT", "HIGH RISK"), ("MRT", "MEDIUM"),
                            ("VLRT", "VERY LOW"), ("LRT", "LOW RISK")):
            if re.search(rf"\b{code}\b", t) or words in t:
                return code
        return "Other"

    def _gl_contract(self, ev, fresh):
        mid, state, ts = ev["mission"], ev["state"], ev["ts"]
        c = self.gl_contracts.setdefault(mid, {"title": "", "state": "", "ts": ts})
        if ev.get("title"):
            c["title"] = ev["title"]
        if c.get("state") == state:
            return  # the game repeats the same notification
        if state == "Accepted" and c.get("state") in ("Complete", "Failed", "Abandoned"):
            return
        c["state"], c["ts"] = state, ts
        tag = {"Complete": "in", "Failed": "warn", "Abandoned": "warn"}.get(state, "hi")
        self._gl_feed(ts, "CONTRACT", f"{state}: {c['title']}", tag)
        if c.get("def") and "reward" not in c:
            self._gl_lookup_reward(mid)
        if not fresh:
            return
        if state in ("Complete", "Failed") and self.gl_session.get("live"):
            self._alert("contract", f"Contract {state.lower()}", c["title"] or "A contract", bad=state == "Failed")
        if state == "Accepted" and self.gl_opt["gl_bounties"].get() and self._gl_is_bounty(c) and \
                self._gl_once(f"bounty-add:{mid}"):
            b = self.bounties.add(target=c["title"], rank=self._gl_rank(c["title"]), reward=c.get("reward") or 0,
                                  where="", place=None, note="Added from the game log", mission=mid)
            c["bounty"] = b["id"]
            self._fill_bounties()
        if state == "Complete":
            if c.get("def") and "reward" not in c:
                c["await_pay"] = True  # pay once the wiki answers
            else:
                self._gl_pay(mid)
        elif state in ("Failed", "Abandoned"):
            b = self._gl_find_bounty(mid)
            if b and b.get("status") == "Active":
                self.bounties.update(b["id"], status="Failed", finished=ts)
                self._fill_bounties()

    def _gl_find_bounty(self, mid):
        return next((b for b in self.bounties.items if b.get("mission") == mid), None)

    def _gl_pay(self, mid):
        c = self.gl_contracts.get(mid)
        if not c or not self._gl_once(f"pay:{mid}"):
            return
        reward = float(c.get("reward") or 0)
        b = self._gl_find_bounty(mid)
        bounty = self._gl_is_bounty(c)
        if b:
            self.bounties.update(b["id"], status="Done", finished=c["ts"], reward=reward or b.get("reward") or 0)
            self._fill_bounties()
        if not self.gl_opt["gl_contracts"].get() or reward <= 0:
            if reward <= 0:
                self._gl_feed(c["ts"], "PAYOUT", f"{c['title']}: reward unknown, add it in MONEY if you were paid", "out")
            return
        src = "your last payout" if c.get("reward_mine") else "wiki reward"
        e = self._ledger_log(ledger.INCOME, "Bounty" if bounty else "Contract payout", reward,
                             f"GAME {c['title']} ({src}, check mobiGlas)", estimate=True, source="gamelog",
                             where=self.gl_session.get("place") or "", when=c["ts"])
        if e and c.get("def"):
            e["ref"], e["ref_title"] = c["def"], c["title"]
            self.ledger.save()
        self._gl_feed(c["ts"], "PAYOUT", f"+{ledger.money(reward)} {c['title']}", "in")

    def _gl_commodity(self, ev):
        guid = ev["guid"]
        name = self.gl_store["guid"].get(guid)
        if name:
            return name
        stock = self.gl_shop_stock.get(ev["shop"])
        if ev["side"] == "buy" and stock and len(stock[1]) == 1 and ev["ts"] - stock[0] < 120:
            name = next(iter(stock[1]))
            self.gl_store["guid"][guid] = name
            return name
        return None

    def _gl_trade(self, ev, fresh):
        name = self._gl_commodity(ev)
        cargo = self.gl_session.setdefault("cargo", {})
        if name:
            cargo[name] = max(0.0, cargo.get(name, 0) + (ev["scu"] if ev["side"] == "buy" else -ev["scu"]))
        verb = "Bought" if ev["side"] == "buy" else "Sold"
        shop_txt = self.gl_session.get("place") or self._gl_shop(ev["shop"])
        what = f"{verb} {ev['scu']:g} SCU {name or 'cargo'} at {shop_txt}"
        self._gl_feed(ev["ts"], "TRADE", f"{what}: {ledger.money(ev['amount'])}",
                      "out" if ev["side"] == "buy" else "in")
        entry = None
        if fresh and self.gl_opt["gl_trades"].get() and \
                self._gl_once(f"trade:{ev['ts']:.3f}:{ev['amount']:.0f}"):
            entry = self._ledger_log(ledger.EXPENSE if ev["side"] == "buy" else ledger.INCOME,
                                     "Trade purchase" if ev["side"] == "buy" else "Trade sale", ev["amount"],
                                     f"GAME {what}", estimate=False, source="gamelog",
                                     where=self.gl_session.get("place") or shop_txt, when=ev["ts"])
            self.gl_pending = {"ts": ev["ts"], "entry": entry["id"] if entry else None, "what": what}
        if not name:
            def done(value, eid=entry["id"] if entry else None, guid=ev["guid"]):
                n = (value or {}).get("name")
                if not n:
                    return

                def apply():
                    self.gl_store["guid"][guid] = n
                    self.mydata.learn_name(guid, n)
                    self.gl_feed[:] = [(a, b, c.replace(" cargo ", f" {n} ", 1) if b == "TRADE" else c, d)
                                       for a, b, c, d in self.gl_feed]
                    e = self.ledger.get(eid) if eid else None
                    if e and " cargo " in e.get("note", ""):
                        e["note"] = e["note"].replace(" cargo ", f" {n} ", 1)
                        self.ledger.save()
                        self._fill_ledger()
                    self._gl_dirty = True
                self.gl_q.put(("call", apply))
            self.gl_lookups.lookup("commodity", ev["guid"], done)

    def _gl_purchase(self, ev, fresh):
        shop_txt = self._gl_shop(ev["shop"])
        what = f"{ev['qty']}x {ev['item']} at {shop_txt}" if ev["qty"] > 1 else f"{ev['item']} at {shop_txt}"
        self._gl_feed(ev["ts"], "SHOP", f"{what}: {ledger.money(ev['amount'])}", "out")
        entry = None
        if fresh and self.gl_opt["gl_shopping"].get() and ev["amount"] > 0 and \
                self._gl_once(f"buy:{ev['ts']:.3f}:{ev['amount']:.0f}"):
            cat = "Ammunition" if re.search(r"mag|ammo|battery", ev["cls"], re.I) else "Item purchase"
            entry = self._ledger_log(ledger.EXPENSE, cat, ev["amount"], f"GAME {what}", estimate=False,
                                     source="gamelog", where=self.gl_session.get("place") or shop_txt, when=ev["ts"])
        self.gl_pending = {"ts": ev["ts"], "entry": entry["id"] if entry else None, "what": what}
        if fresh:
            self.gl_lookups.lookup("item", ev["guid"], lambda v, g=ev["guid"]: (v or {}).get("name") and self._ui(
                lambda: self.mydata.learn_name(g, v["name"])))

    def _gl_match_ship(self, ev):
        """Make the ship you are flying the active one in MY SHIPS, if you own it."""
        model = re.sub(r"[^a-z0-9]", "", ev["model"].lower())
        if not model or not self.hangar.ships:
            return
        best = None
        for sh in self.hangar.ships:
            name = re.sub(r"[^a-z0-9]", "", f"{sh.get('setup') or ''}{sh['ship']}".lower())
            if model in name or re.sub(r"[^a-z0-9]", "", sh["ship"].lower()).endswith(model):
                best = sh
                break
        if best and best["id"] != self.hangar.active:
            self.hangar.set_active(best["id"])
            self._ship_apply(best)
            self._fill_hangar()
            self._gl_feed(ev["ts"], "SHIP", f"MY SHIPS now uses your {self.hangar.label(best)}", "hi")

    def _gl_refresh(self):
        S = self.gl_session
        if not self.gl:
            return
        if S.get("joined") and S.get("live"):
            self.lbl_gl.configure(text="GAME LOG: LIVE", fg=GREEN)
        elif S.get("live"):
            self.lbl_gl.configure(text="GAME LOG: WAITING FOR THE GAME", fg=CYAN)
        bits = []
        if S.get("handle"):
            bits.append(f"Pilot {S['handle']}")
        if S.get("place"):
            bits.append(f"at {S['place']}" + (f" ({S['body']})" if S.get("body") else ""))
        if S.get("ship"):
            bits.append(f"ship {S['ship']}")
        if S.get("armistice"):
            bits.append("in an armistice zone")
        if S.get("joined"):
            sess = self._session_stats(S["joined"], None)
            if sess["entries"]:
                bits.append(f"this session {'+' if sess['net'] >= 0 else ''}{ledger.short_money(sess['net'])}"
                            + (f" ({ledger.short_money(sess['per_hour'])}/h)" if sess["hours"] >= 0.25 else ""))
        if not bits:
            bits.append("No game session yet. Start Star Citizen and this fills in by itself.")
        self.lbl_gl2.configure(text="   ·   ".join(bits), fg=FG)
        t = self.tree_glf
        t.delete(*t.get_children())
        feed = sorted(self.gl_feed[-200:], key=lambda f: f[0], reverse=True)
        for i, (ts, what, detail, tag) in enumerate(feed):
            when = clock_str(time.localtime(ts), "%H:%M:%S")
            t.insert("", "end", values=(when, what, detail), tags=tuple(x for x in (tag, "odd" if i % 2 else "") if x))
        t = self.tree_glc
        t.delete(*t.get_children())
        rows = sorted(self.gl_contracts.items(), key=lambda kv: kv[1].get("ts", 0), reverse=True)
        for i, (mid, c) in enumerate(rows):
            if not c.get("title"):
                continue
            tag = "done" if c["state"] == "Complete" else "failed" if c["state"] in ("Failed", "Abandoned") else ""
            when = clock_str(time.localtime(c.get("ts", 0)), "%H:%M")
            t.insert("", "end", values=(c["title"], c["state"], self._gl_reward_text(c), when),
                     tags=tuple(x for x in (tag, "odd" if i % 2 else "") if x))

    # ------------------------------------------------------------ settings
    def _start_geometry(self, st):
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        name = st.get("window_size", "Remember last size")
        size = dict(WINDOW_SIZES).get(name)
        geom = st.get("window_geom")
        if size is None and geom:
            m = re.match(r"(\d+)x(\d+)([+-]-?\d+)([+-]-?\d+)$", str(geom))
            if m:
                def coord(t):  # Windows saves a window left of or above the main screen as "+-1289"
                    t = t[1:] if t.startswith("+") else t
                    try:
                        return int(t)
                    except ValueError:
                        return None
                w, h, x, y = int(m[1]), int(m[2]), coord(m[3]), coord(m[4])
                vx, vy, vw, vh = self._desktop_area()
                if x is not None and y is not None and vx - w // 2 < x < vx + vw - 80 and \
                        vy <= y < vy + vh - 80 and w <= vw and h <= vh:
                    return f"{w}x{h}+{x}+{y}"  # Tk writes a position left of the main screen as +-1289
        if size is None:
            size = (800, min(980, max(820, int((sh - 90) / self.scale))))
        w, h = int(size[0] * self.scale), int(size[1] * self.scale)
        return f"{min(w, sw)}x{min(h, sh - 60)}"

    @staticmethod
    def _mouse_held():
        """True while the left mouse button is down (dragging the window edge, Windows only)."""
        if not sys.platform.startswith("win"):
            return False
        try:
            import ctypes
            return bool(ctypes.windll.user32.GetAsyncKeyState(0x01) & 0x8000)
        except Exception:  # noqa: BLE001
            return False

    def _frozen(self, fn):
        """Run a layout change with painting switched off for the whole window, then paint it
        once. On Windows every widget is its own window and otherwise repaints piece by piece
        (the black buttons while resizing)."""
        hwnd = None
        if sys.platform.startswith("win"):
            try:
                import ctypes
                hwnd = int(self.root.wm_frame(), 16)
                ctypes.windll.user32.SendMessageW(hwnd, 0x000B, 0, 0)  # WM_SETREDRAW off
            except Exception:  # noqa: BLE001
                hwnd = None
        try:
            fn()
            self.root.update_idletasks()
        finally:
            if hwnd:
                import ctypes
                u = ctypes.windll.user32
                u.SendMessageW(hwnd, 0x000B, 1, 0)  # WM_SETREDRAW on
                # RDW_ERASE | RDW_FRAME | RDW_INVALIDATE | RDW_ALLCHILDREN | RDW_UPDATENOW
                u.RedrawWindow(hwnd, None, None, 0x0004 | 0x0400 | 0x0001 | 0x0080 | 0x0100)

    def _desktop_area(self):
        """(x, y, width, height) of the whole desktop across every monitor."""
        if sys.platform.startswith("win"):
            try:
                import ctypes
                g = ctypes.windll.user32.GetSystemMetrics
                vw, vh = g(78), g(79)
                if vw > 0 and vh > 0:
                    return g(76), g(77), vw, vh
            except Exception:  # noqa: BLE001
                pass
        return 0, 0, self.root.winfo_screenwidth(), self.root.winfo_screenheight()

    def _wheel_scroll(self, cv, e):
        """Smooth wheel scrolling: wheel and touchpad movement is added up and applied once per
        frame in small fixed steps, instead of one big jump per event."""
        if getattr(e, "num", 0) in (4, 5):
            notches = 1.0 if e.num == 4 else -1.0
        else:
            notches = (e.delta / 120.0) if abs(e.delta) >= 1 else 0.0
            if abs(e.delta) < 120 and abs(e.delta) >= 1 and sys.platform == "darwin":
                notches = e.delta / 4.0
        cv._wheel_acc = getattr(cv, "_wheel_acc", 0.0) - notches * 3  # three steps per notch
        if not getattr(cv, "_wheel_job", None):
            def apply():
                cv._wheel_job = None
                steps = int(cv._wheel_acc)
                if steps:
                    cv._wheel_acc -= steps
                    try:
                        cv.yview_scroll(steps, "units")
                    except tk.TclError:
                        pass
            cv._wheel_job = cv.after(12, apply)

    def _build_scroller(self):
        """Everything sits in one frame that scrolls when the window is too short for it (large text sizes).
        When it fits, the frame simply fills the window as before."""
        cv = tk.Canvas(self.root, bg=BG, highlightthickness=0, bd=0)
        sb = ttk.Scrollbar(self.root, orient="vertical", command=cv.yview)
        cv.configure(yscrollcommand=sb.set)
        cv.configure(yscrollincrement=max(8, int(18 * self.scale)))
        body = tk.Frame(cv, bg=BG)
        win = cv.create_window(0, 0, window=body, anchor="nw")
        cv.pack(side="left", fill="both", expand=True)
        self.body, self._body_cv, self._body_sb = body, cv, sb
        state = {"job": None, "last": None, "size": None, "req": None}

        def fit():
            state["job"] = None
            if state.get("dragging") and self._mouse_held():
                state["job"] = cv.after(80, fit)  # still dragging the window edge: lay out when let go
                return
            state["dragging"] = False
            need = body.winfo_reqheight()
            h, w = cv.winfo_height(), cv.winfo_width()
            if h <= 1:
                return
            too_tall = need > h + 2
            if too_tall and not sb.winfo_ismapped():
                sb.pack(side="right", fill="y", before=cv)
            elif not too_tall and sb.winfo_ismapped():
                sb.pack_forget()
                cv.yview_moveto(0)
            want = (w, max(h, need))
            if want != state["last"]:  # only lay the window out again when its size really changed
                width_changed = not state["last"] or state["last"][0] != w
                state["last"] = want

                def apply():
                    cv.itemconfigure(win, width=w, height=want[1])
                    cv.configure(scrollregion=(0, 0) + want)
                    if width_changed and hasattr(self, "header"):
                        self.root.update_idletasks()  # let the banner take its new width first
                        self._draw_header()
                if width_changed:
                    self._frozen(apply)  # a new width moves everything: paint it once, at the end
                else:
                    apply()

        def window_resized(e):
            # while the window is being dragged or maximized, wait until it settles, then lay out once
            size = (e.width, e.height)
            if size == state["size"]:
                return
            state["size"] = size
            state["dragging"] = self._mouse_held()
            if state["job"]:
                cv.after_cancel(state["job"])
            state["job"] = cv.after(120, fit)

        def content_changed(_e=None):
            req = body.winfo_reqheight()
            if req == state["req"]:
                return  # scrolling moves the frame; that is not a change in size
            state["req"] = req
            if not state["job"]:
                state["job"] = cv.after_idle(fit)
        cv.bind("<Configure>", window_resized)
        body.bind("<Configure>", content_changed)

        def wheel(e):
            if not sb.winfo_ismapped():
                return
            w = e.widget
            if not isinstance(w, tk.Misc):
                return
            if not str(w).startswith(str(cv) + "."):
                return  # another window (overlay, a dialog)
            up = e.delta > 0 or e.num == 4
            while w is not None and w is not cv:
                if w.winfo_class() == "TCombobox":
                    return
                if w.winfo_class() in ("Treeview", "Text", "Listbox") or \
                        (getattr(w, "_scrolls", False) and w.winfo_ismapped()):
                    # a list or page with its own scrolling: it scrolls first, and once it reaches
                    # its top or bottom the whole window carries on
                    try:
                        first, last = (float(x) for x in w.yview())
                    except (tk.TclError, ValueError, TypeError):
                        return
                    if (up and first > 0.0005) or (not up and last < 0.9995):
                        return
                    break
                w = w.master
            self._wheel_scroll(cv, e)
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.root.bind_all(seq, wheel, add="+")

    def _scrollable(self, parent):
        """A frame that scrolls with the mouse wheel when its content is taller than the tab."""
        cv = tk.Canvas(parent, bg=PANEL, highlightthickness=0, bd=0)
        sb = ttk.Scrollbar(parent, orient="vertical", command=cv.yview)
        inner = tk.Frame(cv, bg=PANEL)
        cv._scrolls = True
        cv.configure(yscrollincrement=max(8, int(18 * self.scale)))
        win = cv.create_window(0, 0, window=inner, anchor="nw")
        cv.configure(yscrollcommand=sb.set)

        seen = [None]

        def fit(_e=None):
            key = (inner.winfo_reqwidth(), inner.winfo_reqheight(), cv.winfo_height())
            if key == seen[0]:
                return  # scrolling moved the page; nothing to lay out
            seen[0] = key
            cv.configure(scrollregion=(0, 0, key[0], key[1]))
            if key[1] > key[2]:
                if not sb.winfo_ismapped():
                    sb.pack(side="right", fill="y", before=cv)
            elif sb.winfo_ismapped():
                sb.pack_forget()
                cv.yview_moveto(0)
        inner.bind("<Configure>", fit)
        last_w = [None]

        def resized(e):
            if e.width != last_w[0]:
                last_w[0] = e.width
                cv.itemconfigure(win, width=e.width - 4)
            fit()
        cv.bind("<Configure>", resized)

        def wheel(e):
            if inner.winfo_reqheight() > cv.winfo_height():
                self._wheel_scroll(cv, e)
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            cv.bind_all(seq, lambda e: wheel(e) if str(e.widget).startswith(str(cv)) else None, add="+")
        cv.pack(side="left", fill="both", expand=True)
        return inner

    def _build_settings(self, parent):
        st = self._settings()
        top = tk.Frame(parent, bg=PANEL)
        top.pack(fill="x", pady=(0, 2))
        ttk.Button(top, text="APPLY AND RESTART", style="Accent.TButton",
                   command=self._settings_apply).pack(side="left")
        ttk.Button(top, text="RESET TO DEFAULTS", command=self._settings_reset).pack(side="left", padx=6)
        ttk.Button(top, text="WELCOME GUIDE", command=lambda: WelcomeDialog(self.root, self)).pack(side="right")
        self.lbl_set_msg = self._lbl(parent, "Most changes work right away. Text size, font, color mode and window "
                                             "size need APPLY AND RESTART. Nothing you saved is lost.", 8, MUTED,
                                     wraplength=740)
        self.lbl_set_msg.pack(anchor="w", pady=(2, 0))
        parent = self._scrollable(parent)
        self._section(parent, "text", CYAN)
        r = tk.Frame(parent, bg=PANEL)
        r.pack(fill="x", pady=(2, 2))
        self._lbl(r, "TEXT SIZE", 7, MUTED, bold=True).pack(side="left")
        names = [n for n, _ in TEXT_SIZES]
        cur = min(TEXT_SIZES, key=lambda t: abs(t[1] - self.scale))[0]
        self.set_size = tk.StringVar(value=cur)
        cb = ttk.Combobox(r, textvariable=self.set_size, values=names, state="readonly", width=12)
        cb.pack(side="left", padx=(6, 16))
        cb.bind("<<ComboboxSelected>>", lambda e: self._settings_preview())
        self._lbl(r, "FONT", 7, MUTED, bold=True).pack(side="left")
        have = set(tkfont.families())
        fonts = [f for f in FONT_CHOICES if f == "Default" or f in have]
        self.set_font = tk.StringVar(value=st.get("font", "Default") if st.get("font", "Default") in fonts
                                     else "Default")
        cb = ttk.Combobox(r, textvariable=self.set_font, values=fonts, state="readonly", width=20)
        cb.pack(side="left", padx=(6, 0))
        cb.bind("<<ComboboxSelected>>", lambda e: self._settings_preview())
        self.lbl_set_preview = tk.Label(parent, text="Port Tressler  ·  120,180 km  ·  QT to Lyria OM-1",
                                        bg=PANEL_HI, fg=FG, anchor="w", padx=10, pady=6)
        self.lbl_set_preview.pack(fill="x", pady=(4, 2))
        tip = "Atkinson Hyperlegible and OpenDyslexic are free fonts made for easier reading. "
        missing = [f for f in ("Atkinson Hyperlegible", "OpenDyslexic") if f not in have]
        self._lbl(parent, (tip + "Install one in Windows and it shows up here." if missing else tip), 8, MUTED,
                  wraplength=700).pack(anchor="w")

        self._section(parent, "color", ORANGE)
        r = tk.Frame(parent, bg=PANEL)
        r.pack(fill="x", pady=(2, 2))
        self._lbl(r, "COLOR MODE", 7, MUTED, bold=True).pack(side="left")
        self.set_color = tk.StringVar(value=COLOR_MODE)
        cb = ttk.Combobox(r, textvariable=self.set_color, values=COLOR_MODES, state="readonly", width=24)
        cb.pack(side="left", padx=(6, 0))
        cb.bind("<<ComboboxSelected>>", lambda e: self._settings_preview())
        self.set_swatch = tk.Frame(parent, bg=PANEL)
        self.set_swatch.pack(fill="x", pady=(4, 2))
        self._lbl(parent, "Pick Red-green if red and green look alike to you, Blue-yellow if blue and yellow do. "
                          "High contrast: black backgrounds and bright text.", 8, MUTED,
                  wraplength=700).pack(anchor="w")

        self._section(parent, "window", GREEN)
        r = tk.Frame(parent, bg=PANEL)
        r.pack(fill="x", pady=(2, 2))
        self._lbl(r, "SIZE", 7, MUTED, bold=True).pack(side="left")
        self.set_win = tk.StringVar(value=st.get("window_size", "Remember last size"))
        ttk.Combobox(r, textvariable=self.set_win, state="readonly", width=18,
                     values=[n if v is None else f"{n}" for n, v in WINDOW_SIZES]).pack(side="left", padx=(6, 16))
        self._lbl(r, "WINDOW OPACITY", 7, MUTED, bold=True).pack(side="left")
        self.set_alpha = tk.StringVar(value=f"{int(st.get('opacity', 100))}%")
        cb = ttk.Combobox(r, textvariable=self.set_alpha, state="readonly", width=6,
                          values=["100%", "95%", "90%", "85%", "80%", "70%", "60%"])
        cb.pack(side="left", padx=(6, 16))
        cb.bind("<<ComboboxSelected>>", lambda e: self._set_opacity())
        self._lbl(r, "OVERLAY OPACITY", 7, MUTED, bold=True).pack(side="left")
        self.set_ov_alpha = tk.StringVar(value=f"{int(st.get('overlay_opacity', 90))}%")
        cb = ttk.Combobox(r, textvariable=self.set_ov_alpha, state="readonly", width=6,
                          values=["100%", "90%", "80%", "70%", "60%", "50%", "40%", "30%"])
        cb.pack(side="left", padx=(6, 0))
        cb.bind("<<ComboboxSelected>>", lambda e: self._set_overlay_opacity())
        self._tip(cb, "How see-through the in-game overlay is. Lower shows more of the game behind it.")
        r = tk.Frame(parent, bg=PANEL)
        r.pack(fill="x", pady=(4, 0))
        ttk.Checkbutton(r, text="ALWAYS ON TOP", variable=self.on_top, style="Panel.TCheckbutton",
                        command=self._on_top_changed).pack(side="left")
        ttk.Checkbutton(r, text="START IN COMPACT VIEW", variable=self.compact, style="Panel.TCheckbutton",
                        command=self._compact_from_settings).pack(side="left", padx=(16, 0))
        r = tk.Frame(parent, bg=PANEL)
        r.pack(fill="x", pady=(6, 0))
        self._lbl(r, "CLOCK", 7, MUTED, bold=True).pack(side="left")
        self.set_clock = tk.StringVar(value="12 hour (3:45 PM)" if st.get("clock_12h") else "24 hour (15:45)")
        cb = ttk.Combobox(r, textvariable=self.set_clock, state="readonly", width=16,
                          values=["24 hour (15:45)", "12 hour (3:45 PM)"])
        cb.pack(side="left", padx=(6, 10))
        cb.bind("<<ComboboxSelected>>", lambda e: self._set_clock())
        self._lbl(r, "Times use your PC's clock and time zone.", 8, MUTED).pack(side="left")

        self._section(parent, "tickers", GREEN)
        r = tk.Frame(parent, bg=PANEL)
        r.pack(fill="x", pady=(2, 2))
        self.tick_vars = {}
        tc = self._ticker_cfg()
        for k, label in (("market", "MARKET TICKER (COMMODITY PRICES)"), ("news", "NEWS TICKER (SERVERS, VIDEOS, COMM-LINK)")):
            v = tk.BooleanVar(value=tc[k])
            self.tick_vars[k] = v
            ttk.Checkbutton(r, text=label, variable=v, style="Panel.TCheckbutton",
                            command=self._ticker_save).pack(side="left", padx=(0, 20))
        self._lbl(parent, "Two strips under the banner. MARKET shows what terminals pay per SCU and how it moved "
                          "since about a day ago (green up, red down). NEWS shows RSI server status, patch deployments, new "
                          "videos and Comm-Link posts. "
                          "Hover over a strip to pause it, click an item to open it.", 8, MUTED,
                  wraplength=700).pack(anchor="w")

        self._section(parent, "overlay", PURPLE)
        r = tk.Frame(parent, bg=PANEL)
        r.pack(fill="x", pady=(2, 2))
        self.ov_vars = {}
        op = self.overlay_parts()
        for i, (k, label) in enumerate(self.OVERLAY_PARTS):
            v = tk.BooleanVar(value=op[k])
            self.ov_vars[k] = v
            ttk.Checkbutton(r, text=label.upper(), variable=v, style="Panel.TCheckbutton",
                            command=self._overlay_parts_save).grid(row=i // 3, column=i % 3, sticky="w",
                                                                   padx=(0, 20))
        self._lbl(parent, "Pick what the in-game overlay shows (OVERLAY ON at the top). Each part only appears when "
                          "it has something to show, and the overlay grows to fit.", 8, MUTED,
                  wraplength=700).pack(anchor="w")

        self._section(parent, "alerts", AMBER)
        ac = self._alert_cfg()
        self.alert_vars = {}
        r = tk.Frame(parent, bg=PANEL)
        r.pack(fill="x", pady=(2, 0))
        for i, (k, label) in enumerate(self.ALERT_KINDS):
            v = tk.BooleanVar(value=ac.get(k, True))
            self.alert_vars[k] = v
            ttk.Checkbutton(r, text=label.upper(), variable=v, style="Panel.TCheckbutton",
                            command=self._alerts_save).grid(row=i // 2, column=i % 2, sticky="w", padx=(0, 20))
        r = tk.Frame(parent, bg=PANEL)
        r.pack(fill="x", pady=(2, 2))
        for k, label in (("popup", "SHOW A POP-UP"), ("sound", "PLAY A SOUND")):
            v = tk.BooleanVar(value=ac.get(k, True))
            self.alert_vars[k] = v
            ttk.Checkbutton(r, text=label, variable=v, style="Panel.TCheckbutton",
                            command=self._alerts_save).pack(side="left", padx=(0, 20))
        ttk.Button(r, text="TEST ALERT", command=self._alert_test).pack(side="right")
        self._lbl(parent, "The pop-up shows in the bottom right corner of your screen, over the game when you play "
                          "in Borderless mode. Contract alerts come from the game log; illegal cargo is what you "
                          "bought and have not sold yet (Altruciatoxin, E'tam, Freeze, Maze, Neon, SLAM, WiDoW and "
                          "similar).", 8, MUTED, wraplength=700).pack(anchor="w")

        self._section(parent, "starboard updates", GREEN)
        r = tk.Frame(parent, bg=PANEL)
        r.pack(fill="x", pady=(2, 2))
        self.upd_check = tk.BooleanVar(value=self._settings().get("update_check", True))
        ttk.Checkbutton(r, text="CHECK FOR A NEW VERSION WHEN STARBOARD STARTS", variable=self.upd_check,
                        style="Panel.TCheckbutton",
                        command=lambda: self._save_setting("update_check", self.upd_check.get())).pack(side="left")
        ttk.Button(r, text="CHECK NOW", command=lambda: self._update_check(quiet=False)).pack(side="right")
        ttk.Button(r, text="DESKTOP SHORTCUT", command=lambda: self._make_shortcut(quiet=False)).pack(
            side="right", padx=(0, 6))
        r = tk.Frame(parent, bg=PANEL)
        r.pack(fill="x", pady=(2, 2))
        self._lbl(r, "RELEASES FROM", 8, MUTED, bold=True).pack(side="left", padx=(0, 8))
        self.upd_repo = tk.StringVar(value=self._update_repo())
        e = ttk.Entry(r, textvariable=self.upd_repo, width=34)
        e.pack(side="left")
        e.bind("<FocusOut>", lambda _e: self._save_setting("update_repo", self.upd_repo.get().strip()))
        e.bind("<Return>", lambda _e: self._save_setting("update_repo", self.upd_repo.get().strip()))
        self.upd_status = self._lbl(r, f"You have {APP_VERSION}", 8, MUTED)
        self.upd_status.pack(side="left", padx=10)
        self._lbl(parent, "Starboard looks at the latest release on GitHub (owner/name of the project) once a day. "
                          "When a newer version is out it tells you and opens the download page. Your settings, "
                          "hangar, ledger and plans are kept when you install over the top.", 8, MUTED,
                  wraplength=700).pack(anchor="w")

        self._section(parent, "automatic updates", CYAN)
        au = self._auto_cfg()
        self.auto_on = tk.BooleanVar(value=au.get("on", True))
        r = tk.Frame(parent, bg=PANEL)
        r.pack(fill="x", pady=(2, 2))
        ttk.Checkbutton(r, text="KEEP DATA UP TO DATE BY ITSELF", variable=self.auto_on, style="Panel.TCheckbutton",
                        command=self._auto_save).pack(side="left")
        ttk.Button(r, text="UPDATE ALL NOW", command=lambda: self._auto_tick(force=True)).pack(side="right")
        grid = tk.Frame(parent, bg=PANEL)
        grid.pack(fill="x", pady=(2, 2))
        self.auto_vars, self.auto_lbls = {}, {}
        for i, (key, label, _d) in enumerate(self.AUTO_SOURCES):
            self._lbl(grid, label.upper(), 7, MUTED, bold=True).grid(row=i, column=0, sticky="w", pady=2)
            v = tk.StringVar(value=self._auto_label(au.get(key, _d)))
            cb = ttk.Combobox(grid, textvariable=v, state="readonly", width=14,
                              values=[n for n, _h in self.AUTO_CHOICES])
            cb.grid(row=i, column=1, sticky="w", padx=8, pady=2)
            cb.bind("<<ComboboxSelected>>", lambda e: self._auto_save())
            self.auto_vars[key] = v
            lb = self._lbl(grid, "", 8, MUTED)
            lb.grid(row=i, column=2, sticky="w")
            self.auto_lbls[key] = lb
        self._lbl(parent, "Starboard gets new data in the background. If you are offline, it keeps using what it "
                          "already has.", 8, MUTED,
                  wraplength=700).pack(anchor="w")

        self._section(parent, "hotkeys", TEAL)
        self._lbl(parent, "Work in game too. Letters and numbers need Ctrl, Shift or Alt; F-keys can be used alone. "
                          "Leave a box empty to turn that key off. F8, F9 and F10 stay as they are.", 8, MUTED,
                  wraplength=700).pack(anchor="w")
        grid = tk.Frame(parent, bg=PANEL)
        grid.pack(fill="x", pady=(4, 2))
        self.set_hk = {}
        current = self._hotkey_map()
        for i, (action, label, _d) in enumerate(self.HOTKEY_ACTIONS):
            r, c = divmod(i, 2)
            self._lbl(grid, label.upper(), 7, MUTED, bold=True).grid(row=r, column=c * 2, sticky="w",
                                                                     padx=(0 if c == 0 else 20, 6), pady=2)
            v = tk.StringVar(value=current.get(action, ""))
            ttk.Entry(grid, textvariable=v, width=16).grid(row=r, column=c * 2 + 1, sticky="w", pady=2)
            self.set_hk[action] = v
        r = tk.Frame(parent, bg=PANEL)
        r.pack(fill="x", pady=(2, 0))
        ttk.Button(r, text="SAVE HOTKEYS", command=self._hotkeys_save).pack(side="left")
        self.lbl_set_hk = self._lbl(r, "", 8, MUTED)
        self.lbl_set_hk.pack(side="left", padx=8)

        self._section(parent, "comfort", PURPLE)
        r = tk.Frame(parent, bg=PANEL)
        r.pack(fill="x", pady=(2, 0))
        self.set_flash = tk.BooleanVar(value=self.reduce_flash)
        ttk.Checkbutton(r, text="NO BLINKING LIGHTS", variable=self.set_flash, style="Panel.TCheckbutton",
                        command=self._flash_changed).pack(side="left")
        self.set_tips = tk.BooleanVar(value=self.show_tips)
        ttk.Checkbutton(r, text="SHOW HELP TIPS ON HOVER", variable=self.set_tips, style="Panel.TCheckbutton",
                        command=self._tips_changed).pack(side="left", padx=(16, 0))

        self._section(parent, "about and credits", MUTED)
        self._lbl(parent, f"Starboard {APP_VERSION}. Free, open source (GPL-3.0).", 9, FG, bold=True).pack(anchor="w")
        self._lbl(parent, DISCLAIMER, 8, MUTED, wraplength=700).pack(anchor="w", pady=(2, 4))
        self._lbl(parent, f"Your data (settings, hangar, ledger, plans, history): {core.USER_DIR}. It stays when "
                          "you install a new version or uninstall.", 8, MUTED, wraplength=700).pack(anchor="w",
                                                                                                pady=(0, 4))
        self._lbl(parent, "Data: Star Citizen Wiki API (api.star-citizen.wiki) for items, ships, blueprints, missions "
                          "and news. UEX Corp (uexcorp.space) for prices and terminals. VerseTime by dydrmr and the "
                          "Murphy Exploration Group for Stanton and Pyro coordinates. StarMap (starmap.space) for Nyx. "
                          "Star Citizen Location Finder for caves. Full list in README.md.", 8, MUTED,
                  wraplength=700).pack(anchor="w")
        r = tk.Frame(parent, bg=PANEL)
        r.pack(fill="x", pady=(4, 2))
        ttk.Button(r, text="ROBERTS SPACE INDUSTRIES", style="Small.TButton",
                   command=lambda: webbrowser.open("https://robertsspaceindustries.com")).pack(side="left")
        ttk.Button(r, text="OPEN MY DATA FOLDER", style="Small.TButton",
                   command=lambda: os.startfile(core.USER_DIR) if hasattr(os, "startfile") else None).pack(
            side="left", padx=(6, 0))
        ttk.Button(r, text="README", style="Small.TButton",
                   command=lambda: os.startfile(os.path.join(core.HERE, "README.md"))
                   if hasattr(os, "startfile") else None).pack(side="left", padx=(6, 0))

        self._settings_preview()

    def _hotkeys_save(self):
        out, bad, used = {}, [], {"F8", "F9", "F10"}
        for action, label, _d in self.HOTKEY_ACTIONS:
            text = self.set_hk[action].get().strip()
            if not text:
                out[action] = ""
                continue
            parsed = hotkeys_win.parse_hotkey(text)
            if not parsed or parsed[2] in used:
                bad.append(label)
                continue
            used.add(parsed[2])
            out[action] = parsed[2]
            self.set_hk[action].set(parsed[2])
        if bad:
            self.lbl_set_hk.configure(text="Not saved. Check: " + ", ".join(bad) + " (use e.g. Ctrl+Shift+S or F7, "
                                           "each key once).", fg=AMBER)
            return
        self._save_setting("hotkeys_map", out)
        if self.hk:
            self.hk.stop()
            self.hk = None
            self._start_hotkeys()
        self.lbl_set_hk.configure(text="Saved. The new keys work now.", fg=GREEN)

    def _settings_preview(self):
        new = dict(TEXT_SIZES).get(self.set_size.get(), 1.0)
        fam = self.set_font.get()
        fam = self.F_UI if fam == "Default" and not self._settings().get("font") else fam
        if fam == "Default":
            fam = pick_font(["Bahnschrift SemiCondensed", "Bahnschrift", "Segoe UI", "DejaVu Sans"],
                            "TkDefaultFont")
        size = max(6, round(10 * new / self.scale))
        self.lbl_set_preview.configure(font=(fam, size))
        for w in self.set_swatch.winfo_children():
            w.destroy()
        pal = {"GREEN": GREEN, "AMBER": AMBER, "RED": RED, "CYAN": CYAN, "ORANGE": ORANGE}
        if self.set_color.get() != COLOR_MODE:
            base = {"GREEN": "#43e6a6", "AMBER": "#ffb84d", "RED": "#ff5d6c", "CYAN": "#4ab8f5",
                    "ORANGE": "#e9861a"}
            base.update({k: v for k, v in THEMES.get(self.set_color.get(), {}).items() if k in base})
            pal = base
        for key, word in (("GREEN", "GOOD / INCOME / SECURITY"), ("AMBER", "WARNING / HIDEOUT"),
                          ("RED", "DANGER / OUTLAW"), ("CYAN", "HIGHLIGHT"), ("ORANGE", "MAIN BUTTON")):
            f = tk.Frame(self.set_swatch, bg=PANEL)
            f.pack(side="left", padx=(0, 12))
            tk.Frame(f, bg=pal[key], width=14, height=14).pack(side="left")
            tk.Label(f, text=word, bg=PANEL, fg=pal[key], font=(self.F_UI, 8, "bold")).pack(side="left", padx=4)

    def _set_clock(self):
        global CLOCK_12H
        CLOCK_12H = self.set_clock.get().startswith("12")
        self._save_setting("clock_12h", CLOCK_12H)
        # redraw what shows a time now; lists pick it up the next time they refresh
        self._hdr_w = None
        for fn in ("_draw_header", "_refresh_home", "_gl_refresh", "_fill_ledger"):
            try:
                getattr(self, fn)()
            except Exception:
                pass

    def _settings_apply(self):
        st = self._settings()
        new_scale = dict(TEXT_SIZES).get(self.set_size.get(), 1.0)
        if abs(new_scale - float(st.get("text_scale", 1.0) or 1.0)) > 0.01 or \
                self.set_win.get() != st.get("window_size", "Remember last size"):
            self._save_setting("window_geom", None)
            self._keep_geom = False
        self._save_setting("text_scale", new_scale)
        self._save_setting("font", self.set_font.get())
        self._save_setting("color_mode", self.set_color.get())
        self._save_setting("window_size", self.set_win.get())
        self._restart_app()

    def _settings_reset(self):
        self.set_size.set("Normal")
        self.set_font.set("Default")
        self.set_color.set("Default")
        self.set_win.set("Remember last size")
        self.set_alpha.set("100%")
        self._set_opacity()
        self.on_top.set(True)
        self._on_top_changed()
        self.set_flash.set(False)
        self._flash_changed()
        self.set_tips.set(True)
        self._tips_changed()
        for action, _label, d in self.HOTKEY_ACTIONS:
            self.set_hk[action].set(d)
        self._settings_preview()
        self.lbl_set_msg.configure(text="Defaults picked. Press APPLY AND RESTART to use them.", fg=AMBER)

    def _restart_app(self):
        self._restart = True
        closer = getattr(self, "on_close", None)
        if closer:
            closer()
        else:
            self.root.destroy()

    def _set_opacity(self):
        try:
            v = int(self.set_alpha.get().rstrip("%"))
        except ValueError:
            return
        self._save_setting("opacity", v)
        try:
            self.root.attributes("-alpha", v / 100)
        except tk.TclError:
            pass

    # -- MINE > BELTS: getting into asteroid belts that are not on the quantum list
    def _build_belts(self, parent):
        self.belt_plan = None
        self.belt_sel = "aaron"
        pw = ttk.PanedWindow(parent, orient="horizontal")
        pw.pack(fill="both", expand=True)
        left = tk.Frame(pw, bg=PANEL)
        right = tk.Frame(pw, bg=PANEL)
        pw.add(left, weight=1)
        pw.add(right, weight=3)
        self.tree_belts = self._tree(left, [("name", "BELT", 140), ("sys", "SYSTEM", 70)])
        for b in belts.BELTS:
            self.tree_belts.insert("", "end", iid=b["id"], values=(b["name"], b["system"]))
        self.tree_belts.bind("<<TreeviewSelect>>", lambda e: self._belt_pick())
        self._lbl(left, "Press F9 in game (or /showlocation) and Starboard plans from where you are and tells "
                        "you when you are in the belt.", 8, MUTED, wraplength=220).pack(anchor="w", pady=(6, 0))
        box = tk.Frame(right, bg=LINE, padx=1, pady=1)
        box.pack(fill="both", expand=True, padx=(8, 0))
        t = tk.Text(box, bg=CARD, fg=FG, wrap="word", relief="flat", padx=12, pady=10, cursor="arrow",
                    font=(self.F_UI, 10), insertwidth=0, spacing1=1, spacing3=1)
        sb = ttk.Scrollbar(box, orient="vertical", command=t.yview)
        t.configure(yscrollcommand=sb.set)
        t.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        for tag, kw in (("h1", dict(font=(self.F_UI, 16, "bold"), foreground="#ffffff", spacing3=2)),
                        ("h2", dict(font=(self.F_UI, 10, "bold"), foreground=ORANGE, spacing1=12, spacing3=3)),
                        ("muted", dict(foreground=MUTED)), ("small", dict(font=(self.F_UI, 8), foreground=MUTED)),
                        ("good", dict(foreground=GREEN)), ("warn", dict(foreground=AMBER)),
                        ("bold", dict(font=(self.F_UI, 10, "bold"))), ("big", dict(font=(self.F_UI, 12, "bold"),
                                                                                     foreground=CYAN)),
                        ("link", dict(foreground=CYAN, underline=True)),
                        ("step", dict(font=(self.F_UI, 10, "bold"), foreground=CYAN))):
            t.tag_configure(tag, **kw)
        t.tag_bind("link", "<Enter>", lambda e: t.configure(cursor="hand2"))
        t.tag_bind("link", "<Leave>", lambda e: t.configure(cursor="arrow"))
        t.bind("<Key>", lambda e: "break" if e.keysym not in ("Up", "Down", "Prior", "Next", "c") else None)
        self.belt_text = t
        self.tree_belts.selection_set("aaron")

    def _belt_pick(self):
        sel = self.tree_belts.selection()
        if sel:
            self.belt_sel = sel[0]
            self._belt_show()

    def _belt_here(self, belt):
        """Your last fix, if it is in this belt's system."""
        h = self.here
        if h and h.get("system") == belt["system"]:
            return h
        return None

    def _belt_show(self):
        b = belts.get(self.belt_sel)
        if not b:
            return
        old = getattr(self, "_tw", None)
        t = self._bp_begin(self.belt_text)
        self._w(b["name"].upper() + "\n", "h1")
        self._w(f"{b['system']} system\n\n", "muted")
        self._w(b["about"] + "\n")
        here = self._belt_here(b)
        if b["kind"] in ("system", "moon"):
            self._w("WHERE YOU ARE\n", "h2")
            if here:
                w = belts.where(self.world, b, here["global"])
                if w:
                    self._w(("✓ " if w["inside"] else "") + w["text"] + "\n", "good" if w["inside"] else "warn")
                age = (core.utcnow() - here["time"]).total_seconds() if here.get("time") else 0
                if age > 120:
                    self._w(f"From your fix {int(age // 60)} min ago. Press F9 again to update.\n", "small")
            else:
                self._w(f"Press F9 in game (or type /showlocation) while you are in {b['system']} and Starboard "
                        "plans from where you are, then tells you when you are inside.\n", "muted")
        self._w("GET THERE\n", "h2")
        if b["kind"] == "qt":
            self._w("Pick ")
            self._w(b["name"], "bold")
            self._w(" on your quantum list and jump straight there.\n")
        elif b["kind"] == "moon":
            self._w("1. ", "step")
            self._w("Quantum to ")
            self._w(b["body"], "bold")
            self._w(". You arrive close to the inner edge of the ring.\n")
            self._w("2. ", "step")
            self._w(f"Fly away from {b['body']} until you are {b['inner']} to {b['outer']} km from its centre "
                    "(press F9 to check). The ring is flat: look for the band of rocks around the moon.\n")
        else:
            inside = belts.stops_inside(self.world, b)
            if inside:
                self._w("Easiest: ", "bold")
                self._w("quantum straight to " + ", ".join(inside[:3]) + (" (or any other QV Breaker station)"
                                                                          if len(inside) > 3 else "")
                        + ". " + ("It sits" if len(inside) == 1 else "They sit") + " inside the belt.\n")
            w_now = belts.where(self.world, b, here["global"]) if here else None
            if w_now and w_now["inside"]:
                self._w("You are already in it. ", "good")
                self._w("Save good rocks with SAVE SPOT so you can come back.\n", "muted")
            start = ("your position", here["global"]) if here else None
            rs = belts.routes(self.world, b, start=start, when=here["time"] if here else None)
            if rs:
                ring = belts.ring_of(self.world, b)
                self._w(("Or drop out" if inside else "Drop out") + " on the way: set quantum to the "
                        "destination below and leave quantum travel when the distance left reads the number "
                        f"shown. That puts you in {ring[3] if ring else 'the belt'}.\n", "muted")
                self._w(("FROM WHERE YOU ARE\n" if here else "FROM THE MAIN STOPS\n"), "bold")
                for i, r in enumerate(rs, 1):
                    self._w(f"{i}. ", "step")
                    if not here:
                        self._w(f"From {r['from']}: ")
                    self._w("quantum to ")
                    self._w(r["to"], "bold")
                    self._w(", drop out at ")
                    self._w(belts.gm(r["drop"]), "big")
                    self._w(f" left  (between {belts.gm(r['drop_far'])} and {belts.gm(r['drop_near'])}). ",
                            "muted")
                    self._link("SHOW ON OVERLAY", lambda r=r: self._belt_use(b, r))
                    self._w("\n")
                if not here:
                    self._w("Press F9 in game for routes from exactly where you are.\n", "small")
            elif not inside and not (w_now and w_now["inside"]):
                self._w("No route crosses the belt from here. Quantum to a planet or station first, then "
                        "press F9 again.\n", "muted")
        if b.get("bands"):
            self._w("BANDS\n", "h2")
            for n, lo, hi, up, down in b["bands"]:
                star = n == b["target"]
                self._w(f"Band {n:>2}:  {lo / 1e6:.3f} to {hi / 1e6:.3f} Gm from the centre,  "
                        f"{up + down:,} km thick", "bold" if star else "muted")
                self._w("   densest\n" if star else "\n", "good" if star else "muted")
            self._w("Between some bands there are gaps with very few rocks.\n", "small")
        if self.belt_plan and self.belt_plan["belt"] == b["id"]:
            self._w("\nOn your overlay: ", "bold")
            self._w(self.belt_plan["line"] + "  ")
            self._link("CLEAR", self._belt_clear)
            self._w("\n")
        self._w("\n" + b["credit"] + " Quantum travel can steer around planets and moons, so the number can be "
                "off a little: press F9 after you drop out to check.\n", "small")
        t.configure(state="disabled")
        if old is not None:
            self._tw = old

    def _belt_use(self, b, r):
        self.belt_plan = {"belt": b["id"], "name": b["name"], "to": r["to"], "drop": r["drop"],
                          "line": f"Quantum to {r['to']}, drop out at {belts.gm(r['drop'])} left",
                          "set": time.time()}
        parts = self.overlay_parts()
        if not parts.get("belt"):
            self._hk_say("Turn on BELT ROUTE under SETTINGS > OVERLAY to see it in game", ok=False)
        else:
            self._hk_say(f"On the overlay: {self.belt_plan['line']}")
        if self.overlay:
            self.overlay.refresh()
        self._belt_show()

    def _belt_clear(self):
        self.belt_plan = None
        if self.overlay:
            self.overlay.refresh()
        self._belt_show()

    def _belt_after_fix(self):
        """After a new /showlocation fix: refresh the page and the overlay."""
        try:
            if self.nb.select() == str(self.nb_mine) and self.nb_mine.select() == str(self.tab_belts):
                self._belt_show()
        except (tk.TclError, AttributeError):
            pass
        if self.belt_plan and self.overlay:
            self.overlay.refresh()

    # -- EVENTS: major events this month and the next three
    EVENT_COLORS = {"expo": CYAN, "holiday": PURPLE, "community": GREEN, "freefly": AMBER, "patch": TEAL,
                    "event": AMBER}

    def _build_events(self, parent):
        import datetime as _dt
        self.ev_all = events.in_window(events.load(core.DATA_DIR))
        self.ev_month = _dt.date.today().replace(day=1)
        top = tk.Frame(parent, bg=PANEL)
        top.pack(fill="x")
        self.btn_ev_prev = ttk.Button(top, text="◀", width=2, style="Small.TButton",
                                      command=lambda: self._ev_step(-1))
        self.btn_ev_prev.pack(side="left")
        self.lbl_ev_month = self._lbl(top, "", 14, FG, bold=True)
        self.lbl_ev_month.pack(side="left", padx=12)
        self.btn_ev_next = ttk.Button(top, text="▶", width=2, style="Small.TButton",
                                      command=lambda: self._ev_step(1))
        self.btn_ev_next.pack(side="left")
        leg = tk.Frame(parent, bg=PANEL)
        leg.pack(fill="x", pady=(6, 0))
        for k, label in (("expo", "SHOW"), ("holiday", "FESTIVAL"), ("community", "COMMUNITY")):
            tk.Label(leg, text="■", bg=PANEL, fg=self.EVENT_COLORS[k], font=(self.F_UI, 10)).pack(side="left")
            self._lbl(leg, label, 8, MUTED, bold=True).pack(side="left", padx=(2, 10))
        self._lbl(leg, "SOLID = CONFIRMED    OUTLINE = EXPECTED", 8, MUTED, bold=True).pack(side="left", padx=(8, 0))
        self.ev_cv = tk.Canvas(parent, bg=PANEL, highlightthickness=0, bd=0, height=int(380 * self.scale))
        self.ev_cv.pack(fill="x", pady=(8, 6))
        self._ev_job = None

        def resized(_e):
            if self._ev_job:
                self.root.after_cancel(self._ev_job)
            self._ev_job = self.root.after(60, self._ev_draw)
        self.ev_cv.bind("<Configure>", resized)
        self.ev_list = tk.Frame(parent, bg=PANEL)
        self.ev_list.pack(fill="both", expand=True)
        self._lbl(parent, "Major events for this month and the next three. Confirmed dates come from RSI's "
                          "announcements; expected ones are yearly events placed at their usual time until RSI "
                          "announces them. Starboard updates this list with new versions.", 8, MUTED,
                  wraplength=900).pack(anchor="w", pady=(4, 0))
        self._ev_show()

    def _ev_step(self, n):
        lo, hi = events.window()
        m = events.add_months(self.ev_month, n)
        if lo <= m <= hi:
            self.ev_month = m
            self._ev_show()

    def _ev_show(self):
        lo, hi = events.window()
        self.lbl_ev_month.configure(text=self.ev_month.strftime("%B %Y").upper())
        self.btn_ev_prev.state(["!disabled"] if self.ev_month > lo else ["disabled"])
        self.btn_ev_next.state(["!disabled"] if events.add_months(self.ev_month, 1) <= hi else ["disabled"])
        self._ev_draw()
        for w in self.ev_list.winfo_children():
            w.destroy()
        month = events.in_month(self.ev_all, self.ev_month)
        if not month:
            self._lbl(self.ev_list, "No major events known for this month yet.", 10, MUTED).pack(anchor="w")
        for e in month:
            col = self.EVENT_COLORS.get(e.get("kind"), AMBER)
            row = tk.Frame(self.ev_list, bg=PANEL)
            row.pack(fill="x", pady=(0, 6))
            tk.Frame(row, bg=col, width=4).pack(side="left", fill="y", padx=(0, 10))
            body = tk.Frame(row, bg=PANEL)
            body.pack(side="left", fill="x", expand=True)
            head = tk.Frame(body, bg=PANEL)
            head.pack(fill="x")
            self._lbl(head, e["name"].upper(), 11, FG, bold=True).pack(side="left")
            self._lbl(head, events.when(e), 9, AMBER, bold=True).pack(side="left", padx=(10, 0))
            conf = e.get("status") == "confirmed"
            self._lbl(head, "CONFIRMED" if conf else "EXPECTED, DATES NOT ANNOUNCED", 8,
                      GREEN if conf else MUTED, bold=True).pack(side="left", padx=(10, 0))
            if e.get("free_fly"):
                self._lbl(head, "FREE FLY", 8, AMBER, bold=True).pack(side="left", padx=(10, 0))
            if e.get("url"):
                ttk.Button(head, text="OPEN", style="Small.TButton",
                           command=lambda u=e["url"]: webbrowser.open(u)).pack(side="right")
            ab = self._lbl(body, e.get("about", ""), 9, MUTED, wraplength=600)
            ab.pack(fill="x", anchor="w")
            ab.bind("<Configure>", lambda ev, w=ab: w.configure(wraplength=max(200, ev.width - 4)))

    def _ev_draw(self):
        import calendar as _cal
        import datetime as _dt
        self._ev_job = None
        c = self.ev_cv
        c.delete("all")
        W = max(c.winfo_width(), 400)
        H = int(c.cget("height"))
        F = self.F_UI
        head = int(22 * self.scale)
        weeks = _cal.Calendar(firstweekday=6).monthdatescalendar(self.ev_month.year, self.ev_month.month)
        cw, ch = W / 7.0, (H - head) / len(weeks)
        for i, d in enumerate(("SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT")):
            c.create_text(i * cw + 8, head // 2, anchor="w", text=d, fill=MUTED, font=(F, 8, "bold"))
        today = _dt.date.today()
        month = events.in_month(self.ev_all, self.ev_month)
        lane_h = int(17 * self.scale)
        for r, week in enumerate(weeks):
            y0 = head + r * ch
            for i, d in enumerate(week):
                x0 = i * cw
                inside = d.month == self.ev_month.month
                c.create_rectangle(x0 + 1, y0 + 1, x0 + cw - 1, y0 + ch - 1, outline=LINE,
                                   fill=PANEL if inside else BG)
                c.create_text(x0 + 7, y0 + 5, anchor="nw", text=str(d.day),
                              fill=(FG if inside else MUTED), font=(F, 9, "bold"))
                if d == today:
                    c.create_rectangle(x0 + 2, y0 + 2, x0 + cw - 2, y0 + ch - 2, outline=AMBER, width=2)
            # event bars for this week; events on different days share a row
            lanes = []  # per row: list of (a, b) day spans in use
            for e in month:
                s, t = max(e["start"], week[0]), min(e["end"], week[-1])
                if s > t:
                    continue
                a, b = week.index(s), week.index(t)
                lane = 0
                while lane < len(lanes) and any(not (b < x or a > z) for x, z in lanes[lane]):
                    lane += 1
                if lane == len(lanes):
                    lanes.append([])
                lanes[lane].append((a, b))
                y = y0 + int(24 * self.scale) + lane * (lane_h + 2)
                if y + lane_h > y0 + ch - 2:
                    continue
                col = self.EVENT_COLORS.get(e.get("kind"), AMBER)
                conf = e.get("status") == "confirmed"
                tag = f"ev{id(e)}"
                c.create_polygon(round_points(a * cw + 4, y, (b + 1) * cw - 4, y + lane_h, 6), smooth=True,
                                 fill=col if conf else PANEL, outline=col, width=1 if conf else 2, tags=tag)
                txt = e["name"] if s == e["start"] or a == 0 else ""
                room = (b - a + 1) * cw - 16
                while txt and self.tabbar.font.measure(txt) > room:
                    txt = txt[:-2] + "…" if len(txt) > 2 else ""
                c.create_text(a * cw + 10, y + lane_h // 2, anchor="w", text=txt,
                              fill="#08121c" if conf else col, font=(F, 8, "bold"), tags=tag)
                if e.get("url"):
                    c.tag_bind(tag, "<Button-1>", lambda _ev, u=e["url"]: webbrowser.open(u))

    # -- ticker tapes (MARKET: commodity prices, NEWS: Comm-Link posts)
    def _ticker_cfg(self):
        c = self._settings().get("tickers") or {}
        return {"market": c.get("market", True), "news": c.get("news", True)}

    def _ticker_show(self):
        cfg = self._ticker_cfg()
        for k, w in (("market", self.tick_market), ("news", self.tick_news)):
            w.pack_forget()
        for k, w in (("market", self.tick_market), ("news", self.tick_news)):
            if cfg[k]:
                w.pack(fill="x", pady=(0, 2))

    def _ticker_save(self):
        self._save_setting("tickers", {k: v.get() for k, v in self.tick_vars.items()})
        self._ticker_show()

    def _market_refresh(self):
        td = self.trade
        if not td or not td.loaded:
            return
        cur = ticker.commodity_prices(td.prices)
        stamp = (hauling.cache_info(self.world.user_dir) or {}).get("downloaded") or time.time()
        hist = ticker.record(self.world.user_dir, stamp, cur)
        items = []
        for name, price, pct, basis in ticker.changes(cur, hist):
            if abs(pct) < 0.05:
                arrow, col, ptxt = "■", MUTED, "0.0%"
            elif pct > 0:
                arrow, col, ptxt = "▲", GREEN, f"{pct:.1f}%"
            else:
                arrow, col, ptxt = "▼", RED, f"{-pct:.1f}%"
            pr = f"{price:,.0f}" if price >= 100 else f"{price:,.2f}"
            items.append(([(name.upper(), FG), (pr, CYAN), (f"{arrow} {ptxt}", col)],
                          lambda n=name: self._ticker_trade(n)))
        self.tick_market.set_items(items)
        basis = {b for _n, _p, _c, b in ticker.changes(cur, hist)}
        self._tip(self.tick_market, "Average price terminals pay per SCU (UEX). The change is "
                  + ("since about a day ago" if "24h" in basis else
                     "since your last price update" if "last" in basis else
                     "against UEX's usual price, until Starboard has a day of history")
                  + ". Hover to pause, click a commodity for its trade routes.")

    def _ticker_trade(self, name):
        try:
            self.route_comm.set(name)
        except Exception:
            pass
        self._home_go("haul", 0)
        try:
            self._fill_routes()
        except Exception as e:  # noqa: BLE001
            hotkeys_win.log(f"ticker trade: {e}")

    NEWS_EVERY = 600  # seconds between news and server checks

    def _news_refresh(self):
        cache = ticker.load_news(self.world.user_dir)
        if cache.get("items") or cache.get("status"):
            self._news_show(cache.get("items") or [], cache.get("status"))
        if time.time() - cache.get("ts", 0) > self.NEWS_EVERY - 30:
            def work():
                items, status, errors = ticker.fetch_all()
                if errors:
                    hotkeys_win.log("news: " + ", ".join(errors))
                if items or status:
                    ticker.save_news(self.world.user_dir, items or cache.get("items") or [], status)
                    self._ui(lambda: self._news_show(items or cache.get("items") or [], status, fresh=True))
                elif not cache.get("items"):
                    self._ui(lambda: self.tick_news.set_items(
                        [([("Could not reach the news sources. Trying again in a few minutes.", MUTED)], None)]))
            threading.Thread(target=work, daemon=True).start()
        self.root.after(self.NEWS_EVERY * 1000, self._news_refresh)

    SERVER_WORDS = {"operational": ("ONLINE", GREEN), "disrupted": ("DISRUPTED", AMBER), "down": ("DOWN", RED)}

    def _news_show(self, items, status=None, fresh=False):
        rows = []
        if status:
            word, col = self.SERVER_WORDS.get(status.get("summary"), (str(status.get("summary", "")).upper(), AMBER))
            if status.get("summary") == "operational":
                segs = [("SERVERS", TEAL), ("ALL ONLINE", GREEN)]
            else:
                bad = [f"{n.upper()} {self.SERVER_WORDS.get(st, (st.upper(), AMBER))[0]}"
                       for n, st in status.get("systems") or [] if st != "operational"]
                segs = [("SERVERS", TEAL), (", ".join(bad) or word, col)]
            rows.append((segs, lambda: webbrowser.open(ticker.STATUS_URL)))
            # alert when the game servers change state while Starboard is open
            prev = getattr(self, "_server_state", None)
            self._server_state = status.get("summary")
            if fresh and prev and prev != self._server_state:
                if self._server_state == "operational":
                    self._alert("servers", "Servers", "Star Citizen servers are back online.")
                else:
                    self._alert("servers", "Servers", segs[1][0].capitalize() + ". See status.robertsspaceindustries.com",
                                bad=True)
        tags = {"video": ("VIDEO", RED), "server": ("SERVERS", TEAL), "post": ("COMM-LINK", PURPLE)}
        for it in items[:24]:
            try:
                d = time.strftime("%b %d", time.strptime(it["date"], "%Y-%m-%d")).upper()
            except (ValueError, KeyError):
                d = ""
            tag, tcol = tags.get(it.get("kind"), ("NEWS", PURPLE))
            rows.append(([(d, AMBER), (tag, tcol), (it["title"], FG)],
                         (lambda u=it.get("url"): webbrowser.open(u)) if it.get("url") else None))
        self.tick_news.set_items(rows)
        self._tip(self.tick_news, "Server status, patch deployments and incidents from RSI's status page, new "
                                  "videos from RSI's YouTube channel, and Comm-Link posts (through the Star Citizen "
                                  "Wiki, which can be a week or two behind). Checked every 10 minutes. Hover to "
                                  "pause, click an item to open it.")

    # -- desktop shortcut for Starboard.exe
    def _make_shortcut(self, quiet=True):
        if not (sys.platform.startswith("win") and getattr(sys, "frozen", False)):
            if not quiet:
                messagebox.showinfo(APP_TITLE, "A desktop shortcut is made for Starboard.exe. You are running "
                                               "Starboard from Python (run.bat).")
            return
        if quiet and self._settings().get("shortcut_made"):
            return
        exe = sys.executable
        lnk = (EDITION.get("shortcut") or "Starboard").replace("'", "")
        mode = "quiet" if quiet else "now"
        q_exe, q_dir = exe.replace("'", "''"), os.path.dirname(exe).replace("'", "''")
        ps = (f"$d=[Environment]::GetFolderPath('Desktop');$l=Join-Path $d '{lnk}.lnk';"
              f"if((Test-Path $l) -and '{mode}' -eq 'quiet'){{exit 0}};"
              "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($l);"
              f"$s.TargetPath='{q_exe}';$s.WorkingDirectory='{q_dir}';$s.IconLocation='{q_exe},0';"
              f"$s.Description='{lnk}, a Star Citizen companion';$s.Save()")

        def work():
            import subprocess
            try:
                r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
                                   capture_output=True, timeout=30, creationflags=0x08000000)
                ok = r.returncode == 0
            except Exception as e:  # noqa: BLE001
                hotkeys_win.log(f"shortcut: {e}")
                ok = False
            self._ui(lambda: done(ok))

        def done(ok):
            if ok:
                self._save_setting("shortcut_made", True)
            if not quiet:
                (messagebox.showinfo if ok else messagebox.showwarning)(
                    APP_TITLE, "Starboard is on your desktop." if ok else "Could not make the desktop shortcut.")

        threading.Thread(target=work, daemon=True).start()

    # -- new version check (GitHub releases)
    UPDATE_REPO = "Sunfire0816/Starboard"  # where releases are published

    def _update_repo(self):
        return (self._settings().get("update_repo") or self.UPDATE_REPO).strip().strip("/")

    @staticmethod
    def _version_tuple(v):
        return tuple(int(x) for x in re.findall(r"\d+", v or "")[:4]) or (0,)

    def _update_check(self, quiet=True):
        if not EDITION.get("update_check", True):
            if not quiet:
                messagebox.showinfo(APP_TITLE, f"{APP_TITLE} is a private edition and does not check for "
                                               "updates. Rebuild it with installer\\build.bat to update it.")
            return
        repo = self._update_repo()
        st = self._settings()
        if quiet:
            if not st.get("update_check", True) or not repo or time.time() - st.get("update_last", 0) < 86400:
                return
        elif not repo:
            messagebox.showinfo(APP_TITLE, "Type where Starboard's releases are kept (GitHub owner/name) first.")
            return
        if hasattr(self, "upd_status"):
            self.upd_status.configure(text="Checking...")

        def work():
            import json
            try:
                rel = json.loads(data_update.fetch(f"https://api.github.com/repos/{repo}/releases/latest", 20))
                self._ui(lambda: done(rel, None))
            except Exception as ex:  # noqa: BLE001
                self._ui(lambda: done(None, ex))

        def done(rel, err):
            self._save_setting("update_last", time.time())
            if err or not rel:
                txt = "Could not check (offline, or the project name is wrong)"
                if hasattr(self, "upd_status"):
                    self.upd_status.configure(text=txt)
                if not quiet:
                    messagebox.showwarning(APP_TITLE, txt + f".\n\n{err}")
                return
            tag = rel.get("tag_name") or rel.get("name") or ""
            url = rel.get("html_url") or f"https://github.com/{repo}/releases/latest"
            newer = self._version_tuple(tag) > self._version_tuple(APP_VERSION)
            if hasattr(self, "upd_status"):
                self.upd_status.configure(text=f"{tag} is out" if newer else f"You have the latest ({APP_VERSION})")
            if newer:
                if quiet and st.get("update_skip") == tag:
                    return
                notes = clip_text((rel.get("body") or "").strip(), 600)
                if messagebox.askyesno(APP_TITLE, f"Starboard {tag} is out (you have {APP_VERSION}).\n\n"
                                                  + (notes + "\n\n" if notes else "")
                                                  + "Open the download page?"):
                    webbrowser.open(url)
                else:
                    self._save_setting("update_skip", tag)
            elif not quiet:
                messagebox.showinfo(APP_TITLE, f"You have the latest version ({APP_VERSION}).")

        threading.Thread(target=work, daemon=True).start()

    RUN_SHOW_HOURS = 4  # a run you have not touched for this long is treated as finished on the overlay

    def run_for_overlay(self):
        """The hauling run to show on the overlay, or None when you are not hauling: no run, a run
        finished more than two minutes ago, or one left untouched for a few hours."""
        r = getattr(self, "run", None)
        if not r or not r.get("stops"):
            return None
        idle = time.time() - r.get("touched", 0)
        if r["i"] >= len(r["stops"]):
            return r if idle < 120 else None
        return r if idle < self.RUN_SHOW_HOURS * 3600 else None

    OVERLAY_PARTS = [("nav", "Position and target"), ("run", "Hauling run"), ("scan", "Signature scans"),
                     ("refinery", "Refinery timers"), ("contract", "Current contracts"),
                     ("earnings", "Session earnings"), ("belt", "Belt route")]

    def overlay_parts(self):
        c = self._settings().get("overlay_parts") or {}
        return {k: c.get(k, k in ("nav", "run", "scan", "belt")) for k, _l in self.OVERLAY_PARTS}

    def _overlay_parts_save(self):
        self._save_setting("overlay_parts", {k: v.get() for k, v in self.ov_vars.items()})
        if self.overlay:
            self.overlay.refresh()

    def overlay_alpha(self):
        try:
            v = int(self._settings().get("overlay_opacity", 90))
        except (TypeError, ValueError):
            v = 90
        return max(20, min(100, v)) / 100

    def _set_overlay_opacity(self):
        try:
            v = int(self.set_ov_alpha.get().rstrip("%"))
        except ValueError:
            return
        self._save_setting("overlay_opacity", v)
        if self.overlay:
            try:
                self.overlay.attributes("-alpha", v / 100)  # changes right away while it is showing
            except tk.TclError:
                pass

    def _on_top_changed(self):
        self.root.attributes("-topmost", self.on_top.get())
        self._save_setting("on_top", self.on_top.get())

    def _compact_from_settings(self):
        self._save_setting("compact", self.compact.get())
        self._apply_compact()

    def _flash_changed(self):
        self.reduce_flash = self.set_flash.get()
        self._save_setting("reduce_flash", self.reduce_flash)
        self._draw_header()

    def _tips_changed(self):
        self.show_tips = self.set_tips.get()
        self._save_setting("show_tips", self.show_tips)

    def _tip(self, widget, text):
        """Small help text shown when the mouse rests on a widget."""
        state = {"job": None, "win": None}

        def show():
            state["job"] = None
            if state["win"] or not text or not self.show_tips:
                return
            w = tk.Toplevel(widget)
            w.overrideredirect(True)
            try:
                w.attributes("-topmost", True)
            except tk.TclError:
                pass
            tk.Label(w, text=text, bg=BG, fg=FG, font=(self.F_UI, 9), justify="left", wraplength=320,
                     highlightthickness=1, highlightbackground=CYAN_DIM, padx=8, pady=5).pack()
            x, y = widget.winfo_pointerx() + 14, widget.winfo_pointery() + 16
            w.geometry(f"+{x}+{y}")
            state["win"] = w

        def enter(_e):
            if state["job"] is None:
                state["job"] = widget.after(450, show)

        def leave(_e):
            if state["job"]:
                widget.after_cancel(state["job"])
                state["job"] = None
            if state["win"]:
                state["win"].destroy()
                state["win"] = None
        widget.bind("<Enter>", enter, add="+")
        widget.bind("<Leave>", leave, add="+")
        widget.bind("<ButtonPress>", leave, add="+")

    def _tab_changed(self, _ev=None):
        if hasattr(self, "tabbar"):
            self.tabbar.draw()
        try:
            on_haul = self.nb.select() == str(self.tab_haul)
        except tk.TclError:
            return
        if self.nb.select() == str(getattr(self, "tab_missions", "")):
            self._tab_lazy(self.tab_missions)
        if self.nb.select() == str(getattr(self, "tab_craft", "")):
            self._tab_lazy(self.tab_craft)
        if self.nb.select() == str(getattr(self, "nb_hangar", "")) and \
                self.nb_hangar.select() == str(getattr(self, "tab_builder", "")):
            self._sb_lazy()
        if on_haul and self.trade is not None and not self.trade.loaded and not getattr(self, "_haul_auto", False):
            self._haul_auto = True  # first visit with no data: fetch it once
            self._haul_download()

    def _section(self, parent, title, color=None):
        band = tk.Frame(parent, bg=BAND)
        band.pack(fill="x", pady=(6, 4))
        tk.Frame(band, bg=color or CYAN, width=3).pack(side="left", fill="y")
        tk.Label(band, text=spaced(title), bg=BAND, fg=CYAN, font=(self.F_UI, 8, "bold"),
                 anchor="w").pack(side="left", padx=8, pady=3)

    def _build_data(self, parent):
        self._section(parent, "f8, f9 and f10 keys")
        hrow = tk.Frame(parent, bg=PANEL)
        hrow.pack(fill="x", pady=(4, 2))
        st = self._settings()
        self.hk_enabled = tk.BooleanVar(value=st.get("hotkeys_enabled", True))
        ttk.Checkbutton(hrow, text="ON  (F8 READ SIGNATURE · F9 GET POSITION · F10 KEEP GETTING POSITION)", variable=self.hk_enabled,
                        style="Panel.TCheckbutton", command=self._hotkeys_toggled).pack(side="left")
        self._lbl(hrow, "EVERY", 7, MUTED, bold=True).pack(side="left", padx=(12, 4))
        self.repeat_secs = tk.StringVar(value=str(st.get("repeat_seconds", 10)))
        sp = ttk.Combobox(hrow, textvariable=self.repeat_secs, width=4, values=["5", "10", "15", "20", "30", "60"])
        sp._no_suggest = True
        sp.pack(side="left")
        sp.bind("<<ComboboxSelected>>", lambda e: self._save_setting("repeat_seconds", self._repeat_seconds()))
        self._lbl(hrow, "SEC", 7, MUTED, bold=True).pack(side="left", padx=(4, 0))
        self.btn_admin = ttk.Button(hrow, text="RESTART AS ADMIN", command=self._restart_admin)
        self.btn_admin.pack(side="right")
        hrow2 = tk.Frame(parent, bg=PANEL)
        hrow2.pack(fill="x")
        self.always_admin = tk.BooleanVar(value=st.get("always_admin", False))
        ttk.Checkbutton(hrow2, text="ALWAYS START AS ADMINISTRATOR (needed if Star Citizen runs as admin)",
                        variable=self.always_admin, style="Panel.TCheckbutton",
                        command=lambda: self._save_setting("always_admin", self.always_admin.get())
                        ).pack(side="left")
        self.lbl_hk = self._lbl(parent, "", 9, FG, wraplength=560)
        self.lbl_hk.pack(anchor="w", pady=(2, 2))
        self._section(parent, "map data")
        self.lbl_data = self._lbl(parent, "", 9, FG, wraplength=540)
        self.lbl_data.pack(anchor="w", pady=(4, 6))
        row = tk.Frame(parent, bg=PANEL)
        row.pack(fill="x")
        self.btn_update = ttk.Button(row, text="CHECK FOR UPDATES", command=self._start_update)
        self.btn_update.pack(side="left")
        ttk.Button(row, text="UNDO LAST UPDATE", command=self._undo_update).pack(side="left", padx=6)
        self.use_starmap = tk.BooleanVar(value=True)
        chk = ttk.Checkbutton(row, text="ALSO GET NYX AND CAVES", variable=self.use_starmap, style="Panel.TCheckbutton")
        chk.pack(side="left", padx=(6, 0))
        self.txt_update = tk.Text(parent, height=4, bg=BG, fg=FG, insertbackground=CYAN, bd=0, wrap="word",
                                  highlightthickness=1, highlightbackground=LINE, font=(self.F_MONO, 8))
        self.txt_update.pack(fill="x", pady=(6, 4))
        self.txt_update.configure(state="disabled")
        self._lbl(parent, "Gets the latest coordinates after a patch. Your spots, log and calibrations are "
                          "never touched, and the old data is backed up first.", 8, MUTED, wraplength=560
                  ).pack(anchor="w")

        self._section(parent, "share spots")
        row2 = tk.Frame(parent, bg=PANEL)
        row2.pack(fill="x", pady=(4, 6))
        self.share_pois = tk.BooleanVar(value=True)
        self.share_finds = tk.BooleanVar(value=True)
        self.share_system = tk.StringVar(value="All systems")
        ttk.Checkbutton(row2, text="SAVED SPOTS", variable=self.share_pois, style="Panel.TCheckbutton").pack(side="left")
        ttk.Checkbutton(row2, text="LOGGED FINDS", variable=self.share_finds, style="Panel.TCheckbutton").pack(side="left", padx=10)
        ttk.Combobox(row2, textvariable=self.share_system, state="readonly", width=12,
                     values=["All systems"] + self.world.systems()).pack(side="left")
        row3 = tk.Frame(parent, bg=PANEL)
        row3.pack(fill="x")
        ttk.Button(row3, text="EXPORT FILE", command=self._export).pack(side="left")
        ttk.Button(row3, text="IMPORT FILE", command=self._import_file).pack(side="left", padx=6)
        ttk.Button(row3, text="COPY CODES", command=lambda: self._copy_codes(None)).pack(side="left")
        ttk.Button(row3, text="PASTE CODES", command=self._paste_codes).pack(side="left", padx=6)
        self._lbl(parent, "Export a file for a friend, or copy codes to paste in Discord (they copy the message "
                          "and click PASTE CODES). Import also reads community CSV lists. Duplicates are skipped.",
                  8, MUTED, wraplength=560).pack(anchor="w", pady=(6, 0))
        self._update_q = None
        self._refresh_data_label()

    def _refresh_data_label(self):
        info = data_update.read_info(self.world.data_dir)
        def when(v):
            try:
                return clock_str(core.dt.datetime.fromisoformat(v).astimezone(), "%b %d %Y %H:%M")
            except (TypeError, ValueError):
                return "never"
        n_custom = sum(1 for l in self.world.locations if l.source == "custom")
        self.lbl_data.configure(text=(
            f"{len(self.world.bodies)} planets and moons, {sum(1 for l in self.world.locations if l.source == 'db'):,} places.   "
            f"Last updated: {when(info.get('updated'))}.   Last checked: {when(info.get('checked'))}.\n"
            f"Your data: {n_custom} saved spots, {len(self.world.mining_log)} logged finds."))

    def _update_log(self, text, clear=False):
        t = self.txt_update
        t.configure(state="normal")
        if clear:
            t.delete("1.0", "end")
        t.insert("end", text + "\n")
        t.see("end")
        t.configure(state="disabled")

    def _start_update(self):
        if self._update_q is not None:
            return
        self.btn_update.configure(state="disabled")
        self._update_log("Checking for updates...", clear=True)
        q = queue.Queue()
        self._update_q = q
        data_dir, use_sm = self.world.data_dir, self.use_starmap.get()

        def work():
            try:
                data_update.DEBUG_DIR = os.path.join(self.world.user_dir, "starmap_debug")
                rep = data_update.run_update(data_dir, log=lambda m: q.put(("log", m)), use_starmap=use_sm)
                q.put(("done", rep))
            except Exception as e:  # network down, format change, disk error
                q.put(("error", f"{e.__class__.__name__}: {e}"))

        threading.Thread(target=work, daemon=True).start()
        self.root.after(200, self._poll_update)

    def _poll_update(self):
        q = self._update_q
        finished = None
        while q and not q.empty():
            kind, val = q.get()
            if kind == "log":
                self._update_log(val)
            else:
                finished = (kind, val)
        if not finished:
            self.root.after(200, self._poll_update)
            return
        self._update_q = None
        self.btn_update.configure(state="normal")
        kind, val = finished
        if kind == "error":
            self._update_log(f"Update failed, nothing was changed. ({val})")
            return
        self._update_report(val)

    def _update_report(self, r):
        for n in r["notes"]:
            self._update_log(n)
        if not r["changed"]:
            self._update_log("Everything is already current.")
            self._refresh_data_label()
            return
        def few(names):
            return ", ".join(names[:6]) + (f" and {len(names) - 6} more" if len(names) > 6 else "")
        lines = [f"Now {r['bodies']} bodies and {r['locations']} locations."]
        for key, label in (("locations_added", "New locations"), ("locations_removed", "Removed"),
                           ("locations_moved", "Moved"), ("bodies_added", "New bodies"),
                           ("bodies_removed", "Bodies removed"), ("rotation_changed", "Rotation data changed for")):
            if r[key]:
                lines.append(f"{label} ({len(r[key])}): {few(r[key])}")
        if r["om_changed"]:
            lines.append("Orbital marker heights updated.")
        for ln in lines:
            self._update_log(ln)
        self._reload_world()
        stale = [b for b in r["rotation_changed"] if b in self.world.calibration]
        if stale and messagebox.askyesno(APP_TITLE, "The update changed rotation data for bodies you calibrated: "
                                         f"{', '.join(stale)}.\n\nReset those calibrations to use the new data? "
                                         "(Recommended)"):
            for name in stale:
                self.world.reset_calibration(self.world.bodies[name])
            self._recompute()

    def _undo_update(self):
        if not data_update.list_backups(self.world.data_dir):
            messagebox.showinfo(APP_TITLE, "There is no earlier data to go back to.")
            return
        if not messagebox.askyesno(APP_TITLE, "Go back to the data from before the last update?"):
            return
        name = data_update.restore_latest(self.world.data_dir)
        self._update_log(f"Restored the data backed up at {name}.", clear=True)
        self._reload_world()

    def _reload_world(self):
        tkey = (self.target.name, self.target.body) if self.target else None
        self.world = core.World()
        self.target = next((l for l in self.world.locations if (l.name, l.body) == tkey), None) if tkey else None
        names = [b.name for b in sorted(self.world.surface_bodies(), key=lambda b: (b.star, b.name))]
        self.map_cb.configure(values=names)
        self.mat_cb.configure(values=self.world.materials())
        self._refresh_ore_bodies()
        self._fill_browse()
        self._refresh_data_label()
        self.near_body_cb.configure(values=["Where I am"] + self._body_choices())
        self._search_index = None
        if self.trade:  # new locations: place the trade terminals again
            self.trade.world = self.world
            self.trade._match_terminals()
        self._fill_types()
        self._fill_nearby()
        if self.here:
            self.prev_here = None
            self._recompute()
        else:
            self._draw_map()
            self._fill_log()
            self._fill_finder()

    def _share_scope(self):
        sysf = self.share_system.get()
        return self.world.share_items(self.share_pois.get(), self.share_finds.get(),
                                      None if sysf == "All systems" else [sysf])

    def _export(self):
        items = self._share_scope()
        if not items:
            messagebox.showinfo(APP_TITLE, "Nothing to export with these settings. Save some spots or log some "
                                           "finds first.")
            return
        path = filedialog.asksaveasfilename(parent=self.root, title="Export spots", defaultextension=".json",
                                            initialfile="starboard-spots.json",
                                            filetypes=[("Starboard share file", "*.json"), ("Spreadsheet (CSV)", "*.csv")])
        if not path:
            return
        core.write_share(path, items)
        messagebox.showinfo(APP_TITLE, f"Exported {len(items)} entries to\n{path}")

    def _import_items(self, items, label, source_desc):
        if not items:
            messagebox.showwarning(APP_TITLE, f"No spots found in {source_desc}.")
            return
        finds = sum(1 for i in items if i.get("kind") == "find")
        if not messagebox.askyesno(APP_TITLE, f"Found {len(items)} entries in {source_desc} "
                                              f"({len(items) - finds} spots, {finds} logged finds).\n\nImport them?"):
            return
        r = self.world.import_items(items, label)
        msg = f"Added {r['added_pois']} spots and {r['added_finds']} logged finds."
        if r["duplicates"]:
            msg += f"\nSkipped {r['duplicates']} you already had."
        if r["skipped"]:
            msg += f"\nCould not place {len(r['skipped'])}: " + ", ".join(r["skipped"][:5]) + \
                   (" ..." if len(r["skipped"]) > 5 else "")
        messagebox.showinfo(APP_TITLE, msg)
        self.mat_cb.configure(values=self.world.materials())
        self._fill_browse()
        self._refresh_data_label()
        if self.here:
            self._recompute()
        else:
            self._draw_map()
            self._fill_log()

    def _import_file(self):
        path = filedialog.askopenfilename(parent=self.root, title="Import spots",
                                          filetypes=[("Share files", "*.json *.csv *.txt"), ("All files", "*.*")])
        if not path:
            return
        try:
            items, author = core.read_share(path)
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"Could not read that file.\n{e}")
            return
        label = author or os.path.splitext(os.path.basename(path))[0]
        self._import_items(items, label, os.path.basename(path) + (f" from {author}" if author else ""))

    def _copy_codes(self, locs=None):
        if locs is None:
            want = {(i["name"], i["body"]) for i in self._share_scope()}
            locs = [l for l in self.world.locations if l.source in ("custom", "log") and (l.name, l.body) in want]
        if not locs:
            messagebox.showinfo(APP_TITLE, "Nothing to copy. Save some spots or log some finds first.")
            return
        text = "\n".join(core.encode_code(l) for l in locs)
        self.last_clip = text  # so the clipboard watcher ignores it
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        extra = " Discord allows about 25 codes per message." if len(locs) > 25 else ""
        self.status_flash(f"Copied {len(locs)} share code{'s' if len(locs) != 1 else ''}.{extra}")

    def _paste_codes(self):
        try:
            text = self.root.clipboard_get()
        except tk.TclError:
            text = ""
        self._import_items(core.decode_codes(text), "shared codes", "the clipboard")

    def status_flash(self, text):
        messagebox.showinfo(APP_TITLE, text)

    def _need_surface_fix(self):
        if not self.here or not self.here["body"]:
            messagebox.showinfo(APP_TITLE, "Get a /showlocation fix near a planet or moon first.")
            return False
        return True

    def _save_poi(self):
        if not self._need_surface_fix():
            return
        dlg = PoiDialog(self.root, self)
        if not dlg.result:
            return
        name, typ, note = dlg.result
        body = self.here["body"]
        self.world.save_custom_poi(name, typ, body.name, self.here["local"], note)
        self._fill_browse()
        self._recompute()

    def _calibrate(self):
        if not self._need_surface_fix():
            return
        body = self.here["body"]
        choices = [r["loc"] for r in self.here["nearby"][:15]]
        dlg = CalibrateDialog(self.root, self, body, choices)
        if dlg.result == "reset":
            self.world.reset_calibration(body)
            self._recompute()
            return
        if not dlg.result:
            return
        r = self.world.calibrate(body, dlg.result, self.here["global"], self.here["time"])
        msg = (f"{body.name} calibrated at {dlg.result.name}.\n\n"
               f"Error before: {core.fmt_km(r['old_error_km'])}\n"
               f"Height difference vs. that spot: {core.fmt_km(r['radial_gap_km'])}")
        if r["radial_gap_km"] > 3:
            msg += "\n\nThat height gap is large. Make sure you were standing at the spot when you ran /showlocation."
        messagebox.showinfo(APP_TITLE, msg)
        self._recompute()


class Overlay(tk.Toplevel):
    """Small see-through HUD that floats over the game.

    Locked: clicks pass straight through to the game (Windows).
    Unlocked: drag it anywhere; the position is remembered."""

    W, H = 380, 176
    KEY = "#010203"  # this color becomes fully transparent on Windows

    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.is_windows = sys.platform.startswith("win")
        bg = self.KEY if self.is_windows else BG
        self.configure(bg=bg)
        try:
            if self.is_windows:
                self.attributes("-transparentcolor", self.KEY)
            self.attributes("-alpha", app.overlay_alpha())
        except tk.TclError:
            pass
        x, y = self._load_pos()
        self.geometry(f"{self.W}x{self.H}+{x}+{y}")
        self.c = tk.Canvas(self, width=self.W, height=self.H, bg=bg, highlightthickness=0)
        self.after(5000, self._tick)
        self.c.pack()
        self.c.bind("<ButtonPress-1>", self._start_drag)
        self.c.bind("<B1-Motion>", self._drag)
        self.c.bind("<ButtonRelease-1>", lambda e: self._save_pos())
        self.locked = False
        self.refresh()

    # -- position memory
    def _settings_path(self):
        return os.path.join(self.app.world.user_dir, "settings.json")

    def _load_pos(self):
        try:
            import json
            with open(self._settings_path(), encoding="utf-8") as f:
                s = json.load(f)
            return int(s["overlay_x"]), int(s["overlay_y"])
        except Exception:
            return 40, 40

    def _save_pos(self):
        import json
        path = self._settings_path()
        try:
            with open(path, encoding="utf-8") as f:
                s = json.load(f)
        except Exception:
            s = {}
        s["overlay_x"], s["overlay_y"] = self.winfo_x(), self.winfo_y()
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(s, f, indent=1)
        except OSError:
            pass

    def _start_drag(self, e):
        self._dx, self._dy = e.x, e.y

    def _drag(self, e):
        if self.locked:
            return
        self.geometry(f"+{self.winfo_x() + e.x - self._dx}+{self.winfo_y() + e.y - self._dy}")

    # -- click-through
    def set_locked(self, locked):
        self.locked = locked
        if self.is_windows:
            try:
                import ctypes
                GWL_EXSTYLE, WS_EX_LAYERED, WS_EX_TRANSPARENT = -20, 0x80000, 0x20
                # never take focus from the game (otherwise the hotkeys stop working)
                WS_EX_NOACTIVATE, WS_EX_TOOLWINDOW = 0x08000000, 0x80
                user32 = ctypes.windll.user32
                self.update_idletasks()
                hwnd = user32.GetParent(self.winfo_id()) or self.winfo_id()
                style = user32.GetWindowLongW(hwnd, GWL_EXSTYLE) | WS_EX_LAYERED | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW
                style = style | WS_EX_TRANSPARENT if locked else style & ~WS_EX_TRANSPARENT
                user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style)
                # SWP_NOSIZE|NOMOVE|NOZORDER|NOACTIVATE|FRAMECHANGED: apply without stealing focus
                user32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020)
            except Exception:
                pass
        self.refresh()

    def _tick(self):
        """Redraw every few seconds so timers count down."""
        try:
            if self.winfo_exists():
                self.refresh()
                self.after(5000, self._tick)
        except tk.TclError:
            pass

    def close(self):
        self._save_pos()
        self.destroy()

    def _draw_run(self, run, y0, y1):
        c, F, M, w = self.c, self.app.F_UI, self.app.F_MONO, self.W
        c.create_polygon(round_points(1, y0 + 3, w - 1, y1 - 1, 12), smooth=True, fill=PANEL, outline=CYAN_DIM)
        n, i = len(run["stops"]), run["i"]
        if i >= n:
            c.create_text(14, y0 + 8, anchor="nw", text="RUN COMPLETE", fill=GREEN, font=(F, 11, "bold"))
            return
        stop = run["stops"][i]
        c.create_text(14, y0 + 8, anchor="nw", text=f"STOP {i + 1}/{n}", fill=MUTED, font=(M, 9, "bold"))
        here = run.get("arrived")
        c.create_text(96, y0 + 5, anchor="nw", text=clip_text(stop["name"].upper(), 26),
                      fill=GREEN if here else CYAN, font=(F, 12, "bold"))
        c.create_text(w - 12, y0 + 8, anchor="ne", text="HERE" if here else "NEXT",
                      fill=GREEN if here else MUTED, font=(F, 8, "bold"))
        todo = "  ·  ".join(re.sub(r" \([^)]*\)", "", a) for a in stop["actions"])  # drop contract names
        c.create_text(14, y0 + 26, anchor="nw", text=clip_text(todo, 96), width=w - 28,
                      fill=AMBER, font=(F, 8, "bold"))

    def _draw_scan(self, scan, y0, total_h):
        c, F, M = self.c, self.app.F_UI, self.app.F_MONO
        w = self.W
        c.create_polygon(round_points(1, y0 + 3, w - 1, total_h - 1, 12), smooth=True, fill=PANEL,
                         outline=CYAN_DIM)
        c.create_text(14, y0 + 8, anchor="nw", text=f"SIG {scan['value']:,}", fill=MUTED, font=(M, 9, "bold"))
        res = scan["results"]
        if not res:
            c.create_text(120, y0 + 7, anchor="nw", text="NO MATCH", fill=AMBER, font=(F, 12, "bold"))
            return
        top = res[0]
        col = AMBER if top["warn"] else RARITY_COLOR.get(top["rarity"], FG)
        c.create_text(120, y0 + 6, anchor="nw", text=clip_text(top["label"].upper(), 24), fill=col,
                      font=(F, 13, "bold"))
        c.create_text(w - 12, y0 + 9, anchor="ne", text=f"{top['score']}%", fill=MUTED, font=(M, 9))
        alts = "   ".join(f"{a['label']} {a['score']}%" for a in res[1:3])
        sub = (top["rarity"].upper() + "   " if top["rarity"] else "") + (f"or {alts}" if alts else "")
        c.create_text(14, y0 + 32, anchor="nw", text=clip_text(sub, 52), fill=MUTED, font=(F, 8, "bold"))

    def _box(self, y0, y1, title, color=CYAN):
        c, F, w = self.c, self.app.F_UI, self.W
        c.create_polygon(round_points(1, y0 + 3, w - 1, y1 - 1, 12), smooth=True, fill=PANEL,
                         outline=CYAN_DIM if self.locked else AMBER)
        c.create_text(14, y0 + 9, anchor="nw", text=title, fill=color, font=(F, 7, "bold"))

    def _list_rows(self):
        """What the extra overlay sections would show right now: {key: [(left, right, color)]}."""
        app, parts, out = self.app, self.app.overlay_parts(), {}
        if parts.get("refinery") and hasattr(app, "refine"):
            rows = []
            for j in sorted(app.refine.open_jobs(), key=app.refine.ready_at)[:3]:
                left = app.refine.left(j)
                rows.append((clip_text(j.get("refinery") or "Refinery", 30),
                             "READY" if left <= 0 else core.fmt_duration(left, False), GREEN if left <= 0 else FG))
            if rows:
                out["refinery"] = rows
        if parts.get("contract"):
            rows = [(clip_text(c["title"], 44), "", AMBER) for c in
                    sorted(getattr(app, "gl_contracts", {}).values(), key=lambda c: -c.get("ts", 0))
                    if c.get("state") == "Accepted" and c.get("title")][:3]
            if rows:
                out["contract"] = rows
        plan = getattr(app, "belt_plan", None)
        if parts.get("belt") and plan and time.time() - plan.get("set", 0) < 4 * 3600:
            rows = [(f"Quantum to {plan['to']}", f"drop at {belts.gm(plan['drop'])}", AMBER)]
            h = app.here
            b = belts.get(plan["belt"])
            if h and b and h.get("system") == b["system"]:
                w = belts.where(app.world, b, h["global"])
                if w:
                    rows.append((clip_text(belts.short(w), 48), "", GREEN if w["inside"] else MUTED))
            out["belt"] = rows
        if parts.get("earnings") and (getattr(app, "gl_session", {}) or {}).get("joined"):
            st = app._session_stats(app.gl_session["joined"], None)
            out["earnings"] = [(f"{ledger.money(st['net'])} this session",
                                f"{ledger.short_money(st['per_hour'])}/h", GREEN if st["net"] >= 0 else RED)]
        return out

    def _draw_list(self, key, rows, y0, y1):
        c, F, M, w = self.c, self.app.F_UI, self.app.F_MONO, self.W
        title = {"refinery": "REFINERY", "contract": "CONTRACTS", "earnings": "EARNINGS",
                 "belt": "BELT: " + (getattr(self.app, "belt_plan", None) or {}).get("name", "").upper()}[key]
        self._box(y0, y1, title, {"refinery": TEAL, "contract": AMBER, "earnings": GREEN, "belt": CYAN}[key])
        y = y0 + 24
        for left, right, col in rows:
            c.create_text(14, y, anchor="nw", text=left, fill=col, font=(F, 9, "bold"))
            if right:
                c.create_text(w - 14, y, anchor="ne", text=right, fill=col, font=(M, 9, "bold"))
            y += 18

    # -- drawing
    def refresh(self):
        app, c = self.app, self.c
        F, M = app.F_UI, app.F_MONO
        c.delete("all")
        parts = app.overlay_parts()
        scan = app.last_scan if app.last_scan and app._scan_age() < SCAN_SHOW_SECONDS and parts.get("scan") else None
        run = app.run_for_overlay() if parts.get("run") else None
        lists = self._list_rows()
        nav_h = self.H if parts.get("nav") else 0
        stack = []
        if run:
            stack.append(("run", 60))
        for k in ("belt", "refinery", "contract", "earnings"):
            if k in lists:
                stack.append((k, 30 + 18 * len(lists[k])))
        if scan:
            stack.append(("scan", 58))
        total_h = max(40, nav_h + sum(hh for _k, hh in stack))
        if int(c.cget("height")) != total_h:
            c.configure(height=total_h)
            self.geometry(f"{self.W}x{total_h}")
        y = nav_h
        for k, hh in stack:
            if k == "run":
                self._draw_run(run, y, y + hh)
            elif k == "scan":
                self._draw_scan(scan, y, y + hh)
            else:
                self._draw_list(k, lists[k], y, y + hh)
            y += hh
        if not nav_h:
            if not stack:
                self._box(0, 40, "STARBOARD  ·  NOTHING TO SHOW RIGHT NOW", MUTED)
            if not self.locked:
                c.create_text(self.W - 14, 6, anchor="ne", text="UNLOCKED · DRAG TO MOVE", fill=AMBER,
                              font=(F, 7, "bold"))
            return
        w, h = self.W, self.H
        c.create_polygon(round_points(1, 1, w - 1, h - 1, 16), smooth=True,
                         fill=PANEL, outline=CYAN_DIM if self.locked else AMBER, width=1)
        if not self.locked:
            c.create_text(w - 16, 8, anchor="ne", text="UNLOCKED · DRAG TO MOVE", fill=AMBER,
                          font=(F, 7, "bold"))
        elif app.toast:
            c.create_text(w - 22, 6, anchor="ne", text=clip_text(app.toast[0], 34),
                          fill=GREEN if app.toast[1] else AMBER, font=(F, 7, "bold"))

        here, tgt, m = app.here, app.target, app.motion
        cx, cy, r = 70, 80, 50
        # dial
        c.create_oval(cx - r, cy - r, cx + r, cy + r, outline=LINE)
        for deg in range(0, 360, 30):
            a = math.radians(deg - 90)
            c.create_line(cx + (r - 6) * math.cos(a), cy + (r - 6) * math.sin(a),
                          cx + r * math.cos(a), cy + r * math.sin(a), fill=CYAN_DIM)

        arrow, color, mode = None, GREEN, ""
        if here and tgt:
            info = app.world.target_info(here, tgt)
            if info["same_body"]:
                if m and m["turn"] is not None:
                    arrow, mode = m["turn"], "REL"      # up = your direction of travel
                else:
                    arrow, mode = info["bearing"], "N↑"
        elif here and here.get("nearby"):
            arrow, color, mode = here["nearby"][0]["bearing"], CYAN, "N↑"
        if arrow is None:
            c.create_text(cx, cy, text="---", fill=MUTED, font=(M, 12))
        else:
            a = math.radians(arrow - 90)
            tip = (cx + (r - 6) * math.cos(a), cy + (r - 6) * math.sin(a))
            tail = (cx - 18 * math.cos(a), cy - 18 * math.sin(a))
            c.create_line(*tail, *tip, fill=color, width=4, arrow="last", arrowshape=(14, 16, 7))
            c.create_text(cx, cy + r - 12, text=mode, fill=MUTED, font=(F, 7, "bold"))
        if mode == "N↑":
            c.create_text(cx, cy - r + 10, text="N", fill=CYAN, font=(F, 8, "bold"))

        # text column
        x = 136
        def line(y, text, size=10, color=FG, bold=False, mono=False, left=None):
            c.create_text(x if left is None else left, y, anchor="nw", text=text, fill=color,
                          font=(M if mono else F, size, "bold" if bold else "normal"))

        if not here:
            line(30, "STARBOARD", 12, CYAN, bold=True)
            line(56, "Waiting for /showlocation", 9, MUTED)
            return
        body = here.get("body")
        place = body.name if body else (here.get("zone") or "Open space")
        if tgt:
            info = app.world.target_info(here, tgt)
            line(14, spaced("target"), 7, GREEN, bold=True)
            line(28, clip_text(tgt.name, 24), 11, GREEN, bold=True)
            dist = info["surface"] if info["same_body"] else info["straight"]
            line(50, core.fmt_km(dist), 20, FG, bold=True, mono=True)
            y = 84
            if m and m["closing_ms"] is not None:
                if m["closing_ms"] > 0.5:
                    line(y, f"ETA {core.fmt_duration(m['eta_s'])}", 11, FG, mono=True)
                else:
                    line(y, "MOVING AWAY" if m["closing_ms"] < -0.5 else "NOT CLOSING", 10, AMBER, bold=True)
                y += 20
            if m and m["turn"] is not None:
                line(y, core.turn_text(m["turn"]).upper(), 10,
                     GREEN if abs(m["turn"]) < 5 else AMBER, bold=True)
                y += 20
            elif info["same_body"]:
                line(y, f"HEADING {info['bearing']:03.0f}° {core.compass_word(info['bearing'])}", 10, FG, mono=True)
                y += 20
            else:
                rt = app.world.route(here, tgt)
                om = rt.get("om")
                if om and not tgt.quantum:
                    line(y, f"QT {info['body_name']} {om['name']}", 10, AMBER, bold=True)
                    line(y + 18, f"then {om['bearing']:03.0f}°  {core.fmt_km(om['ground'])}", 9, FG, mono=True)
                    y += 36
                else:
                    line(y, f"QT to {clip_text(tgt.name if tgt.quantum else info['body_name'], 20)}", 10, AMBER, bold=True)
                    y += 20
            spd = core.fmt_speed(m["speed_ms"]) if m else "--"
            tb = app.world.bodies[tgt.body]
            sun = app._sun_short(tb, tgt.local, here["time"]) if tb.rotates else ""
            line(h - 22, f"SPD {spd}" + (f"   TARGET {sun}" if sun else ""), 8, MUTED, mono=True, left=16)
        else:
            line(14, spaced("position"), 7, CYAN_DIM, bold=True)
            line(28, place.upper(), 14, CYAN, bold=True)
            if body:
                line(54, f"LAT {here['lat']:+.3f}  LON {here['lon']:+.3f}", 9, FG, mono=True)
                line(72, f"ALT {here['alt']:,.2f} km", 9, FG, mono=True)
                if here.get("nearby"):
                    n = here["nearby"][0]
                    line(96, "CLOSEST", 7, MUTED, bold=True)
                    line(108, clip_text(n["loc"].name, 28), 10, FG)
                    line(126, f"{core.fmt_km(n['surface'])}  {n['bearing']:03.0f}° {core.compass_word(n['bearing'])}",
                         9, CYAN, mono=True)
            elif here.get("space"):
                d, name, typ = here["space"][0]
                line(58, "NEAREST", 7, MUTED, bold=True)
                line(70, clip_text(name, 28), 10, FG)
                line(88, core.fmt_km(d), 11, CYAN, mono=True)
            spd = core.fmt_speed(m["speed_ms"]) if m else "--"
            sun = app._sun_short(body, here["local"], here["time"]) if body else ""
            line(h - 22, f"SPD {spd}" + (f"   {sun}" if sun else ""), 8, MUTED, mono=True, left=16)


class HudDialog(simpledialog.Dialog):
    """Dark dialog matching the main window."""

    def __init__(self, parent, app, title):
        self.app = app
        super().__init__(parent, title)

    def body(self, master):
        self.configure(bg=PANEL)
        master.configure(bg=PANEL)
        return self.build(master)

    def buttonbox(self):
        box = tk.Frame(self, bg=PANEL)
        ttk.Button(box, text="OK", width=10, style="Accent.TButton", command=self.ok).pack(side="left", padx=5, pady=8)
        ttk.Button(box, text="CANCEL", width=10, command=self.cancel).pack(side="left", padx=5, pady=8)
        self.bind("<Return>", self.ok)
        self.bind("<Escape>", self.cancel)
        box.pack()

    def lbl(self, master, text, **kw):
        return tk.Label(master, text=text, bg=PANEL, fg=MUTED, font=(self.app.F_UI, 8, "bold"), **kw)


class PoiDialog(HudDialog):
    TYPES = ["Cave", "Ore deposit", "Wreck", "Landing spot", "Outpost", "Other"]

    def __init__(self, parent, app):
        super().__init__(parent, app, "Save spot")

    def build(self, master):
        for i, t in enumerate(("NAME", "TYPE", "NOTE")):
            self.lbl(master, t).grid(row=i, column=0, sticky="w", padx=(0, 8), pady=3)
        self.e_name = ttk.Entry(master, width=32)
        self.e_name.grid(row=0, column=1, pady=3)
        self.v_type = tk.StringVar(value="Cave")
        ttk.Combobox(master, textvariable=self.v_type, values=self.TYPES, width=30).grid(row=1, column=1, pady=3)
        self.e_note = ttk.Entry(master, width=32)
        self.e_note.grid(row=2, column=1, pady=3)
        return self.e_name

    def validate(self):
        return bool(self.e_name.get().strip())

    def apply(self):
        self.result = (self.e_name.get().strip(), self.v_type.get().strip() or "Other", self.e_note.get().strip())


class LogDialog(HudDialog):
    METHODS = [("Ship", "ship"), ("ROC / ground vehicle", "vehicle"), ("Hand / FPS", "hand")]

    def __init__(self, parent, app, materials, last=None):
        self.materials = materials
        self.last = last
        super().__init__(parent, app, "Log a find")

    def build(self, master):
        rows = ("MATERIAL", "METHOD", "QUALITY", "AMOUNT", "NOTE")
        for i, t in enumerate(rows):
            self.lbl(master, t).grid(row=i, column=0, sticky="w", padx=(0, 8), pady=3)
        self.v_mat = tk.StringVar(value=self.last[0] if self.last else "")
        cb = ttk.Combobox(master, textvariable=self.v_mat, values=self.materials, width=30)
        cb.grid(row=0, column=1, pady=3)
        labels = [m[0] for m in self.METHODS]
        start = next((m[0] for m in self.METHODS if self.last and m[1] == self.last[1]), labels[0])
        self.v_method = tk.StringVar(value=start)
        ttk.Combobox(master, textvariable=self.v_method, values=labels, width=30, state="readonly"
                     ).grid(row=1, column=1, pady=3)
        self.e_q = ttk.Entry(master, width=32)
        self.e_q.grid(row=2, column=1, pady=3)
        self.e_amt = ttk.Entry(master, width=32)
        self.e_amt.grid(row=3, column=1, pady=3)
        self.e_note = ttk.Entry(master, width=32)
        self.e_note.grid(row=4, column=1, pady=3)
        tk.Label(master, text="Quality is the 0 to 1000 value from your scanner (optional).", bg=PANEL, fg=MUTED,
                 font=(self.app.F_UI, 8)).grid(row=5, column=0, columnspan=2, sticky="w", pady=(4, 0))
        return cb

    def validate(self):
        if not self.v_mat.get().strip():
            return False
        q = self.e_q.get().strip()
        if q and not q.isdigit():
            messagebox.showwarning(APP_TITLE, "Quality should be a whole number, or leave it blank.", parent=self)
            return False
        return True

    def apply(self):
        method = dict(self.METHODS).get(self.v_method.get(), "ship")
        q = self.e_q.get().strip()
        mat = self.v_mat.get().strip()
        mat = mat[:1].upper() + mat[1:]
        self.result = (mat, method, int(q) if q else None, self.e_amt.get().strip(), self.e_note.get().strip())


class ContractDialog(HudDialog):
    """Enter a hauling contract: a title, the reward, and one or more legs."""

    def __init__(self, parent, app, places, existing=None):
        self.places = places
        self.labels = sorted(places)
        self.existing = existing
        self.rows = []
        super().__init__(parent, app, "Hauling contract")

    def build(self, master):
        top = tk.Frame(master, bg=PANEL)
        top.pack(fill="x")
        self.lbl(top, "TITLE").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=3)
        self.e_title = ttk.Entry(top, width=40)
        self.e_title.grid(row=0, column=1, sticky="w", pady=3)
        self.lbl(top, "REWARD (aUEC)").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=3)
        self.e_reward = ttk.Entry(top, width=14)
        self.e_reward.grid(row=1, column=1, sticky="w", pady=3)
        self.grid_f = tk.Frame(master, bg=PANEL)
        self.grid_f.pack(fill="x", pady=(8, 0))
        for col, t in enumerate(("PICK UP AT", "DELIVER TO", "CARGO", "SCU", "")):
            self.lbl(self.grid_f, t).grid(row=0, column=col, sticky="w", padx=2)
        btns = tk.Frame(master, bg=PANEL)
        btns.pack(fill="x", pady=(6, 0))
        ttk.Button(btns, text="+ LEG", command=self._add_row).pack(side="left")
        tk.Label(master, text="Type part of a name to search. One contract can have several legs.",
                 bg=PANEL, fg=MUTED, font=(self.app.F_UI, 8)).pack(anchor="w", pady=(6, 0))
        if self.existing:
            self.e_title.insert(0, self.existing["title"])
            self.e_reward.insert(0, f"{float(self.existing.get('reward') or 0):g}")
            for l in self.existing["legs"]:
                self._add_row(l)
        else:
            self._add_row()
        return self.e_title

    def _label_for(self, ref):
        lab = f"{ref['name']} · {ref.get('body', '')}"
        return lab if lab in self.places else ref["name"]

    def _place_box(self, row, col, value=""):
        v = tk.StringVar(value=value)
        cb = ttk.Combobox(self.grid_f, textvariable=v, width=30, values=self.labels)
        cb.grid(row=row, column=col, padx=2, pady=2)

        def filt(ev):
            if ev.keysym in ("Up", "Down", "Return", "Escape", "Tab"):
                return
            words = v.get().lower().split()
            cb.configure(values=[x for x in self.labels if all(w in x.lower() for w in words)] or self.labels)
        cb.bind("<KeyRelease>", filt)
        return v

    def _add_row(self, leg=None):
        r = len(self.rows) + 1
        prev = self.rows[-1] if self.rows else None
        pick = self._label_for(leg["pickup"]) if leg else (prev["pick"].get() if prev else "")
        drop = self._label_for(leg["dropoff"]) if leg else ""
        row = {"pick": self._place_box(r, 0, pick), "drop": self._place_box(r, 1, drop)}
        row["comm"] = tk.StringVar(value=(leg or {}).get("commodity", prev["comm"].get() if prev else ""))
        ttk.Entry(self.grid_f, textvariable=row["comm"], width=14).grid(row=r, column=2, padx=2)
        row["scu"] = tk.StringVar(value=f"{float(leg['scu']):g}" if leg else "")
        ttk.Entry(self.grid_f, textvariable=row["scu"], width=6).grid(row=r, column=3, padx=2)
        widgets = self.grid_f.grid_slaves(row=r)
        row["widgets"] = widgets

        def drop_row():
            if len(self.rows) > 1:
                for w in row["widgets"]:
                    w.grid_forget()
                self.rows.remove(row)
        b = ttk.Button(self.grid_f, text="X", width=2, command=drop_row)
        b.grid(row=r, column=4, padx=2)
        row["widgets"] = widgets + [b]
        self.rows.append(row)

    def validate(self):
        legs = []
        for i, row in enumerate(self.rows, 1):
            p, d = self.places.get(row["pick"].get().strip()), self.places.get(row["drop"].get().strip())
            if not p or not d:
                messagebox.showwarning(APP_TITLE, f"Leg {i}: pick both places from the list.", parent=self)
                return False
            if p is d:
                messagebox.showwarning(APP_TITLE, f"Leg {i}: pickup and delivery are the same place.", parent=self)
                return False
            try:
                scu = float(row["scu"].get().replace(",", ""))
                assert scu > 0
            except (ValueError, AssertionError):
                messagebox.showwarning(APP_TITLE, f"Leg {i}: enter the SCU (a number above 0).", parent=self)
                return False
            legs.append({"pickup": {"name": p.name, "body": p.body}, "dropoff": {"name": d.name, "body": d.body},
                         "scu": scu, "commodity": row["comm"].get().strip()})
        try:
            reward = float(self.e_reward.get().replace(",", "") or 0)
        except ValueError:
            messagebox.showwarning(APP_TITLE, "The reward must be a number.", parent=self)
            return False
        self._out = (self.e_title.get().strip() or f"Contract ({len(legs)} legs)", reward, legs)
        return True

    def apply(self):
        self.result = self._out


class LedgerDialog(HudDialog):
    """Edit one ledger entry."""

    def __init__(self, parent, app, entry):
        self.entry = entry
        super().__init__(parent, app, "Ledger entry")

    def build(self, master):
        e = self.entry
        labels = ("TYPE", "CATEGORY", "AMOUNT (aUEC)", "NOTE", "WHERE", "WHEN")
        for i, t in enumerate(labels):
            self.lbl(master, t).grid(row=i, column=0, sticky="w", padx=(0, 8), pady=3)
        self.v_kind = tk.StringVar(value=e["kind"])
        kinds = [ledger.EXPENSE, ledger.INCOME] + ([ledger.ADJUST] if e["kind"] == ledger.ADJUST else [])
        ttk.Combobox(master, textvariable=self.v_kind, values=kinds, state="readonly", width=30
                     ).grid(row=0, column=1, pady=3, sticky="w")
        self.v_cat = tk.StringVar(value=e["category"])
        ttk.Combobox(master, textvariable=self.v_cat, values=ledger.ALL_CATEGORIES, width=30
                     ).grid(row=1, column=1, pady=3, sticky="w")
        self.e_amt = ttk.Entry(master, width=32)
        self.e_amt.insert(0, f"{abs(e['amount']):.0f}" if e["kind"] != ledger.ADJUST else f"{e['amount']:.0f}")
        self.e_amt.grid(row=2, column=1, pady=3, sticky="w")
        self.e_note = ttk.Entry(master, width=32)
        self.e_note.insert(0, e.get("note", ""))
        self.e_note.grid(row=3, column=1, pady=3, sticky="w")
        self.e_where = ttk.Entry(master, width=32)
        self.e_where.insert(0, e.get("where", ""))
        self.e_where.grid(row=4, column=1, pady=3, sticky="w")
        self.e_when = ttk.Entry(master, width=32)
        self.e_when.insert(0, core.dt.datetime.fromtimestamp(e["time"]).strftime("%Y-%m-%d %H:%M"))
        self.e_when.grid(row=5, column=1, pady=3, sticky="w")
        return self.e_amt

    def validate(self):
        amt = ledger.parse_amount(self.e_amt.get())
        if amt is None:
            messagebox.showwarning(APP_TITLE, "The amount must be a number (12500, 12.5k, 1.2m).", parent=self)
            return False
        try:
            when = core.dt.datetime.strptime(self.e_when.get().strip(), "%Y-%m-%d %H:%M").timestamp()
        except ValueError:
            messagebox.showwarning(APP_TITLE, "Write the time as YYYY-MM-DD HH:MM.", parent=self)
            return False
        kind = self.v_kind.get()
        self._out = {"kind": kind, "category": self.v_cat.get().strip() or "Other",
                     "amount": amt if kind == ledger.ADJUST else abs(amt),
                     "note": self.e_note.get().strip(), "where": self.e_where.get().strip(), "time": when}
        return True

    def apply(self):
        self.result = self._out


class ShipDialog(HudDialog):
    """Add or edit a ship in My Hangar."""

    def __init__(self, parent, app, preset=None, existing=None):
        self.preset, self.existing = preset, existing
        self.ships = app.trade.all_ships()
        self.places = app._haul_places()
        self.place_labels = sorted(self.places)
        super().__init__(parent, app, "Edit ship" if existing else "Add a ship")

    def build(self, master):
        for i, t in enumerate(("SHIP", "SETUP", "NICKNAME", "PARKED AT", "NOTE")):
            self.lbl(master, t).grid(row=i, column=0, sticky="w", padx=(0, 8), pady=3)
        ex = self.existing or {}
        self.v_ship = tk.StringVar(value=ex.get("ship") or self.preset or "")
        self.cb_ship = ttk.Combobox(master, textvariable=self.v_ship, values=self.ships, width=34)
        self.cb_ship.grid(row=0, column=1, sticky="w", pady=3)
        self.cb_ship.bind("<KeyRelease>", self._filter_ships)
        self.cb_ship.bind("<<ComboboxSelected>>", lambda e: self._ship_changed())
        self.v_setup = tk.StringVar(value=ex.get("setup") or "")
        self.cb_setup = ttk.Combobox(master, textvariable=self.v_setup, state="readonly", width=34)
        self.cb_setup.grid(row=1, column=1, sticky="w", pady=3)
        self.e_nick = ttk.Entry(master, width=36)
        self.e_nick.insert(0, ex.get("nickname", ""))
        self.e_nick.grid(row=2, column=1, sticky="w", pady=3)
        p = ex.get("parked") or {}
        lab = f"{p['name']} · {p.get('body', '')}" if p else ""
        self.v_park = tk.StringVar(value=lab if lab in self.places else "")
        self.cb_park = ttk.Combobox(master, textvariable=self.v_park, values=self.place_labels, width=34)
        self.cb_park.grid(row=3, column=1, sticky="w", pady=3)
        self.cb_park.bind("<KeyRelease>", self._filter_places)
        self.e_note = ttk.Entry(master, width=36)
        self.e_note.insert(0, ex.get("note", ""))
        self.e_note.grid(row=4, column=1, sticky="w", pady=3)
        self.lbl_info = tk.Label(master, text="", bg=PANEL, fg=MUTED, font=(self.app.F_UI, 8), justify="left",
                                 wraplength=330)
        self.lbl_info.grid(row=5, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self._ship_changed(keep=True)
        return self.cb_ship

    def _filter_ships(self, ev):
        if ev.keysym in ("Up", "Down", "Return", "Escape", "Tab"):
            return
        words = self.v_ship.get().lower().split()
        self.cb_ship.configure(values=[s for s in self.ships if all(w in s.lower() for w in words)] or self.ships)
        self._ship_changed(keep=True)

    def _filter_places(self, ev):
        if ev.keysym in ("Up", "Down", "Return", "Escape", "Tab"):
            return
        words = self.v_park.get().lower().split()
        self.cb_park.configure(values=[p for p in self.place_labels if all(w in p.lower() for w in words)]
                               or self.place_labels)

    def _ship_changed(self, keep=False):
        name = self.v_ship.get().strip()
        setups = [s["label"] for s in self.app.trade.setups_for(name)]
        self.cb_setup.configure(values=setups or ["Standard"])
        if not keep or self.v_setup.get() not in (setups or ["Standard"]):
            self.v_setup.set(setups[-1] if setups else "Standard")
        info = self.app.trade.ship_info(name)
        if info:
            bits = [info["maker"], ", ".join(info["roles"]) or None,
                    f"crew {info['crew']}" if info["crew"] else None,
                    f"{info['scu']:g} SCU" if info["scu"] else None,
                    f"pad {info['pad']}" if info["pad"] else None]
            self.lbl_info.configure(text="  ·  ".join(b for b in bits if b))
        else:
            self.lbl_info.configure(text="Pick a ship from the list (type part of its name to search).")

    def validate(self):
        name = self.v_ship.get().strip()
        if name not in self.ships:
            messagebox.showwarning(APP_TITLE, "Pick the ship from the list.", parent=self)
            return False
        park = self.places.get(self.v_park.get().strip())
        setup = self.v_setup.get()
        self._out = {"ship": name, "setup": None if setup in ("", "Standard") else setup,
                     "nickname": self.e_nick.get().strip(), "note": self.e_note.get().strip(),
                     "parked": {"name": park.name, "body": park.body} if park else None}
        return True

    def apply(self):
        self.result = self._out


class RefineDialog(HudDialog):
    """Add or edit a refinery work order."""

    def __init__(self, parent, app, existing=None):
        self.existing = existing
        self.refs = app._refineries()
        self.ref_names = sorted(self.refs)
        sd = app._shop_ready()
        ores = sorted(name for (kind, name) in sd.products if kind == "refine") if sd else []
        self.ores = ores or sorted(app.world.materials())
        self.methods = sd.methods if sd else []
        self.rows = []
        super().__init__(parent, app, "Edit refinery job" if existing else "New refinery job")

    def build(self, master):
        ex = self.existing or {}
        top = tk.Frame(master, bg=PANEL)
        top.pack(fill="x")
        labels = ("REFINERY", "METHOD", "TIME LEFT" if not ex else "TOTAL TIME", "COST (aUEC)")
        for i, t in enumerate(labels):
            self.lbl(top, t).grid(row=i, column=0, sticky="w", padx=(0, 8), pady=3)
        self.v_ref = tk.StringVar(value=ex.get("refinery") or self._nearest_refinery())
        self.cb_ref = ttk.Combobox(top, textvariable=self.v_ref, values=self.ref_names, width=34)
        self.cb_ref.grid(row=0, column=1, sticky="w", pady=3)
        self.cb_ref.bind("<KeyRelease>", self._filter_ref)
        self.cb_ref.bind("<<ComboboxSelected>>", lambda e: self._update_info())
        mlabels = [self._method_label(m) for m in self.methods]
        self.v_method = tk.StringVar(value=next((l for l in mlabels if l.startswith(ex.get("method") or "\0")),
                                                ex.get("method", "")))
        ttk.Combobox(top, textvariable=self.v_method, values=mlabels, width=34).grid(row=1, column=1, sticky="w",
                                                                                     pady=3)
        self.e_time = ttk.Entry(top, width=36)
        if ex:
            self.e_time.insert(0, refining.fmt_duration(ex["duration"]))
        self.e_time.grid(row=2, column=1, sticky="w", pady=3)
        self.e_cost = ttk.Entry(top, width=36)
        if ex.get("cost"):
            self.e_cost.insert(0, f"{ex['cost']:g}")
        self.e_cost.grid(row=3, column=1, sticky="w", pady=3)
        self.grid_f = tk.Frame(master, bg=PANEL)
        self.grid_f.pack(fill="x", pady=(8, 0))
        self.lbl(self.grid_f, "ORE").grid(row=0, column=0, sticky="w", padx=2)
        self.lbl(self.grid_f, "SCU").grid(row=0, column=1, sticky="w", padx=2)
        ttk.Button(master, text="+ ORE", command=self._add_row).pack(anchor="w", pady=(4, 0))
        for o in ex.get("ores", []) or [None]:
            self._add_row(o)
        self.v_log = tk.BooleanVar(value=not ex)
        if not ex:
            ttk.Checkbutton(master, text="ADD THE COST TO MY LEDGER", variable=self.v_log,
                            style="Panel.TCheckbutton").pack(anchor="w", pady=(6, 0))
        self.lbl_info = tk.Label(master, text="", bg=PANEL, fg=MUTED, font=(self.app.F_UI, 8), justify="left",
                                 wraplength=360)
        self.lbl_info.pack(anchor="w", pady=(6, 0))
        tk.Label(master, text="TIME LEFT: copy it from the refinery terminal, for example 2h 15m or 2:15.",
                 bg=PANEL, fg=MUTED, font=(self.app.F_UI, 8), wraplength=360, justify="left").pack(anchor="w")
        self._update_info()
        return self.cb_ref

    @staticmethod
    def _method_label(m):
        stars = lambda v: "★" * int(_num0(v))
        return (f"{m.get('name')}  (yield {stars(m.get('rating_yield'))}, speed {stars(m.get('rating_speed'))}, "
                f"cost {stars(m.get('rating_cost'))})")

    def _nearest_refinery(self):
        h = self.app.here
        if not h:
            return ""
        best, bd = "", None
        for name, t in self.refs.items():
            if t.system != h["system"]:
                continue
            d = self.app.trade.distance_from(h, t)
            if d is not None and (bd is None or d < bd):
                best, bd = name, d
        return best if bd is not None and bd < 50 else ""

    def _filter_ref(self, ev):
        if ev.keysym in ("Up", "Down", "Return", "Escape", "Tab"):
            return
        words = self.v_ref.get().lower().split()
        self.cb_ref.configure(values=[r for r in self.ref_names if all(w in r.lower() for w in words)]
                              or self.ref_names)
        self._update_info()

    def _add_row(self, ore=None):
        r = len(self.rows) + 1
        v_ore = tk.StringVar(value=(ore or {}).get("ore", ""))
        cb = ttk.Combobox(self.grid_f, textvariable=v_ore, values=self.ores, width=28)
        cb.grid(row=r, column=0, padx=2, pady=2)
        cb.bind("<<ComboboxSelected>>", lambda e: self._update_info())
        v_scu = tk.StringVar(value=f"{ore['scu']:g}" if ore else "")
        ttk.Entry(self.grid_f, textvariable=v_scu, width=8).grid(row=r, column=1, padx=2)
        self.rows.append((v_ore, v_scu))

    def _update_info(self):
        sd = self.app.shopdata
        term = self.refs.get(self.v_ref.get().strip())
        if not (sd and term):
            self.lbl_info.configure(text="")
            return
        bits = []
        for v_ore, _ in self.rows:
            p = sd.find("refine", v_ore.get().strip())
            if not p:
                continue
            here = next((o[1] for o in p.offers if o[0] is term), None)
            best = p.best()
            if here is not None:
                txt = f"{p.name}: {here:+.0f}% here"
                if best and best[1] > here:
                    txt += f" (best {best[1]:+.0f}% at {best[0].name})"
                bits.append(txt)
        self.lbl_info.configure(text="Yield bonus: " + "; ".join(bits) if bits else "")

    def validate(self):
        ref = self.v_ref.get().strip()
        term = self.refs.get(ref)
        if not ref:
            messagebox.showwarning(APP_TITLE, "Pick the refinery.", parent=self)
            return False
        secs = refining.parse_duration(self.e_time.get())
        if not secs:
            messagebox.showwarning(APP_TITLE, "Enter the time, for example 2h 15m or 2:15.", parent=self)
            return False
        ores = []
        for v_ore, v_scu in self.rows:
            name = v_ore.get().strip()
            if not name:
                continue
            try:
                scu = float(v_scu.get().replace(",", ""))
            except ValueError:
                messagebox.showwarning(APP_TITLE, f"Enter the SCU of {name}.", parent=self)
                return False
            ores.append({"ore": name, "scu": scu})
        if not ores:
            messagebox.showwarning(APP_TITLE, "Add at least one ore.", parent=self)
            return False
        cost = ledger.parse_amount(self.e_cost.get()) or 0
        loc = term.loc if term else None
        data = {"refinery": ref, "ores": ores, "method": self.v_method.get().split("  (")[0].strip(),
                "duration": secs, "cost": abs(cost),
                "place": {"name": loc.name, "body": loc.body} if loc else None}
        if not self.existing:
            data["started"] = time.time()
        else:
            data["started"] = self.existing["started"]
        self._out = (data, self.v_log.get())
        return True

    def apply(self):
        self.result = self._out


class BountyDialog(HudDialog):
    """Add or edit a bounty contract."""

    def __init__(self, parent, app, places, existing=None):
        self.places, self.labels, self.existing = places, sorted(places), existing
        super().__init__(parent, app, "Edit bounty" if existing else "New bounty")

    def build(self, master):
        ex = self.existing or {}
        for i, t in enumerate(("TARGET", "RANK", "REWARD (aUEC)", "WHERE", "NOTE")):
            self.lbl(master, t).grid(row=i, column=0, sticky="w", padx=(0, 8), pady=3)
        self.e_target = ttk.Entry(master, width=36)
        self.e_target.insert(0, ex.get("target", ""))
        self.e_target.grid(row=0, column=1, sticky="w", pady=3)
        rank = ex.get("rank", "")
        self.v_rank = tk.StringVar(value=next((l for l in combat.RANK_LABELS if l.split()[0] == rank),
                                              combat.RANK_LABELS[1]))
        ttk.Combobox(master, textvariable=self.v_rank, values=combat.RANK_LABELS, state="readonly", width=34
                     ).grid(row=1, column=1, sticky="w", pady=3)
        self.e_reward = ttk.Entry(master, width=36)
        if ex.get("reward"):
            self.e_reward.insert(0, f"{float(ex['reward']):g}")
        self.e_reward.grid(row=2, column=1, sticky="w", pady=3)
        p = ex.get("place") or {}
        lab = f"{p['name']} · {p.get('body', '')}" if p else ""
        self.v_where = tk.StringVar(value=lab if lab in self.places else ex.get("where_text", ""))
        self.cb_where = ttk.Combobox(master, textvariable=self.v_where, values=self.labels, width=34)
        self.cb_where.grid(row=3, column=1, sticky="w", pady=3)
        self.cb_where.bind("<KeyRelease>", self._filter)
        self.e_note = ttk.Entry(master, width=36)
        self.e_note.insert(0, ex.get("note", ""))
        self.e_note.grid(row=4, column=1, sticky="w", pady=3)
        tk.Label(master, text="WHERE is optional: pick the place from the list (type to search) to be able to fly "
                              "there, or type anything, such as \"near Yela OM-3\".", bg=PANEL, fg=MUTED,
                 font=(self.app.F_UI, 8), wraplength=330, justify="left").grid(row=5, column=0, columnspan=2,
                                                                               sticky="w", pady=(6, 0))
        return self.e_target

    def _filter(self, ev):
        if ev.keysym in ("Up", "Down", "Return", "Escape", "Tab"):
            return
        words = self.v_where.get().lower().split()
        self.cb_where.configure(values=[x for x in self.labels if all(w in x.lower() for w in words)] or self.labels)

    def validate(self):
        target = self.e_target.get().strip()
        if not target:
            messagebox.showwarning(APP_TITLE, "Enter the target's name.", parent=self)
            return False
        reward = ledger.parse_amount(self.e_reward.get()) if self.e_reward.get().strip() else 0
        if reward is None:
            messagebox.showwarning(APP_TITLE, "The reward must be a number (15000, 15k).", parent=self)
            return False
        w = self.v_where.get().strip()
        loc = self.places.get(w)
        self._out = {"target": target, "rank": self.v_rank.get().split()[0], "reward": abs(reward),
                     "place": {"name": loc.name, "body": loc.body} if loc else None,
                     "where_text": "" if loc else w, "note": self.e_note.get().strip()}
        return True

    def apply(self):
        self.result = self._out


class SigPrompt(tk.Toplevel):
    """F8 box: always on top, type a signature, Enter identifies it, Esc cancels."""

    def __init__(self, app, game_hwnd):
        super().__init__(app.root)
        self.app, self.game = app, game_hwnd
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=PANEL, highlightthickness=1, highlightbackground=CYAN)
        tk.Label(self, text="SCAN SIGNATURE   Enter = identify   Esc = cancel", bg=PANEL, fg=MUTED,
                 font=(app.F_UI, 9, "bold")).pack(anchor="w", padx=12, pady=(8, 2))
        self.var = tk.StringVar()
        e = tk.Entry(self, textvariable=self.var, width=12, bg=BG, fg=CYAN, insertbackground=CYAN, bd=0,
                     font=(app.F_MONO, 22, "bold"), highlightthickness=1, highlightbackground=LINE)
        e.pack(padx=12, pady=(0, 10), fill="x")
        e.bind("<Return>", self._ok)
        e.bind("<KP_Enter>", self._ok)
        e.bind("<Escape>", self._cancel)
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        self.geometry(f"+{(self.winfo_screenwidth() - w) // 2}+120")
        self.lift()
        self.focus_force()
        e.focus_set()
        try:
            hotkeys_win.set_foreground(int(self.wm_frame(), 16))
        except Exception:
            pass
        self.after(50, e.focus_force)

    def _done(self):
        game = self.game
        self.app.sig_prompt = None
        self.destroy()
        if game:
            hotkeys_win.set_foreground(game)

    def _ok(self, _e=None):
        digits = "".join(ch for ch in self.var.get() if ch.isdigit())
        if len(digits) >= 3:
            self.app._scan(int(digits), source="hotkey")
            self.app._hk_say(f"F8: signature {int(digits):,} identified.")
        self._done()

    def _cancel(self, _e=None):
        self._done()


class TeachDialog(HudDialog):
    def __init__(self, parent, app, value):
        self.value = value
        super().__init__(parent, app, "Teach a signature")

    def build(self, master):
        tk.Label(master, text=f"What was {self.value:,}?", bg=PANEL, fg=CYAN,
                 font=(self.app.F_UI, 12, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        self.lbl(master, "NAME").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=3)
        self.lbl(master, "HOW MANY").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=3)
        self.e_name = ttk.Entry(master, width=30)
        self.e_name.grid(row=1, column=1, pady=3)
        self.e_count = ttk.Entry(master, width=30)
        self.e_count.insert(0, "1")
        self.e_count.grid(row=2, column=1, pady=3)
        tk.Label(master, text="Use a name like 'Drake Cutlass' or 'Cave entrance'. If the scan was a group,\n"
                              "enter how many were in it so single ones are recognized too.",
                 bg=PANEL, fg=MUTED, font=(self.app.F_UI, 8), justify="left").grid(row=3, column=0, columnspan=2,
                                                                               sticky="w", pady=(4, 0))
        return self.e_name

    def validate(self):
        return bool(self.e_name.get().strip()) and self.e_count.get().strip().isdigit() and int(self.e_count.get()) > 0

    def apply(self):
        self.result = (self.e_name.get().strip(), int(self.e_count.get().strip()))


class AreaPicker(tk.Toplevel):
    """Full-screen see-through layer: drag a box around the signature readout."""

    def __init__(self, app, on_done):
        super().__init__(app.root)
        self.on_done = on_done
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        try:
            self.attributes("-alpha", 0.35)
        except tk.TclError:
            pass
        w, h = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{w}x{h}+0+0")
        self.c = tk.Canvas(self, bg="#000000", highlightthickness=0, cursor="crosshair")
        self.c.pack(fill="both", expand=True)
        self.c.create_text(w // 2, 60, fill="#ffffff", font=(app.F_UI, 18, "bold"),
                           text="Drag a box around where the scan signature number shows.  Esc to cancel.")
        self.c.bind("<ButtonPress-1>", self._down)
        self.c.bind("<B1-Motion>", self._move)
        self.c.bind("<ButtonRelease-1>", self._up)
        self.bind("<Escape>", lambda e: self.destroy())
        self.rect = None
        self.focus_force()

    def _down(self, e):
        self.x0, self.y0 = e.x_root, e.y_root
        self.rect = self.c.create_rectangle(e.x, e.y, e.x, e.y, outline=CYAN, width=3)

    def _move(self, e):
        if self.rect:
            self.c.coords(self.rect, self.x0 - self.winfo_rootx(), self.y0 - self.winfo_rooty(), e.x, e.y)

    def _up(self, e):
        x0, x1 = sorted((self.x0, e.x_root))
        y0, y1 = sorted((self.y0, e.y_root))
        self.destroy()
        if x1 - x0 >= 8 and y1 - y0 >= 8:
            self.on_done([x0, y0, x1 - x0, y1 - y0])


class CalibrateDialog(HudDialog):
    def __init__(self, parent, app, body, choices):
        self.body_obj = body
        self.choices = choices
        super().__init__(parent, app, f"Calibrate {body.name}")

    def build(self, master):
        tk.Label(master, justify="left", wraplength=380, bg=PANEL, fg=FG, font=(self.app.F_UI, 10), text=(
            f"Stand at one of these known spots on {self.body_obj.name}, run /showlocation, "
            "then pick the spot. This fixes the rotation offset if positions look shifted "
            "after a patch.")).pack(anchor="w", pady=(0, 8))
        self.lb = tk.Listbox(master, width=52, height=10, bg=BG, fg=FG, selectbackground=CYAN_FAINT,
                             highlightthickness=1, highlightbackground=LINE, bd=0,
                             font=(self.app.F_UI, 10))
        for loc in self.choices:
            self.lb.insert("end", f"{loc.name}  ({loc.type})")
        self.lb.pack()
        if self.choices:
            self.lb.selection_set(0)
        self.reset = tk.BooleanVar(value=False)
        ttk.Checkbutton(master, text="RESET TO DEFAULT ROTATION INSTEAD", variable=self.reset
                        ).pack(anchor="w", pady=(8, 0))
        return self.lb

    def apply(self):
        if self.reset.get():
            self.result = "reset"
            return
        sel = self.lb.curselection()
        self.result = self.choices[sel[0]] if sel else None


_shown_errors = set()


def show_crash(text, fatal, root=None):
    """A plain-language error window instead of a raw traceback. Saves the details to crash.log in
    the data folder, lets the player copy them, and says whether Starboard keeps running."""
    import datetime as _dt
    try:
        os.makedirs(core.USER_DIR, exist_ok=True)
        with open(os.path.join(core.USER_DIR, "crash.log"), "a", encoding="utf-8") as f:
            f.write(f"\n=== {_dt.datetime.now():%Y-%m-%d %H:%M:%S}  Starboard {APP_VERSION}  "
                    f"Python {sys.version.split()[0]}  {sys.platform}\n{text}\n")
    except OSError:
        pass
    hotkeys_win.log(("fatal error:\n" if fatal else "error:\n") + text)
    last = [ln for ln in text.strip().splitlines() if ln.strip()][-1:] or ["unknown error"]
    key = last[0] + ("|fatal" if fatal else "")
    if not fatal:
        if key in _shown_errors:
            return  # already told them about this one
        _shown_errors.add(key)
    try:
        own = root is None or not root.winfo_exists()
    except Exception:  # noqa: BLE001
        own = True
    try:
        w = tk.Tk() if own else tk.Toplevel(root)
    except Exception:  # noqa: BLE001
        return
    w.title("Starboard: something went wrong")
    w.configure(bg=PANEL)
    w.resizable(False, False)
    try:
        w.attributes("-topmost", True)
    except tk.TclError:
        pass
    pad = dict(padx=18)
    tk.Label(w, text="STARBOARD RAN INTO A PROBLEM", bg=PANEL, fg=RED if fatal else AMBER,
             font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(16, 4), **pad)
    msg = ("Starboard could not keep going and has to close. Your data (settings, hangar, ledger, plans) "
           "is safe. Start it again. If it keeps happening, please send the details."
           if fatal else
           "Something went wrong, but Starboard is still running and your data is safe. If something "
           "looks wrong, restart it. Please send the details so it can be fixed.")
    tk.Label(w, text=msg, bg=PANEL, fg=FG, font=("Segoe UI", 10), justify="left", wraplength=520).pack(
        anchor="w", **pad)
    tk.Label(w, text="What happened: " + last[0][:200], bg=PANEL, fg=MUTED, font=("Segoe UI", 9),
             justify="left", wraplength=520).pack(anchor="w", pady=(8, 0), **pad)
    tk.Label(w, text=f"Full details are saved in {os.path.join(core.USER_DIR, 'crash.log')}", bg=PANEL,
             fg=MUTED, font=("Segoe UI", 8), justify="left", wraplength=520).pack(anchor="w", pady=(2, 0), **pad)
    row = tk.Frame(w, bg=PANEL)
    row.pack(fill="x", pady=16, **pad)
    status = tk.Label(row, text="", bg=PANEL, fg=GREEN, font=("Segoe UI", 9))

    def copy():
        try:
            w.clipboard_clear()
            w.clipboard_append(f"Starboard {APP_VERSION} ({sys.platform}, Python {sys.version.split()[0]})\n{text}")
            status.configure(text="Copied. Paste it in a message to the developer.")
        except tk.TclError:
            pass

    def folder():
        try:
            os.startfile(core.USER_DIR)  # Windows
        except (AttributeError, OSError):
            pass

    def close():
        try:
            w.destroy()
        except tk.TclError:
            pass
    for label, fn, bg in (("COPY DETAILS", copy, ORANGE), ("OPEN LOG FOLDER", folder, PANEL_HI),
                          ("CLOSE STARBOARD" if fatal else "CLOSE", close, PANEL_HI)):
        tk.Button(row, text=label, command=fn, bg=bg, fg=ON_ACCENT if bg == ORANGE else CYAN, relief="flat",
                  activebackground=bg, font=("Segoe UI", 9, "bold"), padx=12, pady=6, bd=0,
                  cursor="hand2").pack(side="left", padx=(0, 8))
    status.pack(side="left", padx=(4, 0))
    w.protocol("WM_DELETE_WINDOW", close)
    w.update_idletasks()
    sw, sh = w.winfo_screenwidth(), w.winfo_screenheight()
    w.geometry(f"+{(sw - w.winfo_reqwidth()) // 2}+{(sh - w.winfo_reqheight()) // 3}")
    if own:
        w.mainloop()


def main():
    try:
        from ctypes import windll  # crisp text on high-DPI Windows screens
        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    import traceback
    user_dir = core.USER_DIR
    os.makedirs(user_dir, exist_ok=True)
    hotkeys_win.LOG_PATH = os.path.join(user_dir, "sclocator.log")
    hotkeys_win.log(f"--- Starboard {APP_VERSION} starting (Python {sys.version.split()[0]}, "
                    f"admin={hotkeys_win.is_admin()})")
    sys.excepthook = lambda *a: hotkeys_win.log("error:\n" + "".join(traceback.format_exception(*a)))
    threading.excepthook = lambda a: hotkeys_win.log(
        "thread error:\n" + "".join(traceback.format_exception(a.exc_type, a.exc_value, a.exc_traceback)))
    # "always run as administrator" option
    try:
        import json
        with open(os.path.join(user_dir, "settings.json"), encoding="utf-8") as f:
            always_admin = json.load(f).get("always_admin", False)
    except Exception:
        always_admin = False
    if always_admin and hotkeys_win.available() and not hotkeys_win.is_admin() and "--no-elevate" not in sys.argv:
        if hotkeys_win.relaunch_as_admin():
            return
    root = tk.Tk()

    def report(exc, val, tb):
        text = "".join(traceback.format_exception(exc, val, tb))
        try:
            app.lbl_hk.configure(text=f"Something went wrong: {val}", fg=AMBER)
        except Exception:
            pass
        show_crash(text, fatal=False, root=root)

    root.report_callback_exception = report
    if os.path.exists(os.path.join(core.HERE, "perf_on.txt")):
        import perf
        perf.install(root, os.path.join(core.HERE, "perf_log.txt"))
    root.withdraw()  # build everything out of sight, so buttons do not flash white while they load
    app = App(root)
    try:
        alpha = float(root.attributes("-alpha"))
    except (tk.TclError, ValueError):
        alpha = 1.0
    try:
        root.attributes("-alpha", 0.0)
        root.deiconify()
        root.update()
        root.attributes("-alpha", alpha)
    except tk.TclError:
        root.deiconify()

    def on_close():
        try:
            app._gl_stop()
            app._gl_save()
        except Exception:
            pass
        try:
            if getattr(app, "_keep_geom", True) and app._settings().get("window_size",
                                                                         "Remember last size") == "Remember last size":
                app._save_setting("window_geom", root.geometry())
        except Exception:
            pass
        if app.reader:
            app.reader.stop()
        if app.hk:
            app.hk.stop()
        root.destroy()

    app.on_close = on_close
    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()
    if getattr(app, "_restart", False):
        import subprocess
        args = [a for a in sys.argv[1:] if a != "--no-elevate"] + ["--no-elevate"]
        if getattr(sys, "frozen", False):
            subprocess.Popen([sys.executable] + args, cwd=os.path.dirname(sys.executable))
        else:
            subprocess.Popen([sys.executable, os.path.abspath(__file__)] + args,
                             cwd=os.path.dirname(os.path.abspath(__file__)))


if __name__ == "__main__":
    try:
        main()
    except (SystemExit, KeyboardInterrupt):
        raise
    except BaseException:  # noqa: BLE001  anything else: a friendly window, not a raw traceback
        import traceback as _tb
        show_crash(_tb.format_exc(), fatal=True)
