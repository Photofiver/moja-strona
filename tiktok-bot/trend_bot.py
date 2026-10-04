#!/usr/bin/env python3
import asyncio
import json
import os
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path("tiktok-bot/output")
OUT.mkdir(parents=True, exist_ok=True)
TOKEN = os.environ.get("TIKTOK_MS_TOKEN", "").strip()
CREATIVE_URL = "https://ads.tiktok.com/creative/creativeCenter/trends/hashtag?period=7&region=GB"

def clean(s):
    s = re.sub(r"https?://\S+", "", s or "")
    s = re.sub(r"\s+", " ", s).strip()
    return s

async def real_tiktok_trend():
    if not TOKEN:
        return None
    from TikTokApi import TikTokApi
    items = []
    async with TikTokApi() as api:
        await api.create_sessions(
            ms_tokens=[TOKEN],
            num_sessions=1,
            sleep_after=4,
            headless=False,
            browser="chromium",
        )
        async for video in api.trending.videos(count=24):
            v = video.as_dict
            stats = v.get("stats") or {}
            author = v.get("author") or {}
            vid = str(v.get("id") or "")
            handle = author.get("uniqueId") or ""
            desc = clean(v.get("desc") or "")
            if not vid or not handle:
                continue
            items.append({
                "type": "video",
                "id": vid,
                "author": handle,
                "description": desc,
                "views": int(stats.get("playCount") or 0),
                "likes": int(stats.get("diggCount") or 0),
                "shares": int(stats.get("shareCount") or 0),
                "source_url": f"https://www.tiktok.com/@{handle}/video/{vid}",
                "source": "TikTok trending feed",
            })
    if not items:
        return None
    items.sort(key=lambda x: (x["views"], x["likes"], x["shares"]), reverse=True)
    return items[0]

def creative_center_fallback():
    proxy = "https://r.jina.ai/" + CREATIVE_URL
    req = urllib.request.Request(proxy, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=45) as r:
        body = r.read().decode("utf-8", "replace")
    tags = re.findall(r"#[A-Za-z0-9_ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]+", body)
    if not tags:
        raise RuntimeError("Nie udało się pobrać trendu z TikTok Creative Center.")
    tag = tags[0]
    return {
        "type": "hashtag",
        "description": tag,
        "views": 0,
        "likes": 0,
        "shares": 0,
        "source_url": CREATIVE_URL,
        "source": "TikTok Creative Center fallback",
    }

def topic_from(trend):
    text = clean(trend.get("description", ""))
    text = re.sub(r"#[A-Za-z0-9_ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]+", "", text).strip()
    if not text:
        text = clean(trend.get("description", "")) or "ten trend"
    return text[:95]

def build_script(trend):
    topic = topic_from(trend)
    seed = sum(ord(c) for c in topic) % 6
    animals = ["kot", "pies", "kot", "pies", "kot", "pies"]
    animal = animals[seed]
    if animal == "kot":
        templates = [
            f"Wszyscy na TikToku gadają teraz o: {topic}. Ja też sprawdziłem. I mam jedno pytanie: gdzie jest moja kolacja?",
            f"Podobno teraz viralem jest: {topic}. Jako profesjonalny kot potwierdzam: internet znowu zachowuje się dziwnie.",
            f"Zobaczyłem trend o: {topic}. Ludzie mają miliony wyświetleń, a ja nadal nie mam dostępu do lodówki. Skandal.",
        ]
    else:
        templates = [
            f"Na TikToku leci teraz: {topic}. Obejrzałem i szczerze? Dałbym temu dziesięć smaczków na dziesięć.",
            f"Wszyscy oglądają teraz: {topic}. Ja jestem psem i nie rozumiem wszystkiego, ale jeśli jest zabawa, wchodzę.",
            f"Trend dnia to: {topic}. Sprawdziłem go za was. Werdykt: ciekawe, ale czy ktoś powiedział spacer?",
        ]
    line = templates[seed % len(templates)]
    return animal, line, topic

def main():
    if os.environ.get("TIKTOK_TEST_MODE") == "1":
        trend = {
            "type": "test",
            "description": "Test: pies komentuje viralowy trend",
            "views": 0,
            "likes": 0,
            "shares": 0,
            "source_url": "",
            "source": "TEST — bez pobierania TikToka",
        }
    else:
        if not TOKEN:
            raise RuntimeError("Brak sekretu TIKTOK_MS_TOKEN — bot nie będzie udawał prawdziwego popularnego filmu.")
        trend = asyncio.run(real_tiktok_trend())
        if trend is None:
            raise RuntimeError("TikTok nie zwrócił żadnego popularnego filmu.")

    animal, script, topic = build_script(trend)
    trend["animal"] = animal
    trend["topic"] = topic
    trend["script"] = script
    trend["generated_at_utc"] = datetime.now(timezone.utc).isoformat()

    caption = f"{topic} — wersja ze zwierzakiem. #tiktoktrend #viral #ai #{'kot' if animal=='kot' else 'pies'}"
    (OUT/"narration.txt").write_text(script, encoding="utf-8")
    (OUT/"caption.txt").write_text(caption[:2200], encoding="utf-8")
    (OUT/"trend.json").write_text(json.dumps(trend, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(trend, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
