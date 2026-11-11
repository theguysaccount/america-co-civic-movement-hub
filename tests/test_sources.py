"""Reading the official sources: a statement that does not add up is refused, and a source that fails keeps its last good file."""
import json
import os
import unittest
from datetime import timedelta
from decimal import Decimal

from civictools import fedreg, refresh, treasury
from civictools.common import HttpError, read_json
from tests import fixtures


class Treasury(unittest.TestCase):
    def test_reads_final_september_statements_only(self):
        years = treasury.parse_table_9(fixtures.table_9())
        self.assertEqual(sorted(years), [str(y) for y in fixtures.YEARS])
        y = years["2026"]
        self.assertEqual(y["record_date"], "2026-09-30")
        self.assertEqual([f["name"] for f in y["functions"]], fixtures.FUNCTIONS)
        self.assertEqual(Decimal(y["outlays_total"]), fixtures.outlays_total(2026))
        self.assertEqual(Decimal(y["deficit"]), Decimal(y["outlays_total"]) - Decimal(y["receipts_total"]))
        self.assertEqual(len(y["receipts"]), 4, "the heading line with no amount is not a receipt")
        self.assertTrue(any(Decimal(f["amount"]) < 0 for f in y["functions"]), "negative lines are kept as published")

    def test_a_statement_whose_lines_do_not_add_up_is_refused(self):
        with self.assertRaises(treasury.Mismatch):
            treasury.parse_table_9(fixtures.table_9(break_year=2025))

    def test_agency_table_splits_treasury_and_must_reach_the_same_total(self):
        rec = treasury.fetch(fixtures.FakeHttp())
        names = [a["name"] for a in rec["fiscal_years"]["2026"]["agencies"]]
        self.assertIn("Interest on Treasury debt securities (gross)", names)
        self.assertIn("Department of the Treasury, other", names)
        self.assertIn("Undistributed offsetting receipts: other", names)
        self.assertIn("Department of Defense: Military Programs", names)
        self.assertNotIn("Total Outlays", names)
        self.assertNotIn("(On-Budget)", names)
        self.assertNotIn("Individual Income Taxes", names, "receipt lines of table 3 are not agencies")
        total = sum(Decimal(a["amount"]) for a in rec["fiscal_years"]["2026"]["agencies"])
        self.assertEqual(total, Decimal(rec["fiscal_years"]["2026"]["outlays_total"]))
        with self.assertRaises(treasury.Mismatch):
            treasury.fetch(fixtures.FakeHttp(mts_table_3=fixtures.table_3(off_by=Decimal("250.00"))))

    def test_the_request_asks_for_whole_rows(self):
        self.assertNotIn("fields=", treasury.url("mts_table_9"), "this API sums rows when columns are left out")
        self.assertIn("record_calendar_month:eq:09", treasury.url("mts_table_9"))


class FederalRegister(unittest.TestCase):
    def test_only_open_documents_once_each_soonest_first(self):
        rec = fedreg.fetch_open(fixtures.FakeHttp(), "2031-03-10")
        docs = rec["documents"]
        self.assertEqual(len(docs), 70)
        self.assertEqual(len({d["number"] for d in docs}), 70)
        self.assertTrue(all(d["closes"] >= "2031-03-10" for d in docs))
        self.assertEqual([d["closes"] for d in docs], sorted(d["closes"] for d in docs))

    def test_fields_are_copied_and_the_comment_link_is_https_at_regulations_gov(self):
        d = fedreg.tidy(fixtures.fr_doc(7, "2031-03-20"))
        self.assertEqual(d["title"], "Example notice number 7 <about widgets>")
        self.assertEqual(d["comment_url"], "https://www.regulations.gov/commenton/EX-2031-0007-0001")
        self.assertEqual([a["name"] for a in d["agencies"]], ["Example Department", "Example Bureau"])
        self.assertLessEqual(len(d["abstract"]), 420)
        self.assertEqual(fedreg.tidy(fixtures.fr_doc(8, "2031-03-20", comment=False))["comment_url"], "")
        odd = dict(fixtures.fr_doc(9, "2031-03-20"), comment_url="https://example.com/comment")
        self.assertEqual(fedreg.tidy(odd)["comment_url"], "", "a comment link anywhere else is not passed on")

    def test_the_api_is_asked_for_everything_closing_today_or_later(self):
        url = fedreg.open_url("2031-03-10")
        self.assertIn("conditions%5Bcomment_date%5D%5Bgte%5D=2031-03-10", url)
        self.assertTrue(url.startswith("https://www.federalregister.gov/api/v1/"))


