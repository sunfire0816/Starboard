"""
Radar signature identifier.

When you ping in Star Citizen, every rock, gem deposit, harvestable and salvage
piece shows a signature number. A cluster shows the single-item signature
times the number of items in it, so 6340 is two Quantainium rocks (2 x 3170).

identify() turns any number into a ranked list of what it can be, using where
you are (surface or space, which planet, what spawns there) to rank them.
"""

import json
import os
import re

CATEGORY_LABEL = {"ship": "Ship mining", "vehicle": "ROC mining", "hand": "Hand mining",
                  "harvestable": "Harvestable", "salvage": "Salvage", "custom": "Your entry"}
MODES = ["Auto", "Ship mining", "ROC mining", "Hand mining", "Salvage", "Harvestables"]
MODE_CATS = {"Ship mining": {"ship"}, "ROC mining": {"vehicle"}, "Hand mining": {"hand"},
             "Salvage": {"salvage"}, "Harvestables": {"harvestable"}}
RARITY_RANK = {"Legendary": 4, "Epic": 3, "Rare": 2, "Uncommon": 1, "Common": 0, "": 0}

# how likely each kind of signature is in each setting
CONTEXT_WEIGHT = {
    "surface": {"ship": 1.0, "vehicle": 1.0, "hand": 0.9, "harvestable": 0.35, "salvage": 0.15, "custom": 1.0},
    "air":     {"ship": 1.0, "vehicle": 0.5, "hand": 0.4, "harvestable": 0.3, "salvage": 0.3, "custom": 1.0},
    "space":   {"ship": 1.0, "vehicle": 0.02, "hand": 0.02, "harvestable": 0.02, "salvage": 0.9, "custom": 1.0},
    "unknown": {"ship": 1.0, "vehicle": 0.8, "hand": 0.7, "harvestable": 0.5, "salvage": 0.6, "custom": 1.0},
}


