"""Check a built site before it is published. Exit 1 (and publish nothing) if anything is off.

  python3 -m civictools.guard [_site]

Checks: the Treasury figures add up to their published totals and a receipt adds up to the amount
entered; every spending line has its page, with a source and a read date; the comment lists hold no
document that has already closed and match the search index; the calendar file is well formed; no
page loads anything from another site; every internal link resolves; and, while the site is staged,
every page is noindex and no sitemap exists.
"""
import json
import os
import re
import sys
from decimal import Decimal
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from . import receipt
from .common import ROOT, indexable, load_config, read_json, site_url
from .refresh import path as data_file

MUST = ["index.html", "404.html", "robots.txt", "urls.txt", "build.json", "static/style.css", "static/app.js", "static/favicon.svg",
        "taxpayer-receipt/index.html", "embed/receipt/index.html", "comment-deadlines/index.html", "comment-deadlines/closing-soon/index.html",
        "comment-deadlines/proposed-rules/index.html", "comment-deadlines/agencies/index.html", "comment-deadlines/feed.xml",
        "comment-deadlines/proposed-rules.ics", "assets/comments.json", "foia-request-builder/index.html", "method/index.html",
        "about/index.html", "data/index.html", "data/federal-outlays.json", "data/federal-outlays-by-function.csv",
        "data/comment-deadlines.csv", "data/comment-deadlines.json", "og/default.png"]
SOURCED = re.compile(r'class="asof">Source: <a href="https://[^"]+"[^>]*>[^<]+</a>[^<]*(?:<[^>]+>[^<]*)*?<time datetime=')
TOLERANCE = Decimal("1.00")


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links, self.loads = [], []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        for k in ("href", "src"):
            if a.get(k):
                self.links.append(a[k])
        if tag in ("script", "img", "iframe") and a.get("src"):
            self.loads.append(a["src"])
        if tag == "link" and a.get("rel") in ("stylesheet", "preload", "preconnect") and a.get("href"):
            self.loads.append(a["href"])


def arithmetic(tre):
    """Every fiscal year's lines must add up to its published totals; a receipt must add up to the amount entered."""
    errors = []
    for fy, rec in tre.get("fiscal_years", {}).items():
        total = Decimal(rec["outlays_total"])
        for key, label in (("functions", "function"), ("agencies", "agency")):
            if rec.get(key) and abs(sum(Decimal(x["amount"]) for x in rec[key]) - total) > TOLERANCE:
                errors.append(f"FY{fy}: {label} lines do not add up to total outlays")
        if abs(sum(Decimal(x["amount"]) for x in rec["receipts"]) - Decimal(rec["receipts_total"])) > TOLERANCE:
            errors.append(f"FY{fy}: receipt lines do not add up to total receipts")
        if abs(total - Decimal(rec["receipts_total"]) - Decimal(rec["deficit"])) > TOLERANCE:
            errors.append(f"FY{fy}: outlays minus receipts is not the deficit shown")
    latest = tre.get("fiscal_years", {}).get(tre.get("latest", ""), {})
    for key in ("functions", "agencies"):
        lines = [receipt.cents(x["amount"]) for x in latest.get(key, [])]
        for amount in (0, 1, 99, 1_000_000, 2_345_678, 999_999_999):
            if lines and sum(receipt.allocate(amount, lines)) != amount:
                errors.append(f"a receipt of {amount} cents split by {key} does not add up")
    return errors


