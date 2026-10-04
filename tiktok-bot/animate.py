#!/usr/bin/env python3
import audioop
import io
import json
import math
import subprocess
import urllib.request
import wave
from pathlib import Path
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

OUT = Path("tiktok-bot/output")
W, H = 720, 1280
FPS = 15

# Real photographs released as CC0/Public Domain on Wikimedia Commons.
ASSETS = {
    "pies": {
        "url": "https://commons.wikimedia.org/wiki/Special:Redirect/file/Dog-portrait-1367008135LpJ.jpg?width=1400",
        "source": "https://commons.wikimedia.org/wiki/File:Dog-portrait-1367008135LpJ.jpg",
        "mouth_x": 0.50, "mouth_y": 0.69, "mouth_w": 0.22, "mouth_h": 0.09,
    },
    "kot": {
        "url": "https://commons.wikimedia.org/wiki/Special:Redirect/file/Cat_face.jpg?width=1600",
        "source": "https://commons.wikimedia.org/wiki/File:Cat_face.jpg",
        "mouth_x": 0.50, "mouth_y": 0.64, "mouth_w": 0.16, "mouth_h": 0.065,
    },
}

def font(size, bold=False):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for p in paths:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

def wrap(draw, text, fnt, maxw):
    lines, cur = [], ""
    for word in text.split():
        t = (cur + " " + word).strip()
        if draw.textbbox((0, 0), t, font=fnt)[2] <= maxw:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines

def fetch_photo(kind):
    a = ASSETS[kind]
    req = urllib.request.Request(a["url"], headers={"User-Agent":"Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=45) as r:
        data = r.read()
    img = Image.open(io.BytesIO(data)).convert("RGB")
    return img, a

def cover(img, w, h):
    ratio=max(w/img.width, h/img.height)
    nw,nh=int(img.width*ratio),int(img.height*ratio)
    x=img.resize((nw,nh),Image.Resampling.LANCZOS)
    left=(nw-w)//2
    top=(nh-h)//2
    return x.crop((left,top,left+w,top+h))

def audio_levels(path):
    with wave.open(str(path),"rb") as w:
        rate=w.getframerate(); sw=w.getsampwidth()
        levels=[]; chunk=max(1,int(rate/FPS))
        while True:
            data=w.readframes(chunk)
            if not data: break
            levels.append(audioop.rms(data,sw))
        duration=w.getnframes()/rate
    mx=max(levels) if levels else 1
    return duration,[x/mx for x in levels]

def make_base(photo):
    bg=cover(photo,W,H).filter(ImageFilter.GaussianBlur(22))
    bg=ImageEnhance.Brightness(bg).enhance(0.48)
    fg=photo.copy()
    ratio=min((W-80)/fg.width, 810/fg.height)
    fg=fg.resize((int(fg.width*ratio),int(fg.height*ratio)),Image.Resampling.LANCZOS)
    return bg,fg

def frame(i, level, trend, photo, asset):
    bg,fg=make_base(photo)
    canvas=bg.copy()
    bob=int(math.sin(i/5)*4)
    x=(W-fg.width)//2
    y=250+bob
    canvas.paste(fg,(x,y))

    d=ImageDraw.Draw(canvas)
    d.rounded_rectangle((35,30,W-35,160),radius=28,fill=(0,0,0,180))
    d.text((55,52),"TREND Z TIKTOKA — WERSJA AI",font=font(30,True),fill="white")
    d.text((55,105),"Prawdziwe zdjęcie zwierzaka • własny głos i tekst",font=font(20),fill=(220,220,220))

    # Real-photo mouth animation. We do not alter or reuse the source TikTok video.
    fx=x + int(fg.width*asset["mouth_x"])
    fy=y + int(fg.height*asset["mouth_y"])
    mw=max(45,int(fg.width*asset["mouth_w"]))
    base_h=max(10,int(fg.height*asset["mouth_h"]))
    open_amt=max(0.0,min(1.0,(level-0.035)*2.8))
    mh=int(base_h*(0.35+1.25*open_amt))
    if open_amt>0.08:
        d.ellipse((fx-mw//2,fy-mh//2,fx+mw//2,fy+mh//2),fill=(32,12,15),outline=(55,25,25),width=2)
        if open_amt>0.42:
            tw=int(mw*0.55); th=max(6,int(mh*0.32))
            d.ellipse((fx-tw//2,fy+int(mh*0.08),fx+tw//2,fy+int(mh*0.08)+th),fill=(190,83,94))

    # Subtitles: short 2–3 lines at bottom.
    txt=trend.get("script","")
    lines=wrap(d,txt,font(25,True),W-90)[:3]
    yy=H-55-len(lines)*38
    for line in lines:
        box=d.textbbox((0,0),line,font=font(25,True))
        tw=box[2]-box[0]
        d.rounded_rectangle((W//2-tw//2-12,yy-5,W//2+tw//2+12,yy+31),radius=8,fill="black")
        d.text((W//2-tw//2,yy),line,font=font(25,True),fill="white")
        yy+=38
    return canvas

def main():
    trend=json.loads((OUT/"trend.json").read_text(encoding="utf-8"))
    kind=trend.get("animal","pies")
    photo,asset=fetch_photo(kind)
    trend["animal_photo_source"]=asset["source"]
    (OUT/"trend.json").write_text(json.dumps(trend,ensure_ascii=False,indent=2),encoding="utf-8")

    duration,levels=audio_levels(OUT/"voice.wav")
    frames=OUT/"frames"
    frames.mkdir(exist_ok=True)
    for old in frames.glob("*.jpg"):
        old.unlink()
    n=max(1,int(duration*FPS)+5)
    for i in range(n):
        lv=levels[i] if i<len(levels) else 0
        frame(i,lv,trend,photo,asset).save(frames/f"{i:05d}.jpg",quality=90)

    subprocess.run([
        "ffmpeg","-y","-framerate",str(FPS),"-i",str(frames/"%05d.jpg"),
        "-i",str(OUT/"voice.mp3"),"-c:v","libx264","-preset","medium","-crf","21",
        "-pix_fmt","yuv420p","-c:a","aac","-shortest","-movflags","+faststart",
        str(OUT/"tiktok_ready.mp4")
    ],check=True)

if __name__=="__main__":
    main()
