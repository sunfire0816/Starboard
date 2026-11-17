"""
Ship builder data for Starboard, from the Star Citizen Wiki API (api.star-citizen.wiki).

* parts: every ship weapon, missile, missile rack, shield, power plant, cooler and quantum
  drive with its stats, where UEX says it is sold, and the blueprint that crafts it.
* ships: a ship's slots (hardpoints) with their sizes and stock parts, fetched one ship
  at a time when you pick it.

Totals are worked out the simple way (everything switched on), so they are a guide for
comparing builds, not an exact copy of the game's power and heat model.
"""

import json
import os
import re
import time
import urllib.parse

import wikidata

PART_TYPES = ["WeaponGun", "Missile", "MissileLauncher", "Shield", "PowerPlant", "Cooler", "QuantumDrive"]
GROUPS = [("WeaponGun", "WEAPONS"), ("Missile", "MISSILES"), ("Shield", "SHIELDS"), ("PowerPlant", "POWER"),
          ("Cooler", "COOLING"), ("QuantumDrive", "QUANTUM")]
TYPE_WORD = {"WeaponGun": "Weapon", "Missile": "Missile", "MissileLauncher": "Missile rack", "Shield": "Shield",
             "PowerPlant": "Power plant", "Cooler": "Cooler", "QuantumDrive": "Quantum drive"}


def _n(v):
    return wikidata._num(v)


def _power_use(d):
    """Power segments a part uses (or makes, for a power plant) when it is on."""
    for st in ((d.get("resource_network") or {}).get("states") or [])[:1]:
        for de in st.get("deltas") or []:
            if de.get("resource") == "Power" and de.get("type") in ("Consumption", "Conversion"):
                return _n(de.get("rate")) or 0
    return 0


CLASS_INFO = {
    "Military": "Built for combat: tough and strong, but gives off more heat (IR) and electronic noise (EM), "
                "so other ships spot you sooner.",
    "Stealth": "The lowest EM and IR signatures, so you are harder to detect and lock onto. Usually a bit less "
               "durable.",
    "Civilian": "Everyday parts: affordable and middle of the road, with moderate signatures.",
    "Industrial": "Built to last: durable and dependable, with higher signatures.",
    "Competition": "Built for racing performance, with higher signatures.",
}
GRADE_INFO = "Grade A is the best of its class, D the most basic."


def _signature(d):
    """(EM, IR) the part gives off while switched on (Star Citizen Wiki data)."""
    for st in ((d.get("resource_network") or {}).get("states") or []):
        if isinstance(st, dict) and (st.get("name") or "").lower() == "online" and isinstance(st.get("signature"), dict):
            sig = st["signature"]
            return _n(sig.get("em")) or 0, _n(sig.get("ir")) or 0
    e = d.get("emission") or {}
    return _n(e.get("em_max") or e.get("em")) or 0, _n(e.get("ir")) or 0


def short_num(v):
    v = float(v or 0)
    return f"{v / 1000:.1f}k" if v >= 10000 else f"{v:,.0f}"


def sig_text(p):
    if not (p.get("em") or p.get("ir")):
        return ""
    return f"EM {short_num(p.get('em'))} · IR {short_num(p.get('ir'))}"


