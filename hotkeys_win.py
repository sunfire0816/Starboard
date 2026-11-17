"""
Built-in hotkeys for Windows (no AutoHotkey needed).

- Global hotkeys with RegisterHotKey, received on a background thread.
- Keystrokes sent with SendInput as hardware scan codes (games read those),
  looked up for the current keyboard layout.
- Helpers to tell whether Star Citizen is the active window and to restart
  the app with administrator rights (needed when the game runs elevated).
"""

import ctypes
import datetime as _dt
import os
import re
import sys
import threading
import time
import traceback

LOG_PATH = None  # set by the app: user/sclocator.log


def log(msg):
    if not LOG_PATH:
        return
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(f"{_dt.datetime.now():%Y-%m-%d %H:%M:%S}  {msg}\n")
    except OSError:
        pass

IS_WINDOWS = sys.platform.startswith("win")

VK = {f"F{i}": 0x6F + i for i in range(1, 13)}
VK.update({c: ord(c) for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"})
VK.update({"`": 0xC0, "SPACE": 0x20, "HOME": 0x24, "END": 0x23, "INSERT": 0x2D, "PAGEUP": 0x21, "PAGEDOWN": 0x22,
           "NUM0": 0x60, "NUM1": 0x61, "NUM2": 0x62, "NUM3": 0x63, "NUM4": 0x64, "NUM5": 0x65, "NUM6": 0x66,
           "NUM7": 0x67, "NUM8": 0x68, "NUM9": 0x69})
MODS = {"CTRL": 0x11, "SHIFT": 0x10, "ALT": 0x12}


def parse_hotkey(spec):
    """'Ctrl+Shift+S' -> (frozenset({'CTRL','SHIFT'}), 'S', 'Ctrl+Shift+S'), or None if it is not a
    usable key. Letters, digits and the like need at least one modifier so normal typing is not taken."""
    parts = [p.strip().upper() for p in (spec or "").replace(" ", "").split("+") if p.strip()]
    if not parts:
        return None
    key, mods = parts[-1], parts[:-1]
    key = {"CONTROL": "CTRL", "TILDE": "`", "GRAVE": "`"}.get(key, key)
    mods = [{"CONTROL": "CTRL"}.get(m, m) for m in mods]
    if key not in VK or any(m not in MODS for m in mods) or len(set(mods)) != len(mods):
        return None
    if not mods and not re.fullmatch(r"F\d+", key):
        return None
    nice = "+".join([m.capitalize() for m in ("CTRL", "SHIFT", "ALT") if m in mods] +
                    [key if len(key) <= 3 else key.capitalize()])
    return frozenset(mods), key, nice
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012

if IS_WINDOWS:
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32.GetAsyncKeyState.restype = ctypes.c_short
    user32.GetAsyncKeyState.argtypes = [ctypes.c_int]

    ULONG_PTR = ctypes.c_size_t

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                    ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    class _INPUTUNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]

    class INPUT(ctypes.Structure):
        _anonymous_ = ("u",)
        _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]

    INPUT_KEYBOARD = 1
    KEYEVENTF_KEYUP = 0x0002
    KEYEVENTF_SCANCODE = 0x0008

    user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
    user32.SendInput.restype = wintypes.UINT
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
    user32.VkKeyScanW.argtypes = (wintypes.WCHAR,)
    user32.VkKeyScanW.restype = ctypes.c_short
    user32.MapVirtualKeyW.argtypes = (wintypes.UINT, wintypes.UINT)
    user32.RegisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT)
    user32.UnregisterHotKey.argtypes = (wintypes.HWND, ctypes.c_int)
    user32.GetMessageW.argtypes = (ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT)
    user32.PostThreadMessageW.argtypes = (wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ULONG_PTR), ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD),
                    ("szExeFile", wintypes.WCHAR * 260)]

    LRESULT = ctypes.c_ssize_t

    class KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD), ("flags", wintypes.DWORD),
                    ("time", wintypes.DWORD), ("dwExtraInfo", ULONG_PTR)]

    HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
    user32.SetWindowsHookExW.argtypes = (ctypes.c_int, HOOKPROC, wintypes.HINSTANCE, wintypes.DWORD)
    user32.SetWindowsHookExW.restype = wintypes.HHOOK
    user32.CallNextHookEx.argtypes = (wintypes.HHOOK, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
    user32.CallNextHookEx.restype = LRESULT
    user32.UnhookWindowsHookEx.argtypes = (wintypes.HHOOK,)
    kernel32.GetModuleHandleW.argtypes = (wintypes.LPCWSTR,)
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    user32.AttachThreadInput.argtypes = (wintypes.DWORD, wintypes.DWORD, wintypes.BOOL)
    user32.BringWindowToTop.argtypes = (wintypes.HWND,)
    user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)

    kernel32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel32.CreateToolhelp32Snapshot.argtypes = (wintypes.DWORD, wintypes.DWORD)
    kernel32.Process32FirstW.argtypes = (wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W))
    kernel32.Process32NextW.argtypes = (wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W))
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    advapi32.OpenProcessToken.argtypes = (wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE))
    advapi32.GetTokenInformation.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
                                             ctypes.POINTER(wintypes.DWORD))
    kernel32.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                    ctypes.POINTER(wintypes.DWORD))


