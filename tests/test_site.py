"""The built site, from made-up data: the receipt adds up, every number has its source and date,
closed documents never show as open, and the staged copy cannot be indexed."""
import csv
import io
import json
import os
import re
import unittest
from decimal import Decimal

from civictools import build, guard, receipt, refresh
from tests import fixtures


def page(site, rel):
    with open(os.path.join(site, rel), encoding="utf-8") as f:
        return f.read()


class Built(fixtures.TempData, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self.read(10)

    def read(self, day, **routes):
        with fixtures.quiet():
            refresh.run(now=fixtures.when(day), http=fixtures.FakeHttp(**routes), force=True)

    def build(self, day=10, hour=12, **env):
        os.environ.update(env)
        try:
            return build.build(self.site, now=fixtures.when(day, hour))
        finally:
            for k in env:
                os.environ.pop(k, None)

    def lines(self):
        return sorted((receipt.cents(a) for _, a in fixtures.function_amounts(2026)), reverse=True)

    def test_the_receipt_page_lists_every_line_and_adds_up(self):
        self.build()
        html = page(self.site, "taxpayer-receipt/index.html")
        rows = re.search(r'id="receipt-rows">(.*?)</div>\s*<div class="sum">', html, re.S).group(1)
        amounts = re.findall(r'<span class="amt">([^<]+)</span>', rows)
        self.assertEqual(len(amounts), len(fixtures.FUNCTIONS))
        self.assertEqual(amounts, [receipt.usd(c) for c in receipt.allocate(1_000_000, self.lines())])
        cents = [int(a.replace("$", "").replace(",", "").replace(".", "")) for a in amounts]
        self.assertEqual(sum(cents), 1_000_000, "a $10,000 receipt sums to $10,000.00")
        blob = json.loads(re.search(r'id="receipt-data">(.*?)</script>', html, re.S).group(1))
        self.assertEqual(blob["fy"], "2026")
        self.assertEqual(sum(int(l[1]) for l in blob["views"]["purpose"]["lines"]), receipt.cents(fixtures.outlays_total(2026)))
        self.assertEqual(sum(int(l[1]) for l in blob["views"]["agency"]["lines"]), receipt.cents(fixtures.outlays_total(2026)))
        self.assertIn("not a tax estimator", html)
        self.assertIn("not earmarked", html)

    def test_the_home_page_preview_uses_the_full_split(self):
        self.build()
        full = receipt.allocate(1_000_000, self.lines())
        home = page(self.site, "index.html")
        mini = re.search(r'<div class="receipt mini"><div class="rows">(.*?)</div>\s*<p class="fine">', home, re.S).group(1)
        self.assertEqual(re.findall(r'<span class="amt">([^<]+)</span>', mini), [receipt.usd(c) for c in full[:8]],
                         "eight lines are shown, but each is its share of all nineteen")

    def test_every_number_page_names_its_source_and_the_date_it_was_read(self):
        self.build()
        pages = ["taxpayer-receipt/index.html", "comment-deadlines/index.html", "comment-deadlines/closing-soon/index.html",
                 "comment-deadlines/proposed-rules/index.html", "comment-deadlines/agencies/index.html", "index.html"]
        pages += [f"taxpayer-receipt/{d}/index.html" for d in os.listdir(os.path.join(self.site, "taxpayer-receipt")) if d != "index.html"]
        for rel in pages:
            html = page(self.site, rel)
            self.assertRegex(html, guard.SOURCED, rel)
            self.assertIn('<time datetime="2031-03-10T11:00:00Z">March 10, 2031</time>', html, rel)
        receipt_page = page(self.site, "taxpayer-receipt/index.html")
        self.assertIn("fiscaldata.treasury.gov/datasets/monthly-treasury-statement/", receipt_page)
        self.assertIn("final statement for fiscal year 2026 (dated September 30, 2026)", receipt_page)

    def test_each_spending_line_has_a_page_with_its_history(self):
        self.build()
        for name, amount in fixtures.function_amounts(2026):
            slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
            html = page(self.site, f"taxpayer-receipt/{slug}/index.html")
            self.assertIn(f"<h1>{name}</h1>", html)
            for fy in fixtures.YEARS:
                self.assertIn(f"<td>FY {fy}</td>", html)
            self.assertIn("not adjusted for inflation", html)
            if amount < 0:
                self.assertIn("reduced total outlays", html)
            else:
                share = receipt.share(receipt.cents(amount), receipt.cents(fixtures.outlays_total(2026)))
                self.assertIn(f"<b>{share:.1f}%</b><span>Share of total federal outlays</span>", html)

    def test_documents_that_closed_since_the_read_are_not_listed(self):
        out = self.build(day=10)
        self.assertEqual(out["comment_documents"], 70)
        out = self.build(day=20)                      # ten days later, with no new read
        idx = json.loads(page(self.site, "assets/comments.json"))
        self.assertLess(out["comment_documents"], 70)
        self.assertTrue(all(d[4] >= "2031-03-20" for d in idx["docs"]))
        html = page(self.site, "comment-deadlines/closing-soon/index.html")
        closes = re.findall(r'data-closes="([^"]+)"', html)
        self.assertTrue(closes and all("2031-03-20" <= c <= "2031-03-27" for c in closes))
        self.assertIn('id="stale" hidden data-built="2031-03-20"', html, "the page script can warn when the build itself gets old")

    def test_comment_rows_link_to_the_record_and_the_official_comment_form_only(self):
        self.build()
        html = page(self.site, "comment-deadlines/proposed-rules/index.html")
        links = set(re.findall(r'<li class="doc".*?</li>', html, re.S))
        self.assertTrue(links)
        for li in links:
            hrefs = re.findall(r'href="([^"]+)"', li)
            self.assertTrue(hrefs[0].startswith("https://www.federalregister.gov/documents/"))
            self.assertTrue(all(h.startswith(("https://www.federalregister.gov/", "https://www.regulations.gov/commenton/")) for h in hrefs))
            self.assertIn("Proposed rule", li)
        self.assertIn("See the document for how to comment", html, "a document with no comment form says so")
        self.assertNotIn("<about widgets>", html)
        self.assertIn("&lt;about widgets&gt;", html)

    def test_agencies_get_a_page_only_with_enough_documents(self):
        self.build()
        self.assertTrue(os.path.exists(os.path.join(self.site, "comment-deadlines", "agency", "example-department", "index.html")))
        self.assertFalse(os.path.exists(os.path.join(self.site, "comment-deadlines", "agency", "tiny-commission")), "two documents are not a page")
        index = page(self.site, "comment-deadlines/agencies/index.html")
        self.assertIn("<td>Tiny Commission</td>", index, "the small agency is still counted, without a link")
        self.assertIn('/comment-deadlines/agency/other-agency/">Other Agency</a>', index)

    def test_calendar_and_feed(self):
        self.build()
        with open(os.path.join(self.site, "comment-deadlines", "proposed-rules.ics"), encoding="utf-8", newline="") as f:
            cal = f.read()
        self.assertTrue(cal.startswith("BEGIN:VCALENDAR\r\n") and cal.endswith("END:VCALENDAR\r\n"))
        self.assertEqual(cal.count("BEGIN:VEVENT"), 14)
        self.assertTrue(all(len(line.encode()) <= 75 for line in cal.split("\r\n")))
        self.assertIn("DTSTART;VALUE=DATE:203103", cal)
        self.assertNotIn("\r\n\r\n", cal)
        feed = page(self.site, "comment-deadlines/feed.xml")
        self.assertEqual(feed.count("<entry>"), 60)
        self.assertIn("Comments close", feed)

    def test_foia_builder_keeps_everything_in_the_browser(self):
        self.build()
        html = page(self.site, "foia-request-builder/index.html")
        self.assertIn('onsubmit="return false"', html)
        self.assertNotRegex(html, r'<form[^>]+action=')
        self.assertNotIn("localStorage", page(self.site, "static/app.js"))
        self.assertNotIn("sessionStorage", page(self.site, "static/app.js"))
        self.assertEqual(page(self.site, "static/app.js").count("fetch("), 1, "the only request the script makes is for the comment index")
        self.assertIn("5 U.S.C. § 552", html)
        self.assertIn("not legal advice", html)
        self.assertIn('<option value="Agency 000">', html)
        self.assertIn("https://www.foia.gov/agency-search.html", html)

    def test_staged_copy_cannot_be_indexed(self):
        out = self.build()
        self.assertFalse(out["indexable"])
        self.assertFalse(os.path.exists(os.path.join(self.site, "sitemap.xml")))
        self.assertEqual(page(self.site, "robots.txt"), "User-agent: *\nDisallow: /\n")
        self.assertEqual(page(self.site, "urls.txt"), "")
        for dirpath, _, files in os.walk(self.site):
            for fn in files:
                if fn.endswith(".html"):
                    self.assertIn('<meta name="robots" content="noindex, nofollow">', page(dirpath, fn), fn)

    def test_cutover_is_two_settings(self):
        out = self.build(SITE_URL="https://tools.example.org", SITE_INDEXABLE="true")
        self.assertTrue(out["indexable"])
        home = page(self.site, "index.html")
        self.assertNotIn("noindex", home)
        self.assertIn('<link rel="canonical" href="https://tools.example.org/">', home)
        self.assertIn('href="/static/style.css"', home)
        self.assertNotIn("github.io", home)
        sitemap = page(self.site, "sitemap.xml")
        self.assertIn("<loc>https://tools.example.org/taxpayer-receipt/</loc>", sitemap)
        self.assertIn("<loc>https://tools.example.org/taxpayer-receipt/medicare/</loc>", sitemap)
        self.assertNotIn("/embed/", sitemap)
        self.assertNotIn("404", sitemap)
        self.assertIn('<meta name="robots" content="noindex, nofollow">', page(self.site, "embed/receipt/index.html"), "the embed never competes with the tool")
        self.assertIn("Disallow: /embed/", page(self.site, "robots.txt"))
        self.assertIn("https://tools.example.org/embed/receipt/", page(self.site, "taxpayer-receipt/index.html"))
        self.assertIn('"base":"https://tools.example.org"', page(self.site, "taxpayer-receipt/index.html"))

    def test_a_failed_read_is_said_on_the_page_and_the_old_date_stays(self):
        self.read(12, mts_table_9=fixtures.table_9(break_year=2026), documents__json=fixtures.fr_open(first_day=12))
        self.build(day=12)
        html = page(self.site, "taxpayer-receipt/index.html")
        self.assertIn("did not succeed", html)
        self.assertIn('<time datetime="2031-03-10T11:00:00Z">', html)
        self.assertIn("failed", page(self.site, "method/index.html"))
        self.assertNotIn("did not succeed", page(self.site, "comment-deadlines/index.html"))

    def test_sponsor_slot_is_off_until_both_settings_exist(self):
        self.build()
        self.assertNotIn('class="slot"', page(self.site, "index.html"))
        self.build(SPONSOR_URL="https://example.org/", SPONSOR_NAME="Example Fund")
        html = page(self.site, "index.html")
        self.assertIn('rel="noopener sponsored">Example Fund</a>', html)
        self.assertIn("no say over the data", html)

    def test_data_files_match_the_pages(self):
        self.build()
        rows = list(csv.DictReader(io.StringIO(page(self.site, "data/federal-outlays-by-function.csv"))))
        self.assertEqual(len(rows), len(fixtures.YEARS) * len(fixtures.FUNCTIONS))
        latest = [r for r in rows if r["fiscal_year"] == "2026"]
        self.assertEqual(sum(Decimal(r["net_outlays_usd"]) for r in latest), fixtures.outlays_total(2026))
        self.assertTrue(all(r["source"].startswith("https://fiscaldata.treasury.gov/") for r in rows))
        docs = list(csv.DictReader(io.StringIO(page(self.site, "data/comment-deadlines.csv"))))
        self.assertEqual(len(docs), 70)
        data = json.loads(page(self.site, "data/federal-outlays.json"))
        self.assertEqual(data["latest_fiscal_year"], "2026")
        self.assertEqual(data["license"], "CC0-1.0")

    def test_guard_accepts_the_build_and_catches_damage(self):
        self.build()
        os.makedirs(os.path.join(self.site, "og"), exist_ok=True)
        with open(os.path.join(self.site, "og", "default.png"), "wb") as f:
            f.write(b"png")
        errors, counts = guard.check(self.site)
        self.assertEqual(errors, [])
        self.assertEqual(counts["lines"], len(fixtures.FUNCTIONS))
        path = os.path.join(self.site, "taxpayer-receipt", "index.html")
        html = page(self.site, "taxpayer-receipt/index.html")
        blob = re.search(r'id="receipt-data">(.*?)</script>', html, re.S).group(1)
        first = json.loads(blob)["views"]["purpose"]["lines"][0][1]
        with open(path, "w", encoding="utf-8") as f:
            f.write(html.replace(f'"{first}"', f'"{int(first) + 100}"', 1))
        errors, _ = guard.check(self.site)
        self.assertTrue(any("do not add up to Treasury's total" in e for e in errors), errors[:3])
        with open(path, "w", encoding="utf-8") as f:
            f.write(html.replace("</head>", '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=X"></head>'))
        errors, _ = guard.check(self.site)
        self.assertTrue(any("from another site" in e for e in errors))
        with open(path, "w", encoding="utf-8") as f:
            f.write(html)
        os.remove(os.path.join(self.site, "taxpayer-receipt", "medicare", "index.html"))
        errors, _ = guard.check(self.site)
        self.assertTrue(any("medicare: page missing" in e for e in errors))
        self.assertTrue(any("broken link" in e for e in errors))

    def test_guard_arithmetic_catches_a_changed_figure(self):
        tre = refresh.read_json(refresh.path("treasury"))
        self.assertEqual(guard.arithmetic(tre), [])
        tre["fiscal_years"]["2026"]["functions"][3]["amount"] = "1.00"
        self.assertTrue(any("FY2026: function lines do not add up" in e for e in guard.arithmetic(tre)))

    def test_no_contact_address_tracker_or_outside_resource(self):
        self.build()
        for rel in ("index.html", "about/index.html", "method/index.html", "taxpayer-receipt/index.html", "foia-request-builder/index.html", "comment-deadlines/index.html"):
            html = page(self.site, rel)
            self.assertNotRegex(html, r"[\w.+-]+@[\w-]+\.[a-z]{2,}", rel)
            self.assertNotIn("googletagmanager", html)
            self.assertNotIn("fonts.googleapis", html)
            self.assertNotIn("gc.zgo.at", html)
        self.assertIn("github.com/", page(self.site, "about/index.html"))
        self.assertNotIn("@import", page(self.site, "static/style.css"))


if __name__ == "__main__":
    unittest.main()
