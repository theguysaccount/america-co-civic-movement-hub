"""Build the static site from data/.

  python3 -m civictools.build [--site _site]

Environment (all optional):
  SITE_URL          public base URL: the one setting to change at cutover
  SITE_INDEXABLE    "true" to allow indexing (the staged copy is noindex by default)
  GOATCOUNTER_URL   privacy-friendly page counts
  SPONSOR_URL, SPONSOR_NAME   the one marked sponsor slot
"""
import argparse
import csv
import io
import json
import os
import shutil
import sys
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal
from html import escape as E
from urllib.parse import urlsplit

from . import receipt
from .common import ROOT, clip, eastern_today, human_date, indexable, iso, load_config, money, now_utc, parse_iso, read_json, short_date, site_url
from .refresh import path as data_file

DEFAULT_AMOUNT = 1_000_000          # $10,000.00, in cents
TYPE_LABEL = {"Proposed Rule": "Proposed rule", "Rule": "Rule", "Notice": "Notice", "Presidential Document": "Presidential document"}
NOT_EARMARKED = ("Federal receipts are not earmarked taxpayer by taxpayer. The receipt applies each line's share of total outlays "
                 "to the amount you enter.")


def when(ts):
    if not ts:
        return "not yet read"
    return f'<time datetime="{E(ts)}">{human_date(ts)}</time>'


def days_left(closes, today):
    n = (date.fromisoformat(closes) - date.fromisoformat(today)).days
    return "closes today" if n == 0 else "closes tomorrow" if n == 1 else f"{n} days left" if n > 1 else "closed"


def pct(x):
    return f"{x:.1f}%"


def lines_for(items):
    """Receipt lines, largest first; negative lines (collections Treasury records as negative spending) come last."""
    rows = [{"name": i["name"], "slug": i.get("slug", ""), "cents": receipt.cents(i["amount"])} for i in items]
    rows.sort(key=lambda r: -r["cents"])
    total = sum(r["cents"] for r in rows)
    for r in rows:
        r["share"] = receipt.share(r["cents"], total)
    return rows, total


class Site:
    def __init__(self, out, now=None):
        self.cfg = load_config()
        self.url = site_url(self.cfg)
        self.base = urlsplit(self.url).path.rstrip("/")
        self.out = out
        self.now = now or now_utc()
        self.indexable = indexable(self.cfg)
        self.name = self.cfg["name"]
        self.repo_url = f"https://github.com/{self.cfg['repo']}"
        self.urls, self.og_jobs = [], []
        self.foot = ""

    def href(self, path):
        return self.base + path

    def write(self, rel, text):
        path = os.path.join(self.out, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)

    def page(self, path, title, description, body, *, hero="", jsonld=None, nav="", listed=True, og=None, lastmod="", extra_head="", bare=False):
        canonical = self.url + path
        full = title if "America.co" in title else f"{title} | America.co Public Tools"
        robots = "" if (self.indexable and listed) else '<meta name="robots" content="noindex, nofollow">\n'
        ld = ""
        for block in jsonld or []:
            safe = json.dumps(block, ensure_ascii=False).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
            ld += f'<script type="application/ld+json">{safe}</script>\n'
        gc = os.environ.get("GOATCOUNTER_URL", "").strip()
        analytics = f'<script data-goatcounter="{E(gc)}" async src="https://gc.zgo.at/count.js"></script>\n' if gc else ""
        og_file = "default.png"
        if og:
            og_file = og[0] + ".png"
            self.og_jobs.append(og)

        def nav_link(key, label, p):
            cur = ' aria-current="page"' if nav == key else ""
            return f'<a href="{self.href(p)}"{cur}>{label}</a>'

        sponsor_url, sponsor = os.environ.get("SPONSOR_URL", "").strip(), os.environ.get("SPONSOR_NAME", "").strip()
        slot = (f'<aside class="slot" aria-label="Sponsor"><small>Sponsor</small> These tools are supported by '
                f'<a href="{E(sponsor_url)}" rel="noopener sponsored">{E(sponsor)}</a>. Sponsors have no say over the data or the wording.</aside>'
                if sponsor_url.startswith("https://") and sponsor else "")
        head = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(full)}</title>
<meta name="description" content="{E(description)}">
{robots}<link rel="canonical" href="{E(canonical)}">
<meta name="site-base" content="{E(self.base)}">
<meta name="theme-color" content="#071a3f">
<meta property="og:type" content="website">
<meta property="og:site_name" content="America.co Public Tools">
<meta property="og:title" content="{E(title)}">
<meta property="og:description" content="{E(description)}">
<meta property="og:url" content="{E(canonical)}">
<meta property="og:image" content="{E(self.url)}/og/{og_file}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<link rel="icon" href="{self.href('/static/favicon.svg')}" type="image/svg+xml">
<link rel="stylesheet" href="{self.href('/static/style.css')}">
{extra_head}{ld}{analytics}</head>
"""
        if bare:
            html = head + f"<body class=\"bare\">\n{body}\n<script src=\"{self.href('/static/app.js')}\" defer></script>\n</body>\n</html>\n"
        else:
            html = head + f"""<body>