def normalize_part(d):
    typ = d.get("type") or ""
    if typ not in PART_TYPES or not d.get("uuid") or not d.get("name"):
        return None
    name = d["name"]
    if "placeholder" in name.lower() or name == name.lower():
        return None
    p = {"uuid": d["uuid"], "name": name, "type": typ, "size": int(_n(d.get("size")) or 0),
         "grade": d.get("grade") or "", "cls": d.get("class") or "",
         "maker": wikidata._name(d.get("manufacturer")), "power": _power_use(d),
         "craftable": bool(d.get("is_craftable")), "lootable": bool(d.get("is_lootable")),
         "bp": [b.get("uuid") for b in (d.get("blueprint") or []) if isinstance(b, dict) and b.get("uuid")],
         "web": d.get("web_url") or "", "buy": []}
    em, ir = _signature(d)
    p.update(em=em, ir=ir, health=_n((d.get("durability") or {}).get("health")) or 0,
             distortion=_n((d.get("distortion") or {}).get("max") or (d.get("distortion") or {}).get("maximum")) or 0)
    for r in ((d.get("uex_prices") or {}).get("purchase") or []):
        if not isinstance(r, dict) or not _n(r.get("price_buy")):
            continue
        loc = r.get("starmap_location") or {}
        p["buy"].append({"terminal": r.get("terminal_name") or "", "price": _n(r.get("price_buy")),
                         "place": loc.get("name") or "", "body": loc.get("parent_name") or "",
                         "system": loc.get("star_system_name") or "",
                         "date": (r.get("date_updated") or "")[:10]})
    p["buy"].sort(key=lambda b: b["price"])
    if typ == "WeaponGun":
        w = d.get("vehicle_weapon") or {}
        modes = w.get("modes") or [{}]
        m = modes[0] or {}
        dmg = _n(w.get("damage_per_shot")) or 0
        rpm = _n(m.get("rpm") or w.get("rpm")) or 0
        dps = _n(m.get("damage_per_second")) or (dmg * rpm / 60 if dmg and rpm else 0)
        kinds = [x.get("name") for x in (w.get("damages") or []) if isinstance(x, dict) and x.get("name")]
        p.update(dps=dps, alpha=dmg * (_n(m.get("pellets_per_shot")) or 1), rpm=rpm, range=_n(w.get("range")) or 0,
                 ammo=_n(w.get("capacity")) or 0, kind=(w.get("type") or ""),
                 dmg_type="/".join(k.title() for k in kinds) or "")
    elif typ == "Missile":
        m = d.get("missile") or {}
        p.update(damage=_n(m.get("damage_total")) or sum(_n(x.get("damage")) or 0 for x in (m.get("damages") or [])
                                                         if isinstance(x, dict)),
                 signal=(m.get("signal_type") or ""), lock=_n(m.get("lock_time")) or 0,
                 speed=_n(m.get("speed")) or 0,
                 range=_n((m.get("flight") or {}).get("range")) or _n(m.get("lock_range_max")) or 0)
    elif typ == "MissileLauncher":
        r = d.get("missile_rack") or {}
        p.update(count=int(_n(r.get("missile_count")) or 0), missile_size=int(_n(r.get("missile_size")) or 0))
    elif typ == "Shield":
        s = d.get("shield") or {}
        ab = ((s.get("absorption") or {}).get("physical") or {})
        p.update(hp=_n(s.get("max_health")) or 0, regen=_n(s.get("regen_rate")) or 0,
                 delay=_n((s.get("regen_delay") or {}).get("damage")) or 0,
                 phys=(_n(ab.get("max")) or 0) * 100)
    elif typ == "PowerPlant":
        pp = d.get("power_plant") or {}
        p.update(segments=_n(pp.get("power_segment_generation")) or 0)
        p["power"] = 0
    elif typ == "Cooler":
        c = d.get("cooler") or {}
        p.update(coolant=_n(c.get("coolant_segment_generation")) or 0)
    elif typ == "QuantumDrive":
        q = d.get("quantum_drive") or {}
        sj = q.get("standard_jump") or {}
        p.update(speed=_n(sj.get("drive_speed")) or 0, cooldown=_n(sj.get("cooldown_time")) or 0,
                 fuel=_n(q.get("quantum_fuel_requirement")) or 0, spool=_n(sj.get("spool_up_time")) or 0)
    return p


def fetch_parts(cache, progress=None):
    rows = []
    for typ in PART_TYPES:
        idx = wikidata.fetch_index("items", {"filter[type]": typ},
                                   (lambda n, t=typ: progress(f"{TYPE_WORD[t]}s {n}")) if progress else None)
        if idx:
            cache.debug(f"parts_{typ}", idx[:1])
        for d in idx:
            p = normalize_part(d) if isinstance(d, dict) else None
            if p:
                rows.append(p)
    cache.save(rows)
    return rows


