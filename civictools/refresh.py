"""Refresh every source, each one on its own.

  python3 -m civictools.refresh                 # what the daily job runs
  python3 -m civictools.refresh --only comments # some sources (treasury, comments, agencies)
  python3 -m civictools.refresh --check-fresh   # exit 1 if a source has not been read in time

A source that fails keeps its last good file: data/status.json records the error and the last
success, and every page prints the date its numbers were read, so old numbers never pass as new.
"""
import argparse
import json
import os
import sys
import traceback
from datetime import timedelta

from . import fedreg, treasury
from .common import Http, HttpError, data_path, eastern_today, iso, load_config, now_utc, parse_iso, read_json, write_json

SOURCES = ["treasury", "comments", "agencies"]
LABEL = {"treasury": "Monthly Treasury Statement", "comments": "Federal Register comment periods", "agencies": "Federal Register agency list"}
# A source read this recently is left alone, so a second run the same day costs nothing.
MIN_GAP = {"treasury": timedelta(hours=20), "comments": timedelta(hours=3), "agencies": timedelta(days=6)}


def path(name):
    return data_path({"treasury": "treasury.json", "comments": "comments.json", "agencies": "agencies.json", "status": "status.json"}[name])


def write_documents(file, rec):
    """comments.json with one document per line, so a day's changes are a small diff in the repository."""
    head = {k: v for k, v in rec.items() if k != "documents"}
    lines = ",\n".join(json.dumps(d, ensure_ascii=False, sort_keys=True, separators=(",", ":")) for d in rec["documents"])
    text = json.dumps(head, ensure_ascii=False, sort_keys=True, separators=(",", ":"))[:-1] + ',"documents":[\n' + lines + "\n]}\n"
    os.makedirs(os.path.dirname(file), exist_ok=True)
    tmp = file + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, file)


def read_treasury(http, cfg, now):
    rec = treasury.fetch(http)
    years = {fy: v for fy, v in rec["fiscal_years"].items() if int(fy) >= cfg["first_fiscal_year"]}
    if len(years) < cfg["min_fiscal_years"]:
        raise treasury.Mismatch(f"only {len(years)} completed fiscal years in the statement")
    old = read_json(path("treasury"), {}) or {}
    if old.get("latest") and int(rec["latest"]) < int(old["latest"]):
        raise treasury.Mismatch(f"the statement's latest fiscal year went back from {old['latest']} to {rec['latest']}")
    rec["fiscal_years"] = years
    rec["retrieved_at"] = iso(now)
    changed = {k: v for k, v in rec.items() if k != "retrieved_at"} != {k: v for k, v in old.items() if k != "retrieved_at"}
    write_json(path("treasury"), rec)
    return {"note": f"fiscal years {min(years, key=int)} to {rec['latest']}; every year's lines add up to its total", "changed": changed}


def read_comments(http, cfg, now):
    today = eastern_today(now)
    rec = fedreg.fetch_open(http, today)
    n = len(rec["documents"])
    old = read_json(path("comments"), {}) or {}
    still_open = sum(1 for d in old.get("documents", []) if d["closes"] >= today)
    if n < cfg["min_comment_documents"]:
        raise RuntimeError(f"only {n} open documents returned (minimum {cfg['min_comment_documents']})")
    if still_open and n < still_open * (1 - cfg["max_comment_drop_share"]):
        raise RuntimeError(f"{n} open documents returned, but {still_open} from the last good read are still open; kept the last good read")
    known = {d["number"]: d.get("first_seen") or today for d in old.get("documents", [])}
    for d in rec["documents"]:
        d["first_seen"] = known.get(d["number"], today)     # the day this list first carried the document
    rec["retrieved_at"], rec["as_of_date"] = iso(now), today
    write_documents(path("comments"), rec)
    new = sum(1 for d in rec["documents"] if d["number"] not in known) if known else 0
    return {"note": f"{n} documents open for comment on {today}; {new} new since the last read", "changed": True}


def read_agencies(http, cfg, now):
    rec = fedreg.fetch_agencies(http)
    if len(rec["agencies"]) < 100:
        raise RuntimeError(f"only {len(rec['agencies'])} agencies returned")
    old = read_json(path("agencies"), {}) or {}
    changed = old.get("agencies") != rec["agencies"]
    rec["retrieved_at"] = iso(now)
    write_json(path("agencies"), rec, compact=True)
    return {"note": f"{len(rec['agencies'])} agency names", "changed": changed}


READERS = {"treasury": read_treasury, "comments": read_comments, "agencies": read_agencies}


def run(only=None, now=None, http=None, force=False):
    now = now or now_utc()
    cfg = load_config()
    http = http or Http(cfg)
    status = read_json(path("status"), {}) or {}
    for name in SOURCES:
        if only and name not in only:
            continue
        st = status.get(name, {})
        last = parse_iso(st.get("last_success"))
        if not force and st.get("ok") and last and now - last < MIN_GAP[name]:
            print(f"{name}: read {st['last_success']}; not asking again yet", flush=True)
            continue
        st["checked_at"] = iso(now)
        try:
            res = READERS[name](http, cfg, now)
            st.update(ok=True, error="", note=res["note"], last_success=iso(now))
            if res.get("changed"):
                st["last_changed"] = iso(now)
        except Exception as e:      # keep the last good file; report and carry on with the other sources
            st.update(ok=False, error=f"{type(e).__name__}: {e}"[:400])
            if not isinstance(e, (treasury.Mismatch, RuntimeError, HttpError)):
                traceback.print_exc()
        status[name] = st
        print(f"{name}: {'ok ' + st.get('note', '') if st['ok'] else 'FAILED ' + st['error']}", flush=True)
    status["http_calls"] = http.calls
    write_json(path("status"), status)
    return status


def check_fresh(now=None):
    now = now or now_utc()
    cfg = load_config()
    status = read_json(path("status"), {}) or {}
    bad = []
    for name in SOURCES:
        st = status.get(name, {})
        last = parse_iso(st.get("last_success"))
        limit = timedelta(hours=cfg["stale_after_hours"][name])
        if last is None or now - last > limit:
            bad.append(f"{LABEL[name]}: last successful read {st.get('last_success', 'never')} "
                       f"(limit {cfg['stale_after_hours'][name]} hours); last error: {st.get('error', '')}")
    for b in bad:
        print("STALE", b)
    return not bad


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default="", help="comma-separated: " + ",".join(SOURCES))
    ap.add_argument("--force", action="store_true", help="read every source even if it was read a moment ago")
    ap.add_argument("--check-fresh", action="store_true")
    a = ap.parse_args(argv)
    if a.check_fresh:
        return 0 if check_fresh() else 1
    run(only=set(filter(None, a.only.split(","))), force=a.force)
    # The job fails only when there is nothing to publish at all.
    return 0 if read_json(path("treasury")) and read_json(path("comments")) else 1


if __name__ == "__main__":
    sys.exit(main())
