"""
One-click data update for Starboard.

Sources
  - VerseTime (GitHub, GPL-3.0): Stanton and Pyro bodies and locations. Required.
  - StarMap read-only API (starmap.space): Nyx bodies, QV Breaker Stations,
    Nyx locations (such as Levski), orbital marker heights, and extra points
    of interest (caves and the like) on Stanton and Pyro planets and moons.
    Optional; if it is down, the data you already have is kept. Extra points
    for a body are only added when StarMap's positions line up with
    VerseTime's for the places both know.
  - Star Citizen Location Finder (quattrobaje3na-png.github.io, shown on
    citizen-starter-guide.com): caves and other surface places for Stanton
    and Pyro, checked against VerseTime the same way.

Before anything is written, the current data folder is backed up to
data/backups/<timestamp>/ (the last 3 are kept), so an update can be undone.
Ore lists (ores.json) are not touched.
"""

import csv
import datetime as dt
import io
import json
import math
import os
import re
import shutil
import urllib.parse
import urllib.request

VT_BASE = "https://raw.githubusercontent.com/dydrmr/VerseTime/main/data/"
SM_BASE = "https://starmap.space/api/v4/"
USER_AGENT = "SC-Locator/4 (personal Star Citizen navigation tool)"
KEEP_BACKUPS = 3

BODY_COLS = ["name", "ordinal", "type", "parentBody", "parentStar", "coordinateX", "coordinateY", "coordinateZ",
             "quaternionW", "quaternionX", "quaternionY", "quaternionZ", "bodyRadius", "rotationRate",
             "rotationCorrection", "orbitAngle", "orbitRadius", "ringRadiusInner", "ringRadiusOuter",
             "themeColorR", "themeColorG", "themeColorB"]
LOC_COLS = ["name", "type", "parentBody", "parentStar", "coordinateX", "coordinateY", "coordinateZ",
            "wikiLink", "private", "quantum"]

# StarMap container names that differ from this app's names
SM_NAME_MAP = {"Microtech": "microTech", "Pyro1": "Pyro I", "Pyro4": "Pyro IV", "Pyro5": "Pyro V",
               "Nyx1": "Nyx I", "Nyx2": "Nyx II", "Nyx3": "Nyx III"}
ROMAN = {"1": "I", "2": "II", "3": "III", "4": "IV", "5": "V", "6": "VI"}


class UpdateError(Exception):
    pass


def fetch(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8-sig")


def read_csv_text(text):
    return list(csv.DictReader(io.StringIO(text)))


def read_csv_file(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def write_csv(path, rows, cols):
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})
    os.replace(tmp, path)


def _num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _km(v):
    return f"{_num(v) / 1000.0:.6f}"


# ---------------------------------------------------------------- VerseTime
def get_versetime(log):
    log("Downloading Stanton and Pyro data (VerseTime)...")
    bodies = read_csv_text(fetch(VT_BASE + "bodies.csv"))
    locs = read_csv_text(fetch(VT_BASE + "locations.csv"))
    for need, rows, minimum in ((BODY_COLS[:15], bodies, 50), (LOC_COLS[:7], locs, 300)):
        if not rows or any(c not in rows[0] for c in need):
            raise UpdateError("VerseTime data format changed; update cancelled, nothing was changed.")
        if len(rows) < minimum:
            raise UpdateError(f"VerseTime data looks incomplete ({len(rows)} rows); update cancelled.")
    for b in bodies:
        if b.get("type") in ("Planet", "Moon") and _num(b.get("bodyRadius")) <= 0:
            raise UpdateError(f"VerseTime body {b.get('name')} has no radius; update cancelled.")
    return bodies, locs


