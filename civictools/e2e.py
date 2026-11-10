"""Load the built site in headless Chrome and check the parts that need a browser.

  python3 -m civictools.e2e [_site]

Serves the build at the same path it has on the web, then checks that the receipt drawn in the
browser equals the one calculated here, cent for cent, by purpose and by agency; that a share link
restores its amount; that the comment search loads and its filter counts what the data says; and
that the FOIA builder writes its letter.
Skips (exit 0, with a warning) when no Chrome is installed; GitHub's runners have Chrome.
"""
import functools
import http.server
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from html import unescape
from urllib.parse import urlsplit

from . import receipt
from .common import ROOT, load_config, read_json, site_url
from .og import find_chrome
from .refresh import path as data_file


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def dump(chrome, url, profile):
    cmd = [chrome, "--headless=new", "--disable-gpu", "--no-sandbox", "--mute-audio", f"--user-data-dir={profile}",
           "--virtual-time-budget=9000", "--dump-dom", url]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120).stdout


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    site_dir = os.path.abspath(argv[0] if argv else os.path.join(ROOT, "_site"))
    chrome = find_chrome()
    if not chrome:
        print("::warning::e2e skipped: no Chrome found")
        return 0
    base = urlsplit(site_url(load_config())).path.strip("/")
    tre = read_json(data_file("treasury"))
    latest = tre["fiscal_years"][tre["latest"]]
    with open(os.path.join(site_dir, "assets", "comments.json"), encoding="utf-8") as f:
        idx = json.load(f)
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        web = os.path.join(tmp, "web")
        os.makedirs(web)
        if base:
            os.makedirs(os.path.dirname(os.path.join(web, base)), exist_ok=True)
            os.symlink(site_dir, os.path.join(web, base))
        else:
            os.rmdir(web)
            os.symlink(site_dir, web)
        srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=web))
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        root = f"http://127.0.0.1:{srv.server_address[1]}/{base + '/' if base else ''}"
        try:
            n = 0

            def page(path):
                nonlocal n
                n += 1
                return dump(chrome, root + path, os.path.join(tmp, f"profile{n}"))

            for view, key in (("purpose", "functions"), ("agency", "agencies")):
                for cents, shown in ((1234567, "12345.67"), (100, "1"), (987_654_321, "9876543.21")):
                    lines = sorted((receipt.cents(x["amount"]) for x in latest[key]), reverse=True)
                    want = [receipt.usd(c) for c in receipt.allocate(cents, lines)]
                    html = page(f"taxpayer-receipt/#amount={shown}" + ("&view=agency" if view == "agency" else ""))
                    rows = re.search(r'id="receipt-rows">(.*?)</div>\s*<div class="sum">', html, re.S)
                    got = [unescape(x) for x in re.findall(r'<span class="amt">([^<]+)</span>', rows.group(1))] if rows else []
                    if f'data-receipt="{cents}:{view}"' not in html:
                        problems.append(f"receipt: the share link for ${shown} ({view}) was not applied")
                    elif got != want:
                        bad = next((i for i, (a, b) in enumerate(zip(got, want)) if a != b), None)
                        problems.append(f"receipt: ${shown} by {view} differs from the calculation here (line {bad}: {got[bad] if bad is not None else len(got)} vs {want[bad] if bad is not None else len(want)})")
                    if f'id="receipt-sum">{receipt.usd(cents)}<' not in html:
                        problems.append(f"receipt: ${shown} by {view} does not total {receipt.usd(cents)}")
            html = page("comment-deadlines/")
            m = re.search(r'id="count"[^>]*>([\d,]+) documents? open for comment', html)
            total = int(m.group(1).replace(",", "")) if m else None
            if total is None or total > len(idx["docs"]) or total < len(idx["docs"]) * 0.8 or 'id="finder" hidden' in html:
                problems.append(f"comment search: shows {total} documents; the index has {len(idx['docs'])}")
            if "Proposed rule" in idx["types"]:
                t = idx["types"].index("Proposed rule")
                html = page(f"comment-deadlines/?t={t}")
                m = re.search(r'id="count"[^>]*>([\d,]+) documents? open for comment', html)
                got = int(m.group(1).replace(",", "")) if m else None
                want = sum(1 for d in idx["docs"] if d[2] == t)
                if got is None or got > want or got < want * 0.8:
                    problems.append(f"comment search: the proposed-rule filter shows {got}; the index has {want}")
                if got and ">Notice ·" in re.search(r'id="docs">(.*?)</ul>', html, re.S).group(1):
                    problems.append("comment search: the proposed-rule filter lists a notice")
            html = page("foia-request-builder/")
            letter = re.search(r'<pre id="letter">(.*?)</pre>', html, re.S)
            if not letter or "To: FOIA Officer, [AGENCY OR OFFICE]" not in letter.group(1) or "5 U.S.C. § 552" not in letter.group(1):
                problems.append("FOIA builder: the letter was not written by the page script")
        finally:
            srv.shutdown()
    for p in problems:
        print("E2E", p)
    print(f"e2e: receipt arithmetic (6 cases), share links, comment search and FOIA builder checked in Chrome; {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
