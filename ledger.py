"""
Ledger for Starboard: every purchase and every payout, with a running balance.

Entries live in user/ledger.json. Amounts are aUEC; income is positive,
spending is negative. A balance check-in (SET BALANCE) adds an adjustment
so the running balance matches your in-game wallet.
"""

import csv
import datetime as dt
import json
import os
import re
import time

INCOME = "Income"
EXPENSE = "Expense"
ADJUST = "Adjustment"

INCOME_CATEGORIES = ["Trade sale", "Contract payout", "Mining sale", "Salvage sale", "Bounty",
                     "Mission reward", "Item sale", "Transfer in", "Other income"]
EXPENSE_CATEGORIES = ["Trade purchase", "Fuel", "Repairs and restock", "Ammunition", "Ship purchase",
                      "Ship rental", "Ship insurance claim", "Item purchase", "Refining", "Fines",
                      "Hangar fees", "Transfer out", "Other expense"]
ALL_CATEGORIES = INCOME_CATEGORIES + EXPENSE_CATEGORIES

PERIODS = ["Today", "Last 7 days", "Last 30 days", "All time"]


def parse_amount(text):
    """'12,500', '12.5k', '1.2m', '-300' -> float (None if not a number)."""
    t = str(text or "").strip().lower().replace(",", "").replace(" ", "").replace("auec", "")
    if not t:
        return None
    m = re.fullmatch(r"([-+]?\d*\.?\d+)([km]?)", t)
    if not m:
        return None
    v = float(m.group(1))
    return v * {"k": 1e3, "m": 1e6}.get(m.group(2), 1)


def money(v, signed=False):
    s = f"{abs(v):,.0f}"
    if signed:
        return ("+" if v >= 0 else "-") + s
    return ("-" if v < 0 else "") + s


def short_money(v):
    a = abs(v)
    s = f"{a / 1e6:.2f}M" if a >= 1e6 else f"{a / 1e3:.1f}k" if a >= 1e4 else f"{a:,.0f}"
    return ("-" if v < 0 else "") + s


class Ledger:
    def __init__(self, user_dir):
        self.path = os.path.join(user_dir, "ledger.json")
        try:
            with open(self.path, encoding="utf-8") as f:
                self.entries = json.load(f)
        except Exception:
            self.entries = []
        self._next = max([int(e.get("id", 0)) for e in self.entries] + [0]) + 1

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.entries, f, indent=1)
        os.replace(tmp, self.path)

    # -- editing
    def add(self, kind, category, amount, note="", where="", when=None, estimate=False, source=""):
        """amount is the size (positive); kind decides the sign. Returns the entry."""
        amount = abs(float(amount)) if kind != ADJUST else float(amount)
        e = {"id": self._next, "time": when or time.time(), "kind": kind, "category": category,
             "amount": -amount if kind == EXPENSE else amount, "note": note, "where": where}
        if estimate:
            e["estimate"] = True
        if source:
            e["source"] = source
        self._next += 1
        self.entries.append(e)
        self.entries.sort(key=lambda x: x["time"])
        self.save()
        return e

    def update(self, eid, **kw):
        for e in self.entries:
            if e["id"] == eid:
                if "kind" in kw or "amount" in kw:
                    kind = kw.get("kind", e["kind"])
                    amt = float(kw.get("amount", e["amount"]))
                    if kind != ADJUST:
                        amt = -abs(amt) if kind == EXPENSE else abs(amt)
                    kw["amount"] = amt
                e.update(kw)
                e.pop("estimate", None)  # you checked it, so it is no longer a guess
                self.entries.sort(key=lambda x: x["time"])
                self.save()
                return e
        return None

    def delete(self, eid):
        self.entries = [e for e in self.entries if e["id"] != eid]
        self.save()

    def get(self, eid):
        return next((e for e in self.entries if e["id"] == eid), None)

    # -- reading
    def balance(self):
        return sum(e["amount"] for e in self.entries)

    def has_balance(self):
        return any(e["kind"] == ADJUST for e in self.entries)

    def running(self):
        """[(entry, balance after it)] oldest first."""
        out, bal = [], 0.0
        for e in self.entries:
            bal += e["amount"]
            out.append((e, bal))
        return out

    def set_balance(self, actual, where=""):
        """Add an adjustment so the running balance equals what the game shows."""
        diff = float(actual) - self.balance()
        if abs(diff) < 0.5:
            return None
        first = not self.has_balance()
        return self.add(ADJUST, "Starting balance" if first else "Balance check", diff,
                        note=f"Wallet showed {money(actual)} aUEC", where=where)

    @staticmethod
    def period_start(period, now=None):
        now = now or time.time()
        if period == "Today":
            d = dt.datetime.fromtimestamp(now).replace(hour=0, minute=0, second=0, microsecond=0)
            return d.timestamp()
        days = {"Last 7 days": 7, "Last 30 days": 30}.get(period)
        return now - days * 86400 if days else 0

    def in_period(self, period):
        start = self.period_start(period)
        return [e for e in self.entries if e["time"] >= start]

    def totals(self, period="All time"):
        inc = sum(e["amount"] for e in self.in_period(period) if e["kind"] == INCOME)
        exp = -sum(e["amount"] for e in self.in_period(period) if e["kind"] == EXPENSE)
        return {"income": inc, "spent": exp, "net": inc - exp}

    def by_category(self, period="All time"):
        cats = {}
        for e in self.in_period(period):
            if e["kind"] == ADJUST:
                continue
            cats[(e["kind"], e["category"])] = cats.get((e["kind"], e["category"]), 0.0) + e["amount"]
        return cats

    def export_csv(self, path):
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["date", "time", "type", "category", "amount_auec", "balance_auec", "note", "where",
                        "estimate"])
            for e, bal in self.running():
                d = dt.datetime.fromtimestamp(e["time"])
                w.writerow([d.strftime("%Y-%m-%d"), d.strftime("%H:%M"), e["kind"], e["category"],
                            round(e["amount"], 2), round(bal, 2), e.get("note", ""), e.get("where", ""),
                            "yes" if e.get("estimate") else ""])
