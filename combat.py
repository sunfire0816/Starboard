"""
Combat for Starboard: bounty contracts you take (stored in
user/bounties.json) and which places are security, outlaw or hostile.
"""

import json
import os
import time

RANKS = [("VLRT", "very low risk"), ("LRT", "low risk"), ("MRT", "medium risk"), ("HRT", "high risk"),
         ("VHRT", "very high risk"), ("ERT", "extreme risk"), ("Other", "")]
RANK_LABELS = [f"{r} ({d})" if d else r for r, d in RANKS]

ZONES = {
    "Security": "UEE or corporate security. Safe to land, guards may help or shoot at you if you are wanted.",
    "Outlaw stations": "Stations where criminals can land, rearm and clear crimes. Expect players looking for fights.",
    "Outlaw hideouts": "Forward operating bases, derelict settlements and ruins, often held by armed NPCs or players.",
    "Bunkers and facilities": "Underground bunkers, Onyx facilities and labs used by mercenary and bounty missions.",
}
SECURITY_TYPES = {"Security Centre", "Security Post", "Security Outpost", "Prison"}
HIDEOUT_TYPES = {"Forward operating base", "Derelict Settlement", "Derelict settlement", "Ruins", "Drug Lab",
                 "Stash House"}
FACILITY_TYPES = {"Underground bunker", "Underground Facility", "Onyx Facility", "Creature Lab", "Research Lab"}
OUTLAW_STATIONS = {"grimhex", "ruin station", "checkmate", "orbituary", "jumptown"}
LAWLESS_SYSTEMS = {"Pyro", "Nyx"}


def zone_of(loc):
    """Which combat zone group a location belongs to, or None."""
    n = loc.name.lower()
    if loc.type in SECURITY_TYPES:
        return "Security"
    if n in OUTLAW_STATIONS or (loc.star in LAWLESS_SYSTEMS and loc.type in ("Space station", "Space Station",
                                                                             "Asteroid base")):
        return "Outlaw stations"
    if loc.type in HIDEOUT_TYPES:
        return "Outlaw hideouts"
    if loc.type in FACILITY_TYPES:
        return "Bunkers and facilities"
    return None


class Bounties:
    def __init__(self, user_dir):
        self.path = os.path.join(user_dir, "bounties.json")
        try:
            with open(self.path, encoding="utf-8") as f:
                self.items = json.load(f)
        except Exception:
            self.items = []

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.items, f, indent=1)
        os.replace(tmp, self.path)

    def add(self, **b):
        bid = str(int(time.time() * 1000))
        while any(x["id"] == bid for x in self.items):
            bid = str(int(bid) + 1)
        b.update(id=bid, status="Active", added=time.time())
        self.items.append(b)
        self.save()
        return b

    def get(self, bid):
        return next((x for x in self.items if x["id"] == bid), None)

    def update(self, bid, **kw):
        b = self.get(bid)
        if b:
            b.update(kw)
            self.save()
        return b

    def remove(self, bid):
        self.items = [x for x in self.items if x["id"] != bid]
        self.save()

    def stats(self, since=0):
        done = [b for b in self.items if b["status"] == "Done" and b.get("finished", 0) >= since]
        earned = sum(float(b.get("reward") or 0) for b in done)
        return {"active": sum(1 for b in self.items if b["status"] == "Active"), "done": len(done),
                "failed": sum(1 for b in self.items if b["status"] == "Failed" and b.get("finished", 0) >= since),
                "earned": earned, "average": earned / len(done) if done else 0}
