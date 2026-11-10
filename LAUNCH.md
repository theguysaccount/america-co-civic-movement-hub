# LAUNCH

This build is **staged**. It is public at its GitHub Pages address so it can be reviewed, but it tells search engines
to stay away, because america.co serves these tools today. Nothing has been posted, sent or submitted anywhere.

## What is live
- https://theguysaccount.github.io/america-co-civic-movement-hub/ (noindex, robots.txt disallows crawling, no sitemap).
- The IndexNow key file is published but nothing is submitted while the site is staged.

## Going live (Jack's decision)
The exact DNS record and the two settings are in OPERATIONS.md under "Cutover". In short: add `tools.america.co` as a
CNAME to GitHub Pages in Vercel DNS, set `SITE_URL`, and set `SITE_INDEXABLE=true`.

## Once indexed: the search surfaces
| Query pattern | Page |
|---|---|
| "where do my taxes go", "federal taxpayer receipt", "tax receipt calculator" | `/taxpayer-receipt/` |
| "how much does the federal government spend on [Medicare, defense, interest…]" | `/taxpayer-receipt/<line>/` (19 pages) |
| "[agency] proposed rules open for comment", "[agency] comment period" | `/comment-deadlines/agency/<agency>/` |
| "federal rules open for public comment", "comment periods closing this week" | `/comment-deadlines/`, `/closing-soon/`, `/proposed-rules/` |
| "FOIA request template", "how to write a FOIA request" | `/foia-request-builder/` |

Every page carries real figures or records with their source and date. Agency pages exist only with three or more
open documents; the embed is never indexed. `WebApplication`, `FAQPage`, `Dataset` and `WebSite` structured data are
in place.

## Loops built into the product
- **Receipt share link**: carries the amount after the `#`; opens the same receipt for whoever follows it.
- **Receipt embed**: an iframe snippet on the receipt page, linking back.
- **Text download and print** for the receipt and the FOIA request.
- **Calendar file and feed** for comment deadlines: subscribe once, keep getting them.
- **Open data**: CSV and JSON for outlays and for open comment periods.

## The cheapest test (for a human; nothing here has been sent)
Send the receipt to one creator's audience at filing time with a single link, and count how many visitors change the
amount. The share link already carries an example amount: `/taxpayer-receipt/#amount=8500`.
