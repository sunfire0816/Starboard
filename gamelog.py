"""
Game.log reader for Starboard.

Star Citizen writes what happens in a session to Game.log in its install
folder (LIVE, PTU and so on). This module finds that file, follows it while
you play, and turns the lines Starboard cares about into simple events:
logins, servers, where you are, contracts, commodity trades, shop purchases,
your ship, armistice zones and ships you destroy.

It only reads the file. It never touches the game or its memory.
"""

import json
import os
import re
import string
import threading
import time
import urllib.request
from datetime import datetime, timezone

CHANNELS = ("LIVE", "PTU", "EPTU", "HOTFIX", "TECH-PREVIEW")
WIKI = "https://api.star-citizen.wiki/api"
UA = "Starboard (Star Citizen companion)"
NULL_ID = "00000000-0000-0000-0000-000000000000"
UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"


# ------------------------------------------------------------------ finding the log
def candidate_dirs():
    """Folders where a Star Citizen channel folder (LIVE, PTU...) may be."""
    roots = []
    drives = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")] if os.name == "nt" else ["/"]
    for d in drives:
        for sub in ("Program Files\\Roberts Space Industries\\StarCitizen", "Roberts Space Industries\\StarCitizen",
                    "Star Citizen\\StarCitizen", "StarCitizen", "Games\\Roberts Space Industries\\StarCitizen",
                    "Games\\StarCitizen", "Games\\Star Citizen\\StarCitizen", "Program Files\\StarCitizen"):
            roots.append(os.path.join(d, sub))
    # the RSI Launcher's own log names the folders it launched the game from
    appdata = os.environ.get("APPDATA")
    if appdata:
        for name in ("log.log", "main.log"):
            p = os.path.join(appdata, "rsilauncher", "logs", name)
            try:
                with open(p, encoding="utf-8", errors="replace") as f:
                    text = f.read()[-400000:]
                for m in re.finditer(r"([A-Za-z]:[\\/][^\"'\n]*?StarCitizen)[\\/](?:LIVE|PTU|EPTU|HOTFIX|TECH-PREVIEW)",
                                     text):
                    roots.insert(0, m.group(1).replace("/", "\\").replace("\\\\", "\\"))
            except OSError:
                pass
    return roots


def find_logs():
    """Existing Game.log files, newest first, as (path, channel)."""
    seen, out = set(), []
    for root in candidate_dirs():
        for ch in CHANNELS:
            p = os.path.join(root, ch, "Game.log")
            key = os.path.normcase(os.path.abspath(p))
            if key in seen:
                continue
            seen.add(key)
            if os.path.isfile(p):
                out.append((p, ch))
    out.sort(key=lambda t: os.path.getmtime(t[0]), reverse=True)
    return out


# ------------------------------------------------------------------ making names readable
RR = {"ARC_LEO": "Baijini Point", "HUR_LEO": "Everus Harbor", "CRU_LEO": "Seraphim Station",
      "MIC_LEO": "Port Tressler"}
BODY = {"Stanton1": "Hurston", "Stanton1a": "Arial", "Stanton1b": "Aberdeen", "Stanton1c": "Magda",
        "Stanton1d": "Ita", "Stanton2": "Crusader", "Stanton2a": "Cellin", "Stanton2b": "Daymar",
        "Stanton2c": "Yela", "Stanton3": "ArcCorp", "Stanton3a": "Lyria", "Stanton3b": "Wala",
        "Stanton4": "microTech", "Stanton4a": "Calliope", "Stanton4b": "Clio", "Stanton4c": "Euterpe"}
FIXES = {"Area18": "Area18", "NewBabbage": "New Babbage", "RayariHydro": "Rayari", "HurdynMining": "HDMS",
         "HDMSLathan": "Lathan", "ASD": "ASD", "Delve": "Delve", "ArcCorp": "ArcCorp"}


def split_words(s):
    s = re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Za-z])(?=\d)", " ", s)
    return re.sub(r"\s+", " ", s.replace("_", " ")).strip()


# The game's own text (gametext.GameText), set by the app when it can read it.
TEXT = None
MAKERS = ("Aegis", "Anvil", "Aopoa", "Argo", "Banu", "Crusader", "Drake", "Esperia", "Gatac", "Greycat", "Kruger",
          "MISC", "Mirai", "Origin", "RSI", "Tumbril", "Consolidated Outland", "C.O.", "Grey's", "Musashi Industrial",
          "Roberts Space Industries", "Vanduul", "Xi'an")


