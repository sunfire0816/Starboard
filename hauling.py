"""
Hauling for Starboard: trade routes, cargo contracts and a live run tracker.

Prices, terminals and ships come from the UEX Corp public API
(https://uexcorp.space/api, community-reported, updated hourly). They are
downloaded by the app on your PC and cached in user/uex/.

Terminals are matched to Starboard's own locations (stations, landing zones,
outposts) so distances, quantum routes and the overlay work for trade stops.
"""

import difflib
import functools
import itertools
import json
import os
import re
import time
import urllib.request

import core

UEX_BASE = "https://api.uexcorp.uk/2.0/"
USER_AGENT = "SC-Locator/8 (personal Star Citizen navigation tool)"
CACHE_TTL = 30 * 60          # UEX caches prices for 30 minutes
STALE_PRICE_DAYS = 7         # prices older than this are flagged
HERE_KM = 25.0               # terminals this close count as "where I am"

# Cargo sizes UEX does not list yet (it shows 0 for these modules). From the
# launch notes; you can always type your own SCU in the app and it is remembered.
MODULE_SCU = {"RSI Galaxy Cargo Module": 656}
FRONT_WORDS = ("bow", "front")
REAR_WORDS = ("stern", "rear")


# ---------------------------------------------------------------- download / cache
def _get(resource, timeout=40):
    req = urllib.request.Request(UEX_BASE + resource, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = json.loads(r.read().decode("utf-8-sig"))
    if isinstance(raw, dict):
        if raw.get("status") not in (None, "ok") and not raw.get("data"):
            raise RuntimeError(f"UEX said: {raw.get('status')} {raw.get('message', '')}".strip())
        data = raw.get("data", raw)
    else:
        data = raw
    if not isinstance(data, list):
        raise RuntimeError(f"Unexpected answer from UEX for {resource}.")
    return data


def cache_dir(user_dir):
    d = os.path.join(user_dir, "uex")
    os.makedirs(d, exist_ok=True)
    return d


SHOP_FEEDS = (("items_prices", "items_prices_all"), ("categories", "categories"),
              ("ship_buy", "vehicles_purchases_prices_all"), ("ship_rent", "vehicles_rentals_prices_all"),
              ("fuel", "fuel_prices_all"), ("refinery_yields", "refineries_yields"),
              ("refinery_methods", "refineries_methods"))


def download(user_dir, log=print):
    """Fetch prices, terminals and ships from UEX into the cache. Returns counts."""
    d = cache_dir(user_dir)
    counts = {}
    def save(name, data):
        with open(os.path.join(d, name + ".json.tmp"), "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(os.path.join(d, name + ".json.tmp"), os.path.join(d, name + ".json"))
        counts[name] = len(data)

    for name, res in (("terminals", "terminals"), ("prices", "commodities_prices_all"), ("vehicles", "vehicles")):
        log(f"Downloading {name} from UEX...")
        save(name, _get(res))
    # shop data: nice to have, so a failure here keeps the old copy
    for name, res in SHOP_FEEDS:
        try:
            log(f"Downloading {name.replace('_', ' ')} from UEX...")
            save(name, _get(res, timeout=120))
        except Exception as e:
            log(f"Could not download {name}: {e.__class__.__name__}")
    with open(os.path.join(d, "info.json"), "w", encoding="utf-8") as f:
        json.dump({"downloaded": time.time(), "counts": counts}, f)
    log("Trade data updated.")
    return counts


def cache_info(user_dir):
    try:
        with open(os.path.join(cache_dir(user_dir), "info.json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _load(user_dir, name):
    try:
        with open(os.path.join(cache_dir(user_dir), name + ".json"), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


@functools.lru_cache(maxsize=20000)
def _norm(s):
    s = str(s or "").lower().replace("'", "")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return " ".join(s.split())


# ---------------------------------------------------------------- the trade model
class Terminal:
    def __init__(self, row):
        self.id = row.get("id")
        # nickname is the short in-game style name ("TDD Area 18", "ARC-L1")
        self.name = row.get("nickname") or row.get("displayname") or row.get("name") or "?"
        self.full = row.get("name") or row.get("fullname") or self.name
        self.system = row.get("star_system_name") or ""
        self.planet = row.get("planet_name") or ""
        self.moon = row.get("moon_name") or ""
        self.orbit = row.get("orbit_name") or ""
        self.station = row.get("space_station_name") or ""
        self.city = row.get("city_name") or ""
        self.outpost = row.get("outpost_name") or ""
        self.max_box = _num(row.get("max_container_size"), 0)
        self.dock = bool(_num(row.get("has_docking_port"))) or bool(_num(row.get("has_loading_dock")))
        self.available = row.get("is_available_live", row.get("is_available", 1)) not in (0, "0", False)
        self.loc = None    # matched core.Location
        self.body = None   # matched core.Body (fallback)

    @property
    def place(self):
        return self.station or self.city or self.outpost or self.moon or self.planet or self.orbit or self.system


class TradeData:
    def __init__(self, world, user_dir):
        self.world = world
        self.user_dir = user_dir
        self.terminals = {}
        self.prices = []
        self.vehicles = []
        self.reload()

    def reload(self):
        self.terminals = {}
        for r in _load(self.user_dir, "terminals"):
            t = Terminal(r)
            if t.id is not None:
                self.terminals[t.id] = t
        self.prices = _load(self.user_dir, "prices")
        self.vehicles_raw = _load(self.user_dir, "vehicles")
        self.setups = build_setups(self.vehicles_raw)
        self._match_terminals()

    @property
    def loaded(self):
        return bool(self.prices) and bool(self.terminals)

    def age_minutes(self):
        info = cache_info(self.user_dir)
        return (time.time() - info["downloaded"]) / 60 if info.get("downloaded") else None

    # -- match UEX terminals to Starboard locations
    def _match_terminals(self):
        w = self.world
        self.extra_locations = {}
        by_system = {}
        for loc in w.locations:
            if loc.source == "db":
                by_system.setdefault(loc.star, []).append(loc)
        names = {_norm(b): b for b in w.bodies}
        for t in self.terminals.values():
            cands = by_system.get(t.system, [])
            body = None
            for key in (t.moon, t.planet):
                if key and _norm(key) in names:
                    body = w.bodies[names[_norm(key)]]
                    break
            t.body = body
            best, best_score = None, 0.0
            for key in (t.station, t.city, t.outpost, t.name):
                if not key:
                    continue
                nk = _norm(key)
                for loc in cands:
                    nl = _norm(loc.name)
                    if not nl:
                        continue
                    if nk == nl:
                        s = 1.0
                    elif len(nl) >= 5 and (nl in nk or nk in nl):
                        s = 0.9
                    else:
                        fa, fb = (nk.split() or [""])[0], (nl.split() or [""])[0]
                        if not (fa.startswith(fb) or fb.startswith(fa)):
                            continue  # "Terra Gateway" is not "Pyro Gateway": the first word must agree
                        sm = difflib.SequenceMatcher(None, nk, nl)
                        if sm.real_quick_ratio() < 0.75 or sm.quick_ratio() < 0.75:
                            continue  # cheap upper bounds: cannot reach the match threshold
                        s = sm.ratio()
                    if body and loc.body == body.name:
                        s += 0.05
                    if s > best_score:
                        best, best_score = loc, s
                if best_score >= 0.95:
                    break
            if best is not None and best_score >= 0.82:
                t.loc = best
                t.body = w.bodies.get(best.body, body)
                continue
            # jump gateways ("Terra Gateway (Stanton)") sit at their jump point ("Stanton-Terra JP")
            m = re.match(r"^(\w+) Gateway \((\w+)\)", t.station or "")
            jp = names.get(_norm(f"{m.group(2)}-{m.group(1)} JP")) if m else None
            if jp and w.bodies[jp].star == t.system:
                t.body = w.bodies[jp]
                key = (t.station, t.body.name)
                if key not in self.extra_locations:
                    self.extra_locations[key] = core.Location(
                        t.station, "Space station", t.body.name, t.system, (0.0, 0.0, 0.0),
                        source="uex", note="Position of its jump point (from UEX)")
                t.loc = self.extra_locations[key]
                continue
            # Lagrange stations (ARC-L2 ...) sit at their Lagrange point; cities like Levski
            # on a small body: use that body's position
            for key in (t.name, t.station.split(" ")[0] if t.station else "", t.orbit):
                b = names.get(_norm(key)) if key else None
                if b and w.bodies[b].star == t.system:
                    t.body = w.bodies[b]
                    if not t.body.rotates and t.station:
                        # a fixed point in space: make it a target the app can fly you to
                        key = (t.station, t.body.name)
                        if key not in self.extra_locations:
                            self.extra_locations[key] = core.Location(
                                t.station, "Space station", t.body.name, t.system, (0.0, 0.0, 0.0),
                                source="uex", note="Position of its Lagrange point (from UEX)")
                        t.loc = self.extra_locations[key]
                    break

    # -- positions and distances
    def position(self, t, when=None):
        """Global position (km) of a terminal now, or None if unknown."""
        when = when or core.utcnow()
        if t.loc is not None:
            return self.world.location_global(t.loc, when)
        if t.body is not None and t.body.type != "Star":
            return t.body.pos  # the star's position would be meaningless for a gateway or station
        return None

    def distance(self, a, b, when=None):
        pa, pb = self.position(a, when), self.position(b, when)
        if pa is None or pb is None:
            return None
        return core.vlen(core.vsub(pa, pb))

    def distance_from(self, here, t):
        if not here or not here.get("global"):
            return None
        if here["system"] != t.system:
            return None
        p = self.position(t, here["time"])
        return None if p is None else core.vlen(core.vsub(here["global"], p))

    # -- ships
    def ship_names(self):
        return [s["label"] for s in self.setups]

    def ship(self, label):
        for s in self.setups:
            if s["label"] == label:
                return s
        return None

    # -- every ship, for the hangar
    def all_ships(self):
        return sorted({v.get("name_full") or v.get("name") for v in self.vehicles_raw
                       if not _num(v.get("is_addon")) and (v.get("name_full") or v.get("name"))})

    def ship_info(self, name):
        v = next((v for v in self.vehicles_raw if not _num(v.get("is_addon"))
                  and name in (v.get("name_full"), v.get("name"))), None)
        if not v:
            return None
        roles = [label for key, label in ROLE_FLAGS if _num(v.get(key))]
        return {"name": name, "scu": _num(v.get("scu")), "crew": str(v.get("crew") or "").replace(",", "-"),
                "maker": v.get("company_name") or "", "pad": v.get("pad_type") or "", "roles": roles,
                "store": v.get("url_store") or "", "ground": bool(_num(v.get("is_ground_vehicle")))}

    def setups_for(self, name):
        return [s for s in self.setups if s["ship"] == name and (s["modules"] or "(no cargo" in s["label"])]

    def terminals_here(self, here, radius=HERE_KM):
        """Commodity terminals within `radius` km of a fix."""
        out = []
        for t in self.terminals.values():
            if not t.available:
                continue
            d = self.distance_from(here, t)
            if d is not None and d <= radius:
                out.append(t)
        return out

    def commodities_here(self, terminal_ids):
        return sorted({c for c, *_ in self.sold_at(terminal_ids)})

    def sold_at(self, terminal_ids):
        """What the given terminals sell to you: [(commodity, price, stock, terminal)]."""
        out = []
        for p in self.prices:
            if p.get("id_terminal") in terminal_ids and _num(p.get("price_buy")) > 0 \
                    and is_cargo(p.get("commodity_name")):
                out.append((p.get("commodity_name"), _num(p.get("price_buy")), _num(p.get("scu_buy")),
                            self.terminals[p["id_terminal"]]))
        return sorted(out, key=lambda x: x[0] or "")

    # -- routes
    def commodities(self):
        return sorted({p.get("commodity_name") for p in self.prices if is_cargo(p.get("commodity_name"))})

    def routes(self, scu, budget=None, system=None, here=None, commodity=None, same_system=True,
               from_here_km=None, limit=150, buy_at=None, per_pair=3):
        """Best buy-at-A, sell-at-B runs for a cargo hold of `scu`."""
        buys, sells = {}, {}
        now = time.time()
        for p in self.prices:
            t = self.terminals.get(p.get("id_terminal"))
            if not t or not t.available:
                continue
            name = p.get("commodity_name")
            if not is_cargo(name):
                continue
            if commodity and name != commodity:
                continue
            if system and t.system != system:
                continue
            age_days = (now - _num(p.get("date_modified"), now)) / 86400 if p.get("date_modified") else None
            pb, ps = _num(p.get("price_buy")), _num(p.get("price_sell"))
            if pb > 0:
                buys.setdefault(name, []).append((t, pb, _num(p.get("scu_buy")), age_days))
            if ps > 0:
                sells.setdefault(name, []).append((t, ps, _num(p.get("scu_sell")) or _num(p.get("scu_sell_stock")),
                                                   age_days))
        out = []
        when = core.utcnow()
        pos_cache = {}

        def pos(t):
            if t.id not in pos_cache:
                pos_cache[t.id] = self.position(t, when)
            return pos_cache[t.id]

        def dist(a, b):
            pa, pb = pos(a), pos(b)
            return None if pa is None or pb is None else core.vlen(core.vsub(pa, pb))

        here_km = {}

        def from_here(t):
            if t.id not in here_km:
                here_km[t.id] = self.distance_from(here, t) if here else None
            return here_km[t.id]

        for name, blist in buys.items():
            for (ta, pb, stock, age_a) in blist:
                if buy_at is not None and ta.id not in buy_at:
                    continue
                if from_here_km is not None and here:
                    d0 = from_here(ta)
                    if d0 is None or d0 > from_here_km:
                        continue
                for (tb, ps, demand, age_b) in sells.get(name, []):
                    if tb.id == ta.id or ps <= pb:
                        continue
                    if same_system and ta.system != tb.system:
                        continue
                    qty = scu
                    limits = []
                    if stock > 0 and stock < qty:
                        qty, limits = stock, limits + ["stock"]
                    if demand > 0 and demand < qty:
                        qty, limits = demand, limits + ["demand"]
                    if budget and pb * qty > budget:
                        qty, limits = int(budget // pb), limits + ["budget"]
                    qty = int(qty)
                    if qty <= 0:
                        continue
                    profit = qty * (ps - pb)
                    trip = dist(ta, tb)
                    old = max([a for a in (age_a, age_b) if a is not None], default=None)
                    out.append({"commodity": name, "buy": ta, "sell": tb, "price_buy": pb, "price_sell": ps,
                                "margin": ps - pb, "qty": qty, "invest": qty * pb, "profit": profit,
                                "limits": limits, "distance": trip, "age_days": old,
                                "from_here": from_here(ta)})
        out.sort(key=lambda r: -r["profit"])
        # keep the list varied: at most a few sell options per buy terminal and commodity
        seen, varied = {}, []
        for r in out:
            k = (r["buy"].id, r["commodity"])
            seen[k] = seen.get(k, 0) + 1
            if seen[k] <= per_pair:
                varied.append(r)
        return varied[:limit]


ROLE_FLAGS = [("is_cargo", "Cargo"), ("is_mining", "Mining"), ("is_salvage", "Salvage"),
              ("is_refinery", "Refining"), ("is_military", "Combat"), ("is_bomber", "Bomber"),
              ("is_exploration", "Exploration"), ("is_scanning", "Scanning"), ("is_medical", "Medical"),
              ("is_refuel", "Refuel"), ("is_repair", "Repair"), ("is_passenger", "Passenger"),
              ("is_racing", "Racing"), ("is_datarunner", "Data running"), ("is_interdiction", "Interdiction"),
              ("is_carrier", "Carrier"), ("is_construction", "Construction"), ("is_ground_vehicle", "Ground vehicle"),
              ("is_starter", "Starter")]

NOT_CARGO = ("ship ammunition", "countermeasures", "hydrogen fuel", "quantum fuel")


def is_cargo(name):
    """Fuel, ammunition and countermeasures are sold at terminals but are not hauled in boxes."""
    n = (name or "").lower()
    return bool(n) and not any(k in n for k in NOT_CARGO)


# ---------------------------------------------------------------- ships and modules
def _module_scu(v):
    return _num(v.get("scu")) or MODULE_SCU.get(v.get("name_full") or v.get("name"), 0)


def _short_module(base_name, mod_name):
    s = mod_name
    if s.startswith(base_name):
        s = s[len(base_name):]
    s = re.sub(r"[-\u2013]", " ", s)
    s = re.sub(r"\b(module|pod|bay)\b", " ", s, flags=re.I)
    s = re.sub(r"\b(bow|stern|front|rear)\b", " ", s, flags=re.I)
    return " ".join(s.split()) or mod_name


def build_setups(vehicles):
    """Every ship with cargo, plus one entry per cargo module setup (for example
    "RSI Galaxy + Cargo Module", or the Retaliator's bow and stern modules)."""
    by_id = {v.get("id"): v for v in vehicles}
    addons = {}
    for v in vehicles:
        if _num(v.get("is_addon")):
            addons.setdefault(v.get("id_parent"), []).append(v)
    setups = []
    for v in vehicles:
        if _num(v.get("is_addon")):
            continue
        name = v.get("name_full") or v.get("name") or "?"
        base = _num(v.get("scu"))
        mods = [m for m in addons.get(v.get("id"), []) if _module_scu(m) > 0]
        if not mods:
            if base > 0:
                setups.append({"label": name, "ship": name, "modules": [], "scu": base})
            continue
        mod_total = sum(_module_scu(m) for m in mods)
        # UEX sometimes gives the base ship its fully loaded figure (Retaliator 74 = 38 + 36)
        hull = 0.0 if abs(base - mod_total) < 0.5 and len(mods) > 1 else base
        front = [m for m in mods if any(w in (m.get("name_full") or "").lower() for w in FRONT_WORDS)]
        rear = [m for m in mods if any(w in (m.get("name_full") or "").lower() for w in REAR_WORDS)]
        if front or rear:
            combos = [(f, r) for f in [None] + front for r in [None] + rear]
            for f, r in combos:
                parts = [p for p in (("Bow " + _short_module(name, f["name_full"])) if f else None,
                                     ("Stern " + _short_module(name, r["name_full"])) if r else None) if p]
                scu = hull + (_module_scu(f) if f else 0) + (_module_scu(r) if r else 0)
                label = f"{name} ({' + '.join(parts)})" if parts else f"{name} (no cargo modules)"
                setups.append({"label": label, "ship": name, "modules": [m["name_full"] for m in (f, r) if m],
                               "scu": scu})
        else:
            setups.append({"label": f"{name} (no cargo module)", "ship": name, "modules": [], "scu": hull})
            for m in mods:
                setups.append({"label": f"{name} + {_short_module(name, m['name_full'])} Module", "ship": name,
                               "modules": [m["name_full"]], "scu": hull + _module_scu(m)})
    setups = [s for s in setups if s["scu"] > 0 or s["modules"] or "(no cargo" in s["label"]]
    return sorted(setups, key=lambda s: s["label"])


# ---------------------------------------------------------------- contracts and run planning
class Contracts:
    """Hauling contracts you entered: each has one or more legs (pickup -> drop-off)."""

    def __init__(self, world):
        self.world = world
        self.path = os.path.join(world.user_dir, "contracts.json")
        try:
            with open(self.path, encoding="utf-8") as f:
                self.items = json.load(f)
        except Exception:
            self.items = []

    def save(self):
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.items, f, indent=1)

    def add(self, title, reward, legs):
        cid, used = int(time.time() * 1000), {c["id"] for c in self.items}
        while str(cid) in used:
            cid += 1
        c = {"id": str(cid), "title": title, "reward": reward, "legs": legs, "active": True}
        self.items.append(c)
        self.save()
        return c

    def remove(self, cid):
        self.items = [c for c in self.items if c["id"] != cid]
        self.save()

    def active_legs(self):
        legs = []
        for c in self.items:
            if not c.get("active", True):
                continue
            for i, leg in enumerate(c["legs"]):
                legs.append(dict(leg, contract=c["title"], cid=c["id"], leg=i))
        return legs


def split_legs(legs, capacity):
    """Split any leg bigger than the hold into trips that fit (e.g. 96 SCU in a
    64 SCU ship becomes 64 + 32)."""
    out = []
    for leg in legs:
        scu = float(leg["scu"])
        if capacity and scu > capacity + 1e-6:
            n = int(-(-scu // capacity))
            left = scu
            for k in range(n):
                part = min(capacity, left)
                left -= part
                out.append(dict(leg, scu=part, part=f"{k + 1}/{n}"))
        else:
            out.append(leg)
    return out


def find_location(world, name, body=None):
    """Location by name (and body if given)."""
    for l in world.locations:
        if l.name == name and (body is None or l.body == body):
            return l
    return None


def _stop_pos(world, stop, when):
    loc = stop.get("loc")
    if loc is not None:
        return world.location_global(loc, when)
    return None


def plan_run(world, legs, capacity, start=None, when=None):
    """Order pickups and drop-offs to keep the total distance short, never carrying
    more than `capacity` SCU and never dropping cargo before picking it up.

    legs: list of dicts with pickup / dropoff (Location), scu, commodity.
    Returns a list of stops: {loc, actions: [(kind, leg)], load_after, leg_km}."""
    when = when or core.utcnow()
    for merge in (True, False):
        # first try one visit per place; if that cannot work (e.g. two contracts that
        # swap cargo between the same two stations), allow separate visits
        nodes = _make_nodes(legs, merge)
        stops = _solve(world, nodes, legs, capacity, start, when)
        if stops:
            # join back-to-back stops at the same place
            merged = []
            for st in stops:
                if merged and merged[-1]["loc"] is st["loc"]:
                    merged[-1]["actions"] += st["actions"]
                    merged[-1]["load_after"] = st["load_after"]
                else:
                    merged.append(st)
            return merged
    return None


def _make_nodes(legs, merge):
    places, nodes = {}, []
    for i, leg in enumerate(legs):
        for kind in ("pickup", "dropoff"):
            loc = leg[kind]
            if merge:
                key = (loc.name, loc.body)
                if key not in places:
                    places[key] = {"loc": loc, "actions": []}
                    nodes.append(places[key])
                places[key]["actions"].append((kind, i))
            else:
                nodes.append({"loc": loc, "actions": [(kind, i)]})
    return nodes


def _solve(world, nodes, legs, capacity, start, when):
    pos = [world.location_global(n["loc"], when) for n in nodes]
    start_pos = start

    def dist(a, b):
        return core.vlen(core.vsub(a, b))

    def evaluate(order):
        """Simulate an order of node indices: returns total km, or None if invalid.
        At each stop drops happen before pickups."""
        picked, dropped, load, total = set(), set(), 0.0, 0.0
        prev = start_pos
        for idx in order:
            n = nodes[idx]
            for kind, li in n["actions"]:
                if kind == "dropoff" and li in picked and li not in dropped:
                    dropped.add(li)
                    load -= legs[li]["scu"]
            for kind, li in n["actions"]:
                if kind == "pickup" and li not in picked:
                    picked.add(li)
                    load += legs[li]["scu"]
            if load > capacity + 1e-6:
                return None
            if prev is not None:
                total += dist(prev, pos[idx])
            prev = pos[idx]
        # a node may need a second visit (drop at a place visited before the pickup)
        if len(dropped) != len(legs):
            return None
        return total

    n = len(nodes)
    best_order, best_km = None, None
    if n <= 8:
        for order in itertools.permutations(range(n)):
            km = evaluate(order)
            if km is not None and (best_km is None or km < best_km):
                best_order, best_km = list(order), km
    if best_order is None:
        # greedy: nearest stop that keeps the plan valid, then 2-opt style improvement
        remaining, order = set(range(n)), []
        prev = start_pos
        while remaining:
            cand = sorted(remaining, key=lambda j: dist(prev, pos[j]) if prev is not None else 0)
            for j in cand:
                trial = order + [j]
                if _partial_ok(trial, nodes, legs, capacity):
                    order.append(j)
                    remaining.discard(j)
                    prev = pos[j]
                    break
            else:
                order += list(remaining)  # nothing valid; fall back to remaining order
                remaining.clear()
        best_order, best_km = order, evaluate(order)
        improved = True
        while improved and best_km is not None:
            improved = False
            for i in range(n - 1):
                for j in range(i + 1, n):
                    trial = best_order[:i] + best_order[i:j + 1][::-1] + best_order[j + 1:]
                    km = evaluate(trial)
                    if km is not None and km < best_km - 1e-6:
                        best_order, best_km, improved = trial, km, True
    if best_order is None or best_km is None:
        return None  # no valid order this way
    stops, load, prev, picked = [], 0.0, start_pos, set()
    for idx in best_order:
        node = nodes[idx]
        acts = []
        for kind, li in node["actions"]:
            if kind == "dropoff" and li in picked:
                acts.append(("dropoff", li))
                load -= legs[li]["scu"]
        for kind, li in node["actions"]:
            if kind == "pickup":
                acts.append(("pickup", li))
                picked.add(li)
                load += legs[li]["scu"]
        stops.append({"loc": node["loc"], "actions": acts, "load_after": load,
                      "leg_km": dist(prev, pos[idx]) if prev is not None else None})
        prev = pos[idx]
    return stops


def _partial_ok(order, nodes, legs, capacity):
    picked, load = set(), 0.0
    for idx in order:
        for kind, li in nodes[idx]["actions"]:
            if kind == "dropoff":
                if li not in picked:
                    return False  # would arrive before the cargo is on board
                load -= legs[li]["scu"]
        for kind, li in nodes[idx]["actions"]:
            if kind == "pickup":
                picked.add(li)
                load += legs[li]["scu"]
        if load > capacity + 1e-6:
            return False
    return True


def describe_actions(stop, legs):
    out = []
    for kind, li in stop["actions"]:
        leg = legs[li]
        what = f"{leg['scu']:g} SCU" + (f" {leg['commodity']}" if leg.get("commodity") else "")
        tag = f" ({leg['contract']})" if leg.get("contract") else ""
        if leg.get("part"):
            tag += f" trip {leg['part']}"
        out.append(("LOAD " if kind == "pickup" else "UNLOAD ") + what + tag)
    return out