# ------------------------------------------------------------------ ships
def _label(port_name):
    n = re.sub(r"^(hardpoint|Hardpoint)_", "", port_name or "")
    n = re.sub(r"_?(generator|attach|hardpoint|class_\d+)", "", n)
    n = re.sub(r"_+", " ", n).strip()
    return (n[:1].upper() + n[1:]) if n else "Slot"


def normalize_ship(d):
    """Slots you can change: weapons (inside gimbals and turrets too), missile racks, shields, power plants,
    coolers and quantum drives."""
    slots = []

    def walk(ports, path, parent_label):
        for p in ports or []:
            if not isinstance(p, dict):
                continue
            typ = p.get("type") or ""
            sizes = p.get("sizes") or {}
            item = p.get("equipped_item") or {}
            pid = path + "/" + (p.get("name") or "?")
            label = _label(p.get("name"))
            if typ == "WeaponGun":
                slots.append({"id": pid, "type": "WeaponGun", "label": parent_label or label,
                              "min": int(_n(sizes.get("min")) or 0), "max": int(_n(sizes.get("max")) or 0),
                              "stock": item.get("uuid"), "stock_name": item.get("name") or "",
                              "editable": bool(p.get("editable"))})
                continue
            if typ == "MissileLauncher":
                kids = [k for k in (p.get("ports") or []) if isinstance(k, dict) and k.get("type") == "Missile"]
                if kids:
                    k0 = kids[0]
                    ks = k0.get("sizes") or {}
                    mi = k0.get("equipped_item") or {}
                    slots.append({"id": pid, "type": "Missile", "label": label.replace("Missilerack", "Missiles"),
                                  "min": int(_n(ks.get("min")) or 0), "max": int(_n(ks.get("max")) or 0),
                                  "count": len(kids), "stock": mi.get("uuid"), "stock_name": mi.get("name") or "",
                                  "rack": item.get("name") or "", "rack_stock": item.get("uuid"),
                                  "rack_min": int(_n(sizes.get("min")) or 0), "rack_max": int(_n(sizes.get("max")) or 0),
                                  "rack_editable": bool(p.get("editable")), "editable": bool(k0.get("editable"))})
                continue
            if typ in ("Shield", "PowerPlant", "Cooler", "QuantumDrive"):
                slots.append({"id": pid, "type": typ, "label": label, "min": int(_n(sizes.get("min")) or 0),
                              "max": int(_n(sizes.get("max")) or 0), "stock": item.get("uuid"),
                              "stock_name": item.get("name") or "", "editable": bool(p.get("editable"))})
                continue
            if typ in ("Turret", "TurretBase", "WeaponMount", "MannedTurret", "") or p.get("ports"):
                walk(p.get("ports"), pid, label if typ in ("Turret", "TurretBase", "MannedTurret") else parent_label)

    walk(d.get("ports"), "", "")
    order = {t: i for i, (t, _g) in enumerate(GROUPS)}
    slots.sort(key=lambda s: (order.get(s["type"], 9), s["label"]))
    # number duplicate labels: "Gun wing (1)", "Gun wing (2)"
    seen = {}
    for s in slots:
        seen[(s["type"], s["label"])] = seen.get((s["type"], s["label"]), 0) + 1
    count = {}
    for s in slots:
        k = (s["type"], s["label"])
        if seen[k] > 1:
            count[k] = count.get(k, 0) + 1
            s["label"] = f"{s['label']} ({count[k]})"
    return {"uuid": d.get("uuid"), "name": d.get("name") or "", "slots": slots,
            "web": d.get("web_url") or "", "fetched": time.time()}