def available():
    return IS_WINDOWS


def is_admin():
    if not IS_WINDOWS:
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin():
    """Start a second copy of the app with administrator rights. Returns True if Windows accepted."""
    log("relaunching as administrator")
    exe = sys.executable
    if exe.lower().endswith("python.exe"):
        alt = exe[:-10] + "pythonw.exe"
        if os.path.exists(alt):
            exe = alt
    if getattr(sys, "frozen", False):  # Starboard.exe
        exe = sys.executable
        rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, "", os.path.dirname(exe), 1)
        return rc > 32
    script = os.path.abspath(sys.argv[0])
    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, f'"{script}"', os.path.dirname(script), 1)
    return rc > 32


def find_process(exe_name):
    """PID of a running program by file name, or None."""
    if not IS_WINDOWS:
        return None
    snap = kernel32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if not snap or snap in (-1, ctypes.c_void_p(-1).value):
        return None
    try:
        e = PROCESSENTRY32W()
        e.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = kernel32.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            if e.szExeFile.lower() == exe_name.lower():
                return e.th32ProcessID
            ok = kernel32.Process32NextW(snap, ctypes.byref(e))
    finally:
        kernel32.CloseHandle(snap)
    return None


def process_elevated(pid):
    """True if the process runs with administrator rights, False if not, None if unknown.
    A normal program is not allowed to look inside an elevated one, so 'access denied'
    from a non-admin app also means elevated."""
    if not IS_WINDOWS or not pid:
        return None
    h = kernel32.OpenProcess(0x1000, False, pid)
    if not h:
        return None
    try:
        tok = wintypes.HANDLE()
        if not advapi32.OpenProcessToken(h, 0x0008, ctypes.byref(tok)):  # TOKEN_QUERY
            return True if not is_admin() else None
        try:
            elev = wintypes.DWORD()
            size = wintypes.DWORD()
            if advapi32.GetTokenInformation(tok, 20, ctypes.byref(elev), ctypes.sizeof(elev), ctypes.byref(size)):
                return bool(elev.value)  # 20 = TokenElevation
            return None
        finally:
            kernel32.CloseHandle(tok)
    finally:
        kernel32.CloseHandle(h)


def foreground_window():
    return user32.GetForegroundWindow() if IS_WINDOWS else None


def foreground_process_name():
    """File name of the program that owns the active window, e.g. 'StarCitizen.exe'."""
    if not IS_WINDOWS:
        return ""
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return ""
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = kernel32.OpenProcess(0x1000, False, pid.value)  # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return "(protected program)"
    try:
        buf = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value)
        return ""
    finally:
        kernel32.CloseHandle(h)


def set_foreground(hwnd):
    """Bring a window to the front even while a game has focus. Windows normally refuses
    this, so briefly attach to the active window's input queue first (standard workaround)."""
    if not (IS_WINDOWS and hwnd):
        return
    fg = user32.GetForegroundWindow()
    if fg == hwnd:
        return
    cur = kernel32.GetCurrentThreadId()
    fg_tid = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    attached = bool(fg_tid and fg_tid != cur and user32.AttachThreadInput(cur, fg_tid, True))
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(cur, fg_tid, False)


# ---------------------------------------------------------------- typing
def _scan_input(scan, up):
    inp = INPUT(type=INPUT_KEYBOARD)
    inp.ki = KEYBDINPUT(0, scan, KEYEVENTF_SCANCODE | (KEYEVENTF_KEYUP if up else 0), 0, 0)
    return inp


def _tap(scan, hold):
    sent = user32.SendInput(1, ctypes.byref(_scan_input(scan, False)), ctypes.sizeof(INPUT))
    time.sleep(hold)
    sent += user32.SendInput(1, ctypes.byref(_scan_input(scan, True)), ctypes.sizeof(INPUT))
    return sent


