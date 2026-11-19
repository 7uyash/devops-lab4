"""Screenshot pages of the Argo CD UI. Logs in through the API (POST /api/v1/session) and passes the
session token to the browser as the argocd.token cookie.
usage: python scripts/argo_shot.py BASE_URL PASSWORD OUT_DIR"""
import json
import sys
import urllib.request

from playwright.sync_api import sync_playwright

base, password, out = sys.argv[1:4]
req = urllib.request.Request(f"{base}/api/v1/session", method="POST",
                             data=json.dumps({"username": "admin", "password": password}).encode(),
                             headers={"Content-Type": "application/json"})
token = json.load(urllib.request.urlopen(req, timeout=10))["token"]  # nosec B310 - local Argo CD

pages = [("applications", "argocd_apps.png", 4000),
         ("applications/argocd/shoplite?view=tree&resource=", "argocd_tree.png", 6000),
         ("applications/argocd/shoplite?view=tree&resource=&node=argoproj.io%2FApplication%2Fargocd%2Fshoplite%2F0"
          "&tab=events", "argocd_events.png", 4000)]
with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={"width": 1600, "height": 950})
    ctx.add_cookies([{"name": "argocd.token", "value": token, "url": base}])
    page = ctx.new_page()
    for path, name, wait in pages:
        # the UI keeps a live event stream open, so "networkidle" never happens - wait for load + a delay
        page.goto(f"{base}/{path}", wait_until="load", timeout=120000)
        page.wait_for_timeout(wait)
        page.screenshot(path=f"{out}/{name}")
    b.close()
print("saved Argo CD screenshots to", out)
