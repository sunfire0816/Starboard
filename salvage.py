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
class Store:
    def __init__(self, user_dir):
        self.path = os.path.join(user_dir, "salvage.json")
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
        except Exception:
            d = {}
        self.hold = d.get("hold") or {}
        self.hold.setdefault("mats", {})
        self.hold.setdefault("adds", [])
        self.runs = d.get("runs") or []

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"hold": self.hold, "runs": self.runs}, f, indent=1)
        os.replace(tmp, self.path)

    # -- the hold
    def amount(self, key):
        return float(self.hold["mats"].get(key) or 0)

    def total(self):
        return sum(self.amount(k) for k, _n, _s in MATERIALS)

    def _touch(self):
        if not self.hold.get("started"):
            self.hold["started"] = time.time()

    def add(self, key, scu, where=""):
        """Add (or with a negative number, take away) SCU of one material."""
        new = max(0.0, self.amount(key) + scu)
        self._touch()
        self.hold["mats"][key] = round(new, 3)
        self.hold["adds"].append({"ts": time.time(), "mat": key, "scu": round(scu, 3), "where": where})
        self.hold["adds"] = self.hold["adds"][-200:]
        self.save()

    def set(self, key, scu, where=""):
        self.add(key, max(0.0, scu) - self.amount(key), where)

    def set_ship(self, ship, cap):
        self.hold["ship"], self.hold["cap"] = ship, cap
        self.save()

    def clear(self):
        ship, cap = self.hold.get("ship"), self.hold.get("cap")
        self.hold = {"mats": {}, "adds": [], "ship": ship, "cap": cap}
        self.save()

    def started(self):
        return self.hold.get("started")

    # -- runs
    def finish(self, earned, sold_at="", mats=None, note=""):
        """Save a run (the hold, or the given load) with what it sold for, then empty the hold."""
        use_hold = mats is None
        mats = {k: v for k, v in (self.hold["mats"] if use_hold else mats).items() if v}
        run = {"start": self.hold.get("started") if use_hold else None, "end": time.time(),
               "ship": self.hold.get("ship") or "", "mats": mats, "earned": earned, "sold_at": sold_at,
               "note": note}
        if not run["start"]:
            run["start"] = run["end"]
        self.runs.append(run)
        if use_hold:
            self.clear()
        else:
            self.save()
        return run

    def delete_run(self, i):
        if 0 <= i < len(self.runs):
            del self.runs[i]
            self.save()


def run_hours(run):
    return max(0.0, (run.get("end", 0) - (run.get("start") or run.get("end", 0))) / 3600)


def totals(runs, since=0):
    """Runs, SCU, aUEC and aUEC per hour (over runs that have a time) since a timestamp."""
    rs = [r for r in runs if r.get("end", 0) >= since]
    scu = sum(sum(r.get("mats", {}).values()) for r in rs)
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


def buyers(trade, system=None):
    """{terminal id: (terminal, {mat key: (price per SCU, how much it takes or 0, age days)})}"""
    names = {n: k for k, n, _s in MATERIALS}
    now, out = time.time(), {}
    if not (trade and trade.loaded):
        return out
    for p in trade.prices:
        key = names.get(p.get("commodity_name"))
        if not key:
            continue
        price = _num(p.get("price_sell"))
        term = trade.terminals.get(p.get("id_terminal"))
        if price <= 0 or term is None or not term.available or (system and term.system != system):
            continue
        demand = _num(p.get("scu_sell") or p.get("scu_sell_stock"))
        age = (now - _num(p.get("date_modified"))) / 86400 if p.get("date_modified") else None
        out.setdefault(term.id, (term, {}))[1][key] = (price, demand, age)
    return out


def best_price(trade, key, system=None):
    """(terminal, price) that pays the most for one material."""
    best = None
    for term, mats in buyers(trade, system).values():
        if key in mats and (best is None or mats[key][0] > best[1]):
            best = (term, mats[key][0])
    return best


def sell_plan(trade, load, system=None):
    """Where to sell a whole load.
    Returns (rows, split): rows = [(terminal, value, {mat: (price, demand, age)}, missing mats)], best first;
    split = {mat: (terminal, price)} for selling each material where it pays most."""
    load = {k: v for k, v in load.items() if v > 0}
    rows = []
    for term, mats in buyers(trade, system).values():
        if load and not any(k in mats for k in load):
            continue
        value = sum(load[k] * mats[k][0] for k in load if k in mats)
        missing = [k for k in load if k not in mats]
        rows.append((term, value, mats, missing))
    rows.sort(key=lambda r: (-r[1], len(r[3])))
    split = {}
    for k in load:
        b = best_price(trade, k, system)
        if b:
            split[k] = b
    return rows, split


def value_of(trade, load, system=None):
    """What the load is worth selling each material at its best price (0 for unknown)."""
    v = 0.0
    for k, scu in load.items():
        b = best_price(trade, k, system) if scu else None
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
            if hs:
                crew = d.get("crew")
                ships.append({"name": name, "role": role, "cargo": _num(d.get("cargo_capacity")),
                              "crew": crew.get("min") if isinstance(crew, dict) else crew, "heads": hs})
    if not (ships and mods):
        raise RuntimeError("the Wiki sent no salvage gear")
    data = {"source": "api.star-citizen.wiki", "heads": heads, "mods": mods, "ships": ships}
    cache.save(data)
    return data