def fetch_ship(user_dir, uuid, name):
    """A ship's slots, from the cache if it is less than a week old."""
    folder = os.path.join(user_dir, "wiki", "ships")
    os.makedirs(folder, exist_ok=True)
    key = re.sub(r"[^A-Za-z0-9_-]", "_", uuid or name)
    path = os.path.join(folder, key + ".json")
    try:
        with open(path, encoding="utf-8") as f:
            c = json.load(f)
        if time.time() - c.get("fetched", 0) < 7 * 86400 and c.get("slots"):
            return c
    except Exception:
        c = None
    last = None
    for k in [x for x in (uuid, name) if x]:
        try:
            j = wikidata._get(f"{wikidata.API}/vehicles/{urllib.parse.quote(k)}")
        except Exception as e:
            last = e
            continue
        d = j.get("data", j) if isinstance(j, dict) else {}
        if d.get("ports"):
            s = normalize_ship(d)
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(s, f)
            os.replace(tmp, path)
            return s
    if c and c.get("slots"):
        return c
    if last:
        raise last
    return None


# ------------------------------------------------------------------ racks and fitting
def rack_key(slot):
    return slot["id"] + "#rack"


def rack_of(slot, fitted, parts):
    """The missile rack on a missile slot (the stock one unless you changed it)."""
    return parts.get(fitted.get(rack_key(slot), slot.get("rack_stock")))


def rack_slot(slot):
    """A pretend slot for choosing a missile rack on this hardpoint."""
    return {"id": rack_key(slot), "type": "MissileLauncher", "min": slot.get("rack_min", 0),
            "max": slot.get("rack_max", 0), "stock": slot.get("rack_stock"), "label": slot["label"] + " rack"}


def missile_room(slot, fitted, parts):
    """(how many missiles, smallest size, largest size) for a missile slot with its current rack."""
    if rack_key(slot) in fitted:
        r = parts.get(fitted[rack_key(slot)])
        if r and r.get("count"):
            ms = r.get("missile_size") or slot["max"]
            return r["count"], ms, ms
    return slot.get("count", 1), slot["min"], slot["max"]


def fits(part, slot, fitted=None, parts=None):
    if part["type"] != slot["type"]:
        return False
    lo, hi = slot["min"], slot["max"]
    if slot["type"] == "Missile" and fitted is not None:
        _n, lo, hi = missile_room(slot, fitted, parts or {})
    return lo <= part["size"] <= hi


def fitted_part(slot, fitted, parts):
    """The part in a slot: your choice, else the stock part if it still fits (a new rack can rule it out)."""
    uid = fitted.get(slot["id"])
    if uid:
        return parts.get(uid)
    p = parts.get(slot["stock"])
    if p and slot["type"] == "Missile" and rack_key(slot) in fitted and not fits(p, slot, fitted, parts):
        return None
    return p


# ------------------------------------------------------------------ totals


def totals(ship, fitted, parts):
    """Ship totals for a build. fitted: slot id -> part uuid (missing = stock)."""
    t = {"dps": 0, "alpha": 0, "missiles": 0, "missile_dmg": 0, "shield_hp": 0, "shield_regen": 0,
         "power_made": 0, "power_used": 0, "coolant": 0, "qt_speed": 0, "qt_fuel": 0, "guns": 0,
         "dmg_types": {}, "em": 0, "ir": 0}
    for s in ship["slots"]:
        p = fitted_part(s, fitted, parts)
        if not p:
            continue
        typ = s["type"]
        if typ != "Missile":  # missiles sit cold on the rack
            t["em"] += p.get("em", 0) or 0
            t["ir"] += p.get("ir", 0) or 0
        if typ == "WeaponGun":
            t["dps"] += p.get("dps", 0)
            t["alpha"] += p.get("alpha", 0)
            t["guns"] += 1
            for k in (p.get("dmg_type") or "Other").split("/"):
                t["dmg_types"][k] = t["dmg_types"].get(k, 0) + p.get("dps", 0)
            t["power_used"] += p.get("power", 0)
        elif typ == "Missile":
            n = missile_room(s, fitted, parts)[0]
            t["missiles"] += n
            t["missile_dmg"] += n * p.get("damage", 0)
        elif typ == "Shield":
            t["shield_hp"] += p.get("hp", 0)
            t["shield_regen"] += p.get("regen", 0)
            t["power_used"] += p.get("power", 0)
        elif typ == "PowerPlant":
            t["power_made"] += p.get("segments", 0)
        elif typ == "Cooler":
            t["coolant"] += p.get("coolant", 0)
            t["power_used"] += p.get("power", 0)
        elif typ == "QuantumDrive":
            t["qt_speed"] = max(t["qt_speed"], p.get("speed", 0))
            t["qt_fuel"] = max(t["qt_fuel"], p.get("fuel", 0))
            t["power_used"] += p.get("power", 0)
    return t


