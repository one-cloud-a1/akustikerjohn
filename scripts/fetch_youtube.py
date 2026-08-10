#!/usr/bin/env python3
"""Liest den YouTube-RSS-Feed von Akustiker John und schreibt videos.json.

Wird lokal und von der GitHub Action (scheduled) ausgeführt. Kein API-Key nötig.
Fällt bei Bedarf von der Kanal-ID auf die Handle-Auflösung zurück.
"""
import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone

CHANNEL_ID = "UCFLibbi9xb_a4uBMt9tVcVQ"   # @AkustikerJohn
HANDLE = "AkustikerJohn"
MAX_VIDEOS = 12
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "videos.json")
THUMB_DIR = os.path.join(ROOT, "images", "yt")   # lokal gespiegelte Vorschaubilder (DSGVO)

UA = "Mozilla/5.0 (compatible; AkustikerJohnBot/1.0)"


def _get(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=25).read()


def resolve_channel_id():
    """Falls die feste ID mal nicht mehr passt: aus der Handle-Seite auflösen."""
    try:
        html = _get(
            f"https://www.youtube.com/@{HANDLE}/videos",
            headers={"User-Agent": UA, "Cookie": "CONSENT=YES+cb", "Accept-Language": "de"},
        ).decode("utf-8", "ignore")
        m = re.search(r'"(?:externalId|channelId)":"(UC[0-9A-Za-z_-]{22})"', html)
        if m:
            return m.group(1)
    except Exception as e:  # noqa: BLE001
        print(f"handle resolve failed: {e}", file=sys.stderr)
    return CHANNEL_ID


def fetch_feed(channel_id):
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    data = _get(url)
    ns = {
        "a": "http://www.w3.org/2005/Atom",
        "yt": "http://www.youtube.com/xml/schemas/2015",
        "media": "http://search.yahoo.com/mrss/",
    }
    root = ET.fromstring(data)
    channel = (root.findtext("a:title", default="Akustiker John", namespaces=ns) or "").strip()
    videos = []
    for e in root.findall("a:entry", ns):
        vid = e.findtext("yt:videoId", namespaces=ns)
        title = (e.findtext("a:title", namespaces=ns) or "").strip()
        published = e.findtext("a:published", namespaces=ns)
        if not vid:
            continue
        videos.append({"id": vid, "title": title, "published": published})
    return channel, videos


def mirror_thumbnails(videos):
    """Lädt die Vorschaubilder lokal nach images/yt/ (kein Google-Request beim
    Seitenaufruf). Setzt bei Erfolg das Feld 'thumb' auf den lokalen Pfad und
    entfernt nicht mehr benötigte Bilder."""
    os.makedirs(THUMB_DIR, exist_ok=True)
    keep = set()
    for v in videos:
        vid = v["id"]
        dest = os.path.join(THUMB_DIR, f"{vid}.jpg")
        rel = f"images/yt/{vid}.jpg"
        if not os.path.exists(dest):
            got = False
            for name in ("hqdefault", "mqdefault"):
                try:
                    data = _get(f"https://i.ytimg.com/vi/{vid}/{name}.jpg")
                    if data and len(data) > 1000:
                        with open(dest, "wb") as fh:
                            fh.write(data)
                        got = True
                        break
                except Exception as e:  # noqa: BLE001
                    print(f"thumb {vid} ({name}) fehlgeschlagen: {e}", file=sys.stderr)
            if not got:
                continue
        v["thumb"] = rel
        keep.add(f"{vid}.jpg")
    # Verwaiste Thumbnails aufräumen
    for f in os.listdir(THUMB_DIR):
        if f.endswith(".jpg") and f not in keep:
            try:
                os.remove(os.path.join(THUMB_DIR, f))
            except OSError:
                pass


def main():
    cid = CHANNEL_ID
    try:
        channel, videos = fetch_feed(cid)
        if not videos:
            raise ValueError("leerer Feed")
    except Exception as e:  # noqa: BLE001
        print(f"Primärabruf fehlgeschlagen ({e}), versuche Handle-Auflösung …", file=sys.stderr)
        cid = resolve_channel_id()
        channel, videos = fetch_feed(cid)

    videos = videos[:MAX_VIDEOS]
    mirror_thumbnails(videos)

    payload = {
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "channel": channel,
        "channelUrl": f"https://www.youtube.com/@{HANDLE}",
        "videos": videos,
    }
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"{len(payload['videos'])} Videos geschrieben → {OUT}")


if __name__ == "__main__":
    main()
