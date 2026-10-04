#!/usr/bin/env python3
import json, math, time, urllib.parse, urllib.request
from pathlib import Path

OUT=Path("tiktok-bot/output")
OUT.mkdir(parents=True,exist_ok=True)
STATE=Path("tiktok-bot/state.json")
FEED="https://www.tikwm.com/api/feed/list"
REGION="GB"
COUNT=20

def get_json(url):
    req=urllib.request.Request(url,headers={
        "User-Agent":"Mozilla/5.0",
        "Accept":"application/json,text/plain,*/*",
        "Referer":"https://www.tikwm.com/"
    })
    with urllib.request.urlopen(req,timeout=45) as r:
        return json.loads(r.read().decode("utf-8","replace"))

def load_state():
    if not STATE.exists():
        return {}
    try:
        return json.loads(STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def n(v):
    try:return int(v or 0)
    except:return 0

def score_video(v, old, now):
    vid=str(v.get("video_id") or v.get("id") or "")
    plays=n(v.get("play_count") or v.get("playCount"))
    likes=n(v.get("digg_count") or v.get("diggCount"))
    shares=n(v.get("share_count") or v.get("shareCount"))
    comments=n(v.get("comment_count") or v.get("commentCount"))
    created=n(v.get("create_time") or v.get("createTime"))
    prev=(old.get("videos") or {}).get(vid)
    # Best measure after first hourly scan: actual view growth since last scan.
    if prev and n(prev.get("play_count")) <= plays:
        dt=max(900, now-n(prev.get("seen_at")))
        delta=plays-n(prev.get("play_count"))
        rate=delta*3600/dt
        return (2, rate + shares*2 + comments*0.5, delta)
    # First scan/new video: estimate current velocity from age plus engagement.
    age_h=max(0.25,(now-created)/3600) if created else 24
    velocity=plays/age_h
    engagement=likes*0.08 + shares*0.8 + comments*0.2
    return (1, velocity+engagement, 0)

def download(url,path):
    req=urllib.request.Request(url,headers={
        "User-Agent":"Mozilla/5.0",
        "Referer":"https://www.tiktok.com/",
        "Accept":"*/*"
    })
    with urllib.request.urlopen(req,timeout=120) as r, open(path,"wb") as f:
        while True:
            b=r.read(1024*1024)
            if not b:break
            f.write(b)

def main():
    url=FEED+"?"+urllib.parse.urlencode({"region":REGION,"count":COUNT})
    data=get_json(url)
    if n(data.get("code")) != 0:
        raise RuntimeError("TikWM feed error: "+str(data.get("msg")))
    items=data.get("data") or []
    if isinstance(items,dict):
        items=items.get("videos") or items.get("data") or []
    if not items:
        raise RuntimeError("Brak popularnych filmów w feedzie TikWM.")

    old=load_state()
    now=int(time.time())
    ranked=[]
    for v in items:
        vid=str(v.get("video_id") or v.get("id") or "")
        play=v.get("play")
        if not vid or not play:
            continue
        s=score_video(v,old,now)
        ranked.append((s,v))
    if not ranked:
        raise RuntimeError("Feed nie zawiera filmów możliwych do pobrania.")
    ranked.sort(key=lambda x:x[0],reverse=True)
    score,best=ranked[0]

    vid=str(best.get("video_id") or best.get("id"))
    author=best.get("author") or {}
    handle=author.get("unique_id") or author.get("uniqueId") or ""
    title=(best.get("title") or best.get("desc") or "").strip()
    source=f"https://www.tiktok.com/@{handle}/video/{vid}" if handle else f"https://www.tiktok.com/video/{vid}"

    out={
        "type":"viral_video",
        "video_id":vid,
        "author":handle,
        "title":title,
        "source_url":source,
        "play_count":n(best.get("play_count") or best.get("playCount")),
        "digg_count":n(best.get("digg_count") or best.get("diggCount")),
        "share_count":n(best.get("share_count") or best.get("shareCount")),
        "comment_count":n(best.get("comment_count") or best.get("commentCount")),
        "create_time":n(best.get("create_time") or best.get("createTime")),
        "selection_mode":"hourly_delta" if score[0]==2 else "current_velocity_estimate",
        "hourly_view_delta":score[2],
        "region":REGION,
        "selected_at":now
    }
    (OUT/"trend.json").write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    caption=(title[:700]+"\n\nAI animal remix • source: "+source+"\n#tiktoktrend #viral #animal #airemix").strip()
    (OUT/"caption.txt").write_text(caption,encoding="utf-8")

    # save current snapshot for next hourly comparison
    snap={"seen_at":now,"videos":{}}
    for v in items:
        x=str(v.get("video_id") or v.get("id") or "")
        if x:
            snap["videos"][x]={
                "play_count":n(v.get("play_count") or v.get("playCount")),
                "seen_at":now
            }
    STATE.write_text(json.dumps(snap,ensure_ascii=False,indent=2),encoding="utf-8")

    download(best["play"],OUT/"source.mp4")
    print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
