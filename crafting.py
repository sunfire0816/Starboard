"""
Blueprints and crafting for Starboard, from the Star Citizen Wiki API
(api.star-citizen.wiki/api/blueprints and /api/missions).

Ties the whole chain together:
  blueprint -> the contracts that can give it (faction, legal or not, reputation needed)
  blueprint -> the materials it needs -> where they are mined -> where to refine them
and back again (a material -> every blueprint that uses it; a faction -> every
blueprint its contracts give).

Please credit api.star-citizen.wiki when sharing Starboard (their request).
"""

import re

import wikidata

def normalize_blueprint(d):
    out = d.get("output") or {}
    ings = []
    for i in d.get("ingredients") or []:
        if not isinstance(i, dict) or not i.get("name"):
            continue
        ings.append({"name": i["name"], "kind": i.get("kind") or "resource",
                     "scu": wikidata._num(i.get("quantity_scu")), "qty": wikidata._num(i.get("quantity"))})
    back = [{"name": i.get("name"), "scu": wikidata._num(i.get("quantity_scu"))}
            for i in d.get("dismantle_returns") or [] if isinstance(i, dict) and i.get("name")]
    return {
        "uuid": d.get("uuid"), "key": d.get("key") or "",
        "name": d.get("output_name") or out.get("name") or d.get("key") or "",
        "cls": d.get("output_class") or out.get("class") or "",
        "type": out.get("type_label") or out.get("type") or "",
        "sub": out.get("sub_type") or "", "grade": out.get("grade") or "",
        "seconds": wikidata._num(d.get("craft_time_seconds")), "time": d.get("craft_time_label") or "",
        "default": bool(d.get("is_available_by_default")),
        "missions_count": int(wikidata._num(d.get("unlocking_missions_count")) or 0),
        "ingredients": ings, "dismantle": back,
        "web": d.get("web_url") or "", "version": d.get("game_version") or "",
    }


def fetch_blueprints(cache, progress=None):
    rows = wikidata.fetch_index("blueprints", None, progress)
    if rows:
        cache.debug("blueprints_index", rows[:2])
    out = [normalize_blueprint(r) for r in rows if isinstance(r, dict)]
    out = [b for b in out if b["uuid"] and b["name"] and "placeholder" not in b["name"].lower()]
    cache.save(out)
    return out


def fetch_blueprint_detail(uuid):
    j = wikidata._get(f"{wikidata.API}/blueprints/{uuid}")
    return j.get("data", j)


mission_blueprints = wikidata.mission_blueprints
standing = wikidata.mission_standing


class Crafting:
    """Blueprints and missions, indexed every way the CRAFT tab needs."""

    def __init__(self, blueprints, missions):
        blueprints = [b for b in blueprints if "placeholder" not in (b.get("name") or "").lower()]
        self.bps = {b["uuid"]: b for b in blueprints}
        self.by_name = {}
        for b in blueprints:
            self.by_name.setdefault(b["name"].lower(), b)
        self.missions = {m["uuid"]: m for m in missions}
        self.bp_missions = {}     # blueprint uuid -> [mission]
        self.factions = {}        # faction name -> [mission] (only missions that give blueprints)
        for m in missions:
            bps = m.get("bps") or []
            for name, uid in bps:
                b = self.bps.get(uid) or self.by_name.get((name or "").lower())
                if b:
                    self.bp_missions.setdefault(b["uuid"], []).append(m)
            if bps:
                self.factions.setdefault(m.get("faction") or m.get("giver") or "Unknown", []).append(m)
        self.materials = {}       # material name -> [blueprint]
        for b in blueprints:
            for i in b["ingredients"]:
                self.materials.setdefault(i["name"], []).append(b)

    def missions_for(self, bp):
        return self.bp_missions.get(bp["uuid"], [])

    def blueprints_of(self, mission):
        out = []
        for name, uid in mission.get("bps") or []:
            b = self.bps.get(uid) or self.by_name.get((name or "").lower())
            out.append(b or {"uuid": None, "name": name})
        return out

    def faction_blueprints(self, faction):
        seen, out = set(), []
        for m in self.factions.get(faction, []):
            for b in self.blueprints_of(m):
                if b.get("uuid") and b["uuid"] not in seen:
                    seen.add(b["uuid"])
                    out.append(b)
        return out

    def types(self):
        return sorted({b["type"] for b in self.bps.values() if b["type"]})

    def search(self, text="", typ=None, show="All", owned=()):
        words = [w for w in (text or "").lower().split() if w]
        owned_l = {o.lower() for o in owned}
        out = []
        for b in self.bps.values():
            hay = (b["name"] + " " + b["type"] + " " + " ".join(i["name"] for i in b["ingredients"])).lower()
            if words and not all(w in hay for w in words):
                continue
            if typ and typ != "All types" and b["type"] != typ:
                continue
            mine = b["name"].lower() in owned_l
            if show == "I own" and not mine:
                continue
            if show == "Not owned yet" and mine:
                continue
            if show == "From contracts" and not self.missions_for(b):
                continue
            if show == "Known from the start" and not b["default"]:
                continue
            out.append(b)
        return sorted(out, key=lambda b: b["name"].lower())


def ore_name(material):
    """The raw ore a refined material comes from, as UEX names it ('Agricium' -> 'Agricium (Ore)')."""
    m = re.sub(r"\s*\((ore|raw)\)\s*$", "", material, flags=re.I)
    return m, f"{m} (Ore)", f"{m} (Raw)"