<a class="skip" href="#main">Skip to content</a>
<header class="top"><div class="wrap">
<a class="brand" href="{self.href('/')}"><b>America</b><i>.co</i><span>Public tools</span></a>
<nav aria-label="Main">
{nav_link('receipt', 'Taxpayer receipt', '/taxpayer-receipt/')}
{nav_link('comments', 'Comment deadlines', '/comment-deadlines/')}
{nav_link('foia', 'FOIA builder', '/foia-request-builder/')}
{nav_link('method', 'Sources', '/method/')}
{nav_link('data', 'Data', '/data/')}
</nav>
</div></header>
{hero}
<main id="main"><div class="wrap">
{body}
{slot}
</div></main>
<footer class="foot"><div class="wrap"><div class="cols">
<div><strong>Not left. Not right. Up.</strong><p>Free public tools from America.co. No account, no tracking of what you type, and a source
and a date on every number. This is the static edition: plain pages rebuilt from official data by an automated job.</p></div>
<div><strong>The tools</strong><ul>
<li><a href="{self.href('/taxpayer-receipt/')}">Federal taxpayer receipt</a></li>
<li><a href="{self.href('/comment-deadlines/')}">Rules open for public comment</a></li>
<li><a href="{self.href('/foia-request-builder/')}">FOIA request builder</a></li></ul></div>
<div><strong>The record</strong><ul>
<li><a href="{self.href('/method/')}">Sources and arithmetic</a></li>
<li><a href="{self.href('/data/')}">Open data</a></li>
<li><a href="{self.href('/about/')}">About, privacy and corrections</a></li>
<li><a href="{E(self.repo_url)}" rel="noopener">Source code</a></li></ul></div>
</div>
<p class="fine">{self.foot} The linked government record is always the authority. Nothing here is tax, legal or financial advice.
Not affiliated with the Treasury, the Federal Register or any agency.</p>
</div></footer>
<script src="{self.href('/static/app.js')}" defer></script>
</body>
</html>
"""
        rel = path.lstrip("/")
        if rel.endswith("/") or rel == "":
            rel += "index.html"
        self.write(rel, html)
        if listed and self.indexable:
            self.urls.append((canonical, lastmod or iso(self.now)[:10]))


FAVICON = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="7" fill="#071a3f"/>'
           '<path d="M6 22 16 7l10 15h-5l-5-8-5 8z" fill="#ef2328"/><rect x="6" y="24" width="20" height="3" fill="#84aaff"/></svg>')


def receipt_html(rows, amount_cents, link=None, limit=None):
    """The receipt as plain HTML (what a visitor without JavaScript sees; the script redraws the same thing).

    The split is always worked out over every line; `limit` only shortens what is shown."""
    parts = receipt.allocate(amount_cents, [r["cents"] for r in rows])
    top = max(abs(r["cents"]) for r in rows)
    out = []
    for r, c in list(zip(rows, parts))[:limit]:
        name = f'<a href="{link(r)}">{E(r["name"])}</a>' if link and r["slug"] else E(r["name"])
        neg = " neg" if r["cents"] < 0 else ""
        out.append(f'<div class="row{neg}"><span class="what">{name} <small>{pct(r["share"])}</small></span>'
                   f'<span class="amt">{receipt.usd(c)}</span><span class="bar"><i style="width:{abs(r["cents"]) * 100 / top:.2f}%"></i></span></div>')
    return "".join(out)


def doc_li(d, today, show_agency=True):
    agencies = "; ".join(a["name"] for a in d["agencies"])
    bits = [TYPE_LABEL.get(d["type"], d["type"])]
    if show_agency and agencies:
        bits.append(agencies)
    if d["dockets"]:
        bits.append(d["dockets"][0])
    bits.append("published " + short_date(d["published"]))
    comment = (f'<a class="btn sm" href="{E(d["comment_url"])}" rel="noopener">Comment</a>' if d["comment_url"]
               else '<span class="how">See the document for how to comment</span>')
    return (f'<li class="doc" data-closes="{E(d["closes"])}"><div><a href="{E(d["url"])}" rel="noopener">{E(d["title"])}</a>'
            f'<small>{E(" · ".join(bits))}</small></div><div class="due"><b>{E(short_date(d["closes"]))}</b>'
            f'<span class="left">{days_left(d["closes"], today)}</span>{comment}</div></li>')


def ics(docs, site, stamp):
    def fold(line):
        raw, out = line.encode("utf-8"), []
        while len(raw) > 73:
            cut = 73
            while cut > 0 and (raw[cut] & 0xC0) == 0x80:     # never split a UTF-8 character
                cut -= 1
            out.append(raw[:cut].decode("utf-8"))
            raw = b" " + raw[cut:]
        out.append(raw.decode("utf-8"))
        return "\r\n".join(out)

    def esc(s):
        return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", " ")

    host = urlsplit(site.url).hostname
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//America.co Public Tools//Comment deadlines//EN", "CALSCALE:GREGORIAN",
             "X-WR-CALNAME:Federal proposed rules: comment deadlines", f"X-WR-CALDESC:Source: Federal Register API. Built {stamp[:10]}."]
    for d in docs:
        day = d["closes"].replace("-", "")
        nxt = date.fromisoformat(d["closes"]).toordinal() + 1
        lines += ["BEGIN:VEVENT", f"UID:{d['number']}@{host}", f"DTSTAMP:{stamp.replace('-', '').replace(':', '')}",
                  f"DTSTART;VALUE=DATE:{day}", f"DTEND;VALUE=DATE:{date.fromordinal(nxt).strftime('%Y%m%d')}",
                  fold("SUMMARY:" + esc("Comments close: " + clip(d["title"], 140))),
                  fold("DESCRIPTION:" + esc("; ".join(a["name"] for a in d["agencies"]) + ". Confirm the deadline and how to comment in the document: " + d["url"])),
                  fold("URL:" + d["url"]), "TRANSP:TRANSPARENT", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def build(out, now=None):
    site = Site(out, now)
    cfg = site.cfg
    tre = read_json(data_file("treasury")) or {}
    com = read_json(data_file("comments")) or {"documents": []}
    agy = read_json(data_file("agencies")) or {"agencies": []}
    status = read_json(data_file("status"), {}) or {}
    if not tre.get("fiscal_years"):
        raise SystemExit("no Treasury data on file: run python3 -m civictools.refresh first")
    functions = read_json(os.path.join(ROOT, "config", "functions.json"))
    fy = tre["latest"]
    year = tre["fiscal_years"][fy]
    years = sorted(tre["fiscal_years"], key=int)
    src = tre["source"]
    today = eastern_today(site.now)
    docs = [d for d in com["documents"] if d["closes"] >= today]
    site.foot = (f"Spending figures: Monthly Treasury Statement for fiscal year {fy}, read {when(tre.get('retrieved_at', ''))}. "
                 f"Comment deadlines: Federal Register, read {when(com.get('retrieved_at', ''))}.")

    if os.path.isdir(out):
        shutil.rmtree(out)
    os.makedirs(out)
    shutil.copytree(os.path.join(ROOT, "static"), os.path.join(out, "static"))
    site.write("static/favicon.svg", FAVICON)

    def stale_note(name, label):
        st = status.get(name, {})
        if st and not st.get("ok", True):
            return (f'<p class="note warn"><b>The latest attempt to read {label} did not succeed</b> ({E(st.get("error", ""))[:200]}). '
                    f"What you see is from the last good read, on the date shown.</p>")
        return ""

    # ------------------------------------------------------------------ the receipt
    purpose, total_c = lines_for(year["functions"])
    by_agency, total_a = lines_for(year.get("agencies") or [])
    outlays, receipts_total, deficit = Decimal(year["outlays_total"]), Decimal(year["receipts_total"]), Decimal(year["deficit"])
    fy_source = (f'Source: <a href="{E(src["by_function"])}" rel="noopener">Monthly Treasury Statement</a>, U.S. Treasury, final statement for '
                 f'fiscal year {fy} (dated {human_date(year["record_date"])}), read {when(tre.get("retrieved_at", ""))}.')

    def fn_path(r):
        return site.href(f"/taxpayer-receipt/{r['slug']}/")

    blob = {"fy": fy, "record_date": year["record_date"], "read": (tre.get("retrieved_at") or "")[:10], "max": cfg["max_receipt_amount"],
            "base": site.url, "views": {"purpose": {"label": "By purpose", "lines": [[r["name"], str(r["cents"]), r["slug"]] for r in purpose]},
                                        "agency": {"label": "By agency", "lines": [[r["name"], str(r["cents"]), ""] for r in by_agency]}}}
    blob_html = json.dumps(blob, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c").replace("&", "\\u0026")
    neg_names = [r["name"] for r in purpose if r["cents"] < 0]
    neg_note = (f'<p class="note"><b>Why {"is one line" if len(neg_names) == 1 else "are some lines"} negative?</b> Treasury records certain collections '
                f'(fees, premiums, loan repayments, agencies\' payments toward employee retirement) as negative spending. In fiscal year {fy} '
                f'{" and ".join(E(n) for n in neg_names)} {"was" if len(neg_names) == 1 else "were"} below zero, so '
                f'{"it reduces" if len(neg_names) == 1 else "they reduce"} the total. Every line still adds up to the amount you enter.</p>' if neg_names else "")
    receipt_rows = "".join(
        f'<tr><td>{E(r["name"])}</td><td class="num">{money(float(r["amount"]))}</td><td class="num">{pct(float(Decimal(r["amount"]) * 100 / receipts_total))}</td></tr>'
        for r in sorted(year["receipts"], key=lambda r: -Decimal(r["amount"])))
    covers = "".join(f'<li><a href="{fn_path(r)}">{E(r["name"])}</a> <span>{E(functions.get(r["slug"], ""))}</span></li>' for r in purpose)
    embed_code = E(f'<iframe src="{site.url}/embed/receipt/" title="Federal taxpayer receipt" width="420" height="720" style="border:0;max-width:100%" loading="lazy"></iframe>')
    faq = [("Is each taxpayer's money literally divided this way?",
            "No. Federal receipts flow into the Treasury and are not tagged to an individual taxpayer. The receipt applies each line's share of total federal outlays to the amount entered, to make the scale understandable."),
           ("What is an outlay?", "An outlay is money the federal government actually paid out. It differs from an obligation, which is a promise to pay now or later."),
           ("What data does the receipt use?",
            f"The Monthly Treasury Statement from the U.S. Treasury's Bureau of the Fiscal Service: the final statement for fiscal year {fy}, which lists net outlays by budget function and by agency."),
           ("Does this estimate my taxes?", "No. It is a spending-share calculator. Enter the federal tax shown on your return, or any amount you want to understand.")]
    hero = f"""<section class="hero"><div class="wrap">