def cost(ship, fitted, parts):
    """aUEC to buy every part that differs from stock (cheapest UEX price), and parts nobody sells."""
    total, unsold = 0, []
    for s in ship["slots"]:
        if s["type"] == "Missile" and fitted.get(rack_key(s)) not in (None, s.get("rack_stock")):
            r = parts.get(fitted[rack_key(s)])
            if r:
                if r["buy"]:
                    total += r["buy"][0]["price"]
                else:
                    unsold.append(r["name"])
        uid = fitted.get(s["id"])
        if not uid or uid == s["stock"]:
            if s["type"] == "Missile" and rack_key(s) in fitted:
                # a bigger rack with the stock missile: buy the extra missiles
                extra = missile_room(s, fitted, parts)[0] - s.get("count", 1)
                p = fitted_part(s, fitted, parts)
                if extra > 0 and p and p["buy"]:
                    total += p["buy"][0]["price"] * extra
            continue
        p = parts.get(uid)
        if not p:
            continue
        n = missile_room(s, fitted, parts)[0] if s["type"] == "Missile" else 1
        if p["buy"]:
            total += p["buy"][0]["price"] * n
        else:
            unsold.append(p["name"])
    return total, unsold


def key_stat(p):
    t = p["type"]
    if t == "WeaponGun":
        return f"{p.get('dps', 0):,.0f} DPS  {p.get('dmg_type', '')}"
    if t == "Missile":
        return f"{p.get('damage', 0):,.0f} dmg  {p.get('signal', '')}"
    if t == "MissileLauncher":
        return f"{p.get('count', 0)} x S{p.get('missile_size', 0)} missiles"
    if t == "Shield":
        return f"{p.get('hp', 0):,.0f} HP  {p.get('regen', 0):,.0f}/s"
    if t == "PowerPlant":
        return f"{p.get('segments', 0):g} power"
    if t == "Cooler":
        return f"{p.get('coolant', 0):g} cooling"
    if t == "QuantumDrive":
        return f"{p.get('speed', 0) / 1e6:,.0f} Mm/s"
    return ""


# ------------------------------------------------------------------ share codes
def build_code(ship_name, fitted):
    """A short text code for a build, to paste in Discord: SB1:<compressed json>."""
    import base64
    import zlib
    raw = json.dumps({"s": ship_name, "f": fitted}, separators=(",", ":")).encode("utf-8")
    return "SB1:" + base64.urlsafe_b64encode(zlib.compress(raw, 9)).decode("ascii")


def read_code(code):
    """(ship name, fitted) from a build code, or raise ValueError."""
    import base64
    import zlib
    code = (code or "").strip()
    if not code.startswith("SB1:"):
        raise ValueError("not a Starboard build code (they start with SB1:)")
    try:
        d = json.loads(zlib.decompress(base64.urlsafe_b64decode(code[4:].encode("ascii"))))
        return d["s"], dict(d.get("f") or {})
    except Exception:
        raise ValueError("the code is damaged or cut off")
