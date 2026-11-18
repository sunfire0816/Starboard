"""
Salvage for Starboard: the salvage ships and their gear, what is in your hold
right now, your past salvage runs, where to sell a whole load, and which
places have wrecks or salvage contracts.

Gear data comes from the Star Citizen Wiki API (api.star-citizen.wiki): a
copy ships in data/salvage_gear.json and SETUP > UPDATE refreshes it into
user/wiki/salvage.json. Your hold and runs are kept in user/salvage.json.
"""

import json
import os
import re
import time

# (key, UEX commodity name, short name)
MATERIALS = [("rmc", "Recycled Material Composite", "RMC"),
             ("cm", "Construction Materials", "CM"),
             ("scrap", "Scrap", "Scrap")]
MAT_NAME = {k: n for k, n, _s in MATERIALS}
MAT_SHORT = {k: s for k, _n, s in MATERIALS}


# ------------------------------------------------------------------ gear
def load_gear(data_dir, user_dir):
    """The newest gear list we have: a downloaded one, else the copy that ships with Starboard."""
    best = None
    for p in (os.path.join(user_dir, "wiki", "salvage.json"), os.path.join(data_dir, "salvage_gear.json")):
        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            continue
        d = d.get("rows", d) if isinstance(d, dict) and "rows" in d else d
        if isinstance(d, dict) and d.get("ships") and d.get("mods"):
            if best is None:
                best = d
            else:  # keep the bundled contract sites if a download lacks them
                best.setdefault("contract_sites", d.get("contract_sites", {}))
    return best or {"ships": [], "mods": [], "heads": [], "contract_sites": {}}


def ship_for(gear, name):
    """The salvage ship whose name matches a hangar or picker name ('Drake Vulture' -> Vulture)."""
    if not name:
        return None
    n = name.lower()
    for s in gear.get("ships", []):
        sn = s["name"].lower().replace("misc ", "")
        if sn in n or n in s["name"].lower():
            return s
    return None


def module(gear, name):
    for m in gear.get("mods", []):
        if m["name"] == name:
            return m
    return None


GOALS = ["Most material per hull", "Big hulls quickly", "Balanced"]


def _goal_key(goal):
    if goal == GOALS[0]:   # keep the most: recovery first, then speed
        return lambda m: (m["efficiency"], m["speed"])
    if goal == GOALS[1]:   # widest beam first
        return lambda m: (m["radius"], m["efficiency"])
    return lambda m: (m["efficiency"] * m["radius"] * (0.5 + m["speed"]), m["efficiency"])


def suggest(gear, ship, goal):
    """For each salvage head on the ship: the modules to fit for a goal.
    A head keeps its tractor module if it came with one (it is what lets that arm tow)."""
    out = []
    for h in ship.get("heads", []):
        stock = h.get("modules", [])
        keep = [m for m in stock if (module(gear, m) or {}).get("kind") == "tractor"]
        free = len(stock) - len(keep)
        options = [m for m in gear.get("mods", []) if m["kind"] == "scraper" and m.get("fits", h["head"]) == h["head"]]
        options.sort(key=_goal_key(goal), reverse=True)
        best = [m["name"] for m in options[:free]]
        # keep modules that are already a pick in their slot, fill the other scraper slots with the rest
        todo = [b for b in best if b not in stock]
        pick = []
        for m in stock:
            if m in keep or m in best:
                pick.append(m)
            else:
                pick.append(todo.pop(0) if todo else m)
        out.append({"head": h["head"], "stock": stock, "pick": pick})
    return out


def describe_module(m):
    """Plain words for what a module is good at."""
    if m["kind"] == "tractor":
        return "Tractor beam for towing panels and boxes."
    bits = []
    if m["efficiency"] >= 1:
        bits.append("keeps all the material")
    elif m["efficiency"] < 0.75:
        bits.append(f"loses {100 - m['efficiency'] * 100:.0f}% of the material")
    if m["radius"] >= 3:
        bits.append("wide beam for big flat hulls")
    elif m["radius"] <= 1.5:
        bits.append("narrow beam for edges and small spots")
    if m["speed"] >= 0.6:
        bits.append("scrapes fast")
    elif m["speed"] <= 0.15:
        bits.append("scrapes slowly")
    return (", ".join(bits) or "all-round").capitalize() + "."


