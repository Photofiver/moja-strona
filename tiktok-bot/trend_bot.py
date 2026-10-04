#!/usr/bin/env python3
import json, os, re, subprocess, time, urllib.parse, urllib.request
from pathlib import Path
import cv2
from faster_whisper import WhisperModel

OUT=Path("tiktok-bot/output")
OUT.mkdir(parents=True,exist_ok=True)
STATE=Path("tiktok-bot/state.json")
FEED="https://www.tikwm.com/api/feed/list"
REGIONS=["GB","US"]
COUNT=50
MAX_CANDIDATES=24
TMP=OUT/"candidate.mp4"
WAV=OUT/"candidate.wav"

BLOCKED=re.compile(r"\b(baby|babies|toddler|kid|kids|child|children|toy|toys|cartoon|roblox|minecraft|fortnite|monkey|gorilla|ape)\b",re.I)

def get_json(url):
    req=urllib.request.Request(url,headers={
        "User-Agent":"Mozilla/5.0",
        "Accept":"application/json,text/plain,*/*",
        "Referer":"https://www.tikwm.com/"
    })
    with urllib.request.urlopen(req,timeout=45) as r:
        return json.loads(r.read().decode("utf-8","replace"))

def load_state():
    if not STATE.exists(): return {}
    try:return json.loads(STATE.read_text(encoding="utf-8"))
    except:return {}

def n(v):
    try:return int(v or 0)
    except:return 0

def score_video(v,old,now):
    vid=str(v.get("video_id") or v.get("id") or "")
    plays=n(v.get("play_count") or v.get("playCount"))
    likes=n(v.get("digg_count") or v.get("diggCount"))
    shares=n(v.get("share_count") or v.get("shareCount"))
    comments=n(v.get("comment_count") or v.get("commentCount"))
    created=n(v.get("create_time") or v.get("createTime"))
    prev=(old.get("videos") or {}).get(vid)
    if prev and n(prev.get("play_count")) <= plays:
        dt=max(900,now-n(prev.get("seen_at")))
        delta=plays-n(prev.get("play_count"))
        rate=delta*3600/dt
        return (2,rate + shares*2 + comments*0.5,delta)
    age_h=max(0.25,(now-created)/3600) if created else 24
    velocity=plays/age_h
    engagement=likes*0.08+shares*0.8+comments*0.2
    return (1,velocity+engagement,0)

def download(url,path):
    req=urllib.request.Request(url,headers={
        "User-Agent":"Mozilla/5.0",
        "Referer":"https://www.tiktok.com/",
        "Accept":"*/*"
    })
    with urllib.request.urlopen(req,timeout=120) as r,open(path,"wb") as f:
        while True:
            b=r.read(1024*1024)
            if not b:break
            f.write(b)

def duration(path):
    cap=cv2.VideoCapture(str(path))
    fps=cap.get(cv2.CAP_PROP_FPS) or 0
    frames=cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    cap.release()
    return frames/fps if fps else 0

def face_quality(path):
    cap=cv2.VideoCapture(str(path))
    total=int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if total<=0:
        cap.release(); return 0,0
    cascade=cv2.CascadeClassifier(cv2.data.haarcascades+"haarcascade_frontalface_default.xml")
    hits=0; face_total=0; samples=14
    for i in range(samples):
        pos=int((i+1)*total/(samples+1))
        cap.set(cv2.CAP_PROP_POS_FRAMES,pos)
        ok,frame=cap.read()
        if not ok:continue
        h,w=frame.shape[:2]
        scale=min(1.0,720/max(w,h))
        if scale<1:
            frame=cv2.resize(frame,None,fx=scale,fy=scale,interpolation=cv2.INTER_AREA)
        gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
        faces=cascade.detectMultiScale(gray,scaleFactor=1.08,minNeighbors=4,minSize=(38,38))
        good=[f for f in faces if (f[2]*f[3]) >= frame.shape[0]*frame.shape[1]*0.004]
        if good:
            hits+=1
            face_total+=len(good)
    cap.release()
    return hits/samples,face_total

