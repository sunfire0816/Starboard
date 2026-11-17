"""Asteroid belts you cannot quantum to directly, and how to get into them.

Most belts are not on the quantum travel list. The usual way in is to quantum toward a
destination on the far side and drop out of quantum travel when the distance left reads a
certain number. This module finds those routes from where you are (or from the main stops)
and tells you whether a /showlocation fix is inside a belt.

Sources:
- Aaron Halo bands (start, end, thickness): Cornerstone's "Aaron Halo - Detailed Shape and
  Density Survey" (cstone.space). The belt is the same all the way around and band 5 is the
  densest. Checked against the Star Citizen Wiki's routes (Hurston to ArcCorp, drop out at about
  9.5 Gm left; ArcCorp to Hurston at about 13.5 Gm): both put the belt about 20.8 Gm from the
  system centre, inside the surveyed bands.
- Yela's ring: game data through the Star Citizen Wiki API (482 to 782 km from Yela's centre).
- Glaciem Ring and Keeger Belt (Nyx): the distance of Delamar (in the Glaciem Ring) and of the
  QV Breaker stations (in the Keeger Belt) from the centre of Nyx, from Starboard's map data.
- Akiro Cluster (Pyro): a normal quantum destination in game data.
All distances in km. Belts circle the system centre (0, 0, 0) in the plane of the planets.
"""

import math

# (band, start km, end km, height above the plane km, below km)
AARON_BANDS = [
    (1, 19_673_000, 19_715_000, 615, 635),
    (2, 19_815_000, 19_914_000, 2_063, 2_078),
    (3, 19_914_000, 20_071_000, 4_035, 4_058),
    (4, 20_129_000, 20_230_000, 2_897, 2_926),
    (5, 20_230_000, 20_407_000, 4_990, 5_006),
    (6, 20_407_000, 20_540_000, 4_991, 5_008),
    (7, 20_540_000, 20_750_000, 4_989, 5_007),
    (8, 20_793_000, 20_968_000, 3_475, 3_498),
    (9, 21_046_000, 21_132_000, 2_389, 2_411),
    (10, 21_159_000, 21_299_000, 2_006, 2_010),
]

BELTS = [
    {"id": "aaron", "name": "Aaron Halo", "system": "Stanton", "kind": "system",
     "bands": AARON_BANDS, "target": 5,
     "about": "Stanton's asteroid belt, between Crusader and ArcCorp. It is not on the quantum list, so you "
              "quantum toward something on the far side and drop out as you cross it. It has ten bands; band 5 "
              "is the densest, with over 1.5 times the rocks of the others and bigger asteroids.",
     "credit": "Band distances: Cornerstone's Aaron Halo survey (cstone.space)."},
    {"id": "yela", "name": "Yela's ring", "system": "Stanton", "kind": "moon", "body": "Yela",
     "inner": 482, "outer": 782,
     "about": "A thin ring of asteroids around Crusader's moon Yela, 482 to 782 km from Yela's centre. Quantum "
              "to Yela: you arrive close to the inner edge of the ring. Then fly away from Yela and look for the "
              "flat band of rocks around it.",
     "credit": "Ring size: game data through the Star Citizen Wiki."},
    {"id": "glaciem", "name": "Glaciem Ring", "system": "Nyx", "kind": "system", "radius_from": "Delamar",
     "width": 400_000,
     "about": "Nyx's dense inner belt (Nyx belt alpha), home of Levski on Delamar. Easiest way in: quantum to "
              "Delamar, which sits inside the ring. Or drop out on a route that crosses it.",
     "credit": "Distance: Delamar's distance from the centre of Nyx."},
    {"id": "keeger", "name": "Keeger Belt", "system": "Nyx", "kind": "system", "radius_from": "QV Breaker Station",
     "width": 400_000,
     "about": "Nyx's thinner outer belt (Nyx belt beta). The QV Breaker stations sit in it, so quantum to any of "
              "them to get in. Or drop out on a route that crosses it.",
     "credit": "Distance: the QV Breaker stations' distance from the centre of Nyx."},
    {"id": "akiro", "name": "Akiro Cluster", "system": "Pyro", "kind": "qt",
     "about": "A cluster of charred asteroids near Pyro I's L3 point. It is on the quantum list: pick Akiro Cluster "
              "and quantum straight there. Mostly worthless rock, with some rare materials.",
     "credit": "Game data through the Star Citizen Wiki."},
]

