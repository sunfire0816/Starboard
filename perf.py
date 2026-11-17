"""Timing recorder for finding stutter. Starboard turns it on when a file named perf_on.txt
sits next to it, and writes perf_log.txt there: every step that held the window up for more
than 25 ms (which code, how long), every gap in screen updates over 60 ms, and window sizes."""

import time
import tkinter as tk

SLOW = 0.025
GAP = 0.060


def install(root, path):
    f = open(path, "w", encoding="utf-8", buffering=1)
    t0 = time.perf_counter()

    def log(msg):
        f.write(f"{time.perf_counter() - t0:9.3f}  {msg}\n")

    log("recording started")
    orig = tk.CallWrapper.__call__

    def timed(self, *args):
        a = time.perf_counter()
        try:
            return orig(self, *args)
        finally:
            d = time.perf_counter() - a
            if d > SLOW:
                fn = self.func
                if getattr(fn, "__qualname__", "").endswith("callit") and fn.__closure__:  # after(): the real one
                    for cell in fn.__closure__:
                        try:
                            v = cell.cell_contents
                        except ValueError:
                            continue
                        if callable(v):
                            fn = v
                            break
                name = getattr(fn, "__qualname__", None) or getattr(fn, "__name__", None) or repr(fn)
                code = getattr(fn, "__code__", None)
                where = f" line {code.co_firstlineno}" if code else ""
                log(f"SLOW {d * 1000:6.0f} ms  {name}{where}")
    tk.CallWrapper.__call__ = timed

    last = [time.perf_counter()]
    size = [None]

    def watch():
        now = time.perf_counter()
        gap = now - last[0]
        if gap > GAP:
            log(f"GAP  {gap * 1000:6.0f} ms  (nothing updated on screen)")
        last[0] = now
        try:
            s = (root.winfo_width(), root.winfo_height(), root.state())
            if s != size[0]:
                size[0] = s
                log(f"window {s[0]}x{s[1]} {s[2]}")
            root.after(15, watch)
        except tk.TclError:
            pass
    root.after(500, watch)
