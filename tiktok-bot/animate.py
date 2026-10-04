#!/usr/bin/env python3
import subprocess, urllib.request, wave
from pathlib import Path
import cv2, numpy as np

OUT=Path("tiktok-bot/output")
SRC=OUT/"source.mp4"; RAW=OUT/"remix_raw.mp4"; FINAL=OUT/"tiktok_ready.mp4"; WAV=OUT/"source_audio.wav"
DOG_URL="https://commons.wikimedia.org/wiki/Special:Redirect/file/German%20Shepherd%20Transparent.png?width=900"

def fetch_rgba(url):
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
    with urllib.request.urlopen(req,timeout=60) as r:
        arr=np.frombuffer(r.read(),np.uint8)
    img=cv2.imdecode(arr,cv2.IMREAD_UNCHANGED)
    if img is None:raise RuntimeError("Nie udało się pobrać głowy psa.")
    if len(img.shape)==2:img=cv2.cvtColor(img,cv2.COLOR_GRAY2BGRA)
    elif img.shape[2]==3:img=cv2.cvtColor(img,cv2.COLOR_BGR2BGRA)
    return img

def crop_alpha(img):
    a=img[:,:,3]; ys,xs=np.where(a>10)
    if len(xs)==0:return img
    return img[max(0,ys.min()-5):min(img.shape[0],ys.max()+6),max(0,xs.min()-5):min(img.shape[1],xs.max()+6)]

def feather_alpha(fg):
    out=fg.copy()
    out[:,:,3]=cv2.GaussianBlur(out[:,:,3],(0,0),1.2)
    return out

def audio_levels(path,fps,n):
    subprocess.run(["ffmpeg","-y","-i",str(SRC),"-vn","-ac","1","-ar","16000",str(path)],
                   stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=False)
    if not path.exists():return [0.0]*n
    with wave.open(str(path),"rb") as w:
        rate=w.getframerate(); samples=np.frombuffer(w.readframes(w.getnframes()),dtype=np.int16).astype(np.float32)
    hop=max(1,int(rate/fps)); vals=[]
    for i in range(n):
        s=samples[i*hop:(i+1)*hop]
        vals.append(float(np.sqrt(np.mean(s*s)))/32768 if len(s) else 0.0)
    mx=max(vals) if vals else 1
    return [v/mx for v in vals] if mx else vals

def subtle_jaw(base,amp):
    h,w=base.shape[:2]; y0=int(h*0.64)
    shift=int(max(0,min(h*0.018,(amp-0.14)*h*0.035)))
    if shift<=1:return base
    out=np.zeros((h+shift,w,4),dtype=np.uint8)
    out[:y0]=base[:y0]
    out[y0:y0+shift]=base[max(0,y0-1):y0]
    out[y0+shift:y0+shift+h-y0]=base[y0:]
    return out

def overlay(frame,fg,bbox):
    x,y,fw,fh=bbox
    cx=x+fw/2; cy=y+fh*0.48
    tw=max(12,int(fw*1.80)); th=max(12,int(fh*1.88))
    fg=cv2.resize(fg,(tw,th),interpolation=cv2.INTER_AREA)
    x1=int(cx-tw/2); y1=int(cy-th/2); x2=x1+tw; y2=y1+th
    fx1=max(0,-x1); fy1=max(0,-y1); fx2=tw-max(0,x2-frame.shape[1]); fy2=th-max(0,y2-frame.shape[0])
    x1=max(0,x1); y1=max(0,y1); x2=min(frame.shape[1],x2); y2=min(frame.shape[0],y2)
    if x1>=x2 or y1>=y2:return
    crop=fg[fy1:fy2,fx1:fx2]
    a=crop[:,:,3:4].astype(np.float32)/255.0
    frame[y1:y2,x1:x2]=(crop[:,:,:3]*a+frame[y1:y2,x1:x2]*(1-a)).astype(np.uint8)

def center(b):
    x,y,w,h=b
    return x+w/2,y+h/2

def update_tracks(tracks,detections):
    unmatched=set(range(len(detections)))
    for tr in tracks:
        tx,ty=center(tr["bbox"])
        best=None; bestd=1e18
        for j in list(unmatched):
            dx,dy=center(detections[j])
            d=(dx-tx)**2+(dy-ty)**2
            limit=max(tr["bbox"][2],tr["bbox"][3],detections[j][2],detections[j][3])*1.8
            if d<limit*limit and d<bestd:
                best=j; bestd=d
        if best is None:
            tr["miss"]+=1
        else:
            det=detections[best]; unmatched.remove(best)
            a=0.42
            tr["bbox"]=tuple(int((1-a)*o+a*n) for o,n in zip(tr["bbox"],det))
            tr["miss"]=0
    tracks[:]=[t for t in tracks if t["miss"]<=4]
    next_id=max([t["id"] for t in tracks],default=-1)+1
    for j in unmatched:
        tracks.append({"id":next_id,"bbox":tuple(int(v) for v in detections[j]),"miss":0})
        next_id+=1

def main():
    cap=cv2.VideoCapture(str(SRC))
    if not cap.isOpened():raise RuntimeError("Nie mogę otworzyć źródłowego virala.")
    fps=cap.get(cv2.CAP_PROP_FPS) or 30; n=int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    ow=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); oh=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    scale=min(1.0,720/max(ow,1)); w=max(2,int(ow*scale)//2*2); h=max(2,int(oh*scale)//2*2)
    writer=cv2.VideoWriter(str(RAW),cv2.VideoWriter_fourcc(*"mp4v"),fps,(w,h))
    dog=feather_alpha(crop_alpha(fetch_rgba(DOG_URL)))
    levels=audio_levels(WAV,fps,n)
    cascade=cv2.CascadeClassifier(cv2.data.haarcascades+"haarcascade_frontalface_default.xml")
    tracks=[]; i=0
    while True:
        ok,frame=cap.read()
        if not ok:break
        if scale!=1:frame=cv2.resize(frame,(w,h),interpolation=cv2.INTER_AREA)
        gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
        faces=cascade.detectMultiScale(gray,scaleFactor=1.07,minNeighbors=4,minSize=(36,36))
        good=[tuple(int(v) for v in f) for f in faces if f[2]*f[3] >= w*h*0.003]
        update_tracks(tracks,good)

        head=subtle_jaw(dog,levels[i] if i<len(levels) else 0)
        for tr in tracks:
            if tr["miss"]<=2:
                overlay(frame,head,tr["bbox"])

        # Keep the original scene/dialogue; only the human faces become the animal characters.
        cv2.putText(frame,"AI REMIX",(w-92,h-14),cv2.FONT_HERSHEY_SIMPLEX,0.42,(235,235,235),1,cv2.LINE_AA)
        writer.write(frame); i+=1

    cap.release(); writer.release()
    subprocess.run([
        "ffmpeg","-y","-i",str(RAW),"-i",str(SRC),"-map","0:v:0","-map","1:a:0?",
        "-c:v","libx264","-preset","veryfast","-crf","21","-c:a","aac","-b:a","128k",
        "-shortest","-movflags","+faststart",str(FINAL)
    ],check=True)

if __name__=="__main__":
    main()
