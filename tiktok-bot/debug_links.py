#!/usr/bin/env python3
import asyncio, json
from TikTokApi import TikTokApi

async def main():
    out=[]
    async with TikTokApi() as api:
        await api.create_sessions(num_sessions=1, sleep_after=3, browser="chromium", headless=True)
        async for video in api.trending.videos(count=10):
            d=video.as_dict
            author=(d.get("author") or {}).get("uniqueId") or ""
            vid=str(d.get("id") or "")
            stats=d.get("stats") or {}
            out.append({
              "id":vid,
              "author":author,
              "desc":d.get("desc",""),
              "views":stats.get("playCount",0),
              "likes":stats.get("diggCount",0),
              "url":f"https://www.tiktok.com/@{author}/video/{vid}" if author and vid else ""
            })
    out.sort(key=lambda x:x["views"] or 0, reverse=True)
    print(json.dumps(out, ensure_ascii=False, indent=2))

asyncio.run(main())
