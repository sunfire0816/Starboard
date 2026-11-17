"""Editions: the same Starboard with its own name, colors, fonts, banner and icon.

Starboard looks for an edition folder holding an edition.json, in this order:
1. the folder named in the STARBOARD_EDITION environment variable (run_b2.bat sets it)
2. an "edition" folder next to Starboard (build.bat puts it there for an edition build)
Without one it is plain Starboard. Paths inside edition.json are relative to its folder.

edition.json keys (all optional):
  name, subtitle          window title and banner text
  palette                 color names to override (BG, PANEL, CYAN, ORANGE, ...)
  fonts                   {"files": [...], "ui": family, "title": family}
  art                     file name pattern for banner pictures, with {pct}, e.g. "header_{pct}.png"
  icon                    window icon (PNG)
  update_check            false: no public update check (a private edition)
  shortcut                desktop shortcut name
"""

import json
import os
import sys

DEFAULT = {"id": "starboard", "name": "Starboard", "subtitle": "star citizen companion", "palette": {},
           "fonts": None, "art": None, "icon": None, "update_check": True, "shortcut": "Starboard", "dir": None}


def find(here):
    env = os.environ.get("STARBOARD_EDITION")
    for d in ([env] if env else []) + [os.path.join(here, "edition")]:
        if d and os.path.isfile(os.path.join(d, "edition.json")):
            return os.path.abspath(d)
    return None


def load(here):
    d = find(here)
    ed = dict(DEFAULT)
    if not d:
        return ed
    try:
        with open(os.path.join(d, "edition.json"), encoding="utf-8") as f:
            ed.update(json.load(f))
    except (OSError, ValueError):
        return dict(DEFAULT)
    ed["dir"] = d
    return ed


def path(ed, name):
    if not name or not ed.get("dir"):
        return None
    p = os.path.join(ed["dir"], name)
    return p if os.path.exists(p) else None


def load_fonts(ed):
    """Make the edition's font files usable by this program only (Windows), without installing them."""
    fonts = ed.get("fonts") or {}
    loaded = 0
    for name in fonts.get("files") or []:
        p = path(ed, name)
        if not p:
            continue
        if sys.platform.startswith("win"):
            try:
                import ctypes
                FR_PRIVATE = 0x10
                loaded += ctypes.windll.gdi32.AddFontResourceExW(p, FR_PRIVATE, 0) > 0
            except Exception:  # noqa: BLE001
                pass
    return loaded
