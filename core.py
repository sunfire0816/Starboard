"""
Star Citizen Locator: math and data layer (no GUI).

How it works
------------
Typing /showlocation in Star Citizen's chat copies your position to the
clipboard as system-frame coordinates in meters. Planets and moons spin, and
every surface location (outposts, caves, stations, landing zones) is stored in
the body's own rotating frame. To compare the two, we work out how far each
body has rotated since 2020-01-01 00:00 UTC (the reference the game uses),
then rotate your position into that body's frame.

    rotation_deg = (fraction_of_current_day * 360 + rotation_correction) % 360
    local = Rz(-rotation_deg) * (global - body_center)

The rotation correction can drift between patches or servers. The app lets you
recalibrate a body by standing at a known location (see World.calibrate).

All distances in this module are kilometers.
"""

import csv
import datetime as dt
import io
import json
import math
import os
import re

EPOCH = dt.datetime(2020, 1, 1, tzinfo=dt.timezone.utc)
import sys

# Program files: next to sc_locator.py, or next to Starboard.exe when packaged (PyInstaller).
HERE = os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__))
DATA_DIR = os.path.join(HERE, "data")
OLD_USER_DIR = os.path.join(HERE, "user")


def _user_dir():
    """Your own data (settings, hangar, ledger, plans, game log history) lives outside the program
    folder on Windows, in %LOCALAPPDATA%\\Starboard, so installing or rebuilding Starboard never
    touches it and the Python and .exe versions share it. A file named portable.txt next to the
    program keeps everything in its own user folder instead (for a USB stick)."""
    base = os.environ.get("LOCALAPPDATA")
    if os.path.exists(os.path.join(HERE, "portable.txt")) or not base or not sys.platform.startswith("win"):
        return OLD_USER_DIR
    new = os.path.join(base, "Starboard")
    # first start after this change: bring the data from the program's own user folder along
    if not os.path.exists(os.path.join(new, "settings.json")) and \
            os.path.exists(os.path.join(OLD_USER_DIR, "settings.json")):
        try:
            import shutil
            shutil.copytree(OLD_USER_DIR, new, dirs_exist_ok=True)
            with open(os.path.join(OLD_USER_DIR, "MOVED.txt"), "w", encoding="utf-8") as f:
                f.write("Starboard now keeps your data in " + new + "\nThis folder is an old copy; "
                        "you can delete it once Starboard has started fine.\n")
        except OSError:
            return OLD_USER_DIR
    os.makedirs(new, exist_ok=True)
    return new


USER_DIR = _user_dir()

ROTATING_TYPES = ("Planet", "Moon", "Planetoid")
# Static objects (stations, jump points, Lagrange points) this close decide the
# system when you are not near any planet or moon.
SYSTEM_HINT_RANGE_KM = 2_000_000
SYSTEM_SWITCH_KM = 250_000   # this close to another system's object means you are in that system
# The rotation corrections in the data are measured for day/night (sun) maths, which
# counts longitude from a different axis. For placing coordinates the planet's real
# spin is 90 degrees further on. Confirmed against in-game /showlocation readings at
# Area 18 and Baijini Point (ArcCorp), and matches StarMap's rotation values.
ROTATION_FRAME_OFFSET = 90.0
# How close (as a multiple of body radius) you must be to count as "at" a body.
SOI_MULTIPLIER = 3.0

_NUM = r"(-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)"
COORD_RE = re.compile(
    r"x\s*[:=]?\s*" + _NUM + r"[\s,;]+y\s*[:=]?\s*" + _NUM + r"[\s,;]+z\s*[:=]?\s*" + _NUM,
    re.IGNORECASE,
)


def utcnow():
    return dt.datetime.now(dt.timezone.utc)


def parse_showlocation(text):
    """Return (x, y, z) in km from /showlocation clipboard text, or None."""
    if not text or len(text) > 2000:
        return None
    m = COORD_RE.search(text)
    if not m:
        return None
    try:
        x, y, z = (float(v) / 1000.0 for v in m.groups())  # meters -> km
    except ValueError:
        return None
    return (x, y, z)


# ---------------------------------------------------------------- vector math
def vsub(a, b):
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def vadd(a, b):
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def vlen(a):
    return math.sqrt(a[0] * a[0] + a[1] * a[1] + a[2] * a[2])