<p class="eyebrow">America public resource · Fiscal year {fy}</p>
<h1>Taxpayer money finally comes with a receipt.</h1>
<p class="lede">Enter the federal taxes you paid. See how that amount maps onto what the federal government actually paid out in fiscal year {fy}.</p>
</div></section>"""
    body = f"""{stale_note('treasury', 'the Treasury statement')}
<div class="workspace">
<form class="tool" id="receipt-form" onsubmit="return false">
<p class="kicker">Use the receipt</p>
<h2>Where did your money go?</h2>
<p>Use the federal taxes shown on your return, or any amount you want to understand. This is a spending-share calculator, not a tax estimator.</p>
<label for="amount">Federal taxes paid</label>
<div class="money"><span>$</span><input id="amount" name="amount" inputmode="decimal" autocomplete="off" value="10,000" aria-describedby="amount-help"></div>
<p class="help" id="amount-help">Up to ${cfg['max_receipt_amount']:,}. Nothing you type leaves this page.</p>
<div class="quick" role="group" aria-label="Example amounts">
{''.join(f'<button type="button" class="chip" data-amount="{a}">${a // 1000}K</button>' for a in (1000, 5000, 10000, 25000, 50000))}
</div>
<fieldset class="views"><legend>Split it</legend>
<label><input type="radio" name="view" value="purpose" checked> By purpose</label>
<label><input type="radio" name="view" value="agency"> By agency</label></fieldset>
<div class="actions">
<button type="button" class="btn primary" id="copy-link">Copy share link</button>
<button type="button" class="btn" id="download">Download receipt</button>
<button type="button" class="btn" id="print">Print</button>
</div>
<p class="status" id="receipt-status" role="status" aria-live="polite"></p>
</form>
<article class="receipt" id="receipt" aria-label="Your receipt">
<header><b>The people's receipt</b><span>America.co public resource desk</span></header>
<div class="total"><span>Amount allocated by spending share</span><strong id="receipt-total">{receipt.usd(DEFAULT_AMOUNT)}</strong></div>
<p class="meta">Federal fiscal year {fy} · <span id="receipt-view">By purpose</span></p>
<div class="rows" id="receipt-rows">{receipt_html(purpose, DEFAULT_AMOUNT, fn_path)}</div>
<div class="sum"><span>Total</span><strong id="receipt-sum">{receipt.usd(DEFAULT_AMOUNT)}</strong></div>
<p class="fine">Illustrative allocation. {NOT_EARMARKED} Net outlays, Monthly Treasury Statement, fiscal year {fy}; read {E(human_date(tre.get('retrieved_at', '')))}.</p>
</article>
</div>
<script type="application/json" id="receipt-data">{blob_html}</script>
{neg_note}
<div class="stats">
<div class="stat"><b>{money(float(outlays))}</b><span>Total federal outlays, fiscal year {fy}</span></div>
<div class="stat"><b>{money(float(receipts_total))}</b><span>Total federal receipts, fiscal year {fy}</span></div>
<div class="stat"><b>{money(float(deficit))}</b><span>Outlays above receipts (the deficit), fiscal year {fy}</span></div>
</div>
<p class="asof">{fy_source}</p>
<h2 id="lines">What each line covers</h2>
<ul class="covers">{covers}</ul>
<h2 id="came-from">Where the money came from</h2>
<div class="tablewrap"><table><thead><tr><th>Federal receipts by source, fiscal year {fy}</th><th class="num">Amount</th><th class="num">Share</th></tr></thead>
<tbody>{receipt_rows}</tbody><tfoot><tr><td>Total receipts</td><td class="num">{money(float(receipts_total))}</td><td class="num">100.0%</td></tr></tfoot></table></div>
<p class="asof">{fy_source}</p>
<h2 id="fine-print">Read the fine print</h2>
<div class="faq">
{''.join(f'<details><summary>{E(q)}</summary><p>{E(a)}</p></details>' for q, a in faq)}
<details><summary>How is the split calculated?</summary><p>Each line's amount is divided by total net outlays to get its share. Your amount is multiplied by
each share and rounded down to the cent; the few cents left over go to the lines with the largest remainders, so the receipt always adds up to
exactly what you entered. <a href="{site.href('/method/#receipt')}">The full method</a>.</p></details>
<details><summary>Mandatory, discretionary and interest</summary><p>Mandatory spending is set by existing law, discretionary spending is decided each year
through appropriations, and interest is the cost of financing the federal debt.
<a href="https://www.usa.gov/federal-budget-process" rel="noopener">USA.gov's guide to the federal budget process</a> explains the difference.
Treasury explains outlays and obligations in its <a href="https://fiscaldata.treasury.gov/americas-finance-guide/federal-spending/" rel="noopener">federal spending guide</a>.</p></details>
</div>
<h2 id="embed">Put the receipt on your site</h2>
<p>Paste this where the calculator should appear. It runs in the reader's browser and links back here.</p>
<pre class="code"><code>{embed_code}</code></pre>"""
    site.page("/taxpayer-receipt/", "Federal Taxpayer Receipt: Where Your Tax Dollars Go",
              f"Enter the federal taxes you paid and get an itemized receipt: how that amount maps onto what the government paid out in fiscal year {fy}, by purpose or by agency. Source: U.S. Treasury.",
              body, hero=hero, nav="receipt", og=("receipt", "Taxpayer money finally comes with a receipt.", f"Fiscal year {fy} · U.S. Treasury figures"),
              lastmod=(status.get("treasury", {}).get("last_changed") or tre.get("retrieved_at") or "")[:10],
              jsonld=[{"@context": "https://schema.org", "@type": "WebApplication", "name": "Federal Taxpayer Receipt", "url": site.url + "/taxpayer-receipt/",
                       "applicationCategory": "EducationalApplication", "operatingSystem": "Any", "isAccessibleForFree": True,
                       "description": f"An interactive calculator showing how a federal tax amount maps onto fiscal year {fy} federal outlays."},
                      {"@context": "https://schema.org", "@type": "FAQPage",
                       "mainEntity": [{"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]}])

    # the embeddable calculator: its own tiny page, never indexed
    site.page("/embed/receipt/", "Federal Taxpayer Receipt (embed)", f"A compact federal taxpayer receipt for fiscal year {fy}.",
              f"""<form class="tool embed" id="receipt-form" onsubmit="return false">