def speech_info(path,model):
    subprocess.run([
        "ffmpeg","-y","-i",str(path),"-t","35","-vn","-ac","1","-ar","16000",str(WAV)
    ],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
    if not WAV.exists() or WAV.stat().st_size<2000:
        return "",0.0,""
    segs,info=model.transcribe(str(WAV),beam_size=1,vad_filter=True)
    text=" ".join(s.text.strip() for s in segs if s.text.strip())
    return (info.language or ""),float(info.language_probability or 0),text[:1500]

def save_state(items,now):
    snap={"seen_at":now,"videos":{}}
    for v in items:
        x=str(v.get("video_id") or v.get("id") or "")
        if x:
            snap["videos"][x]={
                "play_count":n(v.get("play_count") or v.get("playCount")),
                "seen_at":now
            }
    STATE.write_text(json.dumps(snap,ensure_ascii=False,indent=2),encoding="utf-8")

def main():
    items=[]
    seen_ids=set()
    for region in REGIONS:
        data=get_json(FEED+"?"+urllib.parse.urlencode({"region":region,"count":COUNT}))
        if n(data.get("code"))!=0:
            continue
        part=data.get("data") or []
        if isinstance(part,dict):part=part.get("videos") or part.get("data") or []
        for v in part:
            vid=str(v.get("video_id") or v.get("id") or "")
            if vid and vid not in seen_ids:
                seen_ids.add(vid); items.append(v)
    if not items:raise RuntimeError("Brak popularnych filmów.")

    old=load_state(); now=int(time.time())
    ranked=[]
    for v in items:
        if not (v.get("video_id") or v.get("id")) or not v.get("play"):continue
        ranked.append((score_video(v,old,now),v))
    ranked.sort(key=lambda x:x[0],reverse=True)

    model=WhisperModel("tiny",device="cpu",compute_type="int8")
    rejected=[]
    chosen=None
    for score,v in ranked[:MAX_CANDIDATES]:
        title=(v.get("title") or v.get("desc") or "").strip()
        if BLOCKED.search(title):
            rejected.append(["blocked_title",title[:80]])
            continue
        try:
            download(v["play"],TMP)
        except Exception as e:
            rejected.append(["download",str(e)[:80]])
            continue
        dur=duration(TMP)
        if dur<5 or dur>90:
            rejected.append(["duration",round(dur,1)])
            continue
        face_ratio,face_total=face_quality(TMP)
        if face_ratio<0.20:
            rejected.append(["face",round(face_ratio,2),face_total])
            continue
        lang,prob,transcript=speech_info(TMP,model)
        if lang!="en" or prob<0.65 or len(transcript.split())<3:
            rejected.append(["language",lang,round(prob,2)])
            continue
        if BLOCKED.search(transcript):
            rejected.append(["blocked_speech",transcript[:80]])
            continue
        chosen=(score,v,dur,face_ratio,face_total,lang,prob,transcript)
        break

    save_state(items,now)
    if not chosen:
        raise RuntimeError("Brak odpowiedniego anglojęzycznego virala z widoczną osobą; nic nie publikuję.")

    score,best,dur,face_ratio,face_total,lang,prob,transcript=chosen
    TMP.replace(OUT/"source.mp4")
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
        "duration":round(dur,1),
        "language":lang,
        "language_probability":round(prob,3),
        "face_presence":round(face_ratio,3),
        "sampled_face_detections":face_total,
        "transcript":transcript,
        "selection_mode":"hourly_delta" if score[0]==2 else "current_velocity_estimate",
        "hourly_view_delta":score[2],
        "regions":REGIONS,
        "selected_at":now,
        "rejected_before_selection":rejected
    }
    (OUT/"trend.json").write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    caption=(title[:650]+"\n\nAI visual remix. Original source: "+source+"\n#remix #viral #tiktoktrend #ai").strip()
    (OUT/"caption.txt").write_text(caption,encoding="utf-8")
    print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