def rot_z(v, deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return (v[0] * c - v[1] * s, v[0] * s + v[1] * c, v[2])


def lat_lon_alt(local, radius):
    r = vlen(local)
    if r == 0:
        return 0.0, 0.0, -radius
    lat = math.degrees(math.asin(max(-1.0, min(1.0, local[2] / r))))
    lon = -math.degrees(math.atan2(local[0], local[1]))
    return lat, lon, r - radius


def local_from_lat_lon(lat, lon, r):
    """Inverse of lat_lon_alt (same longitude convention)."""
    p, l = math.radians(lat), math.radians(lon)
    return (-r * math.cos(p) * math.sin(l), r * math.cos(p) * math.cos(l), r * math.sin(p))


def surface_distance(lat1, lon1, lat2, lon2, radius):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(min(1.0, math.sqrt(h)))


def bearing(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.cos(p2) * math.sin(dl)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def compass_word(deg):
    names = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE",
             "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
    return names[int((deg + 11.25) // 22.5) % 16]


def fmt_km(km):
    km = abs(km)
    if km < 1:
        return f"{km * 1000:.0f} m"
    if km < 100:
        return f"{km:.1f} km"
    if km < 1_000_000:
        return f"{km:,.0f} km"
    return f"{km / 1_000_000:,.2f} Gm"


def _f(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------- data model
class Body:
    def __init__(self, row):
        self.name = row["name"]
        self.type = row["type"]
        self.parent = row["parentBody"] or None
        self.star = row["parentStar"] or (self.name if self.type == "Star" else None)
        self.pos = (_f(row["coordinateX"]), _f(row["coordinateY"]), _f(row["coordinateZ"]))
        self.radius = _f(row["bodyRadius"])
        self.rate_hours = _f(row["rotationRate"])
        self.correction = _f(row["rotationCorrection"])
        self.ordinal = row.get("ordinal", "")

    @property
    def rotates(self):
        return self.type in ROTATING_TYPES

    def __repr__(self):
        return f"<Body {self.name}>"


class Location:
    def __init__(self, name, type_, body, star, local, wiki="", quantum=False, source="db", note=""):
        self.name = name
        self.type = type_
        self.body = body
        self.star = star
        self.local = local
        self.wiki = wiki
        self.quantum = quantum
        self.source = source
        self.note = note

    def __repr__(self):
        return f"<Location {self.name} @ {self.body}>"


class World:
    def __init__(self, data_dir=DATA_DIR, user_dir=USER_DIR):
        self.data_dir = data_dir
        self.user_dir = user_dir
        os.makedirs(user_dir, exist_ok=True)
        self.bodies = {}
        self.locations = []
        self.ores = {}
        self.ore_meta = {}
        self.calibration = {}
        self._load()

    # ---------------- loading / saving
    def _load(self):
        with open(os.path.join(self.data_dir, "bodies.csv"), newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                b = Body(row)
                self.bodies[b.name] = b
        with open(os.path.join(self.data_dir, "locations.csv"), newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row["coordinateX"] == "" or row["parentBody"] not in self.bodies:
                    continue
                self.locations.append(Location(
                    row["name"], row["type"], row["parentBody"], row["parentStar"],
                    (_f(row["coordinateX"]), _f(row["coordinateY"]), _f(row["coordinateZ"])),
                    wiki=row.get("wikiLink", ""), quantum=row.get("quantum") == "1"))
        ore_path = os.path.join(self.data_dir, "ores.json")
        if os.path.exists(ore_path):
            with open(ore_path, encoding="utf-8") as f:
                raw = json.load(f)
            self.ores = raw.get("bodies", {})
            self.ore_meta = {k: v for k, v in raw.items() if k != "bodies"}
        self.calibration = self._read_json("calibration.json", {})
        for p in self._read_json("custom_pois.json", []):
            if p.get("body") in self.bodies:
                self.locations.append(self._custom_from_dict(p))
        om_path = os.path.join(self.data_dir, "orbital_markers.json")
        self.om_radius = {}
        if os.path.exists(om_path):
            with open(om_path, encoding="utf-8") as f:
                self.om_radius = json.load(f).get("radius_km", {})
        self.mining_log = [e for e in self._read_json("mining_log.json", []) if e.get("body") in self.bodies]
        for e in self.mining_log:
            self.locations.append(self._log_location(e))

    def _read_json(self, name, default):
        path = os.path.join(self.user_dir, name)
        if not os.path.exists(path):
            return default
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return default

    def _write_json(self, name, obj):
        path = os.path.join(self.user_dir, name)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, indent=1)
        os.replace(tmp, path)

    def _custom_from_dict(self, p):
        b = self.bodies[p["body"]]
        return Location(p["name"], p.get("type", "Custom"), p["body"], b.star,
                        (p["x"], p["y"], p["z"]), source="custom", note=p.get("note", ""))

    def save_custom_poi(self, name, type_, body_name, local, note=""):
        pois = self._read_json("custom_pois.json", [])
        entry = {"name": name, "type": type_, "body": body_name,
                 "x": round(local[0], 4), "y": round(local[1], 4), "z": round(local[2], 4),
                 "note": note, "created": utcnow().isoformat(timespec="seconds")}
        pois.append(entry)
        self._write_json("custom_pois.json", pois)
        loc = self._custom_from_dict(entry)
        self.locations.append(loc)
        return loc

    def delete_custom_poi(self, loc):
        pois = self._read_json("custom_pois.json", [])
        keep = [p for p in pois if not (p["name"] == loc.name and p["body"] == loc.body)]
        self._write_json("custom_pois.json", keep)
        self.locations = [l for l in self.locations if l is not loc]

    # ---------------- mining log
    def _log_location(self, e):
        b = self.bodies[e["body"]]
        q = f" Q{e['quality']}" if e.get("quality") not in (None, "") else ""
        loc = Location(f"{e['material']}{q}", "Logged find", e["body"], b.star, (e["x"], e["y"], e["z"]),
                       source="log", note=e.get("note", ""))
        loc.entry = e
        return loc

    def log_find(self, material, method, body_name, local, quality=None, amount="", note=""):
        e = {"id": utcnow().strftime("%Y%m%d%H%M%S%f"), "time": utcnow().isoformat(timespec="seconds"),
             "material": material, "method": method, "quality": quality, "amount": amount, "note": note,
             "body": body_name, "x": round(local[0], 4), "y": round(local[1], 4), "z": round(local[2], 4)}
        self.mining_log.append(e)
        self._write_json("mining_log.json", self.mining_log)
        loc = self._log_location(e)
        self.locations.append(loc)
        return loc

    def delete_log_entry(self, loc):
        eid = getattr(loc, "entry", {}).get("id")
        self.mining_log = [e for e in self.mining_log if e.get("id") != eid]
        self._write_json("mining_log.json", self.mining_log)
        self.locations = [l for l in self.locations if l is not loc]

    def log_locations(self):
        return [l for l in self.locations if l.source == "log"]

    # ---------------- sharing
    def share_items(self, include_pois=True, include_finds=True, systems=None):
        items = []
        for loc in self.locations:
            if not ((loc.source == "custom" and include_pois) or (loc.source == "log" and include_finds)):
                continue
            b = self.bodies[loc.body]
            if systems and b.star not in systems:
                continue
            lat, lon, alt = lat_lon_alt(loc.local, b.radius)
            it = {"kind": "poi" if loc.source == "custom" else "find", "name": loc.name, "type": loc.type,
                  "body": loc.body, "system": b.star, "x": round(loc.local[0], 4), "y": round(loc.local[1], 4),
                  "z": round(loc.local[2], 4), "lat": round(lat, 5), "lon": round(lon, 5), "alt_km": round(alt, 4),
                  "note": loc.note}
            if loc.source == "log":
                e = loc.entry
                it.update(material=e["material"], method=e.get("method", ""), quality=e.get("quality"),
                          amount=e.get("amount", ""), time=e.get("time", ""))
            items.append(it)
        return items

    def _resolve_body(self, name):
        if not name:
            return None
        if name in self.bodies:
            return self.bodies[name]
        low = str(name).strip().lower().replace(" ", "")
        for b in self.bodies.values():
            if b.name.lower().replace(" ", "") == low:
                return b
        return None

    def _item_local(self, it, body):
        try:
            if all(it.get(k) not in (None, "") for k in ("x", "y", "z")):
                return (float(it["x"]), float(it["y"]), float(it["z"]))
            if it.get("lat") not in (None, "") and it.get("lon") not in (None, ""):
                alt = float(it.get("alt_km") or 0)
                return local_from_lat_lon(float(it["lat"]), float(it["lon"]), body.radius + alt)
        except (TypeError, ValueError):
            return None
        return None

    def import_items(self, items, label=""):
        """Add shared spots and finds. Skips duplicates and unknown bodies."""
        report = {"added_pois": 0, "added_finds": 0, "duplicates": 0, "skipped": []}
        pois = self._read_json("custom_pois.json", [])
        existing = [(l.body, l.name.lower(), l.local) for l in self.locations]
        new_locs = []
        for it in items:
            body = self._resolve_body(it.get("body"))
            name = str(it.get("name") or it.get("material") or "").strip()
            if not body or not body.rotates or not name:
                report["skipped"].append(f"{name or '?'} ({it.get('body') or 'no body'})")
                continue
            local = self._item_local(it, body)
            if local is None:
                report["skipped"].append(f"{name} (no coordinates)")
                continue
            dup = False
            for eb, en, el in existing:
                if eb == body.name:
                    d = vlen(vsub(el, local))
                    if d < 0.01 or (d < 0.05 and en == name.lower()):
                        dup = True
                        break
            if dup:
                report["duplicates"] += 1
                continue
            existing.append((body.name, name.lower(), local))
            note = str(it.get("note") or "")
            if label:
                note = (note + " " if note else "") + f"[from {label}]"
            if it.get("kind") == "find" and it.get("material"):
                q = it.get("quality")
                try:
                    q = int(q) if q not in (None, "") else None
                except (TypeError, ValueError):
                    q = None
                e = {"id": utcnow().strftime("%Y%m%d%H%M%S%f") + str(len(self.mining_log)),
                     "time": it.get("time") or utcnow().isoformat(timespec="seconds"),
                     "material": str(it["material"]), "method": it.get("method") or "", "quality": q,
                     "amount": it.get("amount") or "", "note": note, "body": body.name,
                     "x": round(local[0], 4), "y": round(local[1], 4), "z": round(local[2], 4)}
                self.mining_log.append(e)
                new_locs.append(self._log_location(e))
                report["added_finds"] += 1
            else:
                entry = {"name": name, "type": str(it.get("type") or "Imported"), "body": body.name,
                         "x": round(local[0], 4), "y": round(local[1], 4), "z": round(local[2], 4),
                         "note": note, "created": utcnow().isoformat(timespec="seconds")}
                pois.append(entry)
                new_locs.append(self._custom_from_dict(entry))
                report["added_pois"] += 1
        if report["added_pois"]:
            self._write_json("custom_pois.json", pois)
        if report["added_finds"]:
            self._write_json("mining_log.json", self.mining_log)
        self.locations.extend(new_locs)
        return report

    # ---------------- systems and bodies
    def systems(self):
        return sorted({b.star for b in self.bodies.values() if b.type == "Star"})

    def surface_bodies(self, system=None):
        return [b for b in self.bodies.values()
                if b.rotates and (system is None or b.star == system)]

    def children(self, body_name):
        return [b for b in self.bodies.values() if b.parent == body_name and b.rotates]

    def locations_on(self, body_name):
        return [l for l in self.locations if l.body == body_name]

    # ---------------- rotation
    def correction(self, body):
        c = self.calibration.get(body.name)
        return c["correction"] if c else body.correction

    def is_calibrated(self, body):
        return body.name in self.calibration

    def rotation_deg(self, body, t):
        if not body.rotates or body.rate_hours == 0:
            return self.correction(body) % 360 if body.rotates else 0.0
        days = (t - EPOCH).total_seconds() / 86400.0
        cycle = days / (body.rate_hours / 24.0)
        return ((cycle % 1.0) * 360.0 + self.correction(body) + ROTATION_FRAME_OFFSET) % 360.0

    def to_local(self, body, g, t):
        v = vsub(g, body.pos)
        return rot_z(v, -self.rotation_deg(body, t)) if body.rotates else v

    def to_global(self, body, local, t):
        v = rot_z(local, self.rotation_deg(body, t)) if body.rotates else local
        return vadd(body.pos, v)

    def location_global(self, loc, t):
        return self.to_global(self.bodies[loc.body], loc.local, t)

    def calibrate(self, body, loc, g, t):
        """Solve the rotation correction so that position g (global, at time t)
        lines up with known location `loc` on `body`. Returns a dict with the
        new correction and how far off the old one was."""
        v = vsub(g, body.pos)
        meas = math.degrees(math.atan2(v[1], v[0]))
        known = math.degrees(math.atan2(loc.local[1], loc.local[0]))
        state = (meas - known) % 360
        if body.rate_hours:
            days = (t - EPOCH).total_seconds() / 86400.0
            frac = (days / (body.rate_hours / 24.0)) % 1.0
        else:
            frac = 0.0
        offset = ROTATION_FRAME_OFFSET if body.rate_hours else 0.0
        new_corr = (state - frac * 360.0 - offset) % 360.0
        old_local = self.to_local(body, g, t)
        old_err = vlen(vsub(old_local, loc.local))
        self.calibration[body.name] = {"correction": new_corr, "at": loc.name,
                                       "set": t.isoformat(timespec="seconds")}
        self._write_json("calibration.json", self.calibration)
        new_err = vlen(vsub(self.to_local(body, g, t), loc.local))
        return {"correction": new_corr, "old_error_km": old_err, "new_error_km": new_err,
                "radial_gap_km": abs(vlen(v) - vlen(loc.local))}

    def reset_calibration(self, body):
        if self.calibration.pop(body.name, None) is not None:
            self._write_json("calibration.json", self.calibration)

    # ---------------- the main query
    def find_body(self, g, system=None):
        """Return (body, ratio) for the body whose sphere of influence holds g."""
        best, best_ratio = None, None
        for b in self.surface_bodies(system):
            if b.radius <= 0:
                continue
            ratio = vlen(vsub(g, b.pos)) / b.radius
            if ratio <= SOI_MULTIPLIER and (best_ratio is None or ratio < best_ratio):
                best, best_ratio = b, ratio
        return best, best_ratio

    def guess_system(self, g, hint=None):
        """Both systems share one coordinate origin, so pick the system where
        the position actually lands inside a body's sphere of influence."""
        hits = []
        for s in self.systems():
            b, ratio = self.find_body(g, s)
            if b:
                hits.append((ratio, s))
        if hits:
            if hint in [s for _, s in hits]:
                return hint
            return min(hits)[1]
        near = {}
        for s in self.systems():
            n = self.nearest_space_objects(g, utcnow(), s, n=1)
            if n and n[0][0] < SYSTEM_HINT_RANGE_KM:
                near[s] = n[0][0]
        if not near:
            return hint or "Stanton"
        best = min(near, key=near.get)
        # in open space, stay in the system you were in unless you are right next to
        # something in another one (just out of a jump point, say)
        if hint and best != hint and near[best] > SYSTEM_SWITCH_KM and hint in self.systems():
            return hint
        return best

    def zones(self):
        return self.ore_meta.get("_zones", {})

    def zone_at(self, g, system):
        """Name of the asteroid ring you are inside (Nyx), or None."""
        for name, z in self.zones().items():
            if z.get("system") != system or z.get("kind") != "ring":
                continue
            star = self.bodies.get(system)
            r = math.hypot(g[0] - star.pos[0], g[1] - star.pos[1])
            if abs(r - z["radius_km"]) <= z["half_width_km"]:
                return name
        return None

    def zone_distance(self, name, g, t, system):
        """Rough distance from g to an ore zone (ring or group of stations)."""
        z = self.zones().get(name)
        if not z or z.get("system") != system:
            return None
        if z["kind"] == "ring":
            star = self.bodies[system]
            r = math.hypot(g[0] - star.pos[0], g[1] - star.pos[1])
            return max(0.0, abs(r - z["radius_km"]) - z["half_width_km"])
        dists = [vlen(vsub(g, self.location_global(l, t))) for l in self.locations
                 if l.star == system and z.get("match", "~") in l.name]
        return min(dists) if dists else None

    # ---------------- ore finder
    def materials(self):
        names = set()
        for data in self.ores.values():
            for items in data.values():
                names.update(n for n, _ in items)
        names.update(e["material"] for e in self.mining_log)
        return sorted(names)

    def ore_sources(self, material, here=None):
        """Every body or zone where `material` spawns, best share first.
        Each row: dict(source, system, method, share, distance_km or None)."""
        rows = []
        for src, data in self.ores.items():
            body = self.bodies.get(src)
            system = body.star if body else self.zones().get(src, {}).get("system")
            for method, items in data.items():
                for name, pct in items:
                    if name != material:
                        continue
                    dist = None
                    if here and here["system"] == system:
                        if body:
                            if here.get("body") is body:
                                dist = 0.0
                            else:
                                dist = max(0.0, vlen(vsub(here["global"], body.pos)) - body.radius)
                        else:
                            dist = self.zone_distance(src, here["global"], here["time"], system)
                    rows.append({"source": src, "system": system, "method": method,
                                 "share": pct, "distance_km": dist})
        # your own logged finds for this material, one row per body
        by_body = {}
        for loc in self.log_locations():
            if loc.entry["material"] == material:
                by_body.setdefault(loc.body, []).append(loc)
        for bname, locs in by_body.items():
            body = self.bodies[bname]
            dist = None
            if here and here["system"] == body.star:
                if here.get("body") is body:
                    dist = min(surface_distance(here["lat"], here["lon"],
                                                *lat_lon_alt(l.local, body.radius)[:2], body.radius) for l in locs)
                else:
                    dist = max(0.0, vlen(vsub(here["global"], body.pos)) - body.radius)
            rows.append({"source": bname, "system": body.star, "method": "log", "share": None,
                         "count": len(locs), "distance_km": dist})
        far = float("inf")
        rows.sort(key=lambda r: (r["method"] != "log", -(r["share"] or 0),
                                 far if r["distance_km"] is None else r["distance_km"], r["source"]))
        return rows

    def locate(self, g, t=None, system=None, max_nearby=40):
        t = t or utcnow()
        system = system or self.guess_system(g)
        body, _ = self.find_body(g, system)
        out = {"time": t, "global": g, "system": system, "body": body,
               "nearby": [], "space": []}
        if body:
            local = self.to_local(body, g, t)
            lat, lon, alt = lat_lon_alt(local, body.radius)
            out.update(local=local, lat=lat, lon=lon, alt=alt,
                       calibrated=self.is_calibrated(body))
            rows = []
            for loc in self.locations_on(body.name):
                llat, llon, lalt = lat_lon_alt(loc.local, body.radius)
                rows.append({
                    "loc": loc,
                    "straight": vlen(vsub(local, loc.local)),
                    "surface": surface_distance(lat, lon, llat, llon, body.radius),
                    "bearing": bearing(lat, lon, llat, llon),
                    "alt": lalt,
                })
            rows.sort(key=lambda r: r["straight"])
            out["nearby"] = rows[:max_nearby]
        out["space"] = self.nearest_space_objects(g, t, system)
        out["zone"] = self.zone_at(g, system)
        return out

    @staticmethod
    def is_stale(prev, cur):
        """The game sometimes repeats an old position (seen inside stations). On a
        spinning planet or moon, identical coordinates a while apart cannot be real."""
        if not prev or not cur or not cur.get("body") or not cur["body"].rotates:
            return False
        if cur["body"].rate_hours == 0 or prev["global"] != cur["global"]:
            return False
        return (cur["time"] - prev["time"]).total_seconds() >= 20

    def motion(self, prev, cur, target=None):
        """Speed, course and ETA from two locate() results.
        Returns None when the fixes are too close together or too far apart."""
        if not prev or not cur or prev["system"] != cur["system"]:
            return None
        dt_s = (cur["time"] - prev["time"]).total_seconds()
        if dt_s < 1 or dt_s > 900:
            return None
        same_body = cur.get("body") is not None and prev.get("body") is cur.get("body")
        if same_body:
            moved = vlen(vsub(cur["local"], prev["local"]))  # relative to the ground
        else:
            moved = vlen(vsub(cur["global"], prev["global"]))
        out = {"dt": dt_s, "speed_ms": moved * 1000.0 / dt_s, "same_body": same_body,
               "course": None, "climb_ms": None, "closing_ms": None, "eta_s": None, "turn": None}
        if same_body:
            out["climb_ms"] = (cur["alt"] - prev["alt"]) * 1000.0 / dt_s
            ground = surface_distance(prev["lat"], prev["lon"], cur["lat"], cur["lon"], cur["body"].radius)
            if ground > 0.002:  # need a couple of meters of movement for a course
                out["course"] = bearing(prev["lat"], prev["lon"], cur["lat"], cur["lon"])
        if target is not None:
            a, b = self.target_info(prev, target), self.target_info(cur, target)
            key = "surface" if (a["same_body"] and b["same_body"]) else "straight"
            if not b["same_body"] and cur.get("body") is not None:
                return out  # target is on another body: speed only, use the route instead of an ETA
            closing = (a[key] - b[key]) * 1000.0 / dt_s
            out["closing_ms"] = closing
            if closing > 0.5:
                out["eta_s"] = b[key] * 1000.0 / closing
            if b["same_body"] and out["course"] is not None:
                out["turn"] = (b["bearing"] - out["course"] + 540) % 360 - 180
        return out


    # ---------------- day and night
    def sun_dir_local(self, body, t):
        """Unit vector toward the system's star, in the body's rotating frame."""
        star = self.bodies.get(body.star)
        if not star or star is body:
            return None
        v = self.to_local(body, star.pos, t)
        n = vlen(v)
        return (v[0] / n, v[1] / n, v[2] / n) if n else None

    def sun_elevation(self, body, local, t):
        s = self.sun_dir_local(body, t)
        r = vlen(local)
        if s is None or r == 0:
            return None
        return math.degrees(math.asin(max(-1.0, min(1.0, (local[0] * s[0] + local[1] * s[1] + local[2] * s[2]) / r))))

    def day_info(self, body, local, t):
        """Sun elevation now, next sunrise/sunset and local solar time.
        Times are datetimes; None when the sun does not rise/set in the next day."""
        e0 = self.sun_elevation(body, local, t)
        out = {"elev": e0, "is_day": e0 is not None and e0 > 0, "rise": None, "set": None,
               "solar_time": None, "cycle": False, "day_hours": None}
        if e0 is None or not body.rotates or body.rate_hours == 0:
            return out
        out["cycle"] = True
        period = body.rate_hours * 3600.0
        out["day_hours"] = body.rate_hours
        N = 360
        step = period / N
        f = lambda sec: self.sun_elevation(body, local, t + dt.timedelta(seconds=sec))

        def refine(a, b):
            fa = f(a)
            for _ in range(30):
                m = (a + b) / 2
                fm = f(m)
                if (fa > 0) == (fm > 0):
                    a, fa = m, fm
                else:
                    b = m
            return (a + b) / 2

        prev, best, best_i = e0, e0, 0
        for i in range(1, N + 1):
            e = f(i * step)
            if out["rise"] is None and prev <= 0 < e:
                out["rise"] = t + dt.timedelta(seconds=refine((i - 1) * step, i * step))
            if out["set"] is None and prev > 0 >= e:
                out["set"] = t + dt.timedelta(seconds=refine((i - 1) * step, i * step))
            if e > best:
                best, best_i = e, i
            prev = e
        noon_in = best_i * step  # seconds until the sun is highest
        out["solar_time"] = (12.0 - noon_in / period * 24.0) % 24.0
        return out

    # ---------------- quantum routes
    def orbital_markers(self, body):
        R = self.om_radius.get(body.name)
        if not R:
            return {}
        return {"OM-1": (0, 0, R), "OM-2": (0, 0, -R), "OM-3": (0, R, 0),
                "OM-4": (0, -R, 0), "OM-5": (R, 0, 0), "OM-6": (-R, 0, 0)}

    def route(self, here, loc):
        """How to get to `loc`. Returns a dict with a 'steps' list of strings."""
        body = self.bodies[loc.body]
        steps = []
        same_body = here is not None and here.get("body") is body
        if not body.rotates:
            steps.append(f"Quantum straight to {loc.name}." if loc.quantum else
                         f"Fly to {loc.name}. Nearest named marker: {body.name}.")
            return {"steps": steps, "om": None}
        llat, llon, lalt = lat_lon_alt(loc.local, body.radius)
        if loc.quantum and loc.source == "db":
            if not same_body:
                steps.append(f"Quantum straight to {loc.name} (it has a QT marker).")
                return {"steps": steps, "om": None}
        oms = self.orbital_markers(body)
        best = None
        for name, p in oms.items():
            olat, olon, _ = lat_lon_alt(p, body.radius)
            ground = surface_distance(olat, olon, llat, llon, body.radius)
            if best is None or ground < best["ground"]:
                best = {"name": name, "ground": ground, "lat": olat, "lon": olon,
                        "bearing": bearing(olat, olon, llat, llon), "alt": vlen(p) - body.radius}
        if same_body:
            direct = surface_distance(here["lat"], here["lon"], llat, llon, body.radius)
            if loc.quantum and loc.source == "db" and direct > 60:
                steps.append(f"Quantum straight to {loc.name} (QT marker), or fly {fmt_km(direct)} "
                             f"on bearing {bearing(here['lat'], here['lon'], llat, llon):03.0f}°.")
            elif best and direct > best["ground"] * 1.5 + 50:
                steps.append(f"Faster: quantum to {body.name} {best['name']}, "
                             f"then {fmt_km(best['ground'])} on bearing {best['bearing']:03.0f}°.")
            else:
                steps.append(f"Fly direct: {fmt_km(direct)} on bearing "
                             f"{bearing(here['lat'], here['lon'], llat, llon):03.0f}°.")
            return {"steps": steps, "om": best}
        if best:
            steps.append(f"Quantum to {body.name} {best['name']} "
                         f"({fmt_km(best['alt'])} above the surface).")
            steps.append(f"Then head {best['bearing']:03.0f}° {compass_word(best['bearing'])} "
                         f"for {fmt_km(best['ground'])} over the ground and descend.")
        else:
            steps.append(f"Quantum to {body.name}, then fly to lat {llat:+.2f}, lon {llon:+.2f}.")
        return {"steps": steps, "om": best}

    def nearest_space_objects(self, g, t, system, n=10):
        rows = []
        for b in self.bodies.values():
            if b.star != system or b.type == "Star":
                continue
            d = vlen(vsub(g, b.pos))
            if b.rotates:
                d = max(0.0, d - b.radius)
            rows.append((d, b.name, b.type))
        for loc in self.locations:
            if loc.star != system:
                continue
            if loc.type not in ("Space station", "Space Station", "Asteroid cluster",
                                "Asteroid base", "CommArray", "Orbital laser platform"):
                continue
            rows.append((vlen(vsub(g, self.location_global(loc, t))), loc.name, loc.type))
        rows.sort()
        return rows[:n]

    def target_info(self, here, loc):
        """Distance and bearing from a locate() result to a location."""
        body = self.bodies[loc.body]
        if here.get("body") is body:
            llat, llon, lalt = lat_lon_alt(loc.local, body.radius)
            return {"same_body": True,
                    "straight": vlen(vsub(here["local"], loc.local)),
                    "surface": surface_distance(here["lat"], here["lon"], llat, llon, body.radius),
                    "bearing": bearing(here["lat"], here["lon"], llat, llon),
                    "lat": llat, "lon": llon, "alt": lalt}
        tg = self.location_global(loc, here["time"])
        return {"same_body": False, "straight": vlen(vsub(here["global"], tg)),
                "body_name": body.name}


def append_history(user_dir, here):
    path = os.path.join(user_dir, "history.csv")
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["utc", "system", "body", "global_x_km", "global_y_km", "global_z_km",
                        "local_x_km", "local_y_km", "local_z_km", "lat", "lon", "alt_km", "nearest"])
        b = here.get("body")
        loc = here.get("local", ("", "", ""))
        near = here["nearby"][0]["loc"].name if here.get("nearby") else ""
        w.writerow([here["time"].isoformat(timespec="seconds"), here["system"], b.name if b else "",
                    *[round(v, 4) for v in here["global"]],
                    *[round(v, 4) if v != "" else "" for v in loc],
                    round(here.get("lat", 0), 5) if b else "", round(here.get("lon", 0), 5) if b else "",
                    round(here.get("alt", 0), 4) if b else "", near])


def fmt_duration(sec, seconds=True):
    if sec is None:
        return "--"
    if not seconds and sec >= 60:
        sec = int(round(sec / 60.0)) * 60
    sec = int(round(sec))
    if sec >= 86400:
        return "over a day"
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}h {m:02d}m"
    if m:
        return f"{m}m {s:02d}s" if seconds else f"{m}m"
    return f"{s}s"


def fmt_clock(hours):
    if hours is None:
        return "--:--"
    h = int(hours) % 24
    m = int(round((hours - int(hours)) * 60))
    if m == 60:
        h, m = (h + 1) % 24, 0
    return f"{h:02d}:{m:02d}"


def fmt_speed(ms):
    if ms is None:
        return "--"
    return f"{ms / 1000:,.1f} km/s" if abs(ms) >= 10_000 else f"{ms:,.0f} m/s"


def turn_text(deg):
    if deg is None:
        return ""
    if abs(deg) < 5:
        return "on course"
    return f"turn {'right' if deg > 0 else 'left'} {abs(deg):.0f}°"


# ---------------------------------------------------------------- share files and codes
SHARE_FORMAT = "sc-locator-share"
SHARE_COLS = ["kind", "name", "type", "body", "system", "x", "y", "z", "lat", "lon", "alt_km",
              "material", "method", "quality", "amount", "note", "time"]
CODE_PREFIX = "SCLOC1"
_CSV_ALIASES = {
    "name": ("name", "poiname", "poi", "location", "title"),
    "body": ("body", "planet", "moon", "parent", "parentbody", "container"),
    "type": ("type", "poi_subtype", "category"),
    "x": ("x", "x_km", "xcoord", "localx"), "y": ("y", "y_km", "ycoord", "localy"),
    "z": ("z", "z_km", "zcoord", "localz"),
    "lat": ("lat", "latitude"), "lon": ("lon", "long", "longitude"),
    "alt_km": ("alt_km", "altitude_km", "alt"), "height_m": ("height", "height_m"),
    "note": ("note", "notes", "comment", "description"),
    "kind": ("kind",), "material": ("material", "ore"), "method": ("method",), "quality": ("quality",),
    "amount": ("amount",), "time": ("time", "date", "created"), "system": ("system",),
}


def write_share(path, items, author=""):
    if path.lower().endswith(".csv"):
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=SHARE_COLS, extrasaction="ignore")
            w.writeheader()
            for it in items:
                w.writerow({c: ("" if it.get(c) is None else it.get(c, "")) for c in SHARE_COLS})
    else:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"format": SHARE_FORMAT, "version": 1, "author": author,
                       "exported": utcnow().isoformat(timespec="seconds"), "items": items}, f, indent=1)


def _normalize_row(row):
    low = {str(k).strip().lower(): v for k, v in row.items() if k is not None}
    out = {}
    for key, names in _CSV_ALIASES.items():
        for n in names:
            if low.get(n) not in (None, ""):
                out[key] = low[n]
                break
    if "alt_km" not in out and "height_m" in out:
        try:
            out["alt_km"] = float(out["height_m"]) / 1000.0
        except ValueError:
            pass
    return out


def read_share(path):
    """Read a share file: Starboard JSON, a JSON list, or a CSV with
    name + body and either x/y/z (km, local) or lat/lon (this app's convention)."""
    with open(path, encoding="utf-8-sig") as f:
        text = f.read()
    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        data = json.loads(text)
        items = data.get("items", []) if isinstance(data, dict) else data
        return [_normalize_row(i) | {k: v for k, v in i.items() if k in SHARE_COLS} for i in items
                if isinstance(i, dict)], (data.get("author", "") if isinstance(data, dict) else "")
    codes = decode_codes(text)
    if codes:
        return codes, ""
    return [_normalize_row(r) for r in csv.DictReader(io.StringIO(text))], ""


def encode_code(loc):
    clean = lambda v: str(v).replace("|", "/").replace("\n", " ").strip()
    kind = "find" if loc.source == "log" else "poi"
    mat = loc.entry["material"] if loc.source == "log" else ""
    q = loc.entry.get("quality") if loc.source == "log" else None
    return "|".join([CODE_PREFIX, kind, clean(loc.body), f"{loc.local[0]:.3f}", f"{loc.local[1]:.3f}",
                     f"{loc.local[2]:.3f}", clean(loc.type), clean(loc.name), clean(mat),
                     "" if q in (None, "") else str(q)])


def decode_codes(text):
    items = []
    for m in re.finditer(CODE_PREFIX + r"\|[^\r\n`]*", text or ""):
        parts = m.group(0).split("|")
        if len(parts) < 8:
            continue
        try:
            x, y, z = float(parts[3]), float(parts[4]), float(parts[5])
        except ValueError:
            continue
        it = {"kind": parts[1], "body": parts[2], "x": x, "y": y, "z": z, "type": parts[6], "name": parts[7]}
        if len(parts) > 8 and parts[8]:
            it["material"] = parts[8]
        if len(parts) > 9 and parts[9].strip().isdigit():
            it["quality"] = int(parts[9].strip())
        items.append(it)
    return items
