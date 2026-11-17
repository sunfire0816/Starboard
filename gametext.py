"""
The game's own text (names of items, ships and places, contract titles and
briefings, planet descriptions) for Starboard.

Every Star Citizen install has it. Starboard looks for it in this order:
  1. A text file you picked yourself (SETTINGS > MY DATA).
  2. LIVE\\Data\\Localization\\english\\global.ini: this is there when a text mod such
     as StarStrings is installed, and it has extra details (component grades...).
  3. Inside LIVE\\Data.p4k, the game's main archive, which every player has. Only
     that one file is read out of it; the archive is never changed.
The parts Starboard needs are saved in user/gametext.json and only read again
when the source file changes (after a game patch). The text belongs to the game
and stays on your PC.
"""

import json
import os
import re
import struct
import zlib

INI_REL = os.path.join("Data", "Localization", "english", "global.ini")
P4K_NAME = "Data/Localization/english/global.ini"
ROMAN = {1: "I", 2: "II", 3: "III", 4: "IV", 5: "V", 6: "VI", 7: "VII", 8: "VIII"}


# ------------------------------------------------------------------ reading Data.p4k
def _zstd_decompress(data, size):
    try:
        from compression import zstd  # Python 3.14+
        return zstd.decompress(data)
    except ImportError:
        pass
    import zstandard  # optional fallback for older Pythons
    return zstandard.ZstdDecompressor().decompress(data, max_output_size=max(size, len(data) * 20))


def read_from_p4k(p4k_path, name=P4K_NAME, chunk=32 * 1024 * 1024):
    """One file out of a Star Citizen .p4k (a Zip64 archive with a few twists). Returns bytes."""
    want = name.encode("utf-8")
    want_alt = name.replace("/", "\\").encode("utf-8")
    with open(p4k_path, "rb") as f:
        f.seek(0, 2)
        end = f.tell()
        tail_len = min(end, 1024 * 1024)
        f.seek(end - tail_len)
        tail = f.read(tail_len)
        i = tail.rfind(b"PK\x05\x06")
        if i < 0:
            raise ValueError("not a zip archive (no end record)")
        cd_size, cd_off = struct.unpack("<II", tail[i + 12:i + 20])
        loc = tail.rfind(b"PK\x06\x07", 0, i)
        if loc >= 0:  # Zip64
            z64_off = struct.unpack("<Q", tail[loc + 8:loc + 16])[0]
            f.seek(z64_off)
            z = f.read(56)
            if z[:4] != b"PK\x06\x06":
                raise ValueError("bad zip64 end record")
            cd_size, cd_off = struct.unpack("<QQ", z[40:56])
        # look for the name in the central directory, a chunk at a time
        pos, carry = cd_off, b""
        hdr = None
        while pos < cd_off + cd_size:
            f.seek(pos)
            block = f.read(min(chunk, cd_off + cd_size - pos))
            if not block:
                break
            buf = carry + block
            base = pos - len(carry)
            for needle in (want, want_alt):
                j = buf.find(needle)
                while j >= 0:
                    start = j - 46
                    if start >= 0 and buf[start:start + 2] == b"PK":
                        fn_len = struct.unpack("<H", buf[start + 28:start + 30])[0]
                        if fn_len == len(needle):
                            hdr = (base + start, buf[start:start + 46])
                            break
                    j = buf.find(needle, j + 1)
                if hdr:
                    break
            if hdr:
                break
            carry = buf[-512:]
            pos += len(block)
        if not hdr:
            raise FileNotFoundError(f"{name} not found in {os.path.basename(p4k_path)}")
        hpos, h = hdr
        method = struct.unpack("<H", h[10:12])[0]
        csize, usize = struct.unpack("<II", h[20:28])
        fn_len, ex_len = struct.unpack("<HH", h[28:32])
        local_off = struct.unpack("<I", h[42:46])[0]
        f.seek(hpos + 46 + fn_len)
        extra = f.read(ex_len)
        # Zip64 extra field: sizes and offset that did not fit in 32 bits
        k = 0
        while k + 4 <= len(extra):
            tag, ln = struct.unpack("<HH", extra[k:k + 4])
            body = extra[k + 4:k + 4 + ln]
            if tag == 0x0001:
                vals, q = [], 0
                while q + 8 <= len(body):
                    vals.append(struct.unpack("<Q", body[q:q + 8])[0])
                    q += 8
                it = iter(vals)
                if usize == 0xFFFFFFFF:
                    usize = next(it, usize)
                if csize == 0xFFFFFFFF:
                    csize = next(it, csize)
                if local_off == 0xFFFFFFFF:
                    local_off = next(it, local_off)
            k += 4 + ln
        if len(extra) > 168 and extra[168] > 0:
            raise ValueError("the text file is encrypted in this version of the archive")
        f.seek(local_off)
        lh = f.read(30)
        if lh[:2] != b"PK":
            raise ValueError("bad local header")
        l_fn, l_ex = struct.unpack("<HH", lh[26:30])
        f.seek(local_off + 30 + l_fn + l_ex)
        data = f.read(csize)
    if method == 0:
        return data
    if method == 8:
        return zlib.decompress(data, -15)
    if method in (93, 100):
        return _zstd_decompress(data, usize)
    raise ValueError(f"unknown compression method {method}")