# ---------------------------------------------------------------- StarMap
def _nyx_name(raw, typ):
    if raw in SM_NAME_MAP:
        return SM_NAME_MAP[raw]
    m = re.fullmatch(r"Nyx\s*(\d)", raw)
    if m:
        return "Nyx " + ROMAN.get(m.group(1), m.group(1))
    if typ == "Jumppoint":
        parts = [p for p in re.split(r"[\s_\-]+", raw) if p and p.lower() not in ("nyx", "jump", "point", "jumppoint")]
        return f"Nyx-{parts[0]} JP" if parts else raw
    return raw


def parse_starmap_containers(items):
    """Turn StarMap /oc rows into (nyx_bodies, nyx_locations, om_radius_km)."""
    if not isinstance(items, list):
        raise UpdateError("StarMap returned an unexpected answer.")
    bodies, locs, om = [], [], {}
    for it in items:
        system, raw, typ = it.get("System"), str(it.get("ObjectContainer") or ""), it.get("Type")
        name = SM_NAME_MAP.get(raw, raw)
        omr = _num(it.get("OrbitalMarkerRadius"))
        if omr > 0 and typ == "Planet":
            om[_nyx_name(raw, typ) if system == "Nyx" else name] = omr / 1000.0
        if system != "Nyx":
            continue
        x, y, z = _km(it.get("XCoord")), _km(it.get("YCoord")), _km(it.get("ZCoord"))
        q = [it.get("RotQuatW") or 1, it.get("RotQuatX") or 0, it.get("RotQuatY") or 0, it.get("RotQuatZ") or 0]
        rate = _num(it.get("RotationSpeedX"))
        corr = (_num(it.get("RotationAdjustmentX")) - 90.0) % 360 if rate else 0.0  # StarMap is +90 vs VerseTime
        if typ == "Star":
            bodies.append({"name": "Nyx", "ordinal": "0", "type": "Star", "parentBody": "", "parentStar": "", "coordinateX": x, "coordinateY": y,
                           "coordinateZ": z, "quaternionW": 1, "quaternionX": 0, "quaternionY": 0, "quaternionZ": 0,
                           "bodyRadius": 0, "rotationRate": 0, "rotationCorrection": 0})
        elif typ == "Planet":
            nm = _nyx_name(raw, typ)
            radius = _num(it.get("BodyRadius")) / 1000.0
            m = re.search(r"([IV]+)$", nm)
            bodies.append({"name": nm, "_sm_name": raw, "ordinal": m.group(1) if m else "", "parentBody": "Nyx", "parentStar": "Nyx",
                           "type": "Planet" if nm.startswith("Nyx ") else "Planetoid",
                           "coordinateX": x, "coordinateY": y, "coordinateZ": z,
                           "quaternionW": q[0], "quaternionX": q[1], "quaternionY": q[2], "quaternionZ": q[3],
                           "bodyRadius": f"{radius:.3f}", "rotationRate": rate, "rotationCorrection": f"{corr:.3f}"})
        elif typ == "Jumppoint":
            bodies.append({"name": _nyx_name(raw, typ), "type": "Jump Point", "parentBody": "Nyx", "parentStar": "Nyx",
                           "coordinateX": x, "coordinateY": y, "coordinateZ": z, "quaternionW": 1, "quaternionX": 0,
                           "quaternionY": 0, "quaternionZ": 0, "bodyRadius": 0})
        elif "QV Breaker Station" in raw:
            locs.append({"name": raw, "type": "Asteroid base", "parentBody": "Nyx", "parentStar": "Nyx",
                         "coordinateX": x, "coordinateY": y, "coordinateZ": z,
                         "wikiLink": "https://starcitizen.tools/Nyx_system", "private": "0", "quantum": "1"})
    return bodies, locs, om