QT_BODY_TYPES = {"Planet", "Moon", "Lagrange Point", "Planetoid", "Jump Point"}


def get(belt_id):
    return next((b for b in BELTS if b["id"] == belt_id), None)


def _flat(v):
    return math.hypot(v[0], v[1])


def ring_of(world, belt):
    """(inner km, outer km, half height km or None, label) of the part to aim for."""
    if belt.get("bands"):
        n, lo, hi, up, down = next(b for b in belt["bands"] if b[0] == belt["target"])
        return lo, hi, max(up, down), f"band {n}"
    src = belt.get("radius_from")
    if src:
        rs = [_flat(b.pos) for b in world.bodies.values() if b.name == src and b.star == belt["system"]]
        rs += [_flat(world.location_global(l, None)) for l in world.locations
               if l.name.startswith(src) and l.star == belt["system"]]
        if rs:
            r = sum(rs) / len(rs)
            w = belt.get("width", 400_000) / 2
            return r - w, r + w, None, "the belt"
    return None


def qt_points(world, system, when=None):
    """Quantum destinations in a system that sit in open space: [(name, type, global km)]."""
    out, seen = [], set()
    for b in world.bodies.values():
        if b.star == system and b.type in QT_BODY_TYPES and b.name not in seen:
            seen.add(b.name)
            out.append((b.name, b.type, b.pos))
    for l in world.locations:
        if l.star == system and l.quantum and l.body == system and l.name not in seen:
            seen.add(l.name)
            try:
                out.append((l.name, l.type, world.location_global(l, when)))
            except Exception:  # noqa: BLE001
                pass
    return out


def _band_interval(p, d, lo, hi):
    """First stretch of the straight line p->d (as fractions 0..1) whose flat distance from the
    centre is between lo and hi, or None."""
    dx, dy = d[0] - p[0], d[1] - p[1]
    a = dx * dx + dy * dy
    b = 2 * (p[0] * dx + p[1] * dy)
    c0 = p[0] * p[0] + p[1] * p[1]
    if a == 0:
        return None

    def roots(r):
        c = c0 - r * r
        disc = b * b - 4 * a * c
        if disc < 0:
            return []
        s = math.sqrt(disc)
        return sorted(((-b - s) / (2 * a), (-b + s) / (2 * a)))
    # inside the band where r <= hi and r >= lo; collect the boundary crossings in order
    cuts = sorted({t for t in roots(hi) + roots(lo) if 0.0 < t < 1.0} | {0.0, 1.0})
    for t0, t1 in zip(cuts, cuts[1:]):
        tm = (t0 + t1) / 2
        r = math.sqrt(max(0.0, c0 + b * tm + a * tm * tm))
        if lo <= r <= hi:
            return (t0, t1) if t0 > 0 else None  # starting inside the band: no route needed
    return None


def routes(world, belt, start=None, when=None, limit=6):
    """Ways into a system belt by dropping out of quantum travel.

    start: (name, global km) to plan from where you are; None plans from every main stop.
    Returns [{from, to, to_type, travel, drop, drop_far, drop_near}] sorted by distance flown."""
    ring = ring_of(world, belt)
    if not ring or belt["kind"] != "system":
        return []
    lo, hi, _h, _label = ring
    pts = qt_points(world, belt["system"], when)
    starts = [start] if start else [(n, p) for n, t, p in pts if t in ("Planet", "Planetoid", "Lagrange Point")]
    out = []
    for sname, sp in starts:
        for dname, dtype, dp in pts:
            if dname == sname or lo <= _flat(dp) <= hi:  # a stop already in the belt: just quantum there
                continue
            L = math.dist(sp, dp)
            if L < 1000:
                continue
            iv = _band_interval(sp, dp, lo, hi)
            if not iv:
                continue
            t0, t1 = iv
            tm = (t0 + t1) / 2
            out.append({"from": sname, "to": dname, "to_type": dtype, "travel": tm * L,
                        "drop": (1 - tm) * L, "drop_far": (1 - t0) * L, "drop_near": (1 - t1) * L,
                        "total": L})
    out.sort(key=lambda r: r["travel"])
    if start:
        return out[:limit]
    best = {}  # one route per starting point, the shortest
    for r in out:
        best.setdefault(r["from"], r)
    return sorted(best.values(), key=lambda r: r["travel"])[:limit]


