#!/usr/bin/env python3
from playwright.sync_api import sync_playwright
from urllib.parse import quote
Q="Peacockpartner"
URL="https://www.tiktok.com/search/video?q="+quote(Q)
with sync_playwright() as p:
    b=p.chromium.launch(headless=True)
    page=b.new_page(viewport={"width":1440,"height":1200})
    page.goto(URL,wait_until="domcontentloaded",timeout=60000)
    page.wait_for_timeout(12000)
    print("TITLE",page.title())
    print("URL",page.url)
    seen=set()
    for a in page.locator('a[href*="/video/"]').all():
        try:
            href=a.get_attribute("href")
            if href and href not in seen:
                seen.add(href)
                print("VIDEO",href)
        except: pass
    print("COUNT",len(seen))
    b.close()
