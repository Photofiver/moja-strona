#!/usr/bin/env python3
import json, re, subprocess, time, urllib.parse
from pathlib import Path
import requests
from faster_whisper import WhisperModel

OUT=Path("tiktok-bot/output")
OUT.mkdir(parents=True,exist_ok=True)
STATE=Path("tiktok-bot/state.json")
FEED="https://www.tikwm.com/api/feed/list"
REGIONS=["GB","US"]
COUNT=50
MAX_CANDIDATES=30
TMP=OUT/"candidate.mp4"
WAV=OUT/"candidate.wav"

BLOCKED=re.compile(r"\b(baby|babies|toddler|kid|kids|child|children|toy|toys|cartoon|roblox|minecraft|fortnite|monkey|gorilla|ape)\b",re.I)

def get_json(url):
    r=requests.get(url,headers={"User-Agent":"Mozilla/5.0","Referer":"https://www.tikwm.com/"},timeout=45)
    r.raise_for_status()
    return r.json()

def load_state():
    try:return json.loads(STATE.read_text(encoding="utf-8"))
    except:return {}

def n(v):
    try:return int(v or 0)
    except:return 0

def score_video(v,old,now):
    vid=str(v.get("video_id") or v.get("id") or "")
    plays=n(v.get("play_count") or v.get("playCount"))
    shares=n(v.get("share_count") or v.get("shareCount"))
    comments=n(v.get("comment_count") or v.get("commentCount"))
    likes=n(v.get("digg_count") or v.get("diggCount"))
    created=n(v.get("create_time") or v.get("createTime"))
    prev=(old.get("videos") or {}).get(vid)
    if prev and n(prev.get("play_count"))<=plays:
        dt=max(900,now-n(prev.get("seen_at")))
        delta=plays-n(prev.get("play_count"))
        return (2,delta*3600/dt + shares*2 + comments*0.5,delta)
    age_h=max(0.25,(now-created)/3600) if created else 24
    return (1,plays/age_h + likes*0.08 + shares*0.8 + comments*0.2,0)

def download(url,path):
    with requests.get(url,headers={"User-Agent":"Mozilla/5.0","Referer":"https://www.tiktok.com/"},timeout=120,stream=True) as r:
        r.raise_for_status()
        with open(path,"wb") as f:
            for chunk in r.iter_content(1024*1024):
                if chunk:f.write(chunk)

def duration(path):
    import cv2
    cap=cv2.VideoCapture(str(path))
    fps=cap.get(cv2.CAP_PROP_FPS) or 0
    frames=cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
    cap.release()
    return frames/fps if fps else 0

