"""Weekly: check that the official pages this site sends readers to still answer.

  python3 -m civictools.linkcheck [_site]

Every reference link in the built pages is requested once, a second apart, with this project's
honest User-Agent. Links to individual Federal Register documents and comment forms are not
requested (there are hundreds, and those sites keep their web pages for people); the daily read
of the Federal Register API is their check.

A site that refuses automated requests is reported as "refused" and never worked around. The job
fails only when a link is plainly gone (404 or 410), so someone fixes the page that carries it.
"""
import os
import re
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from .common import ROOT, load_config, site_url

SKIP = re.compile(r"^https://www\.federalregister\.gov/documents/\d{4}/|^https://www\.regulations\.gov/commenton/|^https://github\.com/|^https://gc\.zgo\.at/")
HREF = re.compile(r'href="(https://[^"#]+)')


def collect(site_dir):
    own = site_url(load_config()) + "/"
    found = {}
    for dirpath, _, files in os.walk(site_dir):
        for fn in files:
            if fn.endswith(".html"):
                rel = os.path.relpath(os.path.join(dirpath, fn), site_dir)
                with open(os.path.join(dirpath, fn), encoding="utf-8") as f:
                    for url in HREF.findall(f.read()):
                        url = url.replace("&amp;", "&")
                        if not SKIP.match(url) and not url.startswith(own):       # this site's own pages are the self-test's job
                            found.setdefault(url, rel)
    return found


def check(url, ua):
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.5"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            final = urlsplit(r.geturl()).hostname or ""
            if final.startswith("unblock."):
                return "refused", "sent to a browser check"
            return "ok", str(r.status)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403, 406, 429):
            return "refused", f"HTTP {e.code}"
        return ("gone" if e.code in (404, 410) else "error"), f"HTTP {e.code}"
    except Exception as e:
        return "error", type(e).__name__


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    site_dir = argv[0] if argv else os.path.join(ROOT, "_site")
    ua = load_config()["user_agent"]
    links = collect(site_dir)
    rows, last_host = [], {}
    for url in sorted(links):
        host = urlsplit(url).hostname
        wait = 1.0 - (time.monotonic() - last_host.get(host, 0))
        if wait > 0:
            time.sleep(wait)
        outcome, detail = check(url, ua)
        last_host[host] = time.monotonic()
        rows.append((outcome, detail, url, links[url]))
        print(f"{outcome:8} {detail:22} {url}  (on {links[url]})", flush=True)
    gone = [r for r in rows if r[0] == "gone"]
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("### Reference links\n\n| Result | Detail | Link | First seen on |\n|---|---|---|---|\n")
            for r in sorted(rows):
                f.write(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]} |\n")
    counts = {k: sum(1 for r in rows if r[0] == k) for k in ("ok", "refused", "error", "gone")}
    print(f"linkcheck: {len(rows)} links: {counts['ok']} ok, {counts['refused']} refused automated requests, {counts['error']} errors, {counts['gone']} gone")
    return 1 if gone else 0


if __name__ == "__main__":
    sys.exit(main())
