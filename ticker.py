"""Data for Starboard's two ticker tapes.

Market: the average price terminals pay for each commodity (UEX data), and how it
moved since about a day ago. Starboard keeps a small price history in
user/uex/price_history.json, one entry per price download. Until there is an
older entry to compare with, the change is against UEX's own average price.

News, newest first, from three official sources:
- RSI server status (status.robertsspaceindustries.com, its index.json and RSS feed):
  whether the servers are up, plus incidents and live patch deployments.
- RSI's Star Citizen YouTube channel (YouTube's public channel feed): new videos.
- Comm-Link posts through the Star Citizen Wiki API (api.star-citizen.wiki), which can
  run a week or two behind RSI.
Cached in user/wiki/news.json.
"""

import html
import json
import os
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

NEWS_URL = "https://api.star-citizen.wiki/api/comm-links"
YT_URL = "https://www.youtube.com/feeds/videos.xml?channel_id=UCTeLqJq1mXUX5WWoNXLmOIA"  # RSI's channel
STATUS_URL = "https://status.robertsspaceindustries.com/"
UA = "Starboard (Star Citizen companion; free, non-commercial)"
DAY = 86400
KEEP = 40  # price history entries kept


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def commodity_prices(prices):
    """{commodity: (average sell price now, UEX average sell price)} over terminals that buy it."""
    acc = {}
    for p in prices or []:
        name = (p.get("commodity_name") or "").strip()
        now = _num(p.get("price_sell"))
        if not name or now <= 0:
            continue
        usual = _num(p.get("price_sell_avg")) or now
        a = acc.setdefault(name, [0.0, 0.0, 0])
        a[0] += now
        a[1] += usual
        a[2] += 1
    return {k: (v[0] / v[2], v[1] / v[2]) for k, v in acc.items()}


def _hist_path(user_dir):
    return os.path.join(user_dir, "uex", "price_history.json")


def load_history(user_dir):
    try:
        with open(_hist_path(user_dir), encoding="utf-8") as f:
            h = json.load(f)
        return h if isinstance(h, list) else []
    except Exception:
        return []


def record(user_dir, stamp, cur):
    """Add today's prices to the history once per download (stamp = download time)."""
    hist = load_history(user_dir)
    if not cur or (hist and abs(hist[-1].get("ts", 0) - stamp) < 1):
        return hist
    hist.append({"ts": stamp, "p": {k: round(v[0], 2) for k, v in cur.items()}})
    hist = hist[-KEEP:]
    try:
        os.makedirs(os.path.dirname(_hist_path(user_dir)), exist_ok=True)
        tmp = _hist_path(user_dir) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(hist, f)
        os.replace(tmp, _hist_path(user_dir))
    except OSError:
        pass
    return hist


def changes(cur, hist, now_ts=None, limit=60):
    """[(commodity, price, percent change, basis)] with the biggest moves first.

    basis is "24h" (against the newest entry at least ~20 hours old), "last" (against the
    previous download) or "avg" (against the UEX average)."""
    now_ts = now_ts or (hist[-1]["ts"] if hist else time.time())
    older = [h for h in hist if h.get("ts", 0) <= now_ts - DAY * 0.83]
    day_ref = older[-1]["p"] if older else None
    prev_ref = hist[-2]["p"] if len(hist) >= 2 else None
    out = []
    for name, (price, usual) in cur.items():
        if day_ref and day_ref.get(name):
            ref, basis = day_ref[name], "24h"
        elif prev_ref and prev_ref.get(name):
            ref, basis = prev_ref[name], "last"
        else:
            ref, basis = usual, "avg"
        pct = (price - ref) / ref * 100 if ref else 0.0
        out.append((name, price, pct, basis))
    out.sort(key=lambda r: (-abs(r[2]), r[0]))
    return out[:limit]