<label for="amount">Federal taxes paid</label>
<div class="money"><span>$</span><input id="amount" name="amount" inputmode="decimal" autocomplete="off" value="10,000"></div>
<fieldset class="views"><legend class="sr">Split it</legend>
<label><input type="radio" name="view" value="purpose" checked> By purpose</label>
<label><input type="radio" name="view" value="agency"> By agency</label></fieldset>
</form>
<article class="receipt" id="receipt">
<header><b>The people's receipt</b><span>Fiscal year {fy}</span></header>
<div class="total"><span>Amount allocated by spending share</span><strong id="receipt-total">{receipt.usd(DEFAULT_AMOUNT)}</strong></div>
<p class="meta"><span id="receipt-view">By purpose</span></p>
<h1 class="sr">Federal taxpayer receipt</h1>
<div class="rows" id="receipt-rows">{receipt_html(purpose, DEFAULT_AMOUNT)}</div>
<div class="sum"><span>Total</span><strong id="receipt-sum">{receipt.usd(DEFAULT_AMOUNT)}</strong></div>
<p class="fine">Illustrative. Federal receipts are not earmarked taxpayer by taxpayer. Source: Monthly Treasury Statement, fiscal year {fy}, read {E(short_date(tre.get('retrieved_at', '')))}.
<a href="{E(site.url)}/taxpayer-receipt/" target="_blank" rel="noopener">Full receipt and method at America.co Public Tools</a></p>
</article>
<script type="application/json" id="receipt-data">{blob_html}</script>""", listed=False, bare=True)

    # ------------------------------------------------------------------ one page per spending line
    history = {r["slug"]: [] for r in purpose}
    for y in years:
        rec = tre["fiscal_years"][y]
        tot = Decimal(rec["outlays_total"])
        for f in rec["functions"]:
            if f["slug"] in history:
                history[f["slug"]].append((y, Decimal(f["amount"]), Decimal(f["amount"]) * 100 / tot, rec["record_date"]))
    alloc = dict(zip((r["slug"] for r in purpose), receipt.allocate(DEFAULT_AMOUNT, [r["cents"] for r in purpose])))
    for i, r in enumerate(purpose):
        hist = history[r["slug"]]
        amount = Decimal(r["cents"]) / 100
        prev = hist[-2] if len(hist) > 1 else None
        change = ""
        if prev:
            diff = amount - prev[1]
            rel = f" ({abs(diff) * 100 / abs(prev[1]):.1f}%)" if prev[1] else ""
            change = (f'<div class="stat"><b>{"+" if diff >= 0 else "−"}{money(abs(float(diff)))}</b><span>{"more" if diff >= 0 else "less"} than fiscal year {prev[0]}{rel}</span></div>')
        top = max(abs(h[1]) for h in hist)
        rows = "".join(
            f'<tr><td>FY {y}</td><td class="num">{money(float(a))}</td><td class="num">{pct(float(s))}</td>'
            f'<td class="barcell"><i class="{"neg" if a < 0 else ""}" style="width:{float(abs(a) * 100 / top):.1f}%"></i></td></tr>' for y, a, s, _ in reversed(hist))
        negative = amount < 0
        lede = (f"{money(float(amount))} in fiscal year {fy}. Treasury recorded more collections than spending on this line, so it reduced total outlays."
                if negative else f"{money(float(amount))} in fiscal year {fy}: {pct(r['share'])} of everything the federal government paid out.")
        others = "".join(f'<a class="chip" href="{fn_path(o)}">{E(o["name"])}</a>' for o in purpose if o["slug"] != r["slug"])
        body = f"""<p class="crumbs"><a href="{site.href('/taxpayer-receipt/')}">Taxpayer receipt</a> › Line {i + 1} of {len(purpose)}</p>
<p class="kicker">Federal spending by purpose · Fiscal year {fy}</p>
<h1>{E(r['name'])}</h1>
<p class="lede">{lede}</p>
{stale_note('treasury', 'the Treasury statement')}
<div class="stats">
<div class="stat"><b>{money(float(amount))}</b><span>Net outlays, fiscal year {fy}</span></div>
<div class="stat"><b>{pct(r['share'])}</b><span>Share of total federal outlays</span></div>
<div class="stat"><b>{receipt.usd(alloc[r['slug']])}</b><span>Of a $10,000 receipt</span></div>
{change}
</div>
<p class="asof">{fy_source}</p>
<h2>What this line covers</h2>
<p>{E(functions.get(r['slug'], ''))}</p>
<p class="note">Budget functions group spending by purpose, whichever agency does the spending. The grouping is the federal budget's own; the one-line
description above is a plain-language summary, not a legal definition.</p>
<p><a class="btn primary" href="{site.href('/taxpayer-receipt/')}">Put your own amount on the receipt</a>
<a class="btn" href="https://www.usaspending.gov/explorer/budget_function" rel="noopener">Explore this budget function on USAspending.gov</a></p>
<h2>Year by year</h2>
<div class="tablewrap"><table><thead><tr><th>Fiscal year</th><th class="num">Net outlays</th><th class="num">Share of all outlays</th><th aria-hidden="true"></th></tr></thead><tbody>{rows}</tbody></table></div>
<p class="asof">Each row is the final (September) Monthly Treasury Statement for that fiscal year, not adjusted for inflation.
Source: <a href="{E(src['by_function'])}" rel="noopener">Monthly Treasury Statement, table 9</a>, read {when(tre.get('retrieved_at', ''))}.</p>
<h2>The other lines</h2>
<p class="chips">{others}</p>"""
        title = (f"Federal Spending on {r['name']}: {money(float(amount))} in Fiscal Year {fy}" if not negative
                 else f"{r['name']} in the Federal Budget: {money(float(amount))} in Fiscal Year {fy}")
        site.page(f"/taxpayer-receipt/{r['slug']}/", title,
                  f"{r['name']}: {money(float(amount))} in net federal outlays in fiscal year {fy}"
                  + ("" if negative else f", {pct(r['share'])} of the total") + f". Year-by-year figures since {years[0]} from the U.S. Treasury.",
                  body, nav="receipt", og=(f"line-{r['slug']}", r["name"], f"{money(float(amount))} in fiscal year {fy}" + ("" if negative else f" · {pct(r['share'])} of federal outlays")),
                  lastmod=(status.get("treasury", {}).get("last_changed") or tre.get("retrieved_at") or "")[:10])

    # ------------------------------------------------------------------ comment deadlines
    fr_source = (f'Source: <a href="{E(com.get("source", {}).get("search", "https://www.federalregister.gov/"))}" rel="noopener">Federal Register</a> API, '
                 f'read {when(com.get("retrieved_at", ""))}. Always confirm the deadline and how to comment in the document itself.')
    soon = [d for d in docs if (date.fromisoformat(d["closes"]) - date.fromisoformat(today)).days <= 7]
    proposed = [d for d in docs if d["type"] == "Proposed Rule"]
    by_agency_docs, agency_name = defaultdict(list), {}
    for d in docs:
        for a in d["agencies"]:
            if a["slug"]:
                by_agency_docs[a["slug"]].append(d)
                agency_name[a["slug"]] = a["name"]
    big = {s for s, v in by_agency_docs.items() if len(v) >= cfg["min_agency_list"]}
    stale_script = f'<p class="note warn" id="stale" hidden data-built="{E(today)}"></p>'
    sub_nav = (f'<p class="chips"><a class="chip" href="{site.href("/comment-deadlines/")}">Search all {len(docs):,}</a>'
               f'<a class="chip" href="{site.href("/comment-deadlines/closing-soon/")}">Closing within 7 days ({len(soon):,})</a>'
               f'<a class="chip" href="{site.href("/comment-deadlines/proposed-rules/")}">Proposed rules ({len(proposed):,})</a>'
               f'<a class="chip" href="{site.href("/comment-deadlines/agencies/")}">By agency ({len(by_agency_docs):,})</a></p>')
    comment_note = ('<p class="note">A date here is the Federal Register\'s “comments close on” date. Agencies sometimes extend or reopen a comment period, '
                    'and some accept comments only by mail or through their own system. The document is the authority.</p>')
    type_names = sorted({d["type"] for d in docs})
    agency_names = sorted({a["name"] for d in docs for a in d["agencies"]})
    t_idx, a_idx = {t: i for i, t in enumerate(type_names)}, {a: i for i, a in enumerate(agency_names)}
    site.write("assets/comments.json", json.dumps({
        "as_of": today, "read": com.get("retrieved_at", ""), "types": [TYPE_LABEL.get(t, t) for t in type_names], "agencies": agency_names,
        "docs": [[d["number"], d["title"], t_idx[d["type"]], [a_idx[a["name"]] for a in d["agencies"]], d["closes"], d["published"], d["url"],
                  d["comment_url"], d["abstract"], "; ".join(d["dockets"])] for d in docs]}, ensure_ascii=False, separators=(",", ":")))
    hero = f"""<section class="hero"><div class="wrap">
