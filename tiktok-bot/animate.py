#!/usr/bin/env python3
import json, math, subprocess, urllib.parse
from pathlib import Path
import cv2, numpy as np, requests

OUT=Path("tiktok-bot/output")
TREND=json.loads((OUT/"trend.json").read_text(encoding="utf-8"))
CON=TREND["concept"]
W,H=720,1280
FPS=30

def gen_image(prompt,path,seed):
    full=prompt+", adult cinematic photography, realistic skin, natural lighting, high-end commercial film still, vertical 9:16"
    url="https://image.pollinations.ai/prompt/"+urllib.parse.quote(full,safe="")
    r=requests.get(url,params={"width":W,"height":H,"model":"flux","seed":seed,"nologo":"true","safe":"true","private":"true"},timeout=180)
    r.raise_for_status()
    path.write_bytes(r.content)
    im=cv2.imread(str(path))
    if im is None:raise RuntimeError("Niepoprawny obraz AI.")

def cover(im):
    h,w=im.shape[:2]; s=max(W/w,H/h); nw,nh=int(w*s),int(h*s)
    im=cv2.resize(im,(nw,nh),interpolation=cv2.INTER_CUBIC)
    x=(nw-W)//2; y=(nh-H)//2
    return im[y:y+H,x:x+W]

def write_motion(img,writer,frames,mode):
    base=cover(img)
    for i in range(frames):
        t=i/max(1,frames-1)
        zoom=1.0+0.08*t
        nw,nh=int(W*zoom),int(H*zoom)
        z=cv2.resize(base,(nw,nh),interpolation=cv2.INTER_CUBIC)
        if mode==0:x=int((nw-W)*t*0.6); y=int((nh-H)*0.25)
        elif mode==1:x=int((nw-W)*(0.6-0.4*t)); y=int((nh-H)*0.45)
        else:x=int((nw-W)*0.25); y=int((nh-H)*(0.15+0.45*t))
        x=max(0,min(nw-W,x)); y=max(0,min(nh-H,y))
        fr=z[y:y+H,x:x+W].copy()
        cv2.rectangle(fr,(0,H-84),(W,H),(0,0,0),-1)
        cv2.putText(fr,"ORIGINAL AI REENACTMENT",(24,H-32),cv2.FONT_HERSHEY_SIMPLEX,0.63,(245,245,245),1,cv2.LINE_AA)
        writer.write(fr)

def main():
    imgs=[]
    for i,k in enumerate(("scene1","scene2","scene3"),1):
        p=OUT/f"scene{i}.jpg"; gen_image(CON[k],p,1300+i); imgs.append(cv2.imread(str(p)))
    subprocess.run(["edge-tts","--voice","en-US-GuyNeural","--text-file",str(OUT/"script.txt"),"--write-media",str(OUT/"voice.mp3")],check=True)
    p=subprocess.run(["ffprobe","-v","error","-show_entries","format=duration","-of","default=noprint_wrappers=1:nokey=1",str(OUT/"voice.mp3")],capture_output=True,text=True,check=True)
    dur=max(6.0,float(p.stdout.strip())+0.4)
    total=int(dur*FPS); each=total//3
    raw=OUT/"visual.mp4"
    wr=cv2.VideoWriter(str(raw),cv2.VideoWriter_fourcc(*"mp4v"),FPS,(W,H))
    used=0
    for i,img in enumerate(imgs):
        n=each if i<2 else total-used
        write_motion(img,wr,n,i); used+=n
    wr.release()
    subprocess.run([
      "ffmpeg","-y","-i",str(raw),"-i",str(OUT/"voice.mp3"),
      "-c:v","libx264","-preset","veryfast","-crf","20","-c:a","aac","-b:a","160k",
      "-shortest","-movflags","+faststart",str(OUT/"tiktok_ready.mp4")
    ],check=True)

if __name__=="__main__":main()