class Refresh(fixtures.TempData, unittest.TestCase):
    def run_with(self, now, **routes):
        http = fixtures.FakeHttp(**routes)
        with fixtures.quiet():
            return refresh.run(now=now, http=http), http

    def test_a_good_run_writes_all_three_files(self):
        status, http = self.run_with(fixtures.when())
        self.assertTrue(all(status[s]["ok"] for s in refresh.SOURCES))
        tre = read_json(refresh.path("treasury"))
        self.assertEqual(tre["latest"], "2026")
        self.assertEqual(tre["retrieved_at"], "2031-03-10T11:00:00Z")
        com = read_json(refresh.path("comments"))
        self.assertEqual(com["as_of_date"], "2031-03-10")
        self.assertEqual(len(com["documents"]), 70)
        lines = fixtures.text(refresh.path("comments")).splitlines()
        self.assertEqual(len(lines), 70 + 2, "one document per line")
        self.assertGreaterEqual(len(read_json(refresh.path("agencies"))["agencies"]), 100)

    def test_one_source_failing_leaves_the_others_and_its_own_last_good_file(self):
        self.run_with(fixtures.when(10))
        before = fixtures.text(refresh.path("treasury"))
        status, _ = self.run_with(fixtures.when(12), mts_table_9=fixtures.table_9(break_year=2026), documents__json=fixtures.fr_open(first_day=12))
        self.assertFalse(status["treasury"]["ok"])
        self.assertIn("Mismatch", status["treasury"]["error"])
        self.assertEqual(status["treasury"]["last_success"], "2031-03-10T11:00:00Z")
        self.assertEqual(fixtures.text(refresh.path("treasury")), before)
        self.assertTrue(status["comments"]["ok"])
        self.assertEqual(read_json(refresh.path("comments"))["as_of_date"], "2031-03-12")
        status, _ = self.run_with(fixtures.when(13), mts_table_9=HttpError("https://api.fiscaldata.treasury.gov/x", 503), documents__json=HttpError("https://www.federalregister.gov/x", 0, "timeout"))
        self.assertFalse(status["treasury"]["ok"])
        self.assertFalse(status["comments"]["ok"])
        self.assertEqual(read_json(refresh.path("comments"))["as_of_date"], "2031-03-12", "the last good list stays")

    def test_treasury_is_not_accepted_with_too_few_years_or_an_older_latest_year(self):
        self.run_with(fixtures.when(10))
        status, _ = self.run_with(fixtures.when(12), mts_table_9=fixtures.table_9(years=[2025, 2026]), mts_table_3=fixtures.table_3(years=[2025, 2026]))
        self.assertFalse(status["treasury"]["ok"])
        status, _ = self.run_with(fixtures.when(14), mts_table_9=fixtures.table_9(years=fixtures.YEARS[:-1]), mts_table_3=fixtures.table_3(years=fixtures.YEARS[:-1]))
        self.assertFalse(status["treasury"]["ok"])
        self.assertEqual(read_json(refresh.path("treasury"))["latest"], "2026")

    def test_a_comment_list_that_collapsed_is_not_accepted(self):
        self.run_with(fixtures.when(10))
        status, _ = self.run_with(fixtures.when(11), documents__json=fixtures.fr_open(n=8, first_day=11))
        self.assertFalse(status["comments"]["ok"])
        self.assertEqual(len(read_json(refresh.path("comments"))["documents"]), 70)
        status, _ = self.run_with(fixtures.when(11, 16), documents__json={"results": [], "total_pages": 1})
        self.assertFalse(status["comments"]["ok"])

    def test_first_seen_dates_survive_later_reads(self):
        self.run_with(fixtures.when(10))
        self.run_with(fixtures.when(12), documents__json=fixtures.fr_open(n=75, first_day=12))
        seen = {d["number"]: d["first_seen"] for d in read_json(refresh.path("comments"))["documents"]}
        self.assertEqual(seen["2031-00001"], "2031-03-10")
        self.assertEqual(seen["2031-00075"], "2031-03-12")

    def test_a_second_run_soon_after_asks_nothing_again(self):
        self.run_with(fixtures.when(10, 11))
        files = {name: fixtures.text(refresh.path(name)) for name in refresh.SOURCES + ["status"]}
        status, http = self.run_with(fixtures.when(10, 12))
        self.assertEqual(http.calls, 0)
        self.assertEqual(status["comments"]["last_success"], "2031-03-10T11:00:00Z")
        for name, before in files.items():
            self.assertEqual(fixtures.text(refresh.path(name)), before, f"{name}: a run that asked nothing must leave nothing to commit")
        _, http = self.run_with(fixtures.when(10, 17))
        self.assertTrue(any("documents.json" in u for u in http.log), "the comment list is read again later the same day")
        self.assertFalse(any("mts_table" in u for u in http.log), "the Treasury statement is not")
        with fixtures.quiet():
            refresh.run(now=fixtures.when(10, 18), http=(forced := fixtures.FakeHttp()), force=True)
        self.assertGreaterEqual(forced.calls, 4)

    def test_freshness_check(self):
        with fixtures.quiet():
            self.assertFalse(refresh.check_fresh(now=fixtures.when(10)))
            self.run_with(fixtures.when(10))
            self.assertTrue(refresh.check_fresh(now=fixtures.when(11)))
            self.assertFalse(refresh.check_fresh(now=fixtures.when(10) + timedelta(days=5)), "the comment list is days old")


if __name__ == "__main__":
    unittest.main()
