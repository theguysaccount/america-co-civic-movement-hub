# America.co Public Tools (static edition)

**Staged copy:** https://theguysaccount.github.io/america-co-civic-movement-hub/ (not indexed).
**Live original:** https://america.co (unchanged; the cutover is a separate decision, see [OPERATIONS.md](OPERATIONS.md)).

Three free civic tools that need no account and no server:

| Tool | What it does | Source |
|---|---|---|
| [Federal taxpayer receipt](https://theguysaccount.github.io/america-co-civic-movement-hub/taxpayer-receipt/) | Splits any tax amount across what the federal government paid out last fiscal year, by purpose or by agency, to the cent. A page per spending line with its history. | [Monthly Treasury Statement](https://fiscaldata.treasury.gov/datasets/monthly-treasury-statement/), U.S. Treasury |
| [Comment deadlines](https://theguysaccount.github.io/america-co-civic-movement-hub/comment-deadlines/) | Every federal document open for public comment, soonest deadline first, searchable, by agency, with a calendar file and a feed. | [Federal Register API](https://www.federalregister.gov/developers/documentation/api/v1) |
| [FOIA request builder](https://theguysaccount.github.io/america-co-civic-movement-hub/foia-request-builder/) | Six answers become a clear Freedom of Information Act request to copy, download or print. Nothing is sent or stored. | 5 U.S.C. § 552; links to FOIA.gov |

Nonpartisan by construction: the tools report what the records say, with a source and a read date on every number.
Python's standard library reads the two public APIs and writes a static site. No dependencies, no keys.

## Layout

| Path | What it is |
|---|---|
| `civictools/treasury.py` | Reads the final statement of each fiscal year and refuses any year whose lines do not add up |
| `civictools/fedreg.py` | Every document whose comment period closes today or later; the agency list |
| `civictools/receipt.py` | The receipt's arithmetic in whole cents (mirrored in `static/app.js` with BigInt) |
| `civictools/refresh.py` | Runs the sources independently; `data/status.json` |
| `civictools/build.py`, `og.py` | The static site, search index, CSV/JSON, calendar file, feed, embed, share cards |
| `civictools/guard.py`, `e2e.py`, `selftest.py`, `linkcheck.py` | Pre-deploy checks, browser check, live check, weekly reference-link check |
| `config/site.json`, `config/functions.json` | Base URL default, staged/indexable flag, limits; plain descriptions of the budget functions |
| `data/` | The last good read of each source. Committed by the daily job |

## Run it

```sh
python3 -m unittest discover -s tests -t .      # tests (Python 3.9+; no installs)
python3 -m civictools.refresh                    # read the sources (skips any read a short while ago)
python3 -m civictools.build --site _site         # build the site
python3 -m civictools.og --site _site            # share cards (needs Chrome; falls back to the default card)
python3 -m civictools.guard _site                # the checks every deploy must pass
python3 -m civictools.e2e _site                  # receipt arithmetic, search and FOIA builder in headless Chrome
python3 -m civictools.selftest                   # check the live site
python3 -m civictools.linkcheck _site            # the official pages the site links to
```

To preview locally, serve a folder that contains `_site` under the name `america-co-civic-movement-hub`, or build
with `SITE_URL=http://localhost:8000`.

## Licence

Code: MIT. Compiled data: CC0 1.0 (the underlying federal data is public domain).
More: [PRODUCT.md](PRODUCT.md), [DECISIONS.md](DECISIONS.md), [STATE.md](STATE.md), [LAUNCH.md](LAUNCH.md).