def place_name(code):
    """'Stanton3_Area18' -> ('Area18', 'ArcCorp'); 'RR_ARC_L1' -> ('ARC-L1 station', 'ArcCorp')."""
    if not code:
        return "", ""
    m = re.match(r"RR_([A-Z]+)_(\w+)$", code)
    if m:
        planet = {"ARC": "ArcCorp", "HUR": "Hurston", "CRU": "Crusader", "MIC": "microTech"}.get(m[1], "")
        key = f"{m[1]}_{m[2]}"
        if key in RR:
            return RR[key], planet
        if TEXT and TEXT.place(code):
            return TEXT.place(code), planet
        if m[1] == "JP":
            return split_words(m[2]).replace("Stanton ", "") + " Gateway", ""
        return f"{m[1]}-{m[2]} station", planet
    m = re.match(r"(Stanton\d[a-d]?)_(.+)$", code)
    if m and TEXT and TEXT.place(code):
        return TEXT.place(code), BODY.get(m[1], m[1])
    if m:
        parts = [FIXES.get(p, p) for p in m[2].split("_")]
        name = " ".join(split_words(p) if p not in FIXES.values() else p for p in parts)
        name = re.sub(r"Facility 0*(\d+)", r"Facility \1", name)
        return name, BODY.get(m[1], m[1])
    return split_words(code), ""


def item_name(cls):
    """'volt_rifle_energy_01_mag' -> 'Parallax Rifle Battery (80 Cap)' from the game's text, else a guess."""
    if TEXT:
        n = TEXT.item(cls)
        if n:
            return n
    words = [w for w in re.split(r"[_\s]+", cls or "") if w and not re.fullmatch(r"\d+|[a-z]\d*|\d+[a-z]", w)]
    return " ".join(w.upper() if len(w) <= 3 and w.isalpha() and w.lower() in ("gg", "cbd", "eld", "rsi", "asd")
                    else w.capitalize() for w in words) or cls


def commodity_name(res):
    """'ResourceType.ProcessedFood' -> 'Processed Food'."""
    return split_words((res or "").split(".")[-1])


def ship_from_class(cls):
    """'RSI_Galaxy_928628549224' -> ('RSI', 'Galaxy')."""
    cls = re.sub(r"_\d{6,}$", "", cls or "")
    full = TEXT.vehicle(cls) if TEXT else None
    if full:
        for mk in MAKERS:
            if full.startswith(mk + " "):
                return mk, full[len(mk) + 1:]
        return "", full
    parts = cls.split("_")
    if len(parts) < 2:
        return "", split_words(cls)
    return parts[0], split_words(" ".join(parts[1:]))


def clean_title(t):
    t = re.sub(r"<[^>]+>", "", t or "")
    t = t.replace("[BP]", "").strip().rstrip(":").strip()
    return re.sub(r"\s+", " ", t)


