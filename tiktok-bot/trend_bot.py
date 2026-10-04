#!/usr/bin/env python3
import json, os, re, textwrap, urllib.request
from pathlib import Path
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright
from PIL import Image, ImageDraw, ImageFont

OUT = Path("tiktok-bot/output")
OUT.mkdir(parents=True, exist_ok=True)

VIDEO_URL = "https://ads.tiktok.com/creative/creativeCenter/trends/video?countryCode=GB&period=7&region=GB"
HASHTAG_URL = "https://ads.tiktok.com/creative/creativeCenter/trends?deviceType=pc&locale=en&region=GB"

def clean(s):
    return re.sub(r"\\s+", " ", s or "").strip()

def parse_text(body, source):
    lines = [clean(x).replace("**", "") for x in body.splitlines() if clean(x)]
    skip = {"video", "hashtag", "creator", "action", "view details", "highest video views",
            "highest engagement", "highest 6s views", "please select"}

    # Prefer a visible trending-video card.
    for i, line in enumerate(lines):
        if re.match(r"(?i)^video views\\b", line):
            before = [x for x in lines[max(0, i-10):i] if len(x) > 2]
            usable = [x for x in before if x.lower() not in skip and not x.lower().startswith("image")]
            if usable:
                title = usable[-2] if len(usable) >= 2 else usable[-1]
                creator = usable[-1] if len(usable) >= 2 else ""
                return {"type":"video","title":title[:160],"creator":creator[:80],"metric":line[:80],"source":source}

    # Fallback is still TikTok's own UK trend list.
    for i, line in enumerate(lines):
        m = re.search(r"(#[A-Za-z0-9_ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]+)", line)
        if m:
            tag = m.group(1)
            metric = ""
            near = " ".join(lines[i:i+8])
            mm = re.search(r"([0-9][0-9.,KMBkmb]*\\s+(?:Posts|Views))", near)
            if mm:
                metric = mm.group(1)
            return {"type":"hashtag","title":tag[:80],"creator":"","metric":metric,"source":source}
    return None

def jina_read(url):
    proxy = "https://r.jina.ai/" + url
    req = urllib.request.Request(proxy, headers={"User-Agent":"Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read().decode("utf-8", "replace")

def find_trend(page):
    # First use a free text reader for TikTok's public Creative Center pages.
    for url in (VIDEO_URL, HASHTAG_URL):
        try:
            found = parse_text(jina_read(url), url)
            if found:
                return found
        except Exception:
            pass

    # Browser fallback if the text reader is temporarily unavailable.
    for url in (VIDEO_URL, HASHTAG_URL):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(10000)
            found = parse_text(page.locator("body").inner_text(timeout=15000), url)
            if found:
                return found
        except Exception:
            pass

    raise RuntimeError("TikTok Creative Center did not expose a usable trend.")

def font(size, bold=False):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for p in paths:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

def wrap(draw, text, fnt, max_width):
    words = text.split()
    lines, cur = [], ""
    for word in words:
        test = (cur + " " + word).strip()
        if draw.textbbox((0,0), test, font=fnt)[2] <= max_width:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines

def slide(filename, top, main, bottom):
    img = Image.new("RGB", (1080, 1920), (16, 18, 26))
    d = ImageDraw.Draw(img)
    # simple original background
    for y in range(1920):
        shade = int(16 + 28 * y / 1919)
        d.line((0, y, 1080, y), fill=(shade, 20, 48))
    d.rounded_rectangle((70, 120, 1010, 1800), radius=55, fill=(24, 27, 39), outline=(90, 95, 125), width=3)
    f1, f2, f3 = font(54, True), font(90, True), font(42, False)
    d.text((110, 210), top, font=f1, fill=(220,220,230))
    y = 520
    for line in wrap(d, main, f2, 850):
        d.text((110, y), line, font=f2, fill=(255,255,255))
        y += 115
    y = 1450
    for line in wrap(d, bottom, f3, 850):
        d.text((110, y), line, font=f3, fill=(205,205,220))
        y += 60
    img.save(filename)

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        trend = find_trend(page)
        browser.close()

    title = clean(trend["title"])
    metric = clean(trend.get("metric", ""))
    creator = clean(trend.get("creator", ""))

    hook = "AI SPRAWDZIŁO TIKTOK"
    main_text = title if title else "Nowy trend"
    detail = "Trend znaleziony teraz w publicznym TikTok Creative Center."
    if metric:
        detail += " " + metric
    if creator:
        detail += " Twórca: " + creator + "."

    narration = (
        "Jestem AI i właśnie sprawdziłem trendy na TikToku. "
        f"Jeden z najmocniejszych trendów teraz to {title}. "
        "Sprawdzamy, czy ten trend będzie rósł dalej. Co o tym sądzisz?"
    )

    slide(OUT/"01.png", hook, main_text, detail)
    slide(OUT/"02.png", "TREND TERAZ", main_text, "Nie kopiuję cudzego filmu. To własny materiał inspirowany publicznym trendem.")
    slide(OUT/"03.png", "CO MYŚLISZ?", "WCHODZI W VIRAL?", "Napisz TAK albo NIE w komentarzu.")

    (OUT/"narration.txt").write_text(narration, encoding="utf-8")
    tags = []
    if title.startswith("#"):
        tags.append(title)
    tags += ["#tiktoktrend", "#viral", "#trending", "#ai"]
    caption = f"{title} — AI znalazło ten trend teraz. Co o nim myślisz? " + " ".join(tags)
    (OUT/"caption.txt").write_text(caption[:2200], encoding="utf-8")

    trend["generated_at_utc"] = datetime.now(timezone.utc).isoformat()
    (OUT/"trend.json").write_text(json.dumps(trend, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(trend, ensure_ascii=False))

if __name__ == "__main__":
    main()
