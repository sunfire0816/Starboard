"""
Refinery jobs for Starboard: what you dropped off, where, and when it is
ready. Stored in user/refining.json.
"""

import json
import os
import re
import time


def parse_duration(text):
    """'2h 15m', '2:15', '2:15:30', '135m', '90' (minutes) -> seconds, or None."""
    t = str(text or "").strip().lower().replace(",", " ")
    if not t:
        return None
    m = re.fullmatch(r"(\d+):(\d{1,2})(?::(\d{1,2}))?", t)
    if m:
        h, mi, s = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
        return h * 3600 + mi * 60 + s
    parts = re.findall(r"(\d+(?:\.\d+)?)\s*(d|h|m|s)", t)
    if parts and re.fullmatch(r"(\s*\d+(?:\.\d+)?\s*[dhms]\w*\s*)+", t):
        mult = {"d": 86400, "h": 3600, "m": 60, "s": 1}
        return int(sum(float(n) * mult[u] for n, u in parts))
    if re.fullmatch(r"\d+(?:\.\d+)?", t):
        return int(float(t) * 60)  # a bare number is minutes
    return None


def fmt_duration(sec):
    sec = max(0, int(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h >= 24:
        d, h = divmod(h, 24)
        return f"{d}d {h}h"
    if h:
        return f"{h}h {m:02d}m"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


class RefineJobs:
    def __init__(self, user_dir):
        self.path = os.path.join(user_dir, "refining.json")
        try:
            with open(self.path, encoding="utf-8") as f:
                self.jobs = json.load(f)
        except Exception:
            self.jobs = []

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.jobs, f, indent=1)
        os.replace(tmp, self.path)

    def add(self, **job):
        jid = str(int(time.time() * 1000))
        while any(j["id"] == jid for j in self.jobs):
            jid = str(int(jid) + 1)
        job.update(id=jid, collected=False, notified=False)
        job.setdefault("started", time.time())
        self.jobs.append(job)
        self.save()
        return job

    def get(self, jid):
        return next((j for j in self.jobs if j["id"] == jid), None)

    def update(self, jid, **kw):
        j = self.get(jid)
        if j:
            j.update(kw)
            self.save()
        return j

    def remove(self, jid):
        self.jobs = [j for j in self.jobs if j["id"] != jid]
        self.save()

    @staticmethod
    def ready_at(j):
        return j["started"] + j["duration"]

    def left(self, j, now=None):
        return self.ready_at(j) - (now or time.time())

    def open_jobs(self):
        return [j for j in self.jobs if not j.get("collected")]

    def newly_ready(self, now=None):
        """Jobs that just finished and have not been announced yet (marks them)."""
        now = now or time.time()
        out = []
        for j in self.open_jobs():
            if not j.get("notified") and self.left(j, now) <= 0:
                j["notified"] = True
                out.append(j)
        if out:
            self.save()
        return out

    @staticmethod
    def ores_text(j):
        return ", ".join(f"{o['scu']:g} {o['ore']}" for o in j.get("ores", []))