# ------------------------------------------------------------------ hold and runs
ACTIVE_GAP = 30 * 60   # a gap longer than this between entries is a break, not salvage time


class Store:
    """Your hold: salvage materials, cargo boxes and components you pulled off wrecks.

    A trip runs from the first thing you add until the hold is empty again. You can sell
    it in parts at different terminals; each sale is kept with the trip, and the finished
    trip goes to the runs list."""

    def __init__(self, user_dir):
        self.path = os.path.join(user_dir, "salvage.json")
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            d = {}
        self.hold = d.get("hold") or {}
        h = self.hold
        if "grid" not in h and h.get("cap"):  # from 12.8 test builds
            h["grid"] = h.pop("cap")
        for k, v in (("mats", {}), ("cargo", {}), ("parts", []), ("adds", []), ("sales", [])):
            h.setdefault(k, v)
        self.runs = d.get("runs") or []

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"hold": self.hold, "runs": self.runs}, f, indent=1)
        os.replace(tmp, self.path)

    # -- what is in it
    def amount(self, key):
        return float(self.hold["mats"].get(key) or 0)

    def salvage_scu(self):
        return sum(self.amount(k) for k, _n, _s in MATERIALS)

    def cargo_scu(self):
        return sum(float(v or 0) for v in self.hold["cargo"].values())

    def total(self):
        """SCU in the ship: salvage material plus cargo boxes (components are not counted)."""
        return self.salvage_scu() + self.cargo_scu()

    def empty(self):
        return not self.total() and not self.hold["parts"]

    def capacity(self):
        """(salvage buffer, cargo grid, total) in SCU, any of them may be 0 when unknown."""
        b, g = float(self.hold.get("buffer") or 0), float(self.hold.get("grid") or 0)
        return b, g, b + g

    def load(self):
        """{commodity name: SCU} for everything that sells by the SCU."""
        out = {MAT_NAME[k]: self.amount(k) for k, _n, _s in MATERIALS if self.amount(k)}
        for n, v in self.hold["cargo"].items():
            if v:
                out[n] = out.get(n, 0) + float(v)
        return out

    # -- changing it
    def _log(self, what, amount, where):
        if not self.hold.get("started"):
            self.hold["started"] = time.time()
        self.hold["adds"].append({"ts": time.time(), "what": what, "amount": round(amount, 3), "where": where})
        self.hold["adds"] = self.hold["adds"][-300:]

    def add(self, key, scu, where=""):
        """Add (or with a negative number, take away) SCU of a salvage material."""
        self.hold["mats"][key] = round(max(0.0, self.amount(key) + scu), 3)
        self._log(MAT_SHORT[key], scu, where)
        self.save()

    def set(self, key, scu, where=""):
        self.add(key, max(0.0, scu) - self.amount(key), where)

    def add_cargo(self, name, scu, where=""):
        c = self.hold["cargo"]
        c[name] = round(max(0.0, float(c.get(name) or 0) + scu), 3)
        if not c[name]:
            del c[name]
        self._log(name, scu, where)
        self.save()

    def add_part(self, name, qty=1, value=0, where=""):
        for p in self.hold["parts"]:
            if p["name"] == name and (p.get("value") or 0) == (value or 0):
                p["qty"] += qty
                break
        else:
            self.hold["parts"].append({"name": name, "qty": qty, "value": value or 0})
        self.hold["parts"] = [p for p in self.hold["parts"] if p["qty"] > 0]
        self._log(name, qty, where)
        self.save()

    def remove_part(self, i):
        if 0 <= i < len(self.hold["parts"]):
            del self.hold["parts"][i]
            self.save()

    def set_ship(self, ship, buffer, grid):
        self.hold["ship"], self.hold["buffer"], self.hold["grid"] = ship, buffer, grid
        self.save()

    def started(self):
        return self.hold.get("started")

    def earned(self):
        """aUEC from the sales made so far on this trip."""
        return sum(s.get("earned") or 0 for s in self.hold["sales"])

    def active_hours(self, until=None):
        """Time spent on this trip, not counting breaks longer than 30 minutes."""
        ts = sorted([a["ts"] for a in self.hold["adds"]] + [s["ts"] for s in self.hold["sales"]])
        if until:
            ts.append(until)
        sec = sum(min(b - a, ACTIVE_GAP) for a, b in zip(ts, ts[1:]))
        return sec / 3600

    # -- selling
    def sell(self, sold, earned, at="", where=""):
        """Take what you sold out of the hold and remember the sale.
        sold = {"mats": {key: scu}, "cargo": {name: scu}, "parts": {index: qty}}.
        Returns the finished run when the hold is now empty, else None."""
        h = self.hold
        for k, v in (sold.get("mats") or {}).items():
            h["mats"][k] = round(max(0.0, self.amount(k) - v), 3)
        for n, v in (sold.get("cargo") or {}).items():
            h["cargo"][n] = round(max(0.0, float(h["cargo"].get(n) or 0) - v), 3)
            if not h["cargo"][n]:
                del h["cargo"][n]
        parts = []
        for i, p in enumerate(h["parts"]):
            q = (sold.get("parts") or {}).get(i, 0)
            if q:
                parts.append({"name": p["name"], "qty": min(q, p["qty"])})
                p["qty"] -= q
        h["parts"] = [p for p in h["parts"] if p["qty"] > 0]
        if not h.get("started"):
            h["started"] = time.time()
        h["sales"].append({"ts": time.time(), "earned": earned, "at": at, "where": where,
                           "mats": {k: v for k, v in (sold.get("mats") or {}).items() if v},
                           "cargo": {n: v for n, v in (sold.get("cargo") or {}).items() if v}, "parts": parts})
        if self.empty():
            return self.finish()
        self.save()
        return None

    def finish(self):
        """Close the trip: save it as a run (if anything was sold) and empty the hold."""
        h = self.hold
        run = None
        if h["sales"]:
            mats, cargo, parts, names = {}, {}, 0, []
            for s in h["sales"]:
                for k, v in s.get("mats", {}).items():
                    mats[k] = mats.get(k, 0) + v
                for n, v in s.get("cargo", {}).items():
                    cargo[n] = cargo.get(n, 0) + v
                parts += sum(p.get("qty", 0) for p in s.get("parts", []))
                names += [p["name"] for p in s.get("parts", []) if p["name"] not in names]
            end = h["sales"][-1]["ts"]
            run = {"start": h.get("started") or end, "end": end, "ship": h.get("ship") or "",
                   "mats": mats, "cargo": cargo, "parts": parts, "part_names": names, "earned": self.earned(),
                   "hours": self.active_hours(), "stops": [s.get("at") or "?" for s in h["sales"]],
                   "sold_at": ", ".join(dict.fromkeys(s.get("at") or "?" for s in h["sales"]))}
            self.runs.append(run)
        self.hold = {"mats": {}, "cargo": {}, "parts": [], "adds": [], "sales": [],
                     "ship": h.get("ship"), "buffer": h.get("buffer"), "grid": h.get("grid")}
        self.save()
        return run

    def add_run(self, load, earned, at=""):
        """A sale that did not come out of the hold: saved straight to the runs list."""
        mats = {k: load[n] for k, n, _s in MATERIALS if load.get(n)}
        cargo = {n: v for n, v in load.items() if v and n not in MAT_NAME.values()}
        now = time.time()
        run = {"start": now, "end": now, "ship": self.hold.get("ship") or "", "mats": mats, "cargo": cargo,
               "parts": 0, "earned": earned, "hours": 0, "stops": [at or "?"], "sold_at": at}
        self.runs.append(run)
        self.save()
        return run

    def delete_run(self, i):
        if 0 <= i < len(self.runs):
            del self.runs[i]
            self.save()