<p class="eyebrow">America public resource · Federal rulemaking</p>
<h1>Comment before it closes.</h1>
<p class="lede">{len(docs):,} federal documents are open for public comment today, {len(soon):,} of them closing within a week. Search them, then follow the link to the record and say your piece.</p>
</div></section>"""
    body = f"""{stale_note('comments', 'the Federal Register')}{stale_script}
{sub_nav}
<div class="finder" id="finder" hidden>
<label class="f q">Search titles, agencies and summaries<input type="search" name="q" autocomplete="off" placeholder="For example: drinking water, airworthiness, student loans"></label>
<label class="f">Kind of document<select name="t"><option value="">All</option></select></label>
<label class="f">Agency<select name="a"><option value="">All</option></select></label>
<label class="f">Closing<select name="w"><option value="">Any time</option><option value="7">Within 7 days</option><option value="14">Within 14 days</option><option value="30">Within 30 days</option></select></label>
</div>
<p class="count" id="count" role="status" aria-live="polite">{len(docs):,} documents open for comment. Showing the {min(60, len(docs))} that close soonest.</p>
<ul class="docs" id="docs">{''.join(doc_li(d, today) for d in docs[:60])}</ul>
<p><button class="btn" type="button" id="more" hidden>Show more</button></p>
<noscript><p class="note">Search needs JavaScript. Without it, use the lists by <a href="{site.href('/comment-deadlines/agencies/')}">agency</a>,
the <a href="{site.href('/comment-deadlines/proposed-rules/')}">proposed rules</a> or the documents <a href="{site.href('/comment-deadlines/closing-soon/')}">closing soon</a>.</p></noscript>
<p class="asof">{fr_source}</p>
{comment_note}
<h2>Keep up without checking back</h2>
<p><a class="btn" href="{site.href('/comment-deadlines/proposed-rules.ics')}">Proposed-rule deadlines for your calendar (.ics)</a>
<a class="btn" href="{site.href('/comment-deadlines/feed.xml')}">Newly opened comment periods (feed)</a></p>
<h2>How commenting works</h2>
<ul class="plain">
<li>Most comments are filed at <a href="https://www.regulations.gov/" rel="noopener">Regulations.gov</a>. The “Comment” button opens the form for that document when the Federal Register lists one.</li>
<li>The Federal Register's own guide: <a href="https://www.federalregister.gov/uploads/2011/01/the_rulemaking_process.pdf" rel="noopener">A Guide to the Rulemaking Process (PDF)</a>.</li>
<li>What agencies plan to propose next: the <a href="https://www.reginfo.gov/public/do/eAgendaMain" rel="noopener">Unified Agenda at Reginfo.gov</a>.</li>
</ul>"""
    site.page("/comment-deadlines/", "Federal Rules Open for Public Comment, With Deadlines",
              f"Every federal proposed rule and notice open for public comment today ({len(docs):,}), sorted by closing date, searchable by agency and topic, with a link to the comment form. Rebuilt daily from the Federal Register.",
              body, hero=hero, nav="comments", og=("comments", "Comment before it closes.", f"{len(docs):,} federal documents open for public comment"),
              lastmod=today, extra_head=f'<link rel="alternate" type="application/atom+xml" title="Newly opened comment periods" href="{site.href("/comment-deadlines/feed.xml")}">\n')

    def list_page(path, title, h1, lede, items, desc, show_agency=True, crumb=None):
        crumbs = f'<p class="crumbs"><a href="{site.href("/comment-deadlines/")}">Comment deadlines</a>' + (f' › <a href="{site.href(crumb[1])}">{E(crumb[0])}</a>' if crumb else "") + "</p>"
        site.page(path, title, desc, f"""{crumbs}
<p class="kicker">Open for public comment</p><h1>{E(h1)}</h1><p class="lede">{lede}</p>
{stale_note('comments', 'the Federal Register')}{stale_script}
<p class="asof">{fr_source}</p>
<ul class="docs">{''.join(doc_li(d, today, show_agency) for d in items) or '<li class="doc"><div>Nothing is open in this list today.</div></li>'}</ul>
{comment_note}
{sub_nav}""", nav="comments", lastmod=today)

    list_page("/comment-deadlines/closing-soon/", "Federal Comment Periods Closing This Week", "Closing within seven days",
              f"{len(soon):,} documents stop taking public comments in the next seven days.", soon,
              f"The {len(soon):,} federal proposed rules and notices whose public comment periods close within seven days, soonest first, from the Federal Register.")
    list_page("/comment-deadlines/proposed-rules/", "Proposed Federal Rules Open for Comment", "Proposed rules open for comment",
              f"{len(proposed):,} proposed rules are taking public comments today. These are the documents that become binding regulations.", proposed,
              f"All {len(proposed):,} proposed federal rules currently open for public comment, sorted by closing date, with links to each rule and its comment form.")
    for slug in sorted(big):
        items = by_agency_docs[slug]
        name = agency_name[slug]
        list_page(f"/comment-deadlines/agency/{slug}/", f"{name}: Rules and Notices Open for Public Comment", name,
                  f"{len(items):,} documents from this agency are open for public comment today.", items,
                  f"{len(items):,} {name} proposed rules and notices open for public comment, with closing dates and links to comment. Rebuilt daily from the Federal Register.",
                  show_agency=False, crumb=("By agency", "/comment-deadlines/agencies/"))
    rows = "".join(
        f'<tr><td>{f"""<a href="{site.href(f"/comment-deadlines/agency/{s}/")}">{E(agency_name[s])}</a>""" if s in big else E(agency_name[s])}</td>'
        f'<td class="num">{len(v):,}</td><td>{E(short_date(min(d["closes"] for d in v)))}</td></tr>'
        for s, v in sorted(by_agency_docs.items(), key=lambda kv: (-len(kv[1]), agency_name[kv[0]])))
    site.page("/comment-deadlines/agencies/", "Open Comment Periods by Federal Agency",
              f"How many documents each federal agency has open for public comment today, across {len(by_agency_docs):,} agencies, with the next closing date for each.",
              f"""<p class="crumbs"><a href="{site.href('/comment-deadlines/')}">Comment deadlines</a></p>
<p class="kicker">Open for public comment</p><h1>By agency</h1>
<p class="lede">{len(by_agency_docs):,} agencies have at least one document open for comment today. A document issued by a department and one of its bureaus is counted under both.</p>
<p class="asof">{fr_source}</p>
<div class="tablewrap"><table><thead><tr><th>Agency</th><th class="num">Open documents</th><th>Next closing date</th></tr></thead><tbody>{rows}</tbody></table></div>
<p class="note">Agencies with fewer than {cfg['min_agency_list']} open documents have no page of their own. Find them with the <a href="{site.href('/comment-deadlines/')}">search</a>.</p>
{sub_nav}""", nav="comments", lastmod=today)
    newest = sorted(docs, key=lambda d: (d.get("first_seen", ""), d["published"], d["number"]), reverse=True)[:60]
    site.write("comment-deadlines/feed.xml", '<?xml version="1.0" encoding="utf-8"?>\n<feed xmlns="http://www.w3.org/2005/Atom">'
               f'<title>Federal documents newly open for public comment</title><id>{E(site.url)}/comment-deadlines/</id>'
               f'<link href="{E(site.url)}/comment-deadlines/"/><link rel="self" href="{E(site.url)}/comment-deadlines/feed.xml"/>'
               f'<updated>{E(com.get("retrieved_at") or iso(site.now))}</updated><author><name>America.co Public Tools</name></author>'
               + "".join(f'<entry><title>{E(d["title"])}</title><id>{E(d["url"])}</id><link href="{E(d["url"])}"/>'
                         f'<updated>{E(d["published"])}T00:00:00Z</updated><summary>Comments close {E(human_date(d["closes"]))}. '
                         f'{E("; ".join(a["name"] for a in d["agencies"]))}. {E(d["abstract"])}</summary></entry>' for d in newest) + "</feed>\n")
    with open(os.path.join(out, "comment-deadlines", "proposed-rules.ics"), "w", encoding="utf-8", newline="") as f:
        f.write(ics(proposed, site, (com.get("retrieved_at") or iso(site.now)).replace("-", "").replace(":", "")))

    # ------------------------------------------------------------------ FOIA request builder
    options = "".join(f'<option value="{E(a)}">' for a in agy.get("agencies", []))
    hero = """<section class="hero"><div class="wrap">
