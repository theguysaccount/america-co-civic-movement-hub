"""Made-up Treasury statements and Federal Register answers in the real layouts. No real figure is used."""
import contextlib
import io
import os
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from civictools import common

FUNCTIONS = ["National Defense", "International Affairs", "General Science, Space, and Technology", "Energy", "Natural Resources and Environment",
             "Agriculture", "Commerce and Housing Credit", "Transportation", "Community and Regional Development",
             "Education, Training, Employment, and Social Services", "Health", "Medicare", "Income Security", "Social Security",
             "Veterans Benefits and Services", "Administration of Justice", "General Government", "Net Interest", "Undistributed Offsetting Receipts"]
NEGATIVE = {"Commerce and Housing Credit", "Undistributed Offsetting Receipts"}
YEARS = [2021, 2022, 2023, 2024, 2025, 2026]


def function_amounts(fy):
    """Deterministic made-up amounts with cents; two lines are negative, as in the real statement."""
    out = []
    for i, name in enumerate(FUNCTIONS):
        v = Decimal(1000 + 137 * i * i + (fy - 2020) * 53 * (i + 1)) + Decimal(i * 7 + fy % 10) / 100
        out.append((name, -v / 3 if name in NEGATIVE else v * 1000))
    return [(n, a.quantize(Decimal("0.01"))) for n, a in out]


def _row(fy, line, name, amount, kind="F", level=2):
    return {"record_date": f"{fy}-09-30", "classification_desc": name, "current_fytd_rcpt_outly_amt": "null" if amount is None else str(amount),
            "src_line_nbr": str(line), "record_type_cd": kind, "sequence_level_nbr": str(level), "record_fiscal_year": str(fy),
            "record_calendar_month": "09", "record_calendar_day": "30"}


def table_9(years=YEARS, break_year=None):
    rows = []
    for fy in years:
        receipts = [("Individual Income Taxes", Decimal("9000000.25") + fy), ("Corporation Income Taxes", Decimal("1500000.50")),
                    ("Employment and General Retirement", Decimal("6000000.00")), ("Excise Taxes", Decimal("300000.10"))]
        rows.append(_row(fy, 1, "Receipts", None, "SL", 1))
        rows += [_row(fy, 2 + i, n, a, "RSG", 3 if i == 2 else 2) for i, (n, a) in enumerate(receipts[:2])]
        rows.append(_row(fy, 4, "Social Insurance and Retirement Receipts:", None, "RSG"))
        rows += [_row(fy, 5, receipts[2][0], receipts[2][1], "RSG", 3), _row(fy, 6, receipts[3][0], receipts[3][1], "RSG")]
        rows.append(_row(fy, 7, "Total", sum(a for _, a in receipts), "SL"))
        rows.append(_row(fy, 8, "Net Outlays", None, "SL", 1))
        fns = function_amounts(fy)
        for i, (n, a) in enumerate(fns):
            rows.append(_row(fy, 9 + i, n, a + (Decimal("500.00") if fy == break_year and i == 0 else 0)))
        rows.append(_row(fy, 9 + len(fns), "Total", sum(a for _, a in fns), "SL"))
    # a stray mid-year row, which the reader must ignore
    rows.append(dict(_row(years[-1] + 1, 9, "National Defense", Decimal("1.00")), record_calendar_month="10", record_calendar_day="31", record_date=f"{years[-1]}-10-31"))
    return {"data": rows, "meta": {"count": len(rows)}}


def outlays_total(fy):
    return sum(a for _, a in function_amounts(fy))