def run_hours(run):
    if run.get("hours") is not None:
        return run["hours"]
    return max(0.0, (run.get("end", 0) - (run.get("start") or run.get("end", 0))) / 3600)


def run_scu(run):
    return sum(run.get("mats", {}).values()) + sum(run.get("cargo", {}).values())


def totals(runs, since=0):
    """Runs, SCU, aUEC and aUEC per hour (over runs that have a time) since a timestamp."""
    rs = [r for r in runs if r.get("end", 0) >= since]
    scu = sum(run_scu(r) for r in rs)
    earned = sum(r.get("earned") or 0 for r in rs)
    timed = [r for r in rs if run_hours(r) >= 0.05]
    hours = sum(run_hours(r) for r in timed)
    per_hour = sum(r.get("earned") or 0 for r in timed) / hours if hours else None
    return {"runs": len(rs), "scu": scu, "earned": earned, "hours": hours, "per_hour": per_hour}


# ------------------------------------------------------------------ prices
def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def buyers(trade, system=None, names=None):
    """{terminal id: (terminal, {commodity name: (price per SCU, how much it takes or 0, age days)})}
    for the salvage materials, or for the commodity names given."""
    want = set(names) if names else {n for _k, n, _s in MATERIALS}
    now, out = time.time(), {}
    if not (trade and trade.loaded):
        return out
    for p in trade.prices:
        name = p.get("commodity_name")
        if name not in want:
            continue
        price = _num(p.get("price_sell"))
        term = trade.terminals.get(p.get("id_terminal"))
        if price <= 0 or term is None or not term.available or (system and term.system != system):
            continue
        demand = _num(p.get("scu_sell") or p.get("scu_sell_stock"))
        age = (now - _num(p.get("date_modified"))) / 86400 if p.get("date_modified") else None
        out.setdefault(term.id, (term, {}))[1][name] = (price, demand, age)
    return out


