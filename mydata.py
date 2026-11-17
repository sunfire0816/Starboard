"""
Starboard's own database (user/starboard.db), built from what you actually do in
the game: the prices you paid and got, the shops and places you visited, the
contracts you took and what they really paid. It fills in where outside sources
(UEX, the Star Citizen Wiki) have gaps, and it keeps working when they are down.

Everything is local. Nothing is sent anywhere.
"""

import os
import re
import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS prices (
    ts REAL, kind TEXT, guid TEXT, name TEXT, shop TEXT, place TEXT, body TEXT,
    unit REAL, qty REAL, total REAL, UNIQUE (ts, kind, total));
CREATE TABLE IF NOT EXISTS names (guid TEXT PRIMARY KEY, name TEXT);
CREATE TABLE IF NOT EXISTS places (
    code TEXT PRIMARY KEY, name TEXT, body TEXT, visits INTEGER, first REAL, last REAL);
CREATE TABLE IF NOT EXISTS shops (shop TEXT PRIMARY KEY, place TEXT, body TEXT, last REAL);
CREATE TABLE IF NOT EXISTS missions (
    mission TEXT PRIMARY KEY, definition TEXT, title TEXT, state TEXT, accepted REAL, ended REAL, place TEXT);
CREATE TABLE IF NOT EXISTS rewards (
    definition TEXT PRIMARY KEY, title TEXT, reward REAL, ts REAL, count INTEGER);