<p class="eyebrow">America public resource · Freedom of Information Act</p>
<h1>Specific beats dramatic.</h1>
<p class="lede">Describe records rather than asking questions, name a realistic date range, and send it to the right office. This builder drafts the request; it does not send or store anything.</p>
</div></section>"""
    body = f"""<div class="workspace foia">
<form class="tool" id="foia-form" onsubmit="return false">
<p class="kicker">Build the request</p>
<h2>Six short answers</h2>
<label for="foia-agency">Agency or office that holds the records</label>
<input id="foia-agency" list="agency-list" autocomplete="off" placeholder="Start typing an agency name">
<datalist id="agency-list">{options}</datalist>
<p class="help">Each agency handles its own requests, often by office. <a href="https://www.foia.gov/agency-search.html" rel="noopener">FOIA.gov's agency search</a> gives the address or portal to use.</p>
<label for="foia-records">Records you want</label>
<textarea id="foia-records" rows="5" placeholder="For example: All contracts, task orders and invoices between the agency and Example Corp. for snow removal at the Anytown federal building."></textarea>
<p class="help">Name documents, not questions. Add names, offices, contract or case numbers and keywords that would help a records officer search.</p>
<div class="two"><div><label for="foia-start">From</label><input id="foia-start" type="date"></div>
<div><label for="foia-end">To</label><input id="foia-end" type="date"></div></div>
<label for="foia-format">Format you prefer</label>
<select id="foia-format"><option value="electronic copies, in searchable form where the records exist that way">Searchable electronic copies</option>
<option value="electronic copies in their native file format">Native electronic files</option>
<option value="electronic copies in PDF">PDF</option>
<option value="data as CSV or another machine-readable format">CSV or machine-readable data</option>
<option value="paper copies">Paper copies</option></select>
<label for="foia-category">How you will use the records (this sets the fees an agency may charge)</label>
<select id="foia-category">
<option value="">I would rather not say</option>
<option value="news">For news reporting</option>
<option value="edu">For an educational or scientific institution's research</option>
<option value="personal">For personal, non-commercial use</option>
<option value="commercial">For commercial use</option></select>
<div class="two"><div><label for="foia-cap">Most you agree to pay ($)</label><input id="foia-cap" inputmode="numeric" value="25"></div>
<div class="checks"><label><input type="checkbox" id="foia-waiver"> Ask for a fee waiver</label>
<label><input type="checkbox" id="foia-expedite"> Ask for expedited processing</label></div></div>
<div id="waiver-box" hidden><label for="foia-waiver-why">Why releasing these records serves the public</label>
<textarea id="foia-waiver-why" rows="3" placeholder="How the records will help the public understand what the government is doing, and how you will share them."></textarea></div>
<div id="expedite-box" hidden><label for="foia-expedite-why">Why the request is urgent</label>
<textarea id="foia-expedite-why" rows="3" placeholder="The compelling need: for example, an urgent need to inform the public about a specific government activity."></textarea></div>
<label for="foia-name">Your name and how to reach you (optional)</label>
<textarea id="foia-name" rows="3" placeholder="Name&#10;Email or mailing address&#10;Phone"></textarea>
<p class="help">Nothing you type leaves this page or is saved. Close the tab and it is gone.</p>
<div class="actions">
<button type="button" class="btn primary" id="foia-copy">Copy request</button>
<button type="button" class="btn" id="foia-download">Download .txt</button>
<button type="button" class="btn" id="foia-print">Print</button>
</div>
<p class="status" id="foia-status" role="status" aria-live="polite"></p>
</form>
<article class="letter"><header><b>Your request</b><span>Draft. Read it before you send it.</span></header>
<pre id="letter">Freedom of Information Act Request

To: [AGENCY OR OFFICE]

Under the Freedom of Information Act, 5 U.S.C. § 552, I request copies of the following records:

[DESCRIBE THE RECORDS]

Please provide electronic copies, in searchable form where the records exist that way. If any part of a record is withheld, please release every reasonably segregable portion and cite the exemption that applies to each withholding.

I agree to pay fees up to $25. Please tell me before the cost goes above that amount.

I look forward to your determination within 20 working days, as the statute provides.

Sincerely,
[YOUR NAME]
[HOW TO REACH YOU]</pre></article>
</div>
<p class="note"><b>This is a drafting aid, not legal advice.</b> Agencies set their own submission rules, and some records are exempt from release.
The agency's FOIA office and <a href="https://www.foia.gov/" rel="noopener">FOIA.gov</a> are the authority on how to file and what to expect.</p>
<h2>Before you send it</h2>
<ul class="plain">
<li><b>Find the right office.</b> Use <a href="https://www.foia.gov/agency-search.html" rel="noopener">FOIA.gov's agency search</a>. Many agencies take requests through a web portal; you can paste this text into it.</li>
<li><b>Check whether it is already public.</b> Agencies post frequently requested records in their online reading rooms.</li>
<li><b>Keep the tracking number.</b> You can ask the office's FOIA Public Liaison for status. Disputes can go to the
<a href="https://www.archives.gov/ogis" rel="noopener">Office of Government Information Services</a>, the federal FOIA ombudsman.</li>
<li><b>Know the law's own words.</b> <a href="https://www.justice.gov/oip/freedom-information-act-5-usc-552" rel="noopener">The statute, 5 U.S.C. § 552</a>,
and the Justice Department's <a href="https://www.justice.gov/oip/doj-guide-freedom-information-act-0" rel="noopener">Guide to the Freedom of Information Act</a>.</li>
<li><b>State and local records</b> fall under each state's own public-records law, not this one.</li>
</ul>
<h2>What the builder puts in, and why</h2>
<div class="faq">
<details><summary>The citation and the description</summary><p>A request has to reasonably describe the records and follow the agency's published rules. Citing the statute makes clear which law you are using.</p></details>
<details><summary>Segregable portions</summary><p>The statute requires agencies to release any reasonably segregable part of a record after removing exempt parts. Asking for it, and for the exemption cited, makes a partial release easier to understand.</p></details>
<details><summary>Fees, categories and waivers</summary><p>The law sorts requesters into categories that decide which fees apply, and lets agencies waive or reduce fees when disclosure is in the public interest and not mainly in the requester's commercial interest. An agency decides whether you qualify; the builder only words the ask.</p></details>
<details><summary>Expedited processing</summary><p>The statute provides for faster handling when there is a compelling need, and asks the requester to certify that the explanation is true. Tick the box only if that fits your situation.</p></details>
<details><summary>Twenty working days</summary><p>The statute gives agencies 20 working days to decide on a request, with extensions in unusual circumstances. Many requests take longer in practice.</p></details>
</div>"""
    site.page("/foia-request-builder/", "FOIA Request Builder: Write a Clear Federal Records Request",
              "A free builder for a federal Freedom of Information Act request: describe the records, pick a format, set a fee limit, and copy or download a clear letter. Nothing you type is sent or stored.",
              body, hero=hero, nav="foia", og=("foia", "Specific beats dramatic.", "Write a clear federal FOIA request in a few minutes"),
              lastmod=(status.get("agencies", {}).get("last_changed") or "")[:10],
              jsonld=[{"@context": "https://schema.org", "@type": "WebApplication", "name": "FOIA Request Builder", "url": site.url + "/foia-request-builder/",
                       "applicationCategory": "UtilitiesApplication", "operatingSystem": "Any", "isAccessibleForFree": True,
                       "description": "Drafts a federal Freedom of Information Act request in the browser. Nothing is sent or stored."}])

    # ------------------------------------------------------------------ home
    top3 = purpose[:3]
    hero = f"""<section class="hero home"><div class="wrap">
