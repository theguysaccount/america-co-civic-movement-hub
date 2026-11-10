"""Self-test of the live site. Exit 1 if anything a visitor would notice is broken, stale or does not add up.

  python3 -m civictools.selftest [--site-url URL] [--max-age-hours 60]

Reads only this project's own site. Checks the key pages, redoes the receipt arithmetic from the
published data and compares it with what the build recorded, checks that no closed document is
still listed, and that the staged or indexed state on the live site is the one this repository is
configured for. Prints `stale=true` on its own line when the build is older than the limit or the
comment list is out of date, so the workflow can start a refresh.
"""
import argparse
import concurrent.futures
import json
import sys
import urllib.error
import urllib.request
from datetime import timedelta
from decimal import Decimal

from . import receipt
from .common import eastern_today, indexable, load_config, now_utc, parse_iso, site_url


def fetch(url, ua):
    for _ in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": ua})
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.status, r.read()
        except urllib.error.HTTPError as e:
            if e.code < 500:
                return e.code, b""
        except Exception:
            pass
    return 0, b""


def main(argv=None):
    cfg = load_config()
    ap = argparse.ArgumentParser()
    ap.add_argument("--site-url", default=site_url(cfg))
    ap.add_argument("--max-age-hours", type=float, default=60)
    a = ap.parse_args(argv)
    base, ua = a.site_url.rstrip("/"), cfg["user_agent"]
    problems, stale = [], False
    now = now_utc()

    code, home = fetch(base + "/", ua)
    if code != 200:
        print(f"FAIL home page answered {code}")
        return 1
    want_index = indexable(cfg)
    has_noindex = b'<meta name="robots" content="noindex' in home
    if want_index and has_noindex:
        problems.append("the site is configured as indexable but the live home page is noindex")
    if not want_index and not has_noindex:
        problems.append("the site is configured as staged but the live home page is missing noindex")
    code, body = fetch(base + "/build.json", ua)
    try:
        build = json.loads(body)
        built = parse_iso(build["built_at"])
    except Exception:
        build, built = {}, None
        problems.append(f"build.json did not load (status {code})")
    if built is not None and now - built > timedelta(hours=a.max_age_hours):
        stale = True
        problems.append(f"the live build is from {build.get('built_at')} (limit {a.max_age_hours:g} hours)")
    read = parse_iso(build.get("comments_read"))
    if build and (read is None or now - read > timedelta(hours=cfg["stale_after_hours"]["comments"])):
        stale = True
        problems.append(f"the live comment list was read {build.get('comments_read') or 'never'} (limit {cfg['stale_after_hours']['comments']} hours)")

    # the receipt, recomputed from the data the site publishes
    code, body = fetch(base + "/data/federal-outlays.json", ua)
    try:
        data = json.loads(body)
        year = data["fiscal_years"][data["latest_fiscal_year"]]
        total = Decimal(year["outlays_total"])
        for key in ("functions", "agencies"):
            if abs(sum(Decimal(x["amount"]) for x in year[key]) - total) > 1:
                problems.append(f"published {key} for fiscal year {data['latest_fiscal_year']} do not add up to total outlays")
            lines = sorted((receipt.cents(x["amount"]) for x in year[key]), reverse=True)
            mine = receipt.allocate(build["receipt_check"]["amount_cents"], lines)
            theirs = build["receipt_check"]["purpose" if key == "functions" else "agency"]
            if mine != theirs or sum(mine) != build["receipt_check"]["amount_cents"]:
                problems.append(f"the receipt by {key} recomputed from the published data differs from the build's own figures")
        if data["latest_fiscal_year"] != build.get("fiscal_year"):
            problems.append("the data file and the build disagree on the fiscal year")
    except Exception as e:
        problems.append(f"federal-outlays.json could not be checked (status {code}, {type(e).__name__})")
        year = {"functions": []}

    code, body = fetch(base + "/assets/comments.json", ua)
    today = eastern_today(now)
    try:
        idx = json.loads(body)
        docs = idx["docs"]
        if len(docs) < cfg["min_comment_documents"]:
            problems.append(f"only {len(docs)} documents in the live comment index")
        closed = sum(1 for d in docs if d[4] < today)
        if closed and (now - (read or now)) > timedelta(hours=36):
            stale = True
            problems.append(f"{closed} listed documents have closed and the list has not been rebuilt for over 36 hours")
    except Exception:
        docs = []
        problems.append(f"the comment index did not load (status {code})")

    pages = ["/taxpayer-receipt/", "/embed/receipt/", "/comment-deadlines/", "/comment-deadlines/closing-soon/", "/comment-deadlines/proposed-rules/",
             "/comment-deadlines/agencies/", "/comment-deadlines/feed.xml", "/comment-deadlines/proposed-rules.ics", "/foia-request-builder/",
             "/method/", "/about/", "/data/", "/data/comment-deadlines.csv", "/data/federal-outlays-by-function.csv", "/static/style.css",
             "/static/app.js", "/og/default.png", "/robots.txt"]
    pages += [f"/taxpayer-receipt/{f['slug']}/" for f in year["functions"]]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(lambda p: (p, fetch(base + p, ua)), pages))
    for p, (c, body) in results:
        if c != 200:
            problems.append(f"{p} answered {c}")
        elif p.startswith("/taxpayer-receipt/") and b"<time datetime=" not in body:
            problems.append(f"{p} carries no read date")
    if not want_index:
        code, robots = fetch(base + "/robots.txt", ua)
        if b"Disallow: /" not in robots:
            problems.append("staged site's robots.txt does not disallow crawling")
    for p in problems[:40]:
        print("FAIL", p)
    print(f"selftest: {len(results)} URLs checked, receipt arithmetic redone from the published data, {len(docs)} open documents, {len(problems)} problems")
    print(f"stale={'true' if stale else 'false'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
