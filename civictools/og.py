"""Open Graph share cards (1200x630 PNG), rendered with headless Chrome after civictools.build.

  python3 -m civictools.og [--site _site]

Cards are drawn for the home page, the three tools and each spending line. Every other page uses
static/og-default.png. Without Chrome, or if a render fails, the default card is used, so no page
points at a missing image and a Chrome problem never blocks a deploy.
"""
import argparse
import concurrent.futures
import json
import os
import shutil
import subprocess
import sys
import tempfile
from html import escape as E

from .common import ROOT

CHROMES = [os.environ.get("CHROME", ""), "google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
           "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
DEFAULT = os.path.join(ROOT, "static", "og-default.png")
CSS = """
*{box-sizing:border-box}html,body{margin:0;width:1200px;height:630px;overflow:hidden}
body{background:linear-gradient(127deg,#071a3f 0 66%,#102b62 66%);color:#fff;font-family:Montserrat,"Avenir Next","Helvetica Neue",Helvetica,Arial,"Liberation Sans","DejaVu Sans",sans-serif;
  border-bottom:14px solid #ef2328;padding:54px 68px;display:flex;flex-direction:column}
.brand{font-size:34px;font-weight:900;letter-spacing:-1px}.brand b{color:#ff4a4f}.brand i{font-style:normal;color:#84aaff}
.brand span{font-size:16px;letter-spacing:.2em;text-transform:uppercase;color:#c9d6f5;margin-left:16px;font-weight:800}
.eyebrow{font-size:17px;letter-spacing:.2em;text-transform:uppercase;color:#9db7ff;margin-top:48px;font-weight:800}
h1{font-weight:900;line-height:.98;letter-spacing:-2.5px;margin:14px 0 0;max-height:310px;overflow:hidden;text-transform:uppercase}
.sub{font-size:28px;color:#dfe6f7;margin-top:auto}
.foot{font-size:20px;color:#ffbf31;margin-top:16px;font-weight:700}
"""


def find_chrome():
    for c in CHROMES:
        if c and (os.path.exists(c) or shutil.which(c)):
            return shutil.which(c) or c
    return None


def render(chrome, title, subtitle, out_png):
    size = 84 if len(title) < 34 else 68 if len(title) < 56 else 52
    html = (f"<!doctype html><html><head><meta charset='utf-8'><style>{CSS}h1{{font-size:{size}px}}</style></head><body>"
            f"<div class='brand'><b>America</b><i>.co</i><span>Public tools</span></div>"
            f"<div class='eyebrow'>America public resource desk</div><h1>{E(title)}</h1>"
            f"<div class='sub'>{E(subtitle)}</div><div class='foot'>Not left. Not right. Up.</div></body></html>")
    with tempfile.TemporaryDirectory() as d:
        src = os.path.join(d, "card.html")
        with open(src, "w", encoding="utf-8") as f:
            f.write(html)
        cmd = [chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--hide-scrollbars", "--mute-audio",
               "--force-device-scale-factor=1", "--window-size=1200,630", f"--user-data-dir={os.path.join(d, 'profile')}",
               "--virtual-time-budget=3000", f"--screenshot={out_png}", "file://" + src]
        subprocess.run(cmd, check=True, timeout=90, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return os.path.exists(out_png) and os.path.getsize(out_png) > 1000


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default=os.path.join(ROOT, "_site"))
    ap.add_argument("--default", action="store_true", help="draw static/og-default.png and stop")
    a = ap.parse_args(argv)
    chrome = find_chrome()
    if a.default:
        ok = chrome and render(chrome, "Follow the money. Read the rule. Find the record.",
                               "Three free public tools, no account", DEFAULT)
        print("og: default card", "written" if ok else "NOT written")
        return 0 if ok else 1
    jobs_path = os.path.join(a.site, "og-jobs.json")
    with open(jobs_path, encoding="utf-8") as f:
        jobs = {j[0]: j for j in json.load(f)}
    os.remove(jobs_path)
    out_dir = os.path.join(a.site, "og")
    os.makedirs(out_dir, exist_ok=True)
    shutil.copyfile(DEFAULT, os.path.join(out_dir, "default.png"))

    def one(job):
        key, title, sub = job
        out = os.path.join(out_dir, key + ".png")
        try:
            if chrome and render(chrome, title, sub, out):
                return 1
        except Exception as e:  # a Chrome hiccup must not stop a deploy
            print(f"og: {key}: {type(e).__name__}")
        shutil.copyfile(DEFAULT, out)
        return 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        made = sum(ex.map(one, jobs.values()))
    print(f"og: {made} rendered, {len(jobs) - made} fell back to the default card")
    return 0


if __name__ == "__main__":
    sys.exit(main())