<p class="eyebrow">America.co public resource desk</p>
<h1>Follow the money. Read the rule. Find the record.</h1>
<p class="lede">Three free tools built on official federal data. No account, no email, nothing to install.</p>
</div></section>"""
    body = f"""<div class="tiles">
<a class="tile" href="{site.href('/taxpayer-receipt/')}"><small>Spending</small><b>Federal taxpayer receipt</b>
<span>Enter what you paid. See it itemized across {money(float(outlays))} in fiscal year {fy} outlays: {E(top3[0]['name'])} {pct(top3[0]['share'])}, {E(top3[1]['name'])} {pct(top3[1]['share'])}, {E(top3[2]['name'])} {pct(top3[2]['share'])}.</span>
<em>U.S. Treasury · fiscal year {fy} · read {E(short_date(tre.get('retrieved_at', '')))}</em></a>
<a class="tile" href="{site.href('/comment-deadlines/')}"><small>Participation</small><b>Rules open for public comment</b>
<span>{len(docs):,} federal documents are taking public comments today. {len(soon):,} close within seven days; {len(proposed):,} are proposed rules.</span>
<em>Federal Register · read {E(short_date(com.get('retrieved_at', '')))}</em></a>
<a class="tile" href="{site.href('/foia-request-builder/')}"><small>Records</small><b>FOIA request builder</b>
<span>Six short answers become a clear Freedom of Information Act request you can copy, download or print. It never leaves your browser.</span>
<em>5 U.S.C. § 552 · links to FOIA.gov</em></a>
</div>
{stale_note('treasury', 'the Treasury statement')}{stale_note('comments', 'the Federal Register')}
<h2>What the federal government paid out in fiscal year {fy}</h2>
<div class="receipt mini"><div class="rows">{receipt_html(purpose, DEFAULT_AMOUNT, fn_path, limit=8)}</div>
<p class="fine">The eight largest of {len(purpose)} lines, shown as shares of a $10,000 receipt. <a href="{site.href('/taxpayer-receipt/')}">Open the full receipt</a>.</p></div>
<p class="asof">{fy_source}</p>
<h2>Closing soonest</h2>
<ul class="docs">{''.join(doc_li(d, today) for d in docs[:6])}</ul>
<p><a class="btn" href="{site.href('/comment-deadlines/')}">All {len(docs):,} open documents</a></p>
<p class="asof">{fr_source}</p>
<h2>The source standard</h2>
<div class="tiles small">
<div class="tile"><b>Follow the record home</b><span>Every number links to the government record it came from and shows the date it was read.</span></div>
<div class="tile"><b>Arithmetic you can check</b><span>A fiscal year is published only if its lines add up to Treasury's own total. A receipt always sums to what you entered.</span></div>
<div class="tile"><b>No side taken</b><span>The tools describe what the records say. They do not argue for more spending or less, or for or against any rule.</span></div>
</div>"""
    site.page("/", "America.co Public Tools: Taxpayer Receipt, Comment Deadlines, FOIA Builder", cfg["tagline"], body, hero=hero,
              og=("home", "Follow the money. Read the rule. Find the record.", "Three free public tools, no account"),
              jsonld=[{"@context": "https://schema.org", "@type": "WebSite", "name": "America.co Public Tools", "url": site.url + "/", "description": cfg["tagline"]}])

    # ------------------------------------------------------------------ method, about, data
    st_rows = "".join(
        f'<tr><td>{E(label)}</td><td>{when(status.get(k, {}).get("last_success", ""))}</td>'
        f'<td>{"ok" if status.get(k, {}).get("ok") else "failed: " + E(status.get(k, {}).get("error", "not yet read"))[:160]}</td><td>{E(status.get(k, {}).get("note", ""))}</td></tr>'
        for k, label in (("treasury", "Monthly Treasury Statement"), ("comments", "Federal Register comment periods"), ("agencies", "Federal Register agency list")))
    site.page("/method/", "Sources and Arithmetic", "Where every number on America.co Public Tools comes from, how the taxpayer receipt is calculated, how fresh the data is, and what the tools do not do.",
              f"""<article class="prose"><p class="kicker">Sources and arithmetic</p><h1>Where every number comes from</h1>
<p class="lede">Three official sources, read by an automated job. No estimates of our own, no commentary, and no keys or accounts.</p>
<h2 id="status">When each source was last read</h2>
<div class="tablewrap"><table><thead><tr><th>Source</th><th>Last good read</th><th>Latest attempt</th><th>What was read</th></tr></thead><tbody>{st_rows}</tbody></table></div>
<p>If a read fails, the pages keep the last good data and keep showing the date it was read.</p>
<h2 id="receipt">The taxpayer receipt</h2>
<p><b>Source.</b> The <a href="{E(src['dataset'])}" rel="noopener">Monthly Treasury Statement</a> from the U.S. Treasury's Bureau of the Fiscal Service: table 9
(net outlays by budget function, and receipts by source) and table 3 (net outlays by agency), final statement for fiscal year {fy}, dated {E(human_date(year['record_date']))}.
Earlier fiscal years use their own final statements and are not adjusted for inflation.</p>
<p><b>Check before publishing.</b> A fiscal year is used only if its function lines add up to Treasury's published total outlays, its agency lines add up to the same total,
and its receipt lines add up to total receipts, each within one dollar. A statement that fails is not published; the last good one stays.</p>
<p><b>The split.</b> share = line ÷ total net outlays. Your amount × share is rounded down to the cent, and the cents left over go to the lines with the largest
remainders. The receipt therefore sums to exactly the amount entered. The same steps run in your browser and in the build, and a browser test compares them.</p>
<p><b>Negative lines.</b> Treasury records some collections as negative outlays. They appear as negative lines and reduce the total, exactly as in the statement.</p>
<p><b>What it is not.</b> It is not a tax estimate, and it does not mean your payment was earmarked. {E(NOT_EARMARKED)}</p>
<h2 id="comments">Comment deadlines</h2>
<p><b>Source.</b> The <a href="https://www.federalregister.gov/developers/documentation/api/v1" rel="noopener">Federal Register API</a>: every document whose “comments close on” date is today or later,
read once a day. Titles, agencies, dates, docket numbers and links are the Federal Register's. Summaries are its abstracts, cut to about 420 characters.</p>
<p><b>Dates.</b> “Today” is the date in Washington, D.C. A document leaves the lists the day after its closing date. Your browser hides anything that has closed since the last build,
and warns you if the build is more than two days old.</p>
<p><b>Limits.</b> Agencies extend, reopen and correct comment periods. Some documents take comments only by mail, email or an agency's own system; those show no “Comment” button.
Agency pages exist only for agencies with at least {cfg['min_agency_list']} open documents.</p>
<h2 id="foia">FOIA request builder</h2>
<p>The builder is a template that runs in your browser. It sends nothing and stores nothing. Agency name suggestions come from the Federal Register's agency list;
where to send a request comes from <a href="https://www.foia.gov/agency-search.html" rel="noopener">FOIA.gov</a>, not from this site. It is a drafting aid, not legal advice.</p>
<h2 id="checks">Automated checks</h2>
<ul><li>Daily: read the sources, run the tests, rebuild, and refuse to publish if a page is missing its source, its date or a working link.</li>
<li>Weekly: recompute the receipt arithmetic from the published data, test the live site, and check that the official pages linked here still answer.</li></ul>
<h2 id="corrections">Corrections</h2>
<p>If a page misstates its source, <a href="{E(site.repo_url)}/issues/new/choose" rel="noopener">open an issue</a>. If the official record itself is wrong, only its publisher can fix it.</p></article>""",
              nav="method")
    site.page("/about/", "About America.co Public Tools", "What these tools are, who they are for, how they treat privacy and neutrality, and how to report an error.",
              f"""<article class="prose"><p class="kicker">About</p><h1>Public tools that need nothing from you</h1>
