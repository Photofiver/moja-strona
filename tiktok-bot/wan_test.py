#!/usr/bin/env python3
import json, os, shutil, time, requests
from pathlib import Path
from gradio_client import Client

OUT=Path("tiktok-bot/output")
OUT.mkdir(parents=True,exist_ok=True)

PROMPT="""Vertical 9:16 realistic cinematic smartphone video. Two adults in their mid 20s in a modern outdoor apartment courtyard at night have just completed a difficult challenge. A young woman in casual streetwear looks stunned for a beat, then turns to her friend and both celebrate naturally, saying with excited body language that they did it. Handheld camera, subtle movement, natural faces, realistic clothing and lighting, mature social-media style, no animals, no cartoons, no text, no logos, no childish comedy."""

def copy_video(v):
    # Gradio may return a filepath dict, local temp path, or URL.
    if isinstance(v, dict):
        p=v.get("path") or v.get("url") or v.get("video")
        if p: return copy_video(p)
    if isinstance(v, (list,tuple)):
        for x in v:
            got=copy_video(x)
            if got:return got
        return None
    if not isinstance(v,str) or not v:return None
    dest=OUT/"tiktok_ready.mp4"
    if v.startswith("http"):
        r=requests.get(v,timeout=180,stream=True)
        r.raise_for_status()
        with open(dest,"wb") as f:
            for c in r.iter_content(1024*1024):
                if c:f.write(c)
        return str(dest)
    p=Path(v)
    if p.exists():
        shutil.copyfile(p,dest)
        return str(dest)
    return None

def main():
    client=Client("Wan-AI/Wan2.1")
    info=client.view_api(all_endpoints=True,return_format="dict")
    print(json.dumps(info,indent=2,default=str)[:30000])

    submit="/t2v_generation_async"
    refresh="/status_refresh"
    try:
        res=client.predict(PROMPT,"720*1280",False,-1,api_name=submit)
    except Exception as e:
        raise RuntimeError(f"Nie udało się uruchomić Wan T2V przez {submit}: {e}")
    print("SUBMIT",repr(res))
    # Gradio keeps task_id/status in hidden session state. Public API returns only
    # cost/wait estimates, and /status_refresh takes no public parameters.
    for i in range(36):
        time.sleep(20)
        try:
            rr=client.predict(api_name=refresh)
        except Exception as e:
            print("refresh error",repr(e))
            continue
        print("REFRESH",i,repr(rr))
        got=copy_video(rr[0] if isinstance(rr,(list,tuple)) and rr else rr)
        if got:
            meta={
              "test":True,
              "generator":"Wan2.1",
              "prompt":PROMPT,
              "source_inspiration":"previous English viral test: two adults celebrating, transcript 'We did it! We did it!'",
              "generated_at":int(time.time())
            }
            (OUT/"trend.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8")
            (OUT/"caption.txt").write_text("Original AI reenactment test — English, adult, no animal overlay.",encoding="utf-8")
            print("SAVED",got)
            return
    raise RuntimeError("Wan nie zwrócił gotowego filmu w czasie testu.")

if __name__=="__main__":
    main()
