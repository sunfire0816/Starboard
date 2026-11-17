"""
Game data from the Star Citizen Wiki API (api.star-citizen.wiki) for Starboard:
mining lasers, modules and gadgets with their stats, and every mission
(contract) in the game. Downloaded in the background and cached in user/wiki/.

Please credit api.star-citizen.wiki when sharing Starboard (their request).
"""

import json
import os
import re
import time
import urllib.parse
import urllib.request

API = "https://api.star-citizen.wiki/api"
UA = "Starboard (Star Citizen companion; free, non-commercial)"
MAX_PAGES = 120


def _get(url, timeout=25):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _num(v):
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        m = re.search(r"-?\d+(?:[.,]\d+)?", v.replace(" ", ""))
        if m:
            return float(m.group(0).replace(",", "."))
    return None


def _name(v):
    if isinstance(v, dict):
        return v.get("name") or v.get("label") or v.get("title") or ""
    return v or ""


def fetch_index(path, params=None, progress=None, pause=0.25):
    """Every row of a paginated index route, following the API's next links."""
    q = dict(params or {})
    q.setdefault("limit", 200)
    q.setdefault("page[size]", 200)
    url = f"{API}/{path}?" + urllib.parse.urlencode(q, safe="[]")
    rows, page, seen = [], 1, set()
    while url and page <= MAX_PAGES and url not in seen:
        seen.add(url)
        j = _get(url)
        data = j.get("data", []) if isinstance(j, dict) else j
        if isinstance(data, dict):
            data = [data]
        rows.extend(data)
        if progress:
            progress(len(rows))
        nxt = None
        links, meta = j.get("links") if isinstance(j, dict) else None, j.get("meta") if isinstance(j, dict) else None
        if isinstance(links, dict) and isinstance(links.get("next"), str):
            nxt = links["next"]
        elif isinstance(meta, dict):
            cur, last = meta.get("current_page"), meta.get("last_page")
            if isinstance(cur, int) and isinstance(last, int) and cur < last:
                q["page"] = cur + 1
                nxt = f"{API}/{path}?" + urllib.parse.urlencode(q, safe="[]")
        if not data:
            break
        url, page = nxt, page + 1
        time.sleep(pause)
    return rows


class Cache:
    def __init__(self, user_dir, name):
        self.dir = os.path.join(user_dir, "wiki")
        self.path = os.path.join(self.dir, name + ".json")

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def save(self, rows):
        os.makedirs(self.dir, exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"fetched": time.time(), "rows": rows}, f)
        os.replace(tmp, self.path)

    def debug(self, name, obj):
        """Keep one raw sample so a wrong guess about the API can be fixed later."""
        try:
            os.makedirs(self.dir, exist_ok=True)
            with open(os.path.join(self.dir, f"sample_{name}.json"), "w", encoding="utf-8") as f:
                json.dump(obj, f, indent=1)
        except OSError:
            pass


# ------------------------------------------------------------------ mining
MOD_LABELS = {
    "resistance": "Resistance", "laser_instability": "Instability", "instability": "Instability",
    "optimal_charge_window_size": "Optimal window size", "optimal_charge_window": "Optimal window size",
    "optimal_charge_rate": "Optimal charge rate", "optimal_charge_window_rate": "Optimal charge rate",
    "all_charge_rates": "All charge rates", "overcharge_rate": "Overcharge rate", "inert_materials": "Inert materials",
    "shatter_damage": "Shatter damage", "cluster_modifier": "Clustering", "clustering": "Clustering",
    "extraction_rate": "Extraction rate", "catastrophic_charge_rate": "Catastrophic charge rate",
}
MOD_ORDER = ["resistance", "laser_instability", "optimal_charge_window_size", "optimal_charge_rate",
             "all_charge_rates", "overcharge_rate", "inert_materials", "shatter_damage", "cluster_modifier",
             "catastrophic_charge_rate"]
# lower is better for these
LOWER_BETTER = {"resistance", "laser_instability", "overcharge_rate", "inert_materials", "shatter_damage",
                "catastrophic_charge_rate"}
ALIASES = {"instability": "laser_instability", "optimal_charge_window": "optimal_charge_window_size",
           "optimal_charge_window_rate": "optimal_charge_rate", "clustering": "cluster_modifier"}