def speech_info(path,model):
    subprocess.run(["ffmpeg","-y","-i",str(path),"-t","40","-vn","-ac","1","-ar","16000",str(WAV)],
                   stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
    if not WAV.exists() or WAV.stat().st_size<2000:return "",0.0,""
    segs,info=model.transcribe(str(WAV),beam_size=1,vad_filter=True)
    text=" ".join(s.text.strip() for s in segs if s.text.strip())
    return (info.language or ""),float(info.language_probability or 0),text[:1600]

def make_concept(title,transcript):
    prompt=(
      "Return ONLY valid compact JSON with keys script, scene1, scene2, scene3. "
      "Create an ORIGINAL adult-looking photorealistic cinematic reenactment inspired by the event below. "
      "English only. No commentary, no opinions, no mention of TikTok/trend/viral. "
      "Do not copy the original wording. Script 28-45 words, describing/reenacting what happens. "
      "Each scene prompt must depict the SAME adult characters (age 25+) and same location/clothes, vertical 9:16, "
      "photorealistic, cinematic, contemporary, serious/comedic but NOT childish, no cartoons, no animals, no text in image. "
      f"TITLE: {title}\nTRANSCRIPT: {transcript}"
    )
    url="https://text.pollinations.ai/"+urllib.parse.quote(prompt,safe="")
    r=requests.get(url,params={"model":"openai","json":"true","private":"true"},timeout=90)
    r.raise_for_status()
    txt=r.text.strip()
    try:
        data=json.loads(txt)
    except Exception:
        m=re.search(r"\{[\s\S]*\}",txt)
        if not m: raise RuntimeError("AI nie zwróciło poprawnego JSON.")
        data=json.loads(m.group(0))
    for k in ("script","scene1","scene2","scene3"):
        if not str(data.get(k,"")).strip():raise RuntimeError("Brak pola "+k)
    return {k:str(data[k]).strip() for k in ("script","scene1","scene2","scene3")}

def save_state(items,now):
    snap={"seen_at":now,"videos":{}}
    for v in items:
        x=str(v.get("video_id") or v.get("id") or "")
        if x:snap["videos"][x]={"play_count":n(v.get("play_count") or v.get("playCount")),"seen_at":now}
    STATE.write_text(json.dumps(snap,ensure_ascii=False,indent=2),encoding="utf-8")

def main():
    items=[]; seen=set()
    for region in REGIONS:
        try:data=get_json(FEED+"?"+urllib.parse.urlencode({"region":region,"count":COUNT}))
        except Exception:continue
        part=data.get("data") or []
        if isinstance(part,dict):part=part.get("videos") or part.get("data") or []
        for v in part:
            vid=str(v.get("video_id") or v.get("id") or "")
            if vid and vid not in seen:
                seen.add(vid); items.append(v)
    if not items:raise RuntimeError("Brak popularnych filmów.")

    old=load_state(); now=int(time.time())
    ranked=[(score_video(v,old,now),v) for v in items if (v.get("video_id") or v.get("id")) and v.get("play")]
    ranked.sort(key=lambda x:x[0],reverse=True)
    model=WhisperModel("tiny",device="cpu",compute_type="int8")

    chosen=None; rejected=[]
    for score,v in ranked[:MAX_CANDIDATES]:
        title=(v.get("title") or v.get("desc") or "").strip()
        if BLOCKED.search(title):continue
        try:download(v["play"],TMP)
        except Exception:continue
        dur=duration(TMP)
        if dur<6 or dur>60:continue
        lang,prob,transcript=speech_info(TMP,model)
        if lang!="en" or prob<0.60 or len(transcript.split())<8:continue
        if BLOCKED.search(transcript):continue
        try:concept=make_concept(title,transcript)
        except Exception as e:
            rejected.append(str(e)[:120]); continue
        chosen=(score,v,dur,lang,prob,transcript,concept)
        break

    save_state(items,now)
    if not chosen:raise RuntimeError("Brak odpowiedniego anglojęzycznego virala do oryginalnej przeróbki.")

    score,best,dur,lang,prob,transcript,concept=chosen
    vid=str(best.get("video_id") or best.get("id"))
    author=best.get("author") or {}
    handle=author.get("unique_id") or author.get("uniqueId") or ""
    title=(best.get("title") or best.get("desc") or "").strip()
    source=f"https://www.tiktok.com/@{handle}/video/{vid}" if handle else f"https://www.tiktok.com/video/{vid}"

    out={
      "video_id":vid,"source_url":source,"play_count":n(best.get("play_count") or best.get("playCount")),
      "hourly_view_delta":score[2],"selection_mode":"hourly_delta" if score[0]==2 else "current_velocity_estimate",
      "language":lang,"language_probability":round(prob,3),"original_transcript":transcript,
      "concept":concept,"regions":REGIONS,"selected_at":now
    }
    (OUT/"trend.json").write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    (OUT/"script.txt").write_text(concept["script"],encoding="utf-8")
    (OUT/"caption.txt").write_text(("Original AI reenactment inspired by a current English-language trend.\nSource inspiration: "+source+"\n#viral #remix #ai #shortvideo"),encoding="utf-8")
    print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__=="__main__":main()
