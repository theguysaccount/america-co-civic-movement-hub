"""Federal receipts and outlays from Treasury's Monthly Treasury Statement (Fiscal Data API, no key).

Two tables of the statement are read, for each completed fiscal year (the September statement):
  Table 9  receipts by source and net outlays by budget function
  Table 3  receipts and net outlays by agency
Both tables end at the same total. A year is accepted only if its lines add up to the published
totals, so a receipt built from it adds up too.
"""
from decimal import Decimal

from .common import slugify

API = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/mts"
DATASET = "https://fiscaldata.treasury.gov/datasets/monthly-treasury-statement/"
TABLE_9 = DATASET + "summary-of-receipts-by-source-and-outlays-by-function-of-the-u-s-government"
TABLE_3 = DATASET + "summary-of-receipts-and-outlays-of-the-u-s-government"
TOLERANCE = Decimal("1.00")     # lines may differ from the published total by rounding, never by more than a dollar


class Mismatch(Exception):
    """A statement whose lines do not add up to its own total. It is not used."""


def url(table):
    # No `fields` parameter: this API sums rows when columns are left out.
    return f"{API}/{table}?filter=record_calendar_month:eq:09&sort=-record_date,src_line_nbr&page[size]=5000"


def _amount(row):
    v = row.get("current_fytd_rcpt_outly_amt")
    return None if v in (None, "", "null") else Decimal(v)


def _by_year(payload):
    years = {}
    for row in payload.get("data", []):
        if row.get("record_calendar_month") != "09" or row.get("record_calendar_day") != "30":
            continue
        years.setdefault(row["record_fiscal_year"], []).append(row)
    for rows in years.values():
        rows.sort(key=lambda r: int(r["src_line_nbr"]))
    return years


def _check(label, parts, total):
    got = sum(parts, Decimal(0))
    if abs(got - total) > TOLERANCE:
        raise Mismatch(f"{label}: lines sum to {got} but the statement's total is {total}")


def parse_table_9(payload):
    """{fiscal year: {record_date, receipts: [...], receipts_total, functions: [...], outlays_total}}"""
    out = {}
    for fy, rows in _by_year(payload).items():
        receipts, functions, totals, section = [], [], {}, ""
        for r in rows:
            name, amt, kind = " ".join(r["classification_desc"].split()).rstrip(":"), _amount(r), r.get("record_type_cd")
            if amt is None:
                if name in ("Receipts", "Net Outlays"):
                    section = name
                continue
            if name == "Total":
                totals[section] = amt
            elif section == "Receipts":
                receipts.append({"name": name, "amount": str(amt)})
            elif section == "Net Outlays" and kind == "F":
                functions.append({"name": name, "slug": slugify(name), "amount": str(amt)})
        if "Receipts" not in totals or "Net Outlays" not in totals or len(functions) < 15:
            raise Mismatch(f"fiscal year {fy}: table 9 is missing its totals or its function lines")
        _check(f"FY{fy} outlays by function", [Decimal(f["amount"]) for f in functions], totals["Net Outlays"])
        _check(f"FY{fy} receipts by source", [Decimal(x["amount"]) for x in receipts], totals["Receipts"])
        out[fy] = {"record_date": rows[0]["record_date"], "receipts": receipts, "receipts_total": str(totals["Receipts"]),
                   "functions": functions, "outlays_total": str(totals["Net Outlays"]),
                   "deficit": str(totals["Net Outlays"] - totals["Receipts"])}
    return out


def parse_table_3(payload):
    """{fiscal year: {agencies: [...], outlays_total}}. A department that the statement splits (Treasury) is listed by its parts."""
    out = {}
    for fy, rows in _by_year(payload).items():
        agencies, total, in_outlays, parent = [], None, False, ""
        for r in rows:
            name, amt, level = " ".join(r["classification_desc"].split()).rstrip(":"), _amount(r), int(r.get("sequence_level_nbr") or 0)
            if name == "Budget Outlays":
                in_outlays = True
                continue
            if not in_outlays:
                continue
            if name == "Total Outlays":
                total = amt
                break
            if amt is None:                    # a heading whose parts follow, such as "Department of the Treasury:"
                parent = name if level == 2 else parent
                continue
            if level == 3 and parent:
                label = {"Department of the Treasury": {"Interest on Treasury Debt Securities (Gross)": "Interest on Treasury debt securities (gross)",
                                                        "Other": "Department of the Treasury, other"},
                         "Undistributed Offsetting Receipts": {"Interest": "Undistributed offsetting receipts: interest",
                                                               "Other": "Undistributed offsetting receipts: other"}}.get(parent, {}).get(name, f"{parent}: {name}")
            else:
                label, parent = name.replace("--", ": "), ""
            agencies.append({"name": label, "slug": slugify(label), "amount": str(amt)})
        if total is None or len(agencies) < 20:
            raise Mismatch(f"fiscal year {fy}: table 3 is missing its total or its agency lines")
        _check(f"FY{fy} outlays by agency", [Decimal(a["amount"]) for a in agencies], total)
        out[fy] = {"agencies": agencies, "outlays_total": str(total)}
    return out


def fetch(http):
    """Read both tables and return the combined record. Raises if a year does not add up or the tables disagree."""
    nine = parse_table_9(http.json(url("mts_table_9")))
    three = parse_table_3(http.json(url("mts_table_3")))
    years = {}
    for fy in sorted(nine):
        rec = dict(nine[fy])
        if fy in three:
            if abs(Decimal(three[fy]["outlays_total"]) - Decimal(rec["outlays_total"])) > TOLERANCE:
                raise Mismatch(f"fiscal year {fy}: table 3 and table 9 disagree on total outlays")
            rec["agencies"] = three[fy]["agencies"]
        years[fy] = rec
    if not years:
        raise Mismatch("no completed fiscal year in the statement")
    return {"fiscal_years": years, "latest": max(years, key=int),
            "source": {"name": "Monthly Treasury Statement, U.S. Department of the Treasury, Bureau of the Fiscal Service",
                       "dataset": DATASET, "by_function": TABLE_9, "by_agency": TABLE_3,
                       "api": [url("mts_table_9"), url("mts_table_3")]}}