def commodities(trade):
    """Every commodity name a terminal buys, for the cargo picker."""
    if not (trade and trade.loaded):
        return []
    return sorted({p.get("commodity_name") for p in trade.prices
                   if p.get("commodity_name") and _num(p.get("price_sell")) > 0})


def best_price(trade, name, system=None):
    """(terminal, price) that pays the most for one commodity (by name, or a material key)."""
    name = MAT_NAME.get(name, name)
    best = None
    for term, mats in buyers(trade, system, [name]).values():
        if name in mats and (best is None or mats[name][0] > best[1]):
            best = (term, mats[name][0])
    return best


def _take(scu, demand):
    return scu if not demand or demand <= 0 else min(scu, demand)


def terminal_offers(trade, load, system=None):
    """What each terminal would pay for the load, up to what it takes.
    Returns [(terminal, value, {name: (price, demand, age, scu it takes)}, names it does not buy)], best first."""
    load = {n: v for n, v in load.items() if v > 0}
    rows = []
    for term, prices in buyers(trade, system, load or None).values():
        if load and not any(n in prices for n in load):
            continue
        got, value = {}, 0.0
        for n, (price, demand, age) in prices.items():
            take = _take(load.get(n, 0), demand) if load else 0
            got[n] = (price, demand, age, take)
            value += take * price
        missing = [n for n in load if n not in prices]
        rows.append((term, value, got, missing))
    rows.sort(key=lambda r: (-r[1], len(r[3])))
    return rows


def sell_plan(trade, load, system=None, fewest_stops=False):
    """Plan the stops to sell a whole load when no single terminal takes all of it.

    Most aUEC: each commodity goes to the best price first, then the next best, up to
    what each terminal takes. Fewest stops: keep picking the terminal that takes the most
    value of what is left.
    Returns (stops, unsold): stops = [(terminal, [(name, scu, price)], value)], unsold = {name: scu}."""
    left = {n: v for n, v in load.items() if v > 0}
    offers = buyers(trade, system, left)
    stops = {}
    if fewest_stops:
        used = set()
        while left:
            best = None
            for tid, (term, prices) in offers.items():
                if tid in used:
                    continue
                lines = [(n, _take(left[n], prices[n][1]), prices[n][0]) for n in left if n in prices]
                val = sum(s * p for _n, s, p in lines)
                if lines and (best is None or val > best[2]):
                    best = (tid, lines, val)
            if not best:
                break
            used.add(best[0])
            stops[best[0]] = [list(x) for x in best[1]]
            for n, s, _p in best[1]:
                left[n] -= s
                if left[n] <= 1e-6:
                    del left[n]
    else:
        for n in list(left):
            cands = sorted(((prices[n][0], prices[n][1], tid) for tid, (_t, prices) in offers.items() if n in prices),
                           reverse=True)
            for price, demand, tid in cands:
                if left.get(n, 0) <= 1e-6:
                    break
                s = _take(left[n], demand)
                stops.setdefault(tid, []).append([n, s, price])
                left[n] -= s
            if left.get(n, 0) <= 1e-6:
                left.pop(n, None)
    out = [(offers[tid][0], [tuple(x) for x in lines], sum(s * p for _n, s, p in lines))
           for tid, lines in stops.items()]
    out.sort(key=lambda x: -x[2])
    return out, left