def type_text(text, key_delay=0.03, hold=0.03):
    """Type text as real key presses on the current keyboard layout. Returns events sent."""
    SHIFT = 0x2A
    sent = 0
    for ch in text:
        vks = user32.VkKeyScanW(ch)
        if vks == -1:
            continue
        vk, shift = vks & 0xFF, (vks >> 8) & 1
        scan = user32.MapVirtualKeyW(vk, 0)  # MAPVK_VK_TO_VSC
        if shift:
            sent += user32.SendInput(1, ctypes.byref(_scan_input(SHIFT, False)), ctypes.sizeof(INPUT))
            time.sleep(hold)
        sent += _tap(scan, hold)
        if shift:
            sent += user32.SendInput(1, ctypes.byref(_scan_input(SHIFT, True)), ctypes.sizeof(INPUT))
        time.sleep(key_delay)
    return sent


def press_enter(hold=0.03):
    return _tap(0x1C, hold)


def send_chat_command(command, chat_open_wait=0.25, key_delay=0.03, hold=0.03):
    """Enter, type the command, Enter. Returns the number of key events Windows accepted."""
    sent = press_enter(hold)
    time.sleep(chat_open_wait)
    sent += type_text(command, key_delay, hold)
    time.sleep(0.06)
    sent += press_enter(hold)
    return sent


# ---------------------------------------------------------------- hotkeys
class HotkeyListener:
    """Watches F-keys with a low-level keyboard hook and calls on_key(name) from a
    background thread. Unlike RegisterHotKey, this still works while a game that
    blocks hotkeys (Star Citizen does) has focus. The keys still reach the game."""

    WM_KEYDOWN, WM_SYSKEYDOWN, WM_KEYUP, WM_SYSKEYUP = 0x0100, 0x0104, 0x0101, 0x0105
    LLKHF_INJECTED = 0x10

    def __init__(self, keys, on_key):
        self.keys = list(keys)
        self.on_key = on_key
        self.failed = []
        self._thread = None
        self._tid = None
        self._ready = threading.Event()
        self._down = set()
        self._vk = {}
        for k in self.keys:
            parsed = parse_hotkey(k)
            if parsed:
                mods, key, _nice = parsed
                self._vk.setdefault(VK[key], []).append((mods, k))
        self._proc = None  # keep the callback alive

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(2.0)
        return self.failed

    def _hook(self, n_code, w_param, l_param):
        try:
            if n_code == 0:
                k = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                specs = self._vk.get(k.vkCode)
                if specs and not (k.flags & self.LLKHF_INJECTED):
                    if w_param in (self.WM_KEYDOWN, self.WM_SYSKEYDOWN):
                        held = frozenset(m for m, vk in MODS.items() if user32.GetAsyncKeyState(vk) & 0x8000)
                        # an exact modifier match wins; a plain F-key also fires with modifiers held
                        name = next((s for mods, s in specs if mods == held), None) or \
                            next((s for mods, s in specs if not mods), None)
                        if name and k.vkCode not in self._down:  # ignore auto-repeat while held
                            self._down.add(k.vkCode)
                            log(f"key {name}, active window: {foreground_process_name()}")
                            self.on_key(name)
                    elif w_param in (self.WM_KEYUP, self.WM_SYSKEYUP):
                        self._down.discard(k.vkCode)
        except Exception:
            log("hook error:\n" + traceback.format_exc())
        return user32.CallNextHookEx(None, n_code, w_param, l_param)

    def _run(self):
        hook = None
        try:
            self._tid = kernel32.GetCurrentThreadId()
            self._proc = HOOKPROC(self._hook)
            hook = user32.SetWindowsHookExW(13, self._proc, kernel32.GetModuleHandleW(None), 0)  # WH_KEYBOARD_LL
            if not hook:
                self.failed = list(self.keys)
                log(f"keyboard hook FAILED (error {ctypes.get_last_error()})")
            else:
                log(f"keyboard hook installed for {', '.join(self.keys)}")
            self._ready.set()
            msg = wintypes.MSG()
            while hook:
                r = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if r == 0 or r == -1:
                    break
            log("keyboard hook stopped")
        except Exception:
            self._ready.set()
            log("keyboard hook crashed:\n" + traceback.format_exc())
        finally:
            if hook:
                user32.UnhookWindowsHookEx(hook)

    def stop(self):
        if self._tid:
            user32.PostThreadMessageW(self._tid, WM_QUIT, 0, 0)
            self._tid = None