# ------------------------------------------------------------------ parsing
def parse_ini(text):
    out = {}
    for line in text.splitlines():
        if "=" not in line or line.startswith((";", "#")):
            continue
        k, v = line.split("=", 1)
        k = k.strip().lstrip("﻿")
        if k.endswith(",P"):
            k = k[:-2]
        out[k] = v
    return out


def _clean(v):
    v = re.sub(r"<[^>]+>", "", v or "")
    return v.replace("\\n", "\n").strip()


def extract(table):
    """The parts Starboard uses, keyed in lower case."""
    items, vehicles, places, titles, descs, bodies = {}, {}, {}, {}, {}, {}
    for k, v in table.items():
        kl = k.lower()
        if kl.startswith("item_name") and len(k) > 9 and v:
            items[kl[9:]] = _clean(v)
        elif kl.startswith("vehicle_name") and not kl.endswith("_short") and v:
            vehicles[kl[12:]] = _clean(v)
        elif kl.endswith("_title") and v:
            titles[kl[:-6]] = _clean(v)
        elif re.match(r"^(stanton|pyro|nyx)\d[a-z]?(_[a-z0-9]+)*$", kl) or re.match(r"^rr_[a-z]+_[a-z0-9]+$", kl):
            places[kl] = _clean(v)
        if kl.endswith("_desc") and "potential" in v.lower() and "mineables" in v.lower():
            bodies[kl[:-5]] = _clean(v)
    for k, v in table.items():
        kl = k.lower()
        if kl.endswith("_desc") and kl[:-5] in titles:
            descs[kl[:-5]] = _clean(v)[:1500]
    return {"items": items, "vehicles": vehicles, "places": places, "titles": titles, "descs": descs,
            "bodies": bodies}


