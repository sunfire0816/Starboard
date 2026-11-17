"""
Shop finder for Starboard: where to buy any item, buy or rent a ship, buy
fuel, and which refinery gives the best yield. All from the UEX cache that
hauling.download() fills (user/uex/*.json).
"""

import time

from hauling import _load, _num

SHIPS_BUY = "Ships to buy"
SHIPS_RENT = "Ships to rent"
FUEL = "Fuel"
REFINING = "Refinery yields"
SPECIAL = [SHIPS_BUY, SHIPS_RENT, FUEL, REFINING]


class Product:
    """One thing you can buy (an item, a ship, fuel) or refine (an ore)."""

    def __init__(self, name, category, kind):
        self.name = name
        self.category = category
        self.kind = kind          # item / buy / rent / fuel / refine
        self.offers = []          # (terminal, value, age_days)

    def best(self):
        """Cheapest offer, or for refining the best yield."""
        if not self.offers:
            return None
        if self.kind == "refine":
            return max(self.offers, key=lambda o: o[1])
        return min(self.offers, key=lambda o: o[1])


class ShopData:
    def __init__(self, trade):
        self.trade = trade
        self.products = {}        # (kind, name) -> Product
        self.methods = []
        self.loaded = False
        self.reload()

    def _age(self, row, now):
        t = _num(row.get("date_modified"))
        return (now - t) / 86400 if t else None

    def _add(self, kind, name, category, row, value, now):
        term = self.trade.terminals.get(row.get("id_terminal"))
        if term is None or not name or value <= 0 or not term.available:
            return
        key = (kind, name)
        p = self.products.get(key)
        if p is None:
            p = self.products[key] = Product(name, category, kind)
        p.offers.append((term, value, self._age(row, now)))

    def reload(self):
        ud = self.trade.user_dir
        now = time.time()
        self.products = {}
        cats = {c.get("id"): (c.get("section") or "", c.get("name") or "") for c in _load(ud, "categories")}
        for r in _load(ud, "items_prices"):
            sec, cat = cats.get(r.get("id_category"), ("", ""))
            label = f"{sec} › {cat}" if sec and cat and sec != cat else (cat or sec or "Other")
            self._add("item", r.get("item_name"), label, r, _num(r.get("price_buy")), now)
        ships = {v.get("id"): v.get("name_full") or v.get("name") for v in self.trade.vehicles_raw}
        for r in _load(ud, "ship_buy"):
            self._add("buy", ships.get(r.get("id_vehicle")) or r.get("vehicle_name"), SHIPS_BUY, r,
                      _num(r.get("price_buy")), now)
        for r in _load(ud, "ship_rent"):
            self._add("rent", ships.get(r.get("id_vehicle")) or r.get("vehicle_name"), SHIPS_RENT, r,
                      _num(r.get("price_rent")), now)
        for r in _load(ud, "fuel"):
            self._add("fuel", r.get("commodity_name"), FUEL, r, _num(r.get("price_buy")), now)
        for r in _load(ud, "refinery_yields"):
            term = self.trade.terminals.get(r.get("id_terminal"))
            name = r.get("commodity_name")
            if term is None or not name:
                continue
            p = self.products.setdefault(("refine", name), Product(name, REFINING, "refine"))
            p.offers.append((term, _num(r.get("value")), self._age(r, now)))
        self.methods = _load(ud, "refinery_methods")
        self.loaded = bool(self.products)

    def categories(self):
        cats = sorted({p.category for p in self.products.values() if p.category not in SPECIAL})
        return [c for c in SPECIAL if any(p.category == c for p in self.products.values())] + cats

    def search(self, text="", category=None, system=None):
        words = text.lower().split()
        out = []
        for p in self.products.values():
            if category and p.category != category:
                continue
            if words and not all(w in p.name.lower() or w in p.category.lower() for w in words):
                continue
            offers = [o for o in p.offers if not system or o[0].system == system]
            if offers:
                out.append((p, offers))
        return out

    def find(self, kind, name):
        return self.products.get((kind, name))