# ------------------------------------------------------------------ parsing
RE = {
    "ts": re.compile(r"^<(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(?:\.\d+)?)Z?>"),
    "handle": re.compile(r"User Login Success - Handle\[([^\]]+)\]"),
    "character": re.compile(r"<AccountLoginCharacterStatus_Character>.*?geid (\d+).*? name (\S+)"),
    "join": re.compile(r"<Join PU> address\[[^\]]*\] port\[\d+\] shard\[([^\]]+)\]"),
    "quit": re.compile(r"<SystemQuit>"),
    "location": re.compile(r"<RequestLocationInventory> Player\[([^\]]+)\] requested inventory for Location\[([^\]]+)\]"),
    "notify": re.compile(r'<SHUDEvent_OnNotification> Added notification "([^"]*)"(?:.*?MissionId: \[(' + UUID + r')\])?'),
    "marker": re.compile(r"<CLocalMissionPhaseMarker::CreateMarker>.*?missionId \[(" + UUID + r")\].*?generator name \[([^\]]*)\]"
                         r".*?contract \[([^\]]*)\].*?contractDefinitionId\[(" + UUID + r")\]"),
    "end": re.compile(r"<EndMission> .*?MissionId\[(" + UUID + r")\].*?CompletionType\[(\w+)\]"),
    "cbuy": re.compile(r"SendCommodityBuyRequest> .*?shopName\[([^\]]*)\].*?price\[([\d.]+)\].*?resourceGUID\[(" + UUID +
                       r")\].*?quantity\[([\d.]+) ?(cSCU|SCU)?\]"),
    "csell": re.compile(r"SendCommoditySellRequest> .*?shopName\[([^\]]*)\].*?amount\[([\d.]+)\].*?resourceGUID\[(" + UUID +
                        r")\].*?quantity\[([\d.]+) ?(cSCU|SCU)?\]"),
    "cshop": re.compile(r"LoadShopInventoryData.*?shopName\[([^\]]*)\] commodityName\[([^\]]+)\]"),
    "ibuy": re.compile(r"Send(?:Shop|StandardItem)BuyRequest> .*?shopName\[([^\]]*)\].*?client_price\[([\d.]+)\]"
                       r".*?itemClassGUID\[(" + UUID + r")\] itemName\[([^\]]*)\] quantity\[(\d+)\]"
                       r"(?:.*?currencyType\[(\w+)\])?"),
    "ship_free": re.compile(r"<Vehicle Control Flow> .*?releasing control token for '([^']+)'"),
    "route": re.compile(r"<Calculate Route> .*?\| ([A-Z]{3,5}_[A-Za-z0-9_]+?)\[\d+\]\|CSCItemNavigation::CalculateRoute\|"
                        r"Projected Start Location is (\S+)"),
    "vdestroy": re.compile(r"<Vehicle Destroyed> Vehicle '([^']+)' \[\d+\] class '([^']+)' \(owner player \[(\d+)\], "
                           r"driver \[(\d+)\]\) destroyed: reason \[(\w+)\] level \[(\d)\] -> \[(\d)\].*?killer '([^']*)'"),
    "kill": re.compile(r"<Actor Death> CActor::Kill: '([^']+)' \[\d+\] in zone '([^']*)' killed by '([^']+)' \[\d+\] "
                       r"using '([^']*)'"),
}

CONTRACT_STATES = {"Contract Accepted": "Accepted", "Contract Complete": "Complete", "Contract Completed": "Complete",
                   "Contract Failed": "Failed", "Contract Shared": "Shared", "Contract Abandoned": "Abandoned",
                   "Contract Withdrawn": "Abandoned"}
QUIET_NOTICES = ("Medical Device", "Medical Bed", "Multi-Tool", "Optic Attachments", "Clothing & Armor", "Medication",
                 "FPS Mining", "FPS Harvesting", "Salvage -", "Repair -", "Hospitals & Clinics", "Inventory:",
                 "Regeneration - Location", "Quantum Travel:", "New Objective", "Journal Entry", "Contract Available")


def parse_ts(line):
    m = RE["ts"].match(line)
    if not m:
        return None
    try:
        return datetime.fromisoformat(m[1]).replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return None