def value_of(trade, load, system=None):
    """What a load ({name or material key: SCU}) is worth at the best price for each (0 when unknown)."""
    v = 0.0
    for n, scu in load.items():
        b = best_price(trade, n, system) if scu else None
        if b:
            v += scu * b[1]
    return v


# ------------------------------------------------------------------ contracts
HINTS = [
    (r"salvage rights", "Buy the rights to a wreck, then scrape it. The wreck's location comes with the contract."),
    (r"risky .* salvage job", "Scrape a wreck you have no rights to. Illegal: expect a CrimeStat if caught."),
    (r"salvager needed", "Deliver salvage (RMC, construction materials or components) to Adagio Holdings."),
    (r"^clear .* of salvage", "Clean the wrecks out of a Pyro settlement for Citizens for Prosperity."),
    (r"^scrap salvage at", "Scrap the wrecks at a Pyro settlement for the Headhunters. Illegal."),
    (r"wrecked ships for sale", "Rough & Ready sells you a wreck to salvage."),
    (r"wrecked ships on the drift", "Salvage drifting wrecks for Rough & Ready."),
    (r"lawful salvage", "Salvage contract from the contract board, by difficulty."),
    (r"clean up|cover up", "Clean up a wreck before anyone finds it. Illegal."),
    (r"in the wake of disaster", "Story contract from Clovus Darneely."),
]


def tidy_title(t):
    t = re.sub(r"\[ClaimNumber\]", "…", t or "")
    t = re.sub(r"\[(Ship|ship)\]", "Ship", t)
    t = re.sub(r"\[Location\]", "a site", t)
    t = t.replace("~mission(Contractor|SalvageContractorFrom)", "Contract board")
    t = re.sub(r"^(Stanton\d?|Nyx|Pyro Region A) ", "", t)
    return t.strip()


def hint(title):
    tl = (title or "").lower()
    for pat, text in HINTS:
        if re.search(pat, tl):
            return text
    return ""


def contracts(missions):
    """Salvage missions from the MISSIONS download, one row per distinct contract."""
    groups = {}
    for m in missions or []:
        if "salvag" not in (m.get("type") or "").lower() and "salvag" not in (m.get("title") or "").lower():
            continue
        title = tidy_title(m.get("title"))
        giver = (m.get("giver") or "").replace("~mission(Contractor|SalvageContractorFrom)", "Contract board")
        systems = "/".join(m.get("systems") or []) or "Any"
        key = (title, giver, systems, bool(m.get("illegal")))
        g = groups.setdefault(key, {"title": title, "giver": giver or "Contract board", "systems": systems,
                                    "illegal": bool(m.get("illegal")), "rank": None, "rmin": None, "rmax": None,
                                    "count": 0, "hint": hint(m.get("title"))})
        g["count"] += 1
        if m.get("rank") is not None:
            g["rank"] = m["rank"] if g["rank"] is None else min(g["rank"], m["rank"])
        for k, src in (("rmin", "reward_min"), ("rmax", "reward_max")):
            v = m.get(src)
            if v:
                g[k] = v if g[k] is None else (min(g[k], v) if k == "rmin" else max(g[k], v))
    return sorted(groups.values(), key=lambda g: (g["illegal"], g["title"]))


def contract_sites(gear, missions):
    """{place name: note} for places that salvage contracts send you to."""
    out = {}
    for who, names in (gear.get("contract_sites") or {}).items():
        for n in names:
            out[n] = who
    for m in missions or []:
        t = m.get("title") or ""
        mm = re.match(r"Scrap Salvage at (.+)$", t) or re.match(r"Clear (.+) of Salvage$", t)
        if mm and "[" not in mm.group(1):
            out.setdefault(mm.group(1).strip(), "Headhunters scrap jobs (illegal)" if t.startswith("Scrap")
                           else "CFP clean-up jobs")
    return out


