"""Log in to the Argo CD UI and screenshot pages.
usage: python scripts/argo_shot.py BASE_URL PASSWORD OUT_DIR"""
import sys

from playwright.sync_api import sync_playwright

base, password, out = sys.argv[1:4]
with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 1600, "height": 950})
    page.goto(f"{base}/login", wait_until="networkidle", timeout=120000)
    page.fill("input[name=username]", "admin")
    page.fill("input[name=password]", password)
    page.click("button[type=submit]")
    page.wait_for_url("**/applications**", timeout=60000)
    page.wait_for_timeout(3000)
    page.screenshot(path=f"{out}/argocd_apps.png")
    page.goto(f"{base}/applications/argocd/shoplite?view=tree&resource=", wait_until="networkidle")
    page.wait_for_timeout(5000)
    page.screenshot(path=f"{out}/argocd_tree.png")
    page.goto(f"{base}/applications/argocd/shoplite?view=tree&resource=&node=argoproj.io%2FApplication%2Fargocd%2Fshoplite%2F0&tab=events", wait_until="networkidle")
    page.wait_for_timeout(3000)
    page.screenshot(path=f"{out}/argocd_events.png")
    b.close()
print("saved Argo CD screenshots to", out)