def _mods(block):
    out = {}
    if not isinstance(block, dict):
        return out
    src = block.get("modifier_map") or block.get("modifiers") or {}
    if isinstance(src, list):
        src = {x.get("name"): x.get("value") for x in src if isinstance(x, dict)}
    for k, v in (src or {}).items():
        n = _num(v)
        if k and n is not None:
            key = ALIASES.get(k.lower(), k.lower())
            if key in ("power_modifier", "mining_laser_power", "extraction_laser_power"):
                continue
            out[key] = n
    return out


def _desc_text(d):
    dd = d.get("description_data")
    try:
        return json.dumps(dd).lower()
    except (TypeError, ValueError):
        return ""


def normalize_mining(d):
    """API item -> small dict Starboard uses, or None if it is not mining gear."""
    typ = (d.get("type") or "")
    cls = d.get("class_name") or ""
    classification = d.get("classification") or ""
    row = {"uuid": d.get("uuid"), "name": d.get("name") or cls, "class": cls, "size": _num(d.get("size")) or 0,
           "maker": _name(d.get("manufacturer"))}
    if typ == "WeaponMining" or "mining_laser" in d:
        ml = d.get("mining_laser") or {}
        lp = ml.get("laser_power") if isinstance(ml.get("laser_power"), dict) else {}
        row.update(kind="laser", slots=int(_num(ml.get("module_slots")) or 0),
                   power_min=_num(lp.get("min") if lp else None) or _num(lp.get("minimum") if lp else None),
                   power_max=_num(lp.get("max") if lp else None) or _num(lp.get("maximum") if lp else None)
                   or _num(ml.get("power_transfer")),
                   extract=_num(ml.get("extraction_throughput")) or _num(ml.get("extraction_laser_power")),
                   opt_range=_num(ml.get("optimal_range")), max_range=_num(ml.get("maximum_range")),
                   mods=_mods(ml), fps=classification.lower().startswith("fps") or "fps" in cls.lower())
        return row
    mm = d.get("mining_modifier")
    if typ in ("MiningModifier", "Gadget") or isinstance(mm, dict) or "mining.gadget" in classification.lower():
        mm = mm if isinstance(mm, dict) else {}
        gadget = typ == "Gadget" or "gadget" in classification.lower()
        mods = _mods(mm) or _mods(d.get("mining_gadget") or {})
        pm = _num(mm.get("power_modifier"))
        target = "extract" if "extraction laser power" in _desc_text(d) else "mining"
        row.update(kind="gadget" if gadget else "module", mods=mods, power_mod=pm or 0.0, power_target=target,
                   active="active" in str(mm.get("type") or "").lower() or "Active" in cls,
                   charges=_num(mm.get("charges")), duration=_num(mm.get("duration")))
        return row
    return None


def fetch_mining(cache, progress=None):
    """Lasers, modules and gadgets with full stats. Index rows are short, so each item is
    fetched on its own (about 70 small requests, spaced out to be polite)."""
    rows = []
    for typ in ("WeaponMining", "MiningModifier", "Gadget"):
        idx = fetch_index("items", {"filter[type]": typ}, None)
        if idx:
            cache.debug(f"mining_index_{typ}", idx[:2])
        for i, it in enumerate(idx):
            if progress:
                progress(f"{typ} {i + 1}/{len(idx)}")
            d = it
            needs = (typ == "WeaponMining" and "mining_laser" not in it) or \
                    (typ != "WeaponMining" and "mining_modifier" not in it and "mining_gadget" not in it)
            if needs and it.get("uuid"):
                try:
                    j = _get(f"{API}/items/{it['uuid']}")
                    d = j.get("data", j)
                    time.sleep(0.2)
                except Exception:
                    continue
            if i == 0:
                cache.debug(f"mining_item_{typ}", d)
            r = normalize_mining(d)
            if r and r.get("uuid"):
                rows.append(r)
    rows = clean_mining(rows)
    cache.save(rows)
    return rows


_STD_LASER = re.compile(r"^Mining_Laser_[A-Z]{4}_[A-Za-z]+_S\d$")


