#!/usr/bin/env python3
import io, math, subprocess, urllib.request, wave
from pathlib import Path
import cv2, numpy as np

OUT=Path("tiktok-bot/output")
SRC=OUT/"source.mp4"
NOAUDIO=OUT/"animal_noaudio.mp4"
FINAL=OUT/"tiktok_ready.mp4"
WAV=OUT/"source_audio.wav"

DOG_URL="https://commons.wikimedia.org/wiki/Special:Redirect/file/German%20Shepherd%20Transparent.png?width=900"

def fetch_rgba(url):
    req=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
    with urllib.request.urlopen(req,timeout=60) as r:
        arr=np.frombuffer(r.read(),np.uint8)
    img=cv2.imdecode(arr,cv2.IMREAD_UNCHANGED)
    if img is None:
        raise RuntimeError("Nie udało się pobrać maski zwierzęcia.")
    if img.shape[2]==3:
        img=cv2.cvtColor(img,cv2.COLOR_BGR2BGRA)
    return img

def crop_alpha(img):
    a=img[:,:,3]
    ys,xs=np.where(a>8)
    if len(xs)==0:return img
    return img[max(0,ys.min()-5):min(img.shape[0],ys.max()+6),max(0,xs.min()-5):min(img.shape[1],xs.max()+6)]

def jaw_frame(base,amp):
    # Real pixels of the dog's lower muzzle move; no drawn circle/mouth.
    h,w=base.shape[:2]
    y0=int(h*0.60)
    shift=int(min(h*0.055, max(0,amp-0.06)*h*0.12))
    if shift<=1:return base
    out=np.zeros((h+shift,w,4),dtype=np.uint8)
    out[:y0]=base[:y0]
    out[y0+shift:y0+shift+(h-y0)]=base[y0:]
    # bridge the tiny opening with stretched real fur pixels
    bridge=base[max(0,y0-3):y0+1]
    if bridge.size:
        for y in range(y0,y0+shift):
            out[y]=bridge[-1]
    return out

def overlay_rgba(frame,fg,cx,cy,w,h):
    if w<10 or h<10:return
    fg=cv2.resize(fg,(w,h),interpolation=cv2.INTER_AREA)
    x1=int(cx-w/2); y1=int(cy-h/2)
    x2=x1+w; y2=y1+h
    fx1=max(0,-x1); fy1=max(0,-y1); fx2=w-max(0,x2-frame.shape[1]); fy2=h-max(0,y2-frame.shape[0])
    x1=max(0,x1); y1=max(0,y1); x2=min(frame.shape[1],x2); y2=min(frame.shape[0],y2)
    if x1>=x2 or y1>=y2:return
    crop=fg[fy1:fy2,fx1:fx2]
    alpha=(crop[:,:,3:4].astype(np.float32)/255.0)
    frame[y1:y2,x1:x2]=(crop[:,:,:3]*alpha+frame[y1:y2,x1:x2]*(1-alpha)).astype(np.uint8)

def read_audio_levels(wav_path,fps,nframes):
    if not wav_path.exists():return [0.0]*nframes
    with wave.open(str(wav_path),"rb") as w:
        rate=w.getframerate(); sw=w.getsampwidth(); ch=w.getnchannels()
        samples=w.readframes(w.getnframes())
    if sw!=2:return [0.0]*nframes
    a=np.frombuffer(samples,dtype=np.int16).astype(np.float32)
    if ch>1:a=a.reshape(-1,ch).mean(axis=1)
    levels=[]
    hop=max(1,int(rate/fps))
    for i in range(nframes):
        s=a[i*hop:(i+1)*hop]
        levels.append(float(np.sqrt(np.mean(s*s)))/32768 if len(s) else 0.0)
    mx=max(levels) if levels else 1
    if mx>0: levels=[x/mx for x in levels]
    return levels

def main():
    subprocess.run(["ffmpeg","-y","-i",str(SRC),"-vn","-ac","1","-ar","16000",str(WAV)],check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)

    cap=cv2.VideoCapture(str(SRC))
    if not cap.isOpened():raise RuntimeError("Nie mogę otworzyć filmu źródłowego.")
    fps=cap.get(cv2.CAP_PROP_FPS) or 30
    frames=int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    ow=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)); oh=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    scale=min(1.0,720/max(1,ow))
    w=max(2,int(ow*scale)//2*2); h=max(2,int(oh*scale)//2*2)

    fourcc=cv2.VideoWriter_fourcc(*"mp4v")
    writer=cv2.VideoWriter(str(NOAUDIO),fourcc,fps,(w,h))
    dog=crop_alpha(fetch_rgba(DOG_URL))
    cascade=cv2.CascadeClassifier(cv2.data.haarcascades+"haarcascade_frontalface_default.xml")
    levels=read_audio_levels(WAV,fps,frames)

    last=None; missing=0
    i=0
    while True:
        ok,frame=cap.read()
        if not ok:break
        if scale!=1.0:frame=cv2.resize(frame,(w,h),interpolation=cv2.INTER_AREA)

        # Detect often enough to follow movement, but keep CPU use low.
        if i%3==0:
            gray=cv2.cvtColor(frame,cv2.COLOR_BGR2GRAY)
            faces=cascade.detectMultiScale(gray,scaleFactor=1.12,minNeighbors=5,minSize=(45,45))
            if len(faces):
                x,y,fw,fh=max(faces,key=lambda b:b[2]*b[3])
                new=(x,y,fw,fh)
                if last:
                    a=0.55
                    new=tuple(int(a*n+(1-a)*o) for n,o in zip(new,last))
                last=new; missing=0
            else:
                missing+=3
                if missing>24:last=None

        if last:
            x,y,fw,fh=last
            cx=x+fw/2
            cy=y+fh*0.50
            mask=jaw_frame(dog,levels[i] if i<len(levels) else 0)
            # Animal head slightly larger than human face so original face is fully hidden.
            overlay_rgba(frame,mask,cx,cy,int(fw*2.0),int(fh*2.25))

        # Clear remix attribution on-frame.
        cv2.rectangle(frame,(0,0),(w,38),(0,0,0),-1)
        cv2.putText(frame,"AI ANIMAL REMIX - SOURCE CREDIT IN CAPTION",(14,26),cv2.FONT_HERSHEY_SIMPLEX,0.55,(255,255,255),1,cv2.LINE_AA)

        writer.write(frame)
        i+=1

    cap.release(); writer.release()
    subprocess.run([
        "ffmpeg","-y","-i",str(NOAUDIO),"-i",str(SRC),
        "-map","0:v:0","-map","1:a:0?","-c:v","libx264","-preset","veryfast","-crf","22",
        "-c:a","aac","-b:a","128k","-shortest","-movflags","+faststart",str(FINAL)
    ],check=True)

if __name__=="__main__":
    main()