def table_3(years=YEARS, off_by=Decimal(0)):
    rows = []
    for fy in years:
        total = outlays_total(fy)
        rows += [_row(fy, 1, "Budget Receipts", None, "SLB", 1), _row(fy, 2, "Individual Income Taxes", Decimal("5.00"), "RSG"), _row(fy, 3, "Total Receipts", Decimal("5.00"), "SLB"),
                 _row(fy, 16, "Budget Outlays", None, "SLB", 1)]
        agencies = [(f"Department of Example {i}", (total / 40).quantize(Decimal("0.01"))) for i in range(1, 21)]
        agencies[4] = ("Department of Defense--Military Programs", agencies[4][1])
        used = sum(a for _, a in agencies)
        for i, (n, a) in enumerate(agencies):
            rows.append(_row(fy, 17 + i, n, a, "C"))
        rows.append(_row(fy, 40, "Department of the Treasury:", None, "C"))
        rows += [_row(fy, 41, "Interest on Treasury Debt Securities (Gross)", Decimal("700000.00"), "P", 3), _row(fy, 42, "Other", Decimal("50000.00"), "P", 3)]
        rows.append(_row(fy, 43, "Independent Agencies", total - used - Decimal("750000.00") + Decimal("90000.00") + off_by, "C"))
        rows.append(_row(fy, 49, "Undistributed Offsetting Receipts:", None, "SL"))
        rows += [_row(fy, 50, "Interest", Decimal("-60000.00"), "UORG", 3), _row(fy, 51, "Other", Decimal("-30000.00"), "UORG", 3)]
        rows += [_row(fy, 52, "Total Outlays", total, "SLB"), _row(fy, 53, "(On-Budget)", total, "SLB", 3)]
    return {"data": rows, "meta": {"count": len(rows)}}


def when(day=10, hour=11):
    return datetime(2031, 3, day, hour, 0, 0, tzinfo=timezone.utc)


def fr_doc(i, closes, kind="Notice", agencies=("Example Department", "Example Bureau"), comment=True):
    return {"title": f"Example  notice number {i} <about widgets>", "type": kind, "abstract": "An example abstract. " * 40,
            "document_number": f"2031-{i:05d}", "html_url": f"https://www.federalregister.gov/documents/2031/03/01/2031-{i:05d}/example-{i}",
            "publication_date": "2031-03-01", "comments_close_on": closes,
            "agencies": [{"raw_name": a.upper(), "name": a, "id": n, "slug": common.slugify(a)} for n, a in enumerate(agencies)],
            "docket_ids": [f"Docket No. EX-2031-{i:04d}"], "action": "Notice.", "significant": i % 9 == 0,
            "comment_url": f"http://www.regulations.gov/commenton/EX-2031-{i:04d}-0001" if comment else None}


def fr_open(n=70, first_day=10):
    """n documents closing on and after 2031-03-<first_day>; a few are proposed rules; one small agency; one closed."""
    docs = []
    for i in range(1, n + 1):
        closes = (datetime(2031, 3, first_day) + timedelta(days=i % 25)).strftime("%Y-%m-%d")
        kind = "Proposed Rule" if i % 5 == 0 else "Notice"
        agencies = ("Tiny Commission",) if i in (3, 4) else ("Example Department", "Example Bureau") if i % 2 else ("Other Agency",)
        docs.append(fr_doc(i, closes, kind, agencies, comment=i % 4 != 0))
    docs.append(fr_doc(999, "2031-03-01"))        # already closed: the reader must drop it
    docs.append(dict(fr_doc(1, "2031-03-11")))    # a repeat of document 1
    return {"count": len(docs), "total_pages": 1, "results": docs}


class FakeHttp:
    """Answers by address. A value that is an Exception is raised."""

    def __init__(self, **routes):
        self.routes = {"mts_table_9": table_9(), "mts_table_3": table_3(), "documents.json": fr_open(),
                       "/agencies": [{"name": f"Agency {i:03d}"} for i in range(150)]}
        self.routes.update({k.replace("__", "."): v for k, v in routes.items()})
        self.calls, self.log = 0, []

    def json(self, url, body=None, **kw):
        self.calls += 1
        self.log.append(url)
        for key, value in self.routes.items():
            if key in url:
                if isinstance(value, Exception):
                    raise value
                return value
        raise AssertionError(url)


def quiet():
    return contextlib.redirect_stdout(io.StringIO())


def text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class TempData:
    """Point the pipeline's data folder at an empty temporary folder for one test."""

    def setUp(self):
        self._tmp = tempfile.mkdtemp(prefix="civictools-test-")
        self._old = common.DATA_DIR[0]
        common.DATA_DIR[0] = os.path.join(self._tmp, "data")
        self.site = os.path.join(self._tmp, "site")
        self._env = {k: os.environ.pop(k, None) for k in ("SITE_URL", "SITE_INDEXABLE", "GOATCOUNTER_URL", "SPONSOR_URL", "SPONSOR_NAME", "CLOCK_OFFSET_SECONDS")}

    def tearDown(self):
        common.DATA_DIR[0] = self._old
        shutil.rmtree(self._tmp, ignore_errors=True)
        for k, v in self._env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
