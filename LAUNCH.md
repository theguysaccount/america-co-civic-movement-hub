# LAUNCH

This build is **staged**. It is public at its GitHub Pages address, but it tells search engines to stay away until
it has an address of its own. Nothing has been posted, sent or submitted anywhere.

## What is live
- https://theguysaccount.github.io/america-co-civic-movement-hub/ (noindex, robots.txt disallows crawling, no sitemap).
- The IndexNow key file is published but nothing is submitted while the site is staged.

## Going live
The site goes beside America.co and never replaces it. Two separate steps, both in OPERATIONS.md: its own address
(`tools.america.co` as a CNAME to GitHub Pages in Vercel DNS, the Pages custom domain, a rebuild) and the indexing
switch (`SITE_INDEXABLE=true`). The pages America.co already serves (the receipt tool, the comment deadlines, the
FOIA builder) stay out of search either way and point to America.co.

## Once live: the search surfaces
| Query pattern | Page |
|---|---|
| "how much does the federal government spend on [Medicare, defense, interest…]" | `/taxpayer-receipt/<line>/` (19 pages) |
| "federal outlays by function csv", "federal spending by function data" | `/data/` |
| "america.co public tools", "free civic tools no account" | `/` |

The receipt tool, the comment-deadline pages and the FOIA builder are not search surfaces here: America.co serves
its own, so these stay `noindex` and each points to America.co's page. Every indexable page carries real figures
with their source and date. The embed is never indexed. `WebApplication`, `FAQPage`, `Dataset` and `WebSite`
structured data are in place.

## Loops built into the product
- **Receipt share link**: carries the amount after the `#`; opens the same receipt for whoever follows it.
- **Receipt embed**: an iframe snippet on the receipt page, linking back.
- **Text download and print** for the receipt and the FOIA request.
- **Calendar file and feed** for comment deadlines: subscribe once, keep getting them.
- **Open data**: CSV and JSON for outlays and for open comment periods.

## The cheapest test (for a human; nothing here has been sent)
Send the receipt to one creator's audience at filing time with a single link, and count how many visitors change the
amount. The share link already carries an example amount: `/taxpayer-receipt/#amount=8500`.
