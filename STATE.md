# STATE (2026-11-22)

**Staged:** https://theguysaccount.github.io/america-co-civic-movement-hub/ (noindex), beside america.co, which is
unchanged. Its own address needs one DNS record in Vercel, and indexing is one variable (both in OPERATIONS.md).
Once indexable, the receipt tool, the comment-deadline pages and the FOIA builder still stay out of search because
America.co serves its own; the home page, the 19 spending-line pages, sources, about and data are this site's own.

## Works
- **Taxpayer receipt.** Any amount split across the 19 budget functions or 32 agency lines of Treasury's final fiscal
  year 2026 statement, to the cent, with share links, a text download, print, and an embeddable version. One page per
  spending line with its history since fiscal year 2015.
- **Comment deadlines.** Every federal document open for comment (1,005 on 2026-11-22), searchable, with pages for 86
  agencies, proposed rules, closing-soon, a calendar file and a feed. America.co has since added its own comment
  calendar with a page per agency, month and notice, so these pages now repeat it.
- **FOIA request builder.** Six answers become a request letter with fee category, fee waiver and expedited-processing
  wording. Runs in the browser; sends and stores nothing.
- Daily refresh, weekly arithmetic, live-site and link checks, keep-alive. 41 tests. Sources and read dates on every number.
  Both scheduled workflows have passed on GitHub's own schedule trigger (first on 2026-11-10), not only by hand.

## What the original has that this copy does not
- Every Federal Dollar (needs the `/api/usaspending` server route), Bill Truth, the election calendar, the agency atlas,
  the boards, the movement pages and everything with a database. This copy is the three no-signup tools only.

## Reused from the original (`america-future-release-20261003`, read-only copy)
- The three tools' purpose and wording ("Taxpayer money finally comes with a receipt", "Comment before it closes",
  "Specific beats dramatic"), the receipt's look, the source standard, the palette and the FOIA letter's skeleton.

## Changed on purpose
- The receipt reads Treasury's Monthly Treasury Statement (an API) instead of hand-entered CBO figures for 2025.

## Not done
- No address of its own yet, no analytics, no sponsor (all in OPERATIONS.md). Unified States explainers are not included.