def parse(line):
    """One Game.log line -> event dict, or None."""
    if "<" not in line:
        return None
    ev = None
    if "Added notification" in line:
        m = RE["notify"].search(line)
        if m:
            text = m[1].strip()
            mid = m[2] if m[2] and m[2] != NULL_ID else None
            head, _, rest = text.partition(":")
            if head in CONTRACT_STATES and mid:
                ev = {"type": "contract", "state": CONTRACT_STATES[head], "title": clean_title(rest), "mission": mid}
            elif head.startswith("Received Blueprint"):
                ev = {"type": "blueprint", "item": clean_title(rest)}
            elif head.startswith("Transaction Error"):
                ev = {"type": "tx_error", "text": clean_title(rest)}
            elif head.startswith("Transaction Complete"):
                ev = {"type": "tx_ok"}
            elif head.startswith("Entering Armistice"):
                ev = {"type": "armistice", "on": True}
            elif head.startswith("Leaving Armistice"):
                ev = {"type": "armistice", "on": False}
            elif head.startswith("Entered ") and "Jurisdiction" in head:
                ev = {"type": "jurisdiction", "name": head[8:].replace(" Jurisdiction", "").strip()}
            elif head.startswith("Incapacitated"):
                ev = {"type": "incap"}
            elif head.startswith("You've earned"):
                ev = {"type": "earned", "item": clean_title(rest or head.replace("You've earned", ""))}
            elif text and not text.startswith(QUIET_NOTICES):
                ev = {"type": "notice", "text": clean_title(text)}
    elif "<RequestLocationInventory>" in line:
        m = RE["location"].search(line)
        if m:
            name, body = place_name(m[2])
            ev = {"type": "location", "player": m[1], "code": m[2], "name": name, "body": body}
    elif "SendCommodityBuyRequest" in line:
        m = RE["cbuy"].search(line)
        if m:
            q = float(m[4]) / (100 if (m[5] or "cSCU") == "cSCU" else 1)
            ev = {"type": "trade", "side": "buy", "shop": m[1], "amount": float(m[2]), "guid": m[3].lower(), "scu": q}
    elif "SendCommoditySellRequest" in line:
        m = RE["csell"].search(line)
        if m:
            q = float(m[4]) / (100 if m[5] == "cSCU" else 1)
            ev = {"type": "trade", "side": "sell", "shop": m[1], "amount": float(m[2]), "guid": m[3].lower(), "scu": q}
    elif "LoadShopInventoryData" in line:
        m = RE["cshop"].search(line)
        if m:
            ev = {"type": "shop_stock", "shop": m[1], "commodity": commodity_name(m[2])}
    elif "BuyRequest>" in line:
        m = RE["ibuy"].search(line)
        if m and (m[6] or "UEC").upper() in ("UEC", "AUEC"):
            ev = {"type": "purchase", "shop": m[1], "amount": float(m[2]), "guid": m[3].lower(),
                  "item": item_name(m[4]), "cls": m[4], "qty": int(m[5])}
    elif "<CLocalMissionPhaseMarker::CreateMarker>" in line:
        m = RE["marker"].search(line)
        if m:
            ev = {"type": "contract_def", "mission": m[1], "generator": m[2], "contract": m[3], "definition": m[4]}
    elif "<EndMission>" in line:
        m = RE["end"].search(line)
        if m:
            ev = {"type": "contract_end", "mission": m[1], "how": m[2]}
    elif "<Join PU>" in line:
        m = RE["join"].search(line)
        ev = {"type": "join", "shard": m[1] if m else ""}
    elif "<SystemQuit>" in line:
        ev = {"type": "quit"}
    elif "User Login Success" in line:
        m = RE["handle"].search(line)
        if m:
            ev = {"type": "handle", "handle": m[1]}
    elif "<AccountLoginCharacterStatus_Character>" in line:
        m = RE["character"].search(line)
        if m:
            ev = {"type": "handle", "handle": m[2], "geid": m[1]}
    elif "<Vehicle Control Flow>" in line:
        m = RE["ship_free"].search(line)
        if m:
            mf, model = ship_from_class(m[1])
            ev = {"type": "ship", "maker": mf, "model": model, "cls": m[1]}
    elif "<Calculate Route>" in line:
        m = RE["route"].search(line)
        if m:
            mf, model = ship_from_class(m[1])
            ev = {"type": "ship", "maker": mf, "model": model, "cls": m[1], "from": m[2]}
    elif "<Vehicle Destroyed>" in line:
        m = RE["vdestroy"].search(line)
        if m:
            mf, model = ship_from_class(m[2])
            model = re.sub(r"\b(PU|AI|CIV|CRIM|SEC|FTL|Template)\b.*$", "", model).strip() or model
            ev = {"type": "destroyed", "ship": f"{mf} {model}".strip(), "owner": m[3], "driver": m[4], "reason": m[5],
                  "final": m[7] == "2", "killer": m[8]}
    elif "<Actor Death>" in line:
        m = RE["kill"].search(line)
        if m:
            ev = {"type": "kill", "victim": m[1], "zone": m[2], "killer": m[3], "weapon": item_name(m[4])}
    if ev is not None:
        ev["ts"] = parse_ts(line) or time.time()
    return ev