CREATE TABLE IF NOT EXISTS imported (path TEXT PRIMARY KEY, size INTEGER, ts REAL);
CREATE TABLE IF NOT EXISTS blueprints (name TEXT PRIMARY KEY, ts REAL);
"""


class MyData:
    def __init__(self, user_dir):
        self.path = os.path.join(user_dir, "starboard.db")
        os.makedirs(user_dir, exist_ok=True)
        self._lock = threading.RLock()
        self.db = sqlite3.connect(self.path, check_same_thread=False)
        self.db.executescript(SCHEMA)
        self.db.commit()

    def _x(self, sql, args=(), many=False):
        with self._lock:
            cur = self.db.executemany(sql, args) if many else self.db.execute(sql, args)
            return cur

    def commit(self):
        with self._lock:
            self.db.commit()

    def q(self, sql, args=()):
        with self._lock:
            return self.db.execute(sql, args).fetchall()

    # -- writing
    def add_price(self, ts, kind, guid, name, shop, place, body, qty, total):
        unit = total / qty if qty else None
        self._x("INSERT OR IGNORE INTO prices VALUES (?,?,?,?,?,?,?,?,?,?)",
                (round(ts, 3), kind, guid, name, shop, place, body, unit, qty, total))

    def learn_name(self, guid, name):
        if guid and name:
            self._x("INSERT OR REPLACE INTO names VALUES (?,?)", (guid, name))
            self.commit()

    def visit(self, code, name, body, ts):
        self._x("""INSERT INTO places VALUES (?,?,?,1,?,?) ON CONFLICT(code) DO UPDATE SET
                   visits = visits + (CASE WHEN ? - last > 600 THEN 1 ELSE 0 END), last = max(last, ?)""",
                (code, name, body, ts, ts, ts, ts))

    def shop_at(self, shop, place, body, ts):
        if shop and place:
            self._x("INSERT OR REPLACE INTO shops VALUES (?,?,?,?)", (shop, place, body, ts))

    def mission(self, mission, ts, **kw):
        row = self.q("SELECT definition, title, state, accepted, ended, place FROM missions WHERE mission=?",
                     (mission,))
        cur = dict(zip(("definition", "title", "state", "accepted", "ended", "place"), row[0])) if row else {}
        for k, v in kw.items():
            if v is not None and (k not in ("accepted",) or not cur.get(k)):
                cur[k] = v
        self._x("INSERT OR REPLACE INTO missions VALUES (?,?,?,?,?,?,?)",
                (mission, cur.get("definition"), cur.get("title"), cur.get("state"), cur.get("accepted") or ts,
                 cur.get("ended"), cur.get("place")))

    def learn_reward(self, definition, title, reward, ts=None):
        """What a contract really paid (you corrected it in the ledger, or it came from the game)."""
        if not definition or not reward:
            return
        self._x("""INSERT INTO rewards VALUES (?,?,?,?,1) ON CONFLICT(definition) DO UPDATE SET
                   reward = ?, title = ?, ts = ?, count = count + 1""",
                (definition, title, reward, ts or time.time(), reward, title, ts or time.time()))
        self.commit()

    # -- reading
    def reward(self, definition):
        r = self.q("SELECT reward FROM rewards WHERE definition=?", (definition,))
        return r[0][0] if r else None

    def counts(self):
        out = {}
        for t in ("prices", "places", "shops", "missions", "rewards"):
            out[t] = self.q(f"SELECT count(*) FROM {t}")[0][0]
        out["imported"] = self.q("SELECT count(*) FROM imported")[0][0]
        return out

    def price_rows(self, kind_prefix):
        """Latest price per (thing, place, buy/sell): name, kind, place, body, unit, qty, ts, times seen."""
        return self.q("""
            SELECT coalesce(n.name, p.name, p.guid) AS nm, p.kind, p.place, p.body, p.unit, p.qty, max(p.ts), count(*)
            FROM prices p LEFT JOIN names n ON n.guid = p.guid
            WHERE p.kind LIKE ? GROUP BY nm, p.kind, p.place ORDER BY max(p.ts) DESC""", (kind_prefix + "%",))

    def item_prices(self, name):
        return self.q("""
            SELECT p.place, p.unit, p.ts FROM prices p LEFT JOIN names n ON n.guid = p.guid
            WHERE p.kind = 'item' AND lower(coalesce(n.name, p.name)) = lower(?) ORDER BY p.ts DESC""", (name,))

    def places(self):
        return self.q("SELECT name, body, visits, last FROM places ORDER BY last DESC")

    def missions(self):
        return self.q("""
            SELECT m.title, m.state, m.place, m.accepted, r.reward, m.definition FROM missions m
            LEFT JOIN rewards r ON r.definition = m.definition ORDER BY m.accepted DESC""")

    def own_blueprint(self, name, ts):
        """A blueprint you received (from the game log)."""
        if name:
            self._x("INSERT INTO blueprints VALUES (?,?) ON CONFLICT(name) DO UPDATE SET ts = min(ts, ?)",
                    (name, ts, ts))
            self.commit()

    def was_imported(self, path, size):
        r = self.q("SELECT size FROM imported WHERE path=?", (path,))
        return bool(r) and r[0][0] == size

    def mark_imported(self, path, size):
        self._x("INSERT OR REPLACE INTO imported VALUES (?,?,?)", (path, size, time.time()))
        self.commit()


class Recorder:
    """Turns game log events into rows in MyData. One per log file being read,
    because it remembers where you are and which commodities a shop had."""

    def __init__(self, data, names=None):
        self.d = data
        self.names = names if names is not None else {}  # guid -> commodity name, shared with the app
        self.place = self.body = None
        self.handle = None
        self.stock = {}  # shop -> (ts, {commodity})
        self.dirty = 0

    def feed(self, ev):
        t = ev["type"]
        ts = ev["ts"]
        d = self.d
        if t == "handle":
            self.handle = ev["handle"]
        elif t == "location":
            if self.handle and ev["player"] != self.handle:
                return
            self.place, self.body = ev["name"], ev["body"]
            d.visit(ev["code"], ev["name"], ev["body"], ts)
        elif t == "shop_stock":
            s = self.stock.get(ev["shop"])
            if not s or ts - s[0] > 30:
                s = (ts, set())
                self.stock[ev["shop"]] = s
            s[1].add(ev["commodity"])
            d.shop_at(ev["shop"], self.place, self.body, ts)
        elif t == "trade":
            name = self.names.get(ev["guid"])
            s = self.stock.get(ev["shop"])
            if not name and ev["side"] == "buy" and s and len(s[1]) == 1 and ts - s[0] < 120:
                name = next(iter(s[1]))
                self.names[ev["guid"]] = name
                d.learn_name(ev["guid"], name)
            d.add_price(ts, "commodity_" + ev["side"], ev["guid"], name, ev["shop"], self.place, self.body,
                        ev["scu"], ev["amount"])
            d.shop_at(ev["shop"], self.place, self.body, ts)
        elif t == "purchase":
            d.add_price(ts, "item", ev["guid"], ev["item"], ev["shop"], self.place, self.body, ev["qty"],
                        ev["amount"])
            d.shop_at(ev["shop"], self.place, self.body, ts)
        elif t == "tx_error":
            # the purchase just before did not go through
            d._x("DELETE FROM prices WHERE ts >= ? AND ts <= ? AND kind = 'item'", (ts - 10, ts))
        elif t == "contract":
            kw = {"title": ev["title"], "state": ev["state"]}
            if ev["state"] == "Accepted":
                kw["place"] = self.place
            if ev["state"] in ("Complete", "Failed", "Abandoned"):
                kw["ended"] = ts
            d.mission(ev["mission"], ts, **kw)
        elif t == "contract_def":
            d.mission(ev["mission"], ts, definition=ev["definition"])
        elif t == "blueprint":
            d.own_blueprint(ev["item"], ts)
        else:
            return
        self.dirty += 1
        if self.dirty >= 50:
            d.commit()
            self.dirty = 0

    def flush(self):
        self.d.commit()
        self.dirty = 0


def import_logs(data, paths, parse, names=None, progress=None):
    """Read old Game.log backups into the database (prices, places, contracts).
    Files already imported are skipped. Returns (files read, rows before, rows after)."""
    before = data.counts()
    done = 0
    for i, path in enumerate(paths):
        try:
            size = os.path.getsize(path)
        except OSError:
            continue
        if data.was_imported(path, size):
            continue
        rec = Recorder(data, names)
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                for line in f:
                    ev = parse(line)
                    if ev:
                        rec.feed(ev)
        except OSError:
            continue
        rec.flush()
        data.mark_imported(path, size)
        done += 1
        if progress:
            progress(i + 1, len(paths))
    return done, before, data.counts()


def squash(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())