def clean_mining(rows):
    """Drop what the Wiki lists under mining types but nobody can fit: Origin chess pieces (the game
    files them as 'gadgets'), test and placeholder lasers, and duplicate copies of a laser
    (a ship's built-in arm sharing a store laser's name)."""
    keep = []
    for r in rows:
        cls = r.get("class") or ""
        name = r.get("name") or ""
        if r["kind"] == "gadget" and not cls.lower().startswith("mining_gadget"):
            continue
        if "test" in cls.lower():
            continue
        if r["kind"] == "laser" and (name == name.lower() or re.match(r"^S0+ ", name)):
            continue  # internal names such as 'mining_laser_gama_hyun_s1' or 'S00 Hofstede'
        if r["kind"] == "module" and cls == "Mining_Modules":
            continue
        keep.append(r)
    out, seen = [], {}
    for r in keep:
        key = (r["kind"], r.get("name"))
        if key in seen:
            i = seen[key]
            if r["kind"] == "laser" and _STD_LASER.match(r.get("class") or "") and \
                    not _STD_LASER.match(out[i].get("class") or ""):
                out[i] = r  # keep the normal store laser, not the built-in copy
            continue
        seen[key] = len(out)
        out.append(r)
    return out


def combine(values):
    """Percent modifiers stack by multiplying: +20% and +10% make +32%."""
    f = 1.0
    for v in values:
        f *= 1 + v / 100.0
    return (f - 1) * 100


def loadout_stats(laser, modules, gadget=None, include_active=True):
    """Totals for one laser with its modules (and the gadget on the rock)."""
    if not laser:
        return None
    mods = [m for m in modules if m and (include_active or not m.get("active"))]
    pmult = 1.0
    emult = 1.0
    for m in mods:
        if m.get("power_mod"):
            if m.get("power_target") == "extract":
                emult *= 1 + m["power_mod"]
            else:
                pmult *= 1 + m["power_mod"]
    keys = set(laser.get("mods", {}))
    for m in mods + ([gadget] if gadget else []):
        keys |= set(m.get("mods", {}))
    out = {"power_min": (laser.get("power_min") or 0) * pmult, "power_max": (laser.get("power_max") or 0) * pmult,
           "extract": (laser.get("extract") or 0) * emult, "opt_range": laser.get("opt_range"),
           "max_range": laser.get("max_range"), "mods": {}}
    for k in keys:
        vals = [laser.get("mods", {}).get(k, 0)] + [m.get("mods", {}).get(k, 0) for m in mods]
        if gadget:
            vals.append(gadget.get("mods", {}).get(k, 0))
        out["mods"][k] = combine(v for v in vals if v)
    return out


def crack(stats_list, mass, resistance_pct):
    """Can these lasers (each from loadout_stats, gadget included) break a rock?
    Community formula (Regolith and others): power needed = mass / (1 - resistance) x 0.2, where the
    rock's resistance is changed by the laser, modules and gadget. Lasers on the same rock add up.
    Returns (share of the needed power you bring, needed power for the first laser, effective resistance)."""
    if not mass or mass <= 0:
        return None
    share, need0, eff0 = 0.0, None, None
    for s in stats_list:
        if not s:
            continue
        res = max(0.0, min(0.99, resistance_pct / 100.0 * (1 + s["mods"].get("resistance", 0) / 100.0)))
        need = mass / (1 - res) * 0.2
        if need0 is None:
            need0, eff0 = need, res * 100
        share += (s.get("power_max") or 0) / need if need else 0
    return share, need0, eff0


# ------------------------------------------------------------------ missions
def _bp_uuid_from_link(link):
    m = re.search(r"/blueprints/([0-9a-f-]{36})", link or "")
    return m.group(1) if m else None


PLACEHOLDER = "placeholder"


def mission_blueprints(raw):
    """[(name, blueprint uuid)] a mission index row can give."""
    out = []
    for b in raw.get("blueprints") or []:
        if not isinstance(b, dict):
            continue
        if isinstance(b.get("items"), list):  # detail format: pools of items
            for it in b["items"]:
                if isinstance(it, dict) and it.get("name"):
                    out.append((it["name"], _bp_uuid_from_link(it.get("blueprint_link"))))
        elif b.get("name"):
            out.append((b["name"], _bp_uuid_from_link(b.get("link"))))
    return out