def stops_inside(world, belt, when=None):
    """Quantum destinations that sit inside the belt itself (quantum straight there)."""
    ring = ring_of(world, belt)
    if not ring or belt["kind"] != "system":
        return []
    lo, hi = ring[0], ring[1]  # for the Halo: the band you aim for, not its thin outer bands
    return [n for n, _t, p in qt_points(world, belt["system"], when) if lo <= _flat(p) <= hi]


def where(world, belt, g):
    """Where a /showlocation fix is relative to a belt: dict(inside, text, band, dist)."""
    if belt["kind"] == "moon":
        body = world.bodies.get(belt["body"])
        if not body:
            return None
        d = math.dist(g, body.pos)
        inside = belt["inner"] <= d <= belt["outer"]
        if inside:
            return {"inside": True, "text": f"In {belt['name']}: {d:,.0f} km from {body.name}'s centre."}
        if d > belt["outer"] + 50_000:
            return {"inside": False, "text": f"Not near {body.name}: quantum to {body.name} first."}
        if d < belt["inner"]:
            return {"inside": False, "text": f"{belt['inner'] - d:,.0f} km short of the ring: fly away from "
                                             f"{body.name}."}
        return {"inside": False, "text": f"{d - belt['outer']:,.0f} km beyond the ring: fly toward {body.name}."}
    if belt["kind"] != "system":
        return None
    r, z = _flat(g), g[2]
    if belt.get("bands"):
        for n, lo, hi, up, down in belt["bands"]:
            if lo <= r <= hi:
                if -down <= z <= up:
                    best = " (the densest band)" if n == belt["target"] else ""
                    return {"inside": True, "band": n,
                            "text": f"In {belt['name']}, band {n}{best}. {r / 1e6:,.3f} Gm from the centre."}
                return {"inside": False, "band": n,
                        "text": f"Over band {n}, but {abs(z):,.0f} km {'above' if z > 0 else 'below'} it: "
                                f"fly {'down' if z > 0 else 'up'} into the belt."}
        lo, hi = belt["bands"][0][1], belt["bands"][-1][2]
    else:
        ring = ring_of(world, belt)
        if not ring:
            return None
        lo, hi = ring[0], ring[1]
        if lo <= r <= hi:
            return {"inside": True, "text": f"In {belt['name']}: {r / 1e6:,.3f} Gm from the centre of "
                                            f"{belt['system']}."}
    if r < lo:
        return {"inside": False, "text": f"Not in the belt yet. It starts {gm(lo - r)} further out from the centre."}
    if r > hi:
        return {"inside": False, "text": f"Not in the belt. You are {gm(r - hi)} past its outer edge."}
    return {"inside": False, "text": "Between bands. Fly a little further in or out."}


def gm(km):
    if km >= 1e6:
        return f"{km / 1e6:,.1f} Gm"
    return f"{round(km, -3):,.0f} km" if km >= 10_000 else f"{km:,.0f} km"


def short(w):
    """A few words for the in-game overlay."""
    if not w:
        return ""
    t = w["text"]
    if w.get("inside"):
        return f"In band {w['band']}" + (" (densest)" if "densest" in t else "") if w.get("band") else "In the belt"
    for a, b in (("Not in the belt yet. It starts ", "Belt starts in "), (" further out from the centre.", ""),
                 ("Not in the belt. You are ", ""), (" past its outer edge.", " past the belt"),
                 ("Between bands. Fly a little further in or out.", "Between bands")):
        t = t.replace(a, b)
    return t.rstrip(".")