def fetch_news(timeout=20):
    """Newest Comm-Link posts: [{title, url, date, channel}]."""
    req = urllib.request.Request(NEWS_URL, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = json.loads(r.read().decode("utf-8")).get("data") or []
    out = []
    for d in data:
        t = (d.get("title") or "").strip()
        if t:
            out.append({"title": t, "url": d.get("rsi_url") or "", "date": (d.get("created_at") or "")[:10],
                        "channel": d.get("channel") or "", "series": d.get("series") or ""})
    return out


def _fetch(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def fetch_videos(timeout=20):
    """Newest videos on RSI's YouTube channel: [{title, url, date, ts, kind}]. Shorts that repeat
    a full video's title are left out."""
    ns = {"a": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(_fetch(YT_URL, timeout))
    out, seen = [], set()
    entries = root.findall("a:entry", ns)
    full = {(e.findtext("a:title", "", ns) or "").strip() for e in entries
            if "/shorts/" not in (e.find("a:link", ns).get("href") if e.find("a:link", ns) is not None else "")}
    for e in entries:
        t = (e.findtext("a:title", "", ns) or "").strip()
        link = e.find("a:link", ns)
        url = link.get("href") if link is not None else ""
        if not t or ("/shorts/" in url and t in full) or t in seen:
            continue
        seen.add(t)
        pub = e.findtext("a:published", "", ns)
        try:
            ts = time.mktime(time.strptime(pub[:19], "%Y-%m-%dT%H:%M:%S")) - time.timezone
        except ValueError:
            ts = 0
        out.append({"title": re.sub(r"^Star Citizen\s*\|\s*", "", t), "url": url, "date": pub[:10], "ts": ts,
                    "kind": "video"})
    return out


def _clean_html(text):
    text = re.sub(r"<!--.*?-->", " ", text or "", flags=re.S)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def fetch_status(timeout=20):
    """RSI server status: {"summary": "operational"|"disrupted"|"down", "systems": [(name, status)],
    "incidents": [{title, url, date, ts, kind, text, resolved}]}."""
    j = json.loads(_fetch(STATUS_URL + "index.json", timeout).decode("utf-8"))
    systems = [(s.get("name", ""), s.get("status", "")) for s in j.get("systems") or []]
    incidents = []
    try:
        root = ET.fromstring(_fetch(STATUS_URL + "index.xml", timeout))
        for it in root.iter("item"):
            title = (it.findtext("title") or "").strip()
            resolved = title.startswith("[Resolved]")
            title = re.sub(r"^\[[^\]]*\]\s*", "", title)
            text = _clean_html(it.findtext("description"))
            first = re.split(r"(?<=[.!])\s", text, 1)[0] if text else ""
            first = re.sub(r"-live\.\d+", "", first).replace("🚀", "").strip()
            try:
                dt = parsedate_to_datetime(it.findtext("pubDate") or "")
                ts, date = dt.timestamp(), dt.strftime("%Y-%m-%d")
            except (TypeError, ValueError):
                ts, date = 0, ""
            incidents.append({"title": f"{title}: {first}" if first else title, "url": it.findtext("link") or "",
                              "date": date, "ts": ts, "kind": "server", "resolved": resolved})
    except Exception:  # noqa: BLE001
        pass
    return {"summary": j.get("summaryStatus") or "", "systems": systems, "incidents": incidents}


def fetch_all(timeout=20):
    """Everything for the NEWS ticker. Each source is optional; returns (items, status or None, errors)."""
    items, errors, status = [], [], None
    try:
        status = fetch_status(timeout)
        items += [i for i in status["incidents"] if time.time() - i["ts"] < 14 * DAY or not i["resolved"]][:4]
    except Exception as e:  # noqa: BLE001
        errors.append(f"status: {e.__class__.__name__}")
    try:
        items += fetch_videos(timeout)[:10]
    except Exception as e:  # noqa: BLE001
        errors.append(f"youtube: {e.__class__.__name__}")
    try:
        for n in fetch_news(timeout)[:12]:
            try:
                n["ts"] = time.mktime(time.strptime(n["date"], "%Y-%m-%d")) - time.timezone
            except ValueError:
                n["ts"] = 0
            n["kind"] = "post"
            items.append(n)
    except Exception as e:  # noqa: BLE001
        errors.append(f"wiki: {e.__class__.__name__}")
    items.sort(key=lambda i: -i.get("ts", 0))
    return items, status, errors


NEWS_DAYS = 14   # the NEWS ticker shows today and the 14 days before it


def recent(items, days=NEWS_DAYS, today=None):
    """Only news from today and the last `days` days (by local date). Server problems
    that are still open stay, however old."""
    import datetime as _dt
    today = today or _dt.date.today()
    first = (today - _dt.timedelta(days=days)).isoformat()
    out = []
    for i in items:
        if i.get("kind") == "server" and i.get("resolved") is False:
            out.append(i)
            continue
        d = i.get("date") or (time.strftime("%Y-%m-%d", time.localtime(i["ts"])) if i.get("ts") else "")
        if d and d >= first:
            out.append(i)
    return out


def news_path(user_dir):
    return os.path.join(user_dir, "wiki", "news.json")


def load_news(user_dir):
    try:
        with open(news_path(user_dir), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"ts": 0, "items": []}


def save_news(user_dir, items, status=None):
    try:
        os.makedirs(os.path.dirname(news_path(user_dir)), exist_ok=True)
        with open(news_path(user_dir), "w", encoding="utf-8") as f:
            json.dump({"ts": time.time(), "items": items, "status": status}, f)
    except OSError:
        pass