def mission_standing(raw):
    """(name, min reputation) a mission needs, or ('', None)."""
    ms = raw.get("min_standing")
    name = raw.get("min_standing_name") or (ms.get("name") if isinstance(ms, dict) else "") or ""
    rep = ms.get("min_reputation") if isinstance(ms, dict) else None
    if PLACEHOLDER in name.lower():
        return "", None
    return name, rep


def normalize_mission(d):
    rew_items = d.get("reward_items") or []
    scrip = sum(_num(x.get("amount")) or 0 for x in rew_items if isinstance(x, dict) and "scrip" in
                str(x.get("name", "")).lower())
    danger = (d.get("mission_tokens") or {}).get("Danger") if isinstance(d.get("mission_tokens"), dict) else None
    return {
        "uuid": d.get("uuid"), "title": d.get("title") or d.get("debug_name") or "",
        "type": d.get("mission_type") or _name(d.get("type")) or d.get("reward_scope") or "",
        "giver": d.get("mission_giver") or _name(d.get("faction")) or "",
        "systems": [s for s in (d.get("star_systems") or []) if isinstance(s, str)],
        "reward_min": _num(d.get("reward_min")), "reward_max": _num(d.get("reward_max")),
        "currency": d.get("reward_currency") or "", "scrip": scrip or None,
        "rank": _num(d.get("rank_index")), "illegal": bool(d.get("illegal")),
        "shareable": d.get("shareable"), "minutes": _num(d.get("time_to_complete_minutes")),
        "players": _num(d.get("max_players_per_instance")), "rep": _num(d.get("reputation_amount")),
        "standing": d.get("min_standing_name") or _name(d.get("min_standing")), "danger": ", ".join(danger) if isinstance(danger, list) else "",
        "has_bp": bool(d.get("has_blueprints") or d.get("blueprints")), "web": d.get("web_url") or "",
        "released": d.get("released", True) is not False and not d.get("not_for_release"),
        "wip": bool(d.get("work_in_progress")),
        "bps": mission_blueprints(d), "faction": _name(d.get("faction")) or d.get("mission_giver") or "",
        "min_rep": mission_standing(d)[1],
    }


def tidy_mission(m):
    """Hide placeholders and zero rewards the Wiki sometimes has."""
    if "placeholder" in (m.get("standing") or "").lower():
        m["standing"] = ""
    for k in ("reward_min", "reward_max"):
        if not m.get(k):
            m[k] = None
    if m.get("reward_max") and m.get("reward_min") and m["reward_max"] < m["reward_min"]:
        m["reward_max"] = None
    return m


def mission_locations(d):
    """Place names a mission is offered at or sends you to, from a full mission record."""
    out = []
    ml = d.get("merged_locations")
    if isinstance(ml, dict):
        for v in ml.values():
            for loc in v or []:
                nm = loc.get("name") if isinstance(loc, dict) else str(loc)
                if nm and nm not in out:
                    out.append(nm)
    for grp in d.get("starmap_locations") or []:
        for loc in (grp.get("locations") if isinstance(grp, dict) else None) or []:
            nm = loc.get("name") if isinstance(loc, dict) else str(loc)
            if nm and nm not in out:
                out.append(nm)
    return out


def fetch_missions(cache, progress=None):
    rows = fetch_index("missions", None, progress)
    if rows:
        cache.debug("missions_index", rows[:3])
    out = [tidy_mission(normalize_mission(r)) for r in rows if isinstance(r, dict)]
    out = [m for m in out if m["uuid"] and m["title"] and m["released"] and not m["wip"]]
    cache.save(out)
    return out


def fetch_mission_detail(uuid):
    j = _get(f"{API}/missions/{uuid}")
    return j.get("data", j)


def clean_text(s):
    s = re.sub(r"<[^>]+>", "", s or "")
    s = re.sub(r"~mission\(([^)|]*)(?:\|[^)]*)?\)", lambda m: f"[{m.group(1)}]", s)
    return re.sub(r"\n{3,}", "\n\n", s).strip()