class GameText:
    def __init__(self, user_dir):
        self.cache_path = os.path.join(user_dir, "gametext.json")
        self.data = {}
        self.source = None      # where the text came from
        self.kind = None        # "mod", "p4k", "file"
        self.error = None

    @staticmethod
    def sources(live_dirs, chosen=None):
        out = []
        if chosen and os.path.isfile(chosen):
            out.append(("file" if chosen.lower().endswith(".ini") else "p4k", chosen))
        for d in live_dirs:
            ini = os.path.join(d, INI_REL)
            if os.path.isfile(ini):
                out.append(("mod", ini))
        for d in live_dirs:
            p4k = os.path.join(d, "Data.p4k")
            if os.path.isfile(p4k):
                out.append(("p4k", p4k))
        return out

    def counts(self):
        return {k: len(v) for k, v in (self.data or {}).items()}

    def load_cached(self, live_dirs, chosen=None):
        """Only use the saved copy, and only if its source has not changed (fast, for startup)."""
        try:
            with open(self.cache_path, encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            return False
        for kind, path in self.sources(live_dirs, chosen):
            try:
                st = os.stat(path)
            except OSError:
                continue
            if cache.get("stamp") == [path, st.st_size, int(st.st_mtime)]:
                self.data, self.source, self.kind = cache["data"], path, kind
                return True
            return False  # the best source changed: read it again in the background
        return False

    def load(self, live_dirs, chosen=None, log=print):
        """Use the cache when the source file has not changed, otherwise read it again."""
        cache = None
        try:
            with open(self.cache_path, encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            pass
        self.error = None
        for kind, path in self.sources(live_dirs, chosen):
            try:
                st = os.stat(path)
            except OSError:
                continue
            stamp = [path, st.st_size, int(st.st_mtime)]
            if cache and cache.get("stamp") == stamp:
                self.data, self.source, self.kind = cache["data"], path, kind
                return True
            try:
                log(f"Reading the game's text from {path}...")
                raw = read_from_p4k(path) if kind == "p4k" else open(path, "rb").read()
                table = parse_ini(raw.decode("utf-8-sig", errors="replace"))
                if len(table) < 1000:
                    raise ValueError("the file looks empty")
                self.data, self.source, self.kind = extract(table), path, kind
                tmp = self.cache_path + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump({"stamp": stamp, "kind": kind, "data": self.data}, f)
                os.replace(tmp, self.cache_path)
                return True
            except Exception as e:
                self.error = f"{os.path.basename(path)}: {e}"
                log(f"Could not read the game's text from {path}: {e}")
        if cache and cache.get("data"):
            self.data, self.source, self.kind = cache["data"], (cache.get("stamp") or ["cache"])[0], "cache"
            return True
        return False

    # -- lookups (all return None when unknown)
    def item(self, cls):
        if not cls or not self.data:
            return None
        c = cls.lower()
        it = self.data["items"]
        return it.get(c) or it.get(re.sub(r"_\d{9,}$", "", c))

    def vehicle(self, cls):
        if not cls or not self.data:
            return None
        c = re.sub(r"_\d{6,}$", "", cls.lower())
        return self.data["vehicles"].get(c)

    def place(self, code):
        if not code or not self.data:
            return None
        return self.data["places"].get(code.lower())

    def contract(self, debug_name):
        """Title and briefing for a contract's internal name, e.g. 'Hockrow_FacilityDelve_P2M2-Stanton4_Repeat_0'."""
        if not debug_name or not self.data:
            return None, None
        base = debug_name.split("-")[0].lower()
        short = re.sub(r"_(very)?(easy|medium|hard)", lambda m: "_" + ("v" if m[1] else "") + m[2][0], base)
        cands = [base, re.sub(r"_\d+$", "", base), re.sub(r"_repeat.*$", "", base), short,
                 re.sub(r"_\d+$", "", short)]
        for c in cands:
            if c in self.data["titles"]:
                return self.data["titles"][c], self.data["descs"].get(c)
        return None, None

    def mineables(self, body_name):
        """(ship ores, hand ores) the game lists for a planet or moon, or None."""
        if not self.data or not body_name:
            return None
        bn = re.sub(r"[^a-z0-9]", "", body_name.lower())
        stanton = {"hurston": "stanton1", "arial": "stanton1a", "aberdeen": "stanton1b", "magda": "stanton1c",
                   "ita": "stanton1d", "crusader": "stanton2", "cellin": "stanton2a", "daymar": "stanton2b",
                   "yela": "stanton2c", "arccorp": "stanton3", "lyria": "stanton3a", "wala": "stanton3b",
                   "microtech": "stanton4", "calliope": "stanton4a", "clio": "stanton4b", "euterpe": "stanton4c"}
        for key, text in self.data.get("bodies", {}).items():
            k = key.lower()
            parts = k.split("_")
            name_part = re.sub(r"[^a-z0-9]", "", "".join(parts[1:])) if len(parts) > 1 else ""
            code = parts[0]
            ok = (name_part and name_part == bn) or stanton.get(bn) == code
            m = re.match(r"pyro(\d)$", code)
            if m and not name_part and bn == "pyro" + ROMAN.get(int(m.group(1)), "").lower():
                ok = True
            if ok:
                return _mine_lists(text)
        return None


def _mine_lists(text):
    def block(label):
        m = re.search(label + r"\s*:\s*\n((?:[^\n]+\n?)+?)(?:\n\s*\n|$)", text)
        return [x.strip() for x in m.group(1).split("\n") if x.strip()] if m else []
    return block("Potential Ship Mineables"), block("Potential Hand Mineables")