def _rows(data):
    """StarMap answers are a list, or a dict wrapping one."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("data", "pois", "items", "result"):
            if isinstance(data.get(k), list):
                return data[k]
    return []


def poi_container(it):
    for k in ("Planet", "ObjectContainer", "Container", "PlanetName", "Body"):
        if it.get(k):
            return str(it[k])
    return ""


def parse_starmap_pois(items, body_name, star):
    """StarMap /pois rows for one body -> location rows (StarMap gives local km)."""
    out = []
    items = _rows(items)
    for it in items:
        name = it.get("PoiName") or it.get("Name")
        if not name or it.get("XCoord") in (None, ""):
            continue
        out.append({"name": name, "type": it.get("Type") or "Location", "parentBody": body_name, "parentStar": star,
                    "coordinateX": f"{_num(it.get('XCoord')):.4f}", "coordinateY": f"{_num(it.get('YCoord')):.4f}",
                    "coordinateZ": f"{_num(it.get('ZCoord')):.4f}", "wikiLink": "", "private": "0",
                    "quantum": "1" if str(it.get("QTMarker")) == "1" else "0"})
    return out


def _body_key(name):
    s = re.sub(r"[^a-z0-9]", "", str(name).lower())
    for d, r in sorted(ROMAN.items(), key=lambda x: -len(x[1])):
        s = re.sub(r.lower() + "$", d, s) if s.endswith(r.lower()) and len(s) > len(r) + 2 else s
    return s


def _poi_type(raw_type, name):
    t = str(raw_type or "").strip()
    if "cave" in t.lower() or re.search(r"\bcaves?\b", str(name).lower()):
        return "Cave"
    return t[:1].upper() + t[1:] if t else "Location"


def starmap_bodies_elsewhere(items):
    """StarMap container names of Stanton and Pyro planets and moons."""
    out = []
    for it in items if isinstance(items, list) else []:
        if it.get("System") in ("Stanton", "Pyro") and it.get("Type") in ("Planet", "Moon", "Planetoid") \
                and _num(it.get("BodyRadius")) > 0:
            out.append((it.get("System"), str(it.get("ObjectContainer") or "")))
    return out


LF_BASE = "https://quattrobaje3na-png.github.io/Star-Citizen-Location-Finder/"
LF_SKIP = {"City", "Space Station"}  # already covered, and not body-surface places
LF_TYPE = {"Measured in game": "Landmark", "Race Track": "Racetrack"}


def get_locfinder(log):
    """Location Finder places per body: {(system, body): [location rows in km]}."""
    log("Downloading caves and surface places (Star Citizen Location Finder)...")
    man = json.loads(fetch(LF_BASE + "manifest.json"))
    out = {}
    for system, bodies in (man.get("systems") or {}).items():
        if system not in ("Stanton", "Pyro"):
            continue
        for b in bodies:
            key = b.get("key")
            if not key:
                continue
            try:
                data = json.loads(fetch(LF_BASE + urllib.parse.quote(key) + "/data.json", timeout=60))
            except Exception:
                continue
            rows = []
            for l in data.get("locations") or []:
                pos = l.get("body_fixed_m")
                if l.get("frame") != "body_fixed" or not pos or len(pos) != 3 or l.get("category") in LF_SKIP:
                    continue
                cat = l.get("category") or "Location"
                rows.append({"name": l.get("name") or "?", "type": LF_TYPE.get(cat, cat),
                             "coordinateX": f"{_num(pos[0]) / 1000:.4f}", "coordinateY": f"{_num(pos[1]) / 1000:.4f}",
                             "coordinateZ": f"{_num(pos[2]) / 1000:.4f}", "wikiLink": "", "private": "0",
                             "quantum": "0"})
            if rows:
                out[(system, b.get("name") or key)] = rows
    _debug_save("locfinder_summary.txt", "\n".join(f"{k}: {len(v)}" for k, v in out.items()))
    return out


DEBUG_DIR = None  # set by the app: raw StarMap answers are saved here for checking


def _debug_save(name, text):
    if not DEBUG_DIR:
        return
    try:
        os.makedirs(DEBUG_DIR, exist_ok=True)
        with open(os.path.join(DEBUG_DIR, name), "w", encoding="utf-8") as f:
            f.write(text if isinstance(text, str) else json.dumps(text, indent=1))
    except OSError:
        pass


PROBE_URLS = {
    "wiki_locations_filters": "https://api.star-citizen.wiki/api/locations/filters",
    "wiki_locations_page1": "https://api.star-citizen.wiki/api/locations?page%5Bsize%5D=50",
    "wiki_locations_caves": "https://api.star-citizen.wiki/api/locations?filter%5Btype%5D=Cave&page%5Bsize%5D=50",
    "wiki_locations_caves2": "https://api.star-citizen.wiki/api/locations?filter%5Bclassification%5D=Cave&page%5Bsize%5D=50",
    "uex_poi": "https://api.uexcorp.uk/2.0/poi",
    "uex_outposts": "https://api.uexcorp.uk/2.0/outposts",
}


def probe_sources(log):
    """Save samples from other location sources, to check whether they list caves with positions."""
    if not DEBUG_DIR:
        return
    log("Testing other location sources (Star Citizen Wiki, UEX)...")
    lines = []
    for name, url in PROBE_URLS.items():
        try:
            text = fetch(url, timeout=30)
            _debug_save(f"probe_{name}.json", text[:3_000_000])
            lines.append(f"{name}: OK {len(text)} bytes")
        except Exception as e:
            body = ""
            if hasattr(e, "read"):
                try:
                    body = e.read().decode("utf-8", "replace")[:500]
                except Exception:
                    pass
            lines.append(f"{name}: failed {e.__class__.__name__}: {e} {body}")
    _debug_save("probe_summary.txt", "\n".join(lines))


def get_starmap(log):
    log("Downloading Nyx data and orbital markers (StarMap)...")
    raw_oc = fetch(SM_BASE + "oc/index.php")
    _debug_save("oc.json", raw_oc)
    items = json.loads(raw_oc)
    bodies, locs, om = parse_starmap_containers(items)
    extra = {}
    others = starmap_bodies_elsewhere(items)
    summary = [f"oc rows: {len(items) if isinstance(items, list) else type(items).__name__}",
               f"Stanton/Pyro bodies found: {len(others)}: {others}"]
    if others:
        log(f"Downloading points of interest for {len(others)} Stanton and Pyro planets and moons (StarMap)...")
    # one request for every point of interest; per-planet requests only as a fallback
    bulk = None
    for ver in ("v4", "v3"):
        try:
            text = fetch(f"https://starmap.space/api/{ver}/pois/index.php", timeout=60)
            _debug_save(f"pois_all_{ver}.json", text)
            bulk = _rows(json.loads(text))
            summary.append(f"pois {ver}: {len(bulk)} rows; fields: {sorted(bulk[0].keys()) if bulk else []}")
            if bulk:
                break
        except Exception as e:
            summary.append(f"pois {ver}: failed {e.__class__.__name__}: {e}")
    if bulk:
        wanted = {raw: system for system, raw in others}
        by_key = {re.sub(r"[^a-z0-9]", "", r.lower()): r for r in wanted}
        groups = {}
        for it in bulk:
            c = by_key.get(re.sub(r"[^a-z0-9]", "", poi_container(it).lower()))
            if c:
                groups.setdefault(c, []).append(it)
        for raw, rows in groups.items():
            got = parse_starmap_pois(rows, raw, wanted[raw])
            summary.append(f"{raw}: {len(got)} points")
            if got:
                extra[(wanted[raw], raw)] = got
        others = []  # done
    for system, raw in others:
        try:
            q = urllib.parse.urlencode({"planet": raw})
            text = fetch(SM_BASE + "pois/index.php?" + q)
            _debug_save(f"pois_{re.sub(r'[^A-Za-z0-9]', '_', raw)}.json", text)
            got = parse_starmap_pois(json.loads(text), raw, system)
            summary.append(f"{raw}: {len(got)} points")
            if got:
                extra[(system, raw)] = got
        except Exception as e:
            summary.append(f"{raw}: failed {e.__class__.__name__}: {e}")
    _debug_save("summary.txt", "\n".join(summary))
    if not any(b["type"] == "Star" for b in bodies):
        raise UpdateError("StarMap answer had no Nyx star.")
    for b in [b for b in bodies if b["type"] in ("Planet", "Planetoid")]:
        try:
            q = urllib.parse.urlencode({"planet": b.get("_sm_name", b["name"])})
            raw = json.loads(fetch(SM_BASE + "pois/index.php?" + q))
            got = parse_starmap_pois(raw, b["name"], "Nyx")
            if got:
                log(f"  {len(got)} locations on {b['name']}")
            locs += got
        except Exception:
            pass  # locations are a bonus; containers are what matter
    return bodies, locs, om, extra, starmap_pyro(items)


def merge_extra_pois(extra, vt_bodies, vt_locs, log=print, max_offset_km=2.0):
    """Add StarMap points (caves and more) that VerseTime does not have.
    Per body, StarMap and VerseTime must agree on the places both list, or
    that body's extra points are skipped. Returns (rows, notes)."""
    names = {_body_key(b["name"]): b["name"] for b in vt_bodies if b.get("type") in ("Planet", "Moon", "Planetoid")}
    by_body = {}
    for r in vt_locs:
        by_body.setdefault(r.get("parentBody"), []).append(r)
    known_types = {r.get("type", "").lower(): r.get("type") for r in vt_locs if r.get("type")}
    radius = {b["name"]: _num(b.get("bodyRadius")) for b in vt_bodies}
    add, notes = [], []
    verified, rejected, unchecked = 0, 0, []
    pending = sorted(extra.items())
    for (system, raw), rows in pending:
        body = names.get(_body_key(SM_NAME_MAP.get(raw, raw)))
        if not body:
            continue
        known = by_body.get(body, [])
        kn = {re.sub(r"[^a-z0-9]", "", r["name"].lower()): r for r in known}
        offsets = []
        for r in rows:
            k = kn.get(re.sub(r"[^a-z0-9]", "", r["name"].lower()))
            if k:
                offsets.append(sum((_num(k[c]) - _num(r[c])) ** 2 for c in ("coordinateX", "coordinateY", "coordinateZ"))
                               ** 0.5)
        if not offsets:
            unchecked.append((system, body, rows, known, kn))
            continue
        offsets.sort()
        med = offsets[len(offsets) // 2]
        if med > max_offset_km and any(k for k in kn.values()):
            # maybe StarMap sent meters: try again in km
            scaled = [dict(r, **{c: f"{_num(r[c]) / 1000.0:.4f}" for c in ("coordinateX", "coordinateY", "coordinateZ")})
                      for r in rows]
            offs2 = sorted(sum((_num(kn[key][c]) - _num(r[c])) ** 2 for c in ("coordinateX", "coordinateY", "coordinateZ"))
                           ** 0.5 for r in scaled
                           for key in [re.sub(r"[^a-z0-9]", "", r["name"].lower())] if key in kn)
            if offs2 and offs2[len(offs2) // 2] <= max_offset_km:
                rows, med = scaled, offs2[len(offs2) // 2]
        if med > max_offset_km:
            rejected += 1
            notes.append(f"{body}: StarMap points skipped (positions differ by {med:.1f} km).")
            continue
        verified += 1
        _add_rows(system, body, rows, known, kn, known_types, add, log)
    # bodies with nothing to compare: trust the source only if it matched everywhere it could be
    # checked, and only points that sit on the body's surface
    for system, body, rows, known, kn in unchecked:
        r_km = radius.get(body, 0)
        if verified >= 3 and not rejected and r_km > 0:
            ok = [r for r in rows if abs(sum(_num(r[c]) ** 2 for c in ("coordinateX", "coordinateY", "coordinateZ"))
                                       ** 0.5 - r_km) < 30]
            if ok:
                _add_rows(system, body, ok, known, kn, known_types, add, log)
                continue
        notes.append(f"{body}: StarMap points skipped (no shared places to check them against).")
    return add, notes


def _add_rows(system, body, rows, known, kn, known_types, add, log):
    n = 0
    for r in rows:
        key = re.sub(r"[^a-z0-9]", "", r["name"].lower())
        if key in kn:
            continue
        p = [_num(r[c]) for c in ("coordinateX", "coordinateY", "coordinateZ")]
        if any(sum((_num(k[c]) - v) ** 2 for c, v in zip(("coordinateX", "coordinateY", "coordinateZ"), p)) ** 0.5
               < 0.5 for k in known):
            continue  # same spot under another name
        typ = _poi_type(r.get("type"), r["name"])
        typ = known_types.get(typ.lower().replace("centre", "center"), typ)
        row = dict(r, parentBody=body, parentStar=system, type=typ)
        add.append(row)
        known.append(row)
        kn[key] = row
        n += 1
    if n:
        log(f"  {n} extra points on {body}")


# ---------------------------------------------------------------- diff, backup, write
def _key(r):
    return r.get("name") or "", r.get("parentBody") or ""


def diff(old, new, moved_km=0.05):
    o = {_key(r): r for r in old}
    n = {_key(r): r for r in new}
    added = sorted(k[0] for k in n.keys() - o.keys())
    removed = sorted(k[0] for k in o.keys() - n.keys())
    moved = []
    for k in n.keys() & o.keys():
        a, b = o[k], n[k]
        d = sum((_num(a.get(c)) - _num(b.get(c))) ** 2 for c in ("coordinateX", "coordinateY", "coordinateZ")) ** 0.5
        if d > moved_km:
            moved.append(k[0])
    return added, removed, sorted(moved)


def rotation_changes(old_bodies, new_bodies):
    o = {r["name"]: r for r in old_bodies}
    out = []
    for r in new_bodies:
        a = o.get(r["name"])
        if a and (abs(_num(a.get("rotationCorrection")) - _num(r.get("rotationCorrection"))) > 0.01
                  or abs(_num(a.get("rotationRate")) - _num(r.get("rotationRate"))) > 1e-6):
            out.append(r["name"])
    return out


def backup(data_dir):
    root = os.path.join(data_dir, "backups")
    os.makedirs(root, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(root, stamp)
    os.makedirs(dest)
    for fn in os.listdir(data_dir):
        p = os.path.join(data_dir, fn)
        if os.path.isfile(p):
            shutil.copy2(p, dest)
    for old in sorted(os.listdir(root))[:-KEEP_BACKUPS]:
        shutil.rmtree(os.path.join(root, old), ignore_errors=True)
    return dest


def list_backups(data_dir):
    root = os.path.join(data_dir, "backups")
    return sorted(os.listdir(root)) if os.path.isdir(root) else []


def restore_latest(data_dir):
    names = list_backups(data_dir)
    if not names:
        raise UpdateError("No backup to restore.")
    src = os.path.join(data_dir, "backups", names[-1])
    for fn in os.listdir(src):
        shutil.copy2(os.path.join(src, fn), os.path.join(data_dir, fn))
    shutil.rmtree(src, ignore_errors=True)
    return names[-1]


def read_info(data_dir):
    try:
        with open(os.path.join(data_dir, "update_info.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


# ---------------------------------------------------------------- Pyro layout
# VerseTime still has Pyro laid out as it was before Alpha 4.1: the game turned the
# whole system by about 274.77 degrees around the star. StarMap has the current layout.
PYRO_V_NOW = (-3912426.7345, -42758732.5976)   # Pyro V in km, from StarMap (Alpha 4.1)
PYRO_NAMES = {"Pyro1": "Pyro I", "Pyro4": "Pyro IV", "Pyro5": "Pyro V", "Pyro6": "Terminus", "pyro3": "Bloom",
              "Pyro2": "Monox", "Pyro-Stanton Jump Point": "Pyro-Stanton JP"}


def starmap_pyro(items):
    """Current Pyro planet, moon and asteroid cluster positions from StarMap /oc, in km."""
    out = {"bodies": {}, "clusters": {}}
    for it in items if isinstance(items, list) else []:
        if it.get("System") != "Pyro":
            continue
        raw, typ = str(it.get("ObjectContainer") or ""), it.get("Type")
        pos = (_num(it.get("XCoord")) / 1000.0, _num(it.get("YCoord")) / 1000.0, _num(it.get("ZCoord")) / 1000.0)
        if typ == "Planet" and _num(it.get("BodyRadius")) > 0:
            out["bodies"][PYRO_NAMES.get(raw, raw)] = pos
        elif raw.startswith("Cluster "):
            out["clusters"][raw] = pos
    return out


def _rot(x, y, deg):
    a = math.radians(deg)
    return x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a)


def align_pyro(bodies, locs, current=None, log=print):
    """Turn VerseTime's Pyro rows into the current layout, in place.
    Returns the angle used (0 when VerseTime already matches the game)."""
    by = {b["name"]: b for b in bodies}
    pv = by.get("Pyro V")
    if not pv:
        return 0.0
    now = (current or {}).get("bodies", {}).get("Pyro V") or PYRO_V_NOW
    old_a = math.degrees(math.atan2(_num(pv["coordinateY"]), _num(pv["coordinateX"])))
    new_a = math.degrees(math.atan2(now[1], now[0]))
    theta = (new_a - old_a) % 360
    if min(theta, 360 - theta) < 0.5:
        return 0.0
    rotating = {"Planet", "Moon", "Planetoid"}
    kinds = {}
    for b in bodies:
        if b.get("parentStar") != "Pyro":
            continue
        kinds[b["name"]] = b.get("type")
        x, y = _rot(_num(b["coordinateX"]), _num(b["coordinateY"]), theta)
        b["coordinateX"], b["coordinateY"] = f"{x:.3f}", f"{y:.3f}"
        if b.get("type") in rotating:
            b["rotationCorrection"] = f"{(_num(b.get('rotationCorrection')) + theta) % 360:.3f}"
        cur = (current or {}).get("bodies", {}).get(b["name"])
        if cur:  # StarMap knows where it is now
            b["coordinateX"], b["coordinateY"], b["coordinateZ"] = (f"{v:.3f}" for v in cur)
    kinds["Pyro"] = "Star"
    clusters = (current or {}).get("clusters", {})
    for r in locs:
        if r.get("parentStar") != "Pyro" or kinds.get(r.get("parentBody")) in rotating:
            continue  # places on a planet or moon turn with it
        if r.get("coordinateX") in (None, ""):
            continue
        if r["name"] in clusters and r.get("parentBody") == "Pyro":
            r["coordinateX"], r["coordinateY"], r["coordinateZ"] = (f"{v:.3f}" for v in clusters[r["name"]])
            continue
        x, y = _rot(_num(r["coordinateX"]), _num(r["coordinateY"]), theta)
        r["coordinateX"], r["coordinateY"] = f"{x:.3f}", f"{y:.3f}"
    log(f"Pyro: turned VerseTime's layout by {theta:.2f} degrees to match the game.")
    return theta


def run_update(data_dir, log=print, use_starmap=True, _vt=None, _sm=None, _lf=None):
    """Download, check, back up and write. Returns a report dict.
    _vt / _sm let tests inject data instead of downloading."""
    old_bodies = read_csv_file(os.path.join(data_dir, "bodies.csv"))
    old_locs = read_csv_file(os.path.join(data_dir, "locations.csv"))
    vt_bodies, vt_locs = _vt if _vt else get_versetime(log)

    vt_names = {r["name"] for r in vt_bodies}

    notes = []
    sm = None
    if use_starmap:
        try:
            sm = _sm if _sm else get_starmap(log)
        except Exception as e:  # keep going with the Nyx data we already have
            notes.append(f"StarMap could not be reached ({e.__class__.__name__}); kept your current Nyx data.")
    extra_locs = []
    lf = None
    if use_starmap:
        try:
            lf = _lf if _lf is not None else get_locfinder(log)
        except Exception as e:
            notes.append(f"Location Finder could not be reached ({e.__class__.__name__}).")
    if lf:
        got, lf_notes = merge_extra_pois(lf, vt_bodies, vt_locs, log)
        extra_locs += got
        notes += [n.replace("StarMap", "Location Finder") for n in lf_notes]
    align_pyro(vt_bodies, vt_locs, sm[4] if sm and len(sm) > 4 else None, log)
    if sm:
        nyx_bodies, nyx_locs, om = sm[:3]
        if len(sm) > 3 and sm[3]:
            got, extra_notes = merge_extra_pois(sm[3], vt_bodies, vt_locs + extra_locs, log)
            extra_locs += got
            notes += extra_notes
    else:
        nyx_bodies = [r for r in old_bodies if r.get("parentStar") == "Nyx" or r.get("name") == "Nyx"]
        nyx_locs = [r for r in old_locs if r.get("parentStar") == "Nyx"]
        om = None
    if not extra_locs:  # sources down: keep extra points from an earlier update
        vt_keys = {_key(r) for r in vt_locs}
        extra_locs = [r for r in old_locs if r.get("parentStar") in ("Stanton", "Pyro") and _key(r) not in vt_keys]
    # if VerseTime starts covering Nyx, its rows win
    nyx_bodies = [r for r in nyx_bodies if r["name"] not in vt_names]
    vt_loc_keys = {_key(r) for r in vt_locs}
    nyx_locs = [r for r in nyx_locs if _key(r) not in vt_loc_keys]

    new_bodies = vt_bodies + nyx_bodies
    new_locs = vt_locs + nyx_locs + extra_locs
    b_add, b_rem, b_mov = diff(old_bodies, new_bodies, moved_km=1.0)
    l_add, l_rem, l_mov = diff(old_locs, new_locs)
    rot = rotation_changes(old_bodies, new_bodies)

    changed = any((b_add, b_rem, b_mov, l_add, l_rem, l_mov, rot))
    om_path = os.path.join(data_dir, "orbital_markers.json")
    om_changed = False
    if om:
        try:
            with open(om_path, encoding="utf-8") as f:
                om_old = json.load(f)
        except Exception:
            om_old = {"radius_km": {}}
        merged = dict(om_old.get("radius_km", {}))
        known = {r["name"] for r in new_bodies}
        for k, v in om.items():
            if k in known and abs(merged.get(k, 0) - v) > 0.01:
                merged[k] = v
                om_changed = True
        om_old["radius_km"] = merged

    report = {"bodies": len(new_bodies), "locations": len(new_locs),
              "bodies_added": b_add, "bodies_removed": b_rem, "bodies_moved": b_mov,
              "locations_added": l_add, "locations_removed": l_rem, "locations_moved": l_mov,
              "rotation_changed": rot, "om_changed": om_changed, "notes": notes,
              "changed": changed or om_changed, "backup": None}
    if not report["changed"]:
        log("Already up to date.")
    else:
        report["backup"] = backup(data_dir)
        write_csv(os.path.join(data_dir, "bodies.csv"), new_bodies, BODY_COLS)
        write_csv(os.path.join(data_dir, "locations.csv"), new_locs, LOC_COLS)
        if om_changed:
            with open(om_path, "w", encoding="utf-8") as f:
                json.dump(om_old, f, indent=1)
        log("Data updated.")
    info = {"checked": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "starmap_ok": sm is not None}
    if report["changed"]:
        info["updated"] = info["checked"]
    else:
        info["updated"] = read_info(data_dir).get("updated")
    with open(os.path.join(data_dir, "update_info.json"), "w", encoding="utf-8") as f:
        json.dump(info, f, indent=1)
    return report