# ------------------------------------------------------------------ following the file
class Watcher:
    """Follows one Game.log in a thread. on_event(event, live) is called from
    that thread for every event: first the current session (live=False), then
    each new line as the game writes it (live=True)."""

    POLL = 0.5

    def __init__(self, path, on_event, on_status=None):
        self.path = path
        self.on_event = on_event
        self.on_status = on_status or (lambda s: None)
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True, name="GameLog")
        self._thread.start()

    def stop(self):
        self._stop.set()

    @staticmethod
    def session_start(text):
        """Where the last game launch in this text begins (the file restarts each launch)."""
        i = text.rfind("Log started on")
        return max(0, text.rfind("\n", 0, i) + 1) if i > 0 else 0

    def _emit(self, line, live):
        try:
            ev = parse(line)
        except Exception:
            ev = None
        if ev:
            self.on_event(ev, live)

    def _run(self):
        pos, ino = 0, None
        first = True
        while not self._stop.is_set():
            try:
                st = os.stat(self.path)
            except OSError:
                self.on_status("missing")
                time.sleep(2)
                continue
            key = (st.st_ctime if os.name == "nt" else st.st_ino)
            if ino is not None and (key != ino or st.st_size < pos):
                pos = 0  # the game started a new log
                self.on_status("new session")
            ino = key
            if st.st_size > pos:
                try:
                    with open(self.path, "rb") as f:
                        f.seek(pos)
                        data = f.read(st.st_size - pos)
                except OSError:
                    time.sleep(1)
                    continue
                cut = data.rfind(b"\n")
                if cut < 0:
                    time.sleep(self.POLL)
                    continue
                chunk = data[:cut + 1].decode("utf-8", errors="replace")
                pos += cut + 1
                if first:
                    chunk = chunk[self.session_start(chunk):]
                for line in chunk.splitlines():
                    self._emit(line, live=not first)
                if first:
                    self.on_status("caught up")
                    first = False
            elif first:
                self.on_status("caught up")
                first = False
            self._stop.wait(self.POLL)


# ------------------------------------------------------------------ wiki lookups (cached)
class Lookups:
    """Names and rewards from the Star Citizen Wiki API, cached in
    user/gamelog_cache.json. Calls are made off the UI thread."""

    def __init__(self, user_dir):
        self.path = os.path.join(user_dir, "gamelog_cache.json")
        try:
            with open(self.path, encoding="utf-8") as f:
                self.data = json.load(f)
        except Exception:
            self.data = {}
        for k in ("mission", "commodity", "item"):
            self.data.setdefault(k, {})
        self._lock = threading.Lock()

    def save(self):
        with self._lock:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f)
            os.replace(tmp, self.path)

    def get(self, kind, uuid):
        return self.data[kind].get(uuid)

    def learn(self, kind, uuid, value):
        self.data[kind][uuid] = value
        self.save()

    @staticmethod
    def _fetch(url):
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=12) as r:
            j = json.loads(r.read().decode("utf-8"))
        return j.get("data", j) if isinstance(j, dict) else {}

    def lookup(self, kind, uuid, done):
        """Look a uuid up in the background; done(value or None) runs in that thread."""
        if uuid in self.data[kind]:
            done(self.data[kind][uuid])
            return

        def work():
            value = None
            try:
                path = {"mission": "missions", "commodity": "commodities", "item": "items"}[kind]
                d = self._fetch(f"{WIKI}/{path}/{uuid}")
                if kind == "mission":
                    reward = d.get("reward_min") or d.get("reward") or d.get("reward_max") or 0
                    typ = d.get("mission_type") or d.get("type")
                    if isinstance(typ, dict):
                        typ = typ.get("name") or typ.get("label")
                    locs = []
                    for grp in (d.get("merged_locations") or {}).values() if isinstance(d.get("merged_locations"),
                                                                                       dict) else []:
                        for loc in grp or []:
                            nm = loc.get("name") if isinstance(loc, dict) else str(loc)
                            if nm and nm not in locs:
                                locs.append(nm)
                    value = {"title": d.get("title") or d.get("name") or "", "reward": float(reward or 0),
                             "reward_max": float(d.get("reward_max") or reward or 0), "type": typ or "",
                             "locations": locs[:12], "web": d.get("web_url") or "",
                             "giver": d.get("mission_giver") or ""}
                else:
                    value = {"name": d.get("name") or ""}
            except Exception:
                value = None
            if value is not None:
                self.learn(kind, uuid, value)
            done(value)

        threading.Thread(target=work, daemon=True).start()
