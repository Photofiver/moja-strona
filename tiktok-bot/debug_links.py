#!/usr/bin/env python3
from playwright.sync_api import sync_playwright
import re

URL="https://ads.tiktok.com/creative/creativeCenter/trends/video?countryCode=GB&period=7&region=GB"

with sync_playwright() as p:
    b=p.chromium.launch(headless=True)
    page=b.new_page(viewport={"width":1440,"height":1200})
    page.goto(URL,wait_until="domcontentloaded",timeout=60000)
    page.wait_for_timeout(12000)
    print("TITLE",page.title())
    for a in page.locator("a").all():
        try:
            href=a.get_attribute("href") or ""
            txt=(a.inner_text() or "").strip().replace("\n"," ")
            if href:
                print("A",repr(txt[:120]),href)
        except:
            pass
    html=page.content()
    pats=re.findall(r'https?[^"\\\\ ]*tiktok[^"\\\\ ]*',html,re.I)
    print("PATTERNS")
    for x in pats[:100]:
        print(x)
    b.close()