<p class="lede">America.co builds civic tools for people who want to see the record for themselves. Its line is “Not left. Not right. Up.”</p>
<p>This is the static edition of three of those tools: a receipt for federal taxes, the list of federal documents open for public comment, and a builder for
Freedom of Information Act requests. Static means there is no server behind them: the pages are rebuilt from official data by an automated job, and everything
you type stays in your browser.</p>
<h2>Nonpartisan by construction</h2>
<p>The tools report what official records say, with the source and the date. They take no position on any spending line, rule, agency, party or official.</p>
<h2>Privacy</h2>
<p>No accounts, no cookies, no sign-up. The amount you enter, your search words and your FOIA request never leave your device, and nothing is saved between visits.
A share link carries only the amount you chose, after the “#”, where it is not sent to any server.
{'Page views are counted with GoatCounter, which stores no personal data.' if os.environ.get('GOATCOUNTER_URL') else 'The site runs no analytics.'}</p>
<h2>Not an official site, and not advice</h2>
<p>These pages are not affiliated with the Treasury, the Federal Register, the Justice Department or any agency. Nothing here is tax, legal or financial advice.</p>
<h2>Corrections and contact</h2>
<p><a href="{E(site.repo_url)}/issues" rel="noopener">Open an issue on GitHub</a>. The code that builds this site is public in the same place.</p></article>""")

    # data files
    site.write("data/federal-outlays.json", json.dumps({"license": "CC0-1.0", "source": src, "retrieved_at": tre.get("retrieved_at", ""),
                                                        "latest_fiscal_year": fy, "fiscal_years": tre["fiscal_years"]}, ensure_ascii=False, separators=(",", ":")) + "\n")
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["fiscal_year", "statement_date", "budget_function", "net_outlays_usd", "share_of_total_outlays_percent", "source"])
    for y in years:
        rec = tre["fiscal_years"][y]
        tot = Decimal(rec["outlays_total"])
        for f in rec["functions"]:
            w.writerow([y, rec["record_date"], f["name"], f["amount"], f"{Decimal(f['amount']) * 100 / tot:.4f}", src["by_function"]])
    site.write("data/federal-outlays-by-function.csv", buf.getvalue())
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["document_number", "title", "type", "agencies", "comments_close_on", "publication_date", "federal_register_url", "comment_url", "dockets"])
    for d in docs:
        w.writerow([d["number"], d["title"], d["type"], "; ".join(a["name"] for a in d["agencies"]), d["closes"], d["published"], d["url"], d["comment_url"], "; ".join(d["dockets"])])
    site.write("data/comment-deadlines.csv", buf.getvalue())
    site.write("data/comment-deadlines.json", json.dumps({"license": "CC0-1.0", "source": com.get("source", {}), "retrieved_at": com.get("retrieved_at", ""),
                                                          "as_of_date": today, "count": len(docs), "documents": docs}, ensure_ascii=False, separators=(",", ":")) + "\n")
    site.page("/data/", "Open Data: Federal Outlays and Comment Deadlines as CSV and JSON",
              "Download the data behind America.co Public Tools: federal outlays by budget function and agency for each fiscal year, and every federal document open for comment today.",
              f"""<article class="prose"><p class="kicker">Open data</p><h1>Take the data</h1>
<p class="lede">The files these pages are built from. Federal data is in the public domain; this compilation is released under CC0.</p>
<h2>Federal outlays and receipts</h2>
<p><a class="btn primary" href="{site.href('/data/federal-outlays-by-function.csv')}">Outlays by function, {years[0]} to {fy} (CSV)</a>
<a class="btn" href="{site.href('/data/federal-outlays.json')}">Functions, agencies and receipts (JSON)</a></p>
<p class="asof">{fy_source} Amounts are dollars as published, to the cent, as text so no precision is lost.</p>
<h2>Documents open for public comment</h2>
<p><a class="btn primary" href="{site.href('/data/comment-deadlines.csv')}">Open comment periods (CSV)</a>
<a class="btn" href="{site.href('/data/comment-deadlines.json')}">Open comment periods (JSON)</a>
<a class="btn" href="{site.href('/comment-deadlines/proposed-rules.ics')}">Proposed-rule deadlines (.ics)</a></p>
<p class="asof">{len(docs):,} documents. {fr_source}</p>
<p>When you reuse a figure, cite the original publisher and the date shown here, and link the page so readers can see later updates.</p></article>""",
              nav="data", jsonld=[{"@context": "https://schema.org", "@type": "Dataset", "name": "U.S. federal net outlays by budget function and agency, by fiscal year",
                                   "description": "Final-year net outlays and receipts from the Monthly Treasury Statement, checked to add up to the published totals.",
                                   "url": site.url + "/data/", "license": "https://creativecommons.org/publicdomain/zero/1.0/", "dateModified": tre.get("retrieved_at", ""),
                                   "creator": {"@type": "Organization", "name": "America.co Public Tools", "url": site.url + "/"},
                                   "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": site.url + "/data/federal-outlays-by-function.csv"},
                                                    {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": site.url + "/data/federal-outlays.json"}]}])
    site.page("/404.html", "Page not found", "That page does not exist.",
              f'<h1>Page not found</h1><p class="lede">That address is not on this site.</p><p><a class="btn primary" href="{site.href("/")}">See the three tools</a></p>', listed=False)

    with open(os.path.join(ROOT, "config", "indexnow-key.txt"), encoding="utf-8") as f:
        key = f.read().strip()
    site.write(f"{key}.txt", key + "\n")
    if site.indexable:
        site.write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n' + "".join(
            f"<url><loc>{E(u)}</loc><lastmod>{E(d)}</lastmod></url>\n" for u, d in site.urls) + "</urlset>\n")
        site.write("robots.txt", f"User-agent: *\nAllow: /\nDisallow: /embed/\n\nSitemap: {site.url}/sitemap.xml\n")
    else:
        site.write("robots.txt", "User-agent: *\nDisallow: /\n")
    site.write("urls.txt", "\n".join(u for u, _ in site.urls) + ("\n" if site.urls else ""))
    site.write("og-jobs.json", json.dumps(site.og_jobs))
    site.write("build.json", json.dumps({
        "built_at": iso(site.now), "as_of_date": today, "indexable": site.indexable, "base_url": site.url, "fiscal_year": fy,
        "outlays_total": year["outlays_total"], "functions": len(purpose), "agencies": len(by_agency), "comment_documents": len(docs),
        "agency_pages": len(big), "treasury_read": tre.get("retrieved_at", ""), "comments_read": com.get("retrieved_at", ""),
        "receipt_check": {"amount_cents": DEFAULT_AMOUNT, "purpose": receipt.allocate(DEFAULT_AMOUNT, [r["cents"] for r in purpose]),
                          "agency": receipt.allocate(DEFAULT_AMOUNT, [r["cents"] for r in by_agency]) if by_agency else []}}, indent=1) + "\n")
    site.write(".nojekyll", "")
    return {"fiscal_year": fy, "functions": len(purpose), "agencies": len(by_agency), "comment_documents": len(docs), "agency_pages": len(big),
            "indexable": site.indexable, "og": len(site.og_jobs), "types": dict(Counter(d["type"] for d in docs))}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default=os.path.join(ROOT, "_site"))
    a = ap.parse_args(argv)
    print(json.dumps(build(a.site)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