# ------------------------------------------------------------------ Wiki refresh
def fetch_gear(cache):
    """Download salvage heads, modules and ships from the Wiki and save them like data/salvage_gear.json."""
    import wikidata
    api = wikidata.API

    def price(d):
        p = [x for x in ((d.get("uex_prices") or {}).get("purchase") or []) if _num(x.get("price_buy")) > 0]
        if not p:
            return None
        return {"min": min(_num(x["price_buy"]) for x in p),
                "at": list(dict.fromkeys(x.get("terminal_name") for x in p if x.get("terminal_name")))[:4]}

    def detail(link):
        j = wikidata._get(link)
        return j.get("data", j)

    heads, mods, ships = [], [], []
    for it in wikidata.fetch_index("items", {"filter[type]": "SalvageHead"}):
        if "tractor" in (it.get("name") or "").lower():
            continue
        heads.append({"name": it.get("name"), "size": it.get("size"),
                      "maker": wikidata._name(it.get("manufacturer"))})
    for it in wikidata.fetch_index("items", {"filter[type]": "SalvageModifier"}):
        d = detail(it.get("link") or f"{api}/items/{it.get('uuid')}")
        s = ((d.get("weapon_modifier") or {}).get("salvage")) or {}
        name = d.get("name") or it.get("name")
        mods.append({"name": name, "maker": wikidata._name(d.get("manufacturer")),
                     "kind": "tractor" if "tractor" in name.lower() else "scraper",
                     "speed": _num(s.get("salvage_speed_multiplier")) or 1,
                     "radius": _num(s.get("radius_multiplier")) or 1,
                     "efficiency": _num(s.get("extraction_efficiency")) or 1,
                     "craftable": bool(d.get("is_craftable")), "price": price(d),
                     "fits": "Salvation Salvage Head" if "salvation" in (d.get("class_name") or "").lower()
                     else "Baler Salvage Head"})
    for role in ("Light Salvage", "Medium Salvage", "Heavy Salvage", "Starter / Light Salvage"):
        for v in wikidata.fetch_index("vehicles", {"filter[role]": role}):
            name = v.get("name") or ""
            if re.search(r"wikelo|best in show", name, re.I):
                continue
            d = detail((v.get("link") or f"{api}/vehicles/{v.get('uuid')}") + "?include=ports")
            hs = []

            def walk(ports, cur):
                for p in ports or []:
                    it = p.get("equipped_item") or {}
                    sub = p.get("ports") or it.get("ports")
                    if it.get("type") == "SalvageHead":
                        h = {"head": it.get("name"), "modules": []}
                        hs.append(h)
                        walk(sub, h)
                    elif it.get("type") == "SalvageModifier" and cur is not None:
                        cur["modules"].append(it.get("name"))
                        walk(sub, cur)
                    else:
                        walk(sub, cur)
            walk(d.get("ports"), None)
            buffer = 0.0

            def storages(ports):
                for p in ports or []:
                    it = p.get("equipped_item") or {}
                    if it.get("type") == "SalvageInternalStorage":
                        yield it
                    yield from storages(p.get("ports") or it.get("ports"))
            for it in storages(d.get("ports")):
                if it.get("link"):
                    try:
                        cap = ((detail(it["link"]).get("resource_container") or {}).get("capacity") or {})
                        buffer = _num(cap.get("scu") or cap.get("value"))
                    except Exception:
                        pass
            if hs:
                crew = d.get("crew")
                ships.append({"name": name, "role": role, "cargo": _num(d.get("cargo_capacity")), "buffer": buffer,
                              "crew": crew.get("min") if isinstance(crew, dict) else crew, "heads": hs})
    if not (ships and mods):
        raise RuntimeError("the Wiki sent no salvage gear")
    data = {"source": "api.star-citizen.wiki", "heads": heads, "mods": mods, "ships": ships}
    cache.save(data)
    return data
