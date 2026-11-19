"""Take a browser screenshot of a page: python scripts/shot.py URL OUT.png [--wait S] [--width W] [--height H] [--full] [--selector CSS]"""
import argparse

from playwright.sync_api import sync_playwright

ap = argparse.ArgumentParser()
ap.add_argument("url")
ap.add_argument("out")
ap.add_argument("--wait", type=float, default=5)
ap.add_argument("--width", type=int, default=1600)
ap.add_argument("--height", type=int, default=1000)
ap.add_argument("--full", action="store_true")
ap.add_argument("--selector", default=None, help="wait for this element before the screenshot")
a = ap.parse_args()

with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": a.width, "height": a.height}, device_scale_factor=1)
    page.goto(a.url, wait_until="networkidle", timeout=120000)
    if a.selector:
        page.wait_for_selector(a.selector, timeout=120000)
    page.wait_for_timeout(int(a.wait * 1000))
    page.screenshot(path=a.out, full_page=a.full)
    b.close()
print("saved", a.out)