class SignatureDB:
    def __init__(self, data_dir, user_dir):
        self.user_path = os.path.join(user_dir, "signatures_custom.json")
        with open(os.path.join(data_dir, "signatures.json"), encoding="utf-8") as f:
            raw = json.load(f)
        self.entries = raw["entries"]
        self.custom = []
        if os.path.exists(self.user_path):
            try:
                with open(self.user_path, encoding="utf-8") as f:
                    self.custom = json.load(f)
            except (OSError, json.JSONDecodeError):
                self.custom = []

    def all_entries(self):
        return self.entries + [dict(c, category="custom", min=1, max=c.get("max", 10), cluster=[1, 1],
                                    rarity="", materials=[]) for c in self.custom]

    def teach(self, value, name, count=1, note=""):
        """Remember a signature you identified yourself (any object, even ships)."""
        base = round(value / max(1, count))
        self.custom = [c for c in self.custom if not (c["name"] == name and c["base"] == base)]
        self.custom.append({"name": name, "base": base, "max": 10, "note": note})
        os.makedirs(os.path.dirname(self.user_path), exist_ok=True)
        with open(self.user_path, "w", encoding="utf-8") as f:
            json.dump(self.custom, f, indent=1)
        return base

    def forget(self, name, base):
        self.custom = [c for c in self.custom if not (c["name"] == name and c["base"] == base)]
        with open(self.user_path, "w", encoding="utf-8") as f:
            json.dump(self.custom, f, indent=1)

    # ------------------------------------------------------------------
    def identify(self, value, world=None, here=None, mode="Auto", limit=8):
        """Ranked candidates for a signature value. Each is a dict with
        name, count, base, category, exact, score (0-100), rarity, detail."""
        if value is None or value <= 0:
            return []
        setting, ores = self._context(world, here)
        allowed = MODE_CATS.get(mode)
        tol = max(2, value * 0.002)  # covers a misread digit or rounding on screen
        cands = []
        for e in self.all_entries():
            cat = e["category"]
            if allowed and cat not in allowed and cat != "custom":
                continue
            base = e["base"]
            n_lo, n_hi = e.get("min", 1), e.get("max", 1)
            n = round(value / base)
            if n < n_lo or n > n_hi:
                continue
            diff = abs(n * base - value)
            if diff > tol:
                continue
            exact = diff == 0
            score = CONTEXT_WEIGHT[setting].get(cat, 0.5)
            cmin, cmax = e.get("cluster", [1, 1])
            if n > cmax:
                score *= 0.35  # bigger group than this usually spawns in
            elif n >= cmin and n > 1:
                score *= 1.3   # a typical group size
            if not exact:
                score *= 0.3
            spawn_txt = ""
            warn = False
            if ores is not None:
                if cat == "ship":
                    share = _share(ores.get("ship", []), e["name"])
                    if share is None:
                        score *= 0.06
                        spawn_txt = "not known to spawn here"
                        warn = True
                    else:
                        score *= 1.0 + share / 15.0
                        spawn_txt = f"{share:g}% of rocks here"
                elif cat in ("vehicle", "hand"):
                    here_list = [(m, _share(ores.get(cat, []), m)) for m in e["materials"]]
                    here_list = [(m, s) for m, s in here_list if s is not None]
                    if here_list:
                        score *= 1.4
                        spawn_txt = ", ".join(f"{m} {s:g}%" for m, s in sorted(here_list, key=lambda x: -x[1]))
                    else:
                        score *= 0.15
                        spawn_txt = "not known to spawn here"
                        warn = True
                elif cat == "harvestable":
                    names = [m for m, _ in ores.get("harvestable", [])]
                    if names:
                        score *= 1.2
                        spawn_txt = ", ".join(names[:4])
            if cat == "custom":
                score *= 1.6
            label = e["name"] if n == 1 else f"{e['name']} x{n}"
            what = {"ship": "rock", "vehicle": "deposit", "hand": "deposit", "harvestable": "item",
                    "salvage": "piece", "custom": "object"}.get(cat, "object")
            detail = [CATEGORY_LABEL.get(cat, cat)]
            if e.get("rarity"):
                detail.append(e["rarity"])
            detail.append(f"{n} {what}{'s' if n != 1 else ''} of {base:,}")
            if spawn_txt:
                detail.append(spawn_txt)
            if not exact:
                detail.append(f"close match ({n * base:,})")
            cands.append({"name": e["name"], "label": label, "count": n, "base": base, "category": cat,
                          "exact": exact, "raw": score, "warn": warn or not exact, "rarity": e.get("rarity", ""),
                          "detail": "  ·  ".join(detail), "materials": e.get("materials", [])})
        if not cands:
            return []
        total = sum(c["raw"] for c in cands)
        for c in cands:
            c["score"] = round(100 * c["raw"] / total)
        cands.sort(key=lambda c: (-c["raw"], -RARITY_RANK.get(c["rarity"], 0)))
        return cands[:limit]

    @staticmethod
    def _context(world, here):
        """('surface'|'air'|'space'|'unknown', ore lists for where you are or None)."""
        if world is None or here is None:
            return "unknown", None
        body = here.get("body")
        if body is not None:
            alt = here.get("alt", 0)
            setting = "surface" if alt < 8 else ("air" if alt < body.radius * 0.5 else "space")
            ores = world.ores.get(body.name)
            if setting == "space":
                ores = None
            return setting, ores
        zone = here.get("zone")
        return "space", (world.ores.get(zone) if zone else None)


def _share(items, name):
    for n, pct in items:
        if n == name:
            return pct if pct is not None else 1.0
    return None


_NUM_RE = re.compile(r"(?<![\d.])(\d{1,3}(?:[ ,.]\d{3})+|\d{4,6})(?![\d])")


def numbers_in_text(text):
    """Signature-sized numbers (1,000 to 999,999) found in OCR or pasted text."""
    out = []
    for m in _NUM_RE.finditer(text or ""):
        v = int(re.sub(r"[ ,.]", "", m.group(1)))
        if 1000 <= v <= 999999:
            out.append(v)
    return out


SIG_CLIP_RE = re.compile(r"^\s*SCSIG\s*:\s*([\d ,.]+)\s*$", re.IGNORECASE)


def parse_sig_clip(text):
    """'SCSIG:6340' (from the hotkey script) -> 6340."""
    m = SIG_CLIP_RE.match(text or "")
    if not m:
        return None
    digits = re.sub(r"[^\d]", "", m.group(1))
    return int(digits) if digits else None