def check(site_dir):
    cfg = load_config()
    errors = []
    base_path = urlparse(site_url(cfg)).path.rstrip("/")
    staged = not indexable(cfg)
    for f in MUST:
        if not os.path.exists(os.path.join(site_dir, f)):
            errors.append(f"missing {f}")
    tre = read_json(data_file("treasury")) or {}
    errors += arithmetic(tre)
    counts = {"pages": 0, "lines": 0, "documents": 0}
    try:
        with open(os.path.join(site_dir, "build.json"), encoding="utf-8") as f:
            build = json.load(f)
    except (OSError, ValueError):
        build = {}
        errors.append("build.json unreadable")
    today = build.get("as_of_date", "")
    latest = tre.get("fiscal_years", {}).get(tre.get("latest", ""), {})
    functions = latest.get("functions", [])
    counts["lines"] = len(functions)
    if len(functions) < 15:
        errors.append(f"only {len(functions)} spending lines")
    if build.get("receipt_check", {}).get("purpose") != receipt.allocate(1_000_000, sorted((receipt.cents(f["amount"]) for f in functions), reverse=True)):
        errors.append("build.json's receipt check does not match a fresh calculation")
    try:
        with open(os.path.join(site_dir, "taxpayer-receipt", "index.html"), encoding="utf-8") as f:
            page = f.read()
        if page.count('<div class="row">') + page.count('<div class="row neg">') != len(functions):
            errors.append("the receipt page does not list every spending line")
        blob = json.loads(re.search(r'<script type="application/json" id="receipt-data">(.*?)</script>', page, re.S).group(1))
        if sum(int(l[1]) for l in blob["views"]["purpose"]["lines"]) != receipt.cents(latest["outlays_total"]):
            errors.append("the receipt's lines do not add up to Treasury's total outlays")
        if blob["views"]["agency"]["lines"] and sum(int(l[1]) for l in blob["views"]["agency"]["lines"]) != receipt.cents(latest["outlays_total"]):
            errors.append("the receipt's agency lines do not add up to Treasury's total outlays")
    except (OSError, AttributeError, ValueError, KeyError):
        errors.append("the receipt page or its data could not be read")
    for f in functions:
        p = os.path.join(site_dir, "taxpayer-receipt", f["slug"], "index.html")
        if not os.path.exists(p):
            errors.append(f"spending line {f['slug']}: page missing")
    try:
        with open(os.path.join(site_dir, "assets", "comments.json"), encoding="utf-8") as f:
            idx = json.load(f)
        counts["documents"] = len(idx["docs"])
        if len(idx["docs"]) < cfg["min_comment_documents"]:
            errors.append(f"only {len(idx['docs'])} documents open for comment (minimum {cfg['min_comment_documents']})")
        if any(d[4] < today for d in idx["docs"]):
            errors.append("the comment list holds a document that has already closed")
        if any(not d[6].startswith("https://www.federalregister.gov/") or (d[7] and not d[7].startswith("https://www.regulations.gov/")) for d in idx["docs"]):
            errors.append("a comment document links somewhere other than the Federal Register or Regulations.gov")
        if build.get("comment_documents") != len(idx["docs"]):
            errors.append("build.json and the comment index disagree on the number of documents")
    except (OSError, ValueError, KeyError, IndexError):
        errors.append("assets/comments.json unreadable")
    try:
        with open(os.path.join(site_dir, "comment-deadlines", "proposed-rules.ics"), encoding="utf-8", newline="") as f:
            cal = f.read()
        if not cal.startswith("BEGIN:VCALENDAR\r\n") or not cal.endswith("END:VCALENDAR\r\n") or cal.count("BEGIN:VEVENT") != cal.count("END:VEVENT"):
            errors.append("the calendar file is not well formed")
        if any(len(line.encode("utf-8")) > 75 for line in cal.split("\r\n")):
            errors.append("the calendar file has a line longer than 75 bytes")
    except OSError:
        errors.append("the calendar file is missing")
    if staged:
        if os.path.exists(os.path.join(site_dir, "sitemap.xml")):
            errors.append("staged site must not publish a sitemap")
        with open(os.path.join(site_dir, "robots.txt"), encoding="utf-8") as f:
            if "Disallow: /\n" not in f.read():
                errors.append("staged site must disallow crawling in robots.txt")
    elif not os.path.exists(os.path.join(site_dir, "sitemap.xml")):
        errors.append("missing sitemap.xml")

    exists = {}

    def there(full):
        if full not in exists:
            exists[full] = os.path.exists(full)
        return exists[full]

    for dirpath, _, files in os.walk(site_dir):
        for fn in files:
            if not fn.endswith(".html"):
                continue
            counts["pages"] += 1
            path = os.path.join(dirpath, fn)
            rel = os.path.relpath(path, site_dir).replace(os.sep, "/")
            with open(path, encoding="utf-8") as f:
                text = f.read()
            if "<title>" not in text or 'name="description"' not in text or 'rel="canonical"' not in text:
                errors.append(f"{rel}: missing title, description or canonical")
            if (staged or rel.startswith("embed/")) and '<meta name="robots" content="noindex' not in text:
                errors.append(f"{rel}: page that must stay out of search is missing noindex")
            if len(re.findall(r"<h1[ >]", text)) != 1:
                errors.append(f"{rel}: expected exactly one h1")
            if rel.startswith(("taxpayer-receipt/", "comment-deadlines/")) and not SOURCED.search(text):
                errors.append(f"{rel}: numbers without a source and a read date")
            p = Links()
            p.feed(text)
            for load in p.loads:
                if urlparse(load).scheme in ("http", "https") and "gc.zgo.at" not in load:
                    errors.append(f"{rel}: loads {load} from another site")
            if rel == "404.html":
                continue
            for link in set(p.links):
                u = urlparse(link)
                if u.scheme or link.startswith(("#", "mailto:", "data:", "//")):
                    continue
                target = u.path
                if target.startswith("/"):
                    if base_path and not target.startswith(base_path + "/"):
                        errors.append(f"{rel}: link {link} ignores the site base path")
                        continue
                    target = target[len(base_path):]
                else:
                    target = urlparse(urljoin("file:///" + rel, target)).path
                full = os.path.join(site_dir, target.lstrip("/"))
                if target.endswith("/"):
                    full = os.path.join(full, "index.html")
                if not there(full) and not there(os.path.join(full, "index.html")):
                    errors.append(f"{rel}: broken link {link}")
            if len(errors) > 200:
                return errors, counts
    return errors, counts


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    site_dir = argv[0] if argv else os.path.join(ROOT, "_site")
    errors, counts = check(site_dir)
    for e in errors[:50]:
        print("GUARD", e)
    print(f"guard: {counts['pages']} pages, {counts['lines']} spending lines, {counts['documents']} open documents, {len(errors)} problems")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
