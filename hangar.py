"""
My Hangar for Starboard: the ships you own, which one you are flying, and
where each one is parked. Stored in user/hangar.json.
"""

import json
import os
import time


class Hangar:
    def __init__(self, user_dir):
        self.path = os.path.join(user_dir, "hangar.json")
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
        self.ships = data.get("ships", [])
        self.active = data.get("active")

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"ships": self.ships, "active": self.active}, f, indent=1)
        os.replace(tmp, self.path)

    def add(self, ship, setup=None, nickname="", parked=None, note=""):
        sid = str(int(time.time() * 1000))
        while any(s["id"] == sid for s in self.ships):
            sid = str(int(sid) + 1)
        entry = {"id": sid, "ship": ship, "setup": setup, "nickname": nickname, "parked": parked, "note": note}
        self.ships.append(entry)
        if self.active is None:
            self.active = sid
        self.save()
        return entry

    def update(self, sid, **kw):
        s = self.get(sid)
        if s:
            s.update(kw)
            self.save()
        return s

    def remove(self, sid):
        self.ships = [s for s in self.ships if s["id"] != sid]
        if self.active == sid:
            self.active = self.ships[0]["id"] if self.ships else None
        self.save()

    def get(self, sid):
        return next((s for s in self.ships if s["id"] == sid), None)

    def active_ship(self):
        return self.get(self.active) if self.active else None

    def set_active(self, sid):
        if self.get(sid):
            self.active = sid
            self.save()

    @staticmethod
    def label(s):
        return s.get("nickname") or s["ship"]
