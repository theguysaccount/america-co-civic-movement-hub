"""Documents open for public comment, from the Federal Register API (no key), and the agency list.

The API is the route FederalRegister.gov offers to software. Only the API is read; the website's
pages are for people and are never fetched.
"""
from urllib.parse import urlencode

from .common import clip

API = "https://www.federalregister.gov/api/v1"
FIELDS = ["title", "type", "abstract", "document_number", "html_url", "publication_date", "agencies", "comments_close_on",
          "docket_ids", "action", "significant", "comment_url"]
TYPES = {"Proposed Rule": "Proposed rule", "Rule": "Rule", "Notice": "Notice", "Presidential Document": "Presidential document"}


def open_url(today, page=1):
    q = [("per_page", "1000"), ("page", str(page)), ("order", "oldest"), ("conditions[comment_date][gte]", today)]
    q += [("fields[]", f) for f in FIELDS]
    return f"{API}/documents.json?{urlencode(q)}"


def human_search_url():
    return "https://www.federalregister.gov/"


def tidy(doc):
    """One compact record per document. Nothing is added: every field is the Federal Register's."""
    agencies = []
    for a in doc.get("agencies") or []:
        name = a.get("name") or " ".join((a.get("raw_name") or "").title().split())
        if name and name not in [x["name"] for x in agencies]:
            agencies.append({"name": name, "slug": a.get("slug") or ""})
    # The API's own link to the comment form. It still says http; the same address is served over https.
    comment_url = doc.get("comment_url") or ""
    if comment_url.startswith("http://www.regulations.gov/"):
        comment_url = "https://" + comment_url[len("http://"):]
    if not comment_url.startswith("https://www.regulations.gov/"):
        comment_url = ""
    return {"number": doc.get("document_number") or "", "title": " ".join((doc.get("title") or "").split()),
            "type": doc.get("type") or "", "agencies": agencies, "closes": doc.get("comments_close_on") or "",
            "published": doc.get("publication_date") or "", "url": doc.get("html_url") or "", "comment_url": comment_url,
            "dockets": [d for d in (doc.get("docket_ids") or []) if d][:4], "action": clip(doc.get("action") or "", 120),
            "significant": bool(doc.get("significant")), "abstract": clip(doc.get("abstract") or "", 420)}


def fetch_open(http, today):
    """Every document whose comment period closes today or later, soonest first."""
    docs, page = [], 1
    while page <= 10:
        payload = http.json(open_url(today, page))
        docs += [tidy(d) for d in payload.get("results") or []]
        if not payload.get("next_page_url") or page >= int(payload.get("total_pages") or 1):
            break
        page += 1
    docs = [d for d in docs if d["number"] and d["title"] and d["closes"] >= today and d["url"].startswith("https://www.federalregister.gov/")]
    seen, out = set(), []
    for d in sorted(docs, key=lambda d: (d["closes"], d["published"], d["number"])):
        if d["number"] not in seen:
            seen.add(d["number"])
            out.append(d)
    return {"documents": out, "source": {"name": "Federal Register API, Office of the Federal Register (National Archives) and Government Publishing Office",
                                         "api": open_url(today), "search": human_search_url()}}


def fetch_agencies(http):
    """Agency names for the FOIA builder's suggestions. Names only: where to send a request is FOIA.gov's to say."""
    rows = http.json(f"{API}/agencies")
    names = sorted({" ".join((a.get("name") or "").split()) for a in rows if a.get("name")})
    return {"agencies": names, "source": {"name": "Federal Register API agency list", "api": f"{API}/agencies"}}
