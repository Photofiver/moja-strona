#!/usr/bin/env python3
import audioop
import json
import math
import os
import subprocess
import wave
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT=Path("tiktok-bot/output")
W,H=720,1280
FPS=15

def font(size,bold=False):
    paths=[
      "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
      "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for p in paths:
        if Path(p).exists():
            return ImageFont.truetype(p,size)
    return ImageFont.load_default()

def wrap(draw,text,f,maxw):
    out=[]; cur=""
    for word in text.split():
        t=(cur+" "+word).strip()
        if draw.textbbox((0,0),t,font=f)[2] <= maxw:
            cur=t
        else:
            if cur: out.append(cur)
            cur=word
    if cur: out.append(cur)
    return out

def audio_levels(wav_path):
    with wave.open(str(wav_path),"rb") as w:
        rate=w.getframerate(); sw=w.getsampwidth(); ch=w.getnchannels(); n=w.getnframes()
        duration=n/rate
        levels=[]
        chunk=max(1,int(rate/FPS))
        while True:
            data=w.readframes(chunk)
            if not data: break
            rms=audioop.rms(data,sw) if data else 0
            levels.append(rms)
    mx=max(levels) if levels else 1
    return duration,[v/mx for v in levels]

def draw_cat(d,cx,cy,mouth,blink,bounce):
    y=cy+bounce
    fur=(205,150,90); dark=(90,55,35); pink=(245,135,150)
    d.polygon([(cx-180,y-150),(cx-105,y-315),(cx-35,y-155)],fill=fur)
    d.polygon([(cx+180,y-150),(cx+105,y-315),(cx+35,y-155)],fill=fur)
    d.ellipse((cx-205,y-220,cx+205,y+185),fill=fur)
    # eyes
    eh=6 if blink else 42
    d.ellipse((cx-105,y-70-eh//2,cx-45,y-70+eh//2),fill=(20,20,20))
    d.ellipse((cx+45,y-70-eh//2,cx+105,y-70+eh//2),fill=(20,20,20))
    d.polygon([(cx,y-15),(cx-18,y+7),(cx+18,y+7)],fill=pink)
    d.line((cx,y+7,cx,y+35),fill=dark,width=5)
    mh=18+int(55*mouth)
    d.ellipse((cx-60,y+30,cx+60,y+30+mh),fill=(65,25,25),outline=dark,width=4)
    if mouth>.35:
        d.ellipse((cx-35,y+45,cx+35,y+45+mh//2),fill=pink)
    # whiskers
    for off in (-10,15,40):
        d.line((cx-40,y+off,cx-210,y+off-25),fill=dark,width=3)
        d.line((cx+40,y+off,cx+210,y+off-25),fill=dark,width=3)

def draw_dog(d,cx,cy,mouth,blink,bounce):
    y=cy+bounce
    fur=(170,115,65); dark=(65,38,25); cream=(220,180,125)
    d.ellipse((cx-215,y-200,cx-80,y+90),fill=dark)
    d.ellipse((cx+80,y-200,cx+215,y+90),fill=dark)
    d.ellipse((cx-190,y-220,cx+190,y+190),fill=fur)
    eh=6 if blink else 42
    d.ellipse((cx-105,y-70-eh//2,cx-45,y-70+eh//2),fill=(20,20,20))
    d.ellipse((cx+45,y-70-eh//2,cx+105,y-70+eh//2),fill=(20,20,20))
    d.ellipse((cx-85,y-10,cx+85,y+105),fill=cream)
    d.ellipse((cx-30,y-5,cx+30,y+35),fill=(35,25,20))
    mh=16+int(65*mouth)
    d.ellipse((cx-65,y+55,cx+65,y+55+mh),fill=(65,25,25),outline=dark,width=4)
    if mouth>.35:
        d.ellipse((cx-38,y+72,cx+38,y+72+mh//2),fill=(245,120,130))

def frame(i,level,total,trend):
    img=Image.new("RGB",(W,H),(14,16,26)); d=ImageDraw.Draw(img)
    # gradient background
    for y in range(H):
        d.line((0,y,W,y),fill=(14+int(30*y/H),16+int(8*y/H),26+int(38*y/H)))
    # header
    d.rounded_rectangle((35,35,W-35,180),radius=30,fill=(25,29,45),outline=(95,102,140),width=3)
    d.text((60,60),"TREND Z TIKTOKA → WERSJA AI",font=font(34,True),fill=(255,255,255))
    src="POPULARNY FILM" if trend.get("type")=="video" else "TREND / HASHTAG"
    d.text((60,120),src,font=font(25),fill=(205,210,230))

    # topic box
    topic=trend.get("topic","trend")
    f=font(37,True)
    lines=wrap(d,topic,f,W-110)[:3]
    y=225
    for line in lines:
        d.text((55,y),line,font=f,fill=(245,245,250))
        y+=48

    # animal
    bounce=int(math.sin(i/4)*8)
    mouth=min(1,max(0,(level-.04)*2.2))
    blink=(i%73 in (0,1,2))
    if trend.get("animal")=="pies":
        draw_dog(d,W//2,650,mouth,blink,bounce)
    else:
        draw_cat(d,W//2,650,mouth,blink,bounce)

    # microphone
    d.ellipse((W//2-60,900,W//2+60,1020),fill=(55,60,75),outline=(175,180,195),width=5)
    d.rectangle((W//2-14,1010,W//2+14,1115),fill=(110,115,130))
    d.rectangle((W//2-90,1110,W//2+90,1132),fill=(110,115,130))

    # captions
    script=trend.get("script","")
    small=font(26,True)
    cap=wrap(d,script,small,W-90)
    y=1150-len(cap[:3])*34
    for line in cap[:3]:
        box=d.textbbox((0,0),line,font=small)
        tw=box[2]-box[0]
        d.rounded_rectangle((W//2-tw//2-12,y-4,W//2+tw//2+12,y+31),radius=8,fill=(0,0,0))
        d.text((W//2-tw//2,y),line,font=small,fill=(255,255,255))
        y+=35
    return img

def main():
    trend=json.loads((OUT/"trend.json").read_text(encoding="utf-8"))
    duration,levels=audio_levels(OUT/"voice.wav")
    frames=OUT/"frames"
    frames.mkdir(exist_ok=True)
    n=max(1,int(duration*FPS)+FPS)
    for i in range(n):
        level=levels[i] if i<len(levels) else 0
        frame(i,level,n,trend).save(frames/f"{i:05d}.jpg",quality=88)
    subprocess.run([
      "ffmpeg","-y","-framerate",str(FPS),"-i",str(frames/"%05d.jpg"),
      "-i",str(OUT/"voice.mp3"),"-c:v","libx264","-preset","medium","-crf","22",
      "-pix_fmt","yuv420p","-c:a","aac","-shortest","-movflags","+faststart",
      str(OUT/"tiktok_ready.mp4")
    ],check=True)

if __name__=="__main__":
    main()
