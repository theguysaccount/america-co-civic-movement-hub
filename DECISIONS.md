# DECISIONS

1. **Three tools only.** The brief is the no-signup civic tools: Taxpayer Receipt, comment deadlines, FOIA builder.
   The boards, movement pages and everything that needs a database or a server route are left to america.co.
2. **Staged, not launched.** `america.co` serves all three tools today, so this copy is `noindex`, has no sitemap and
   skips IndexNow. Two settings switch it over (OPERATIONS.md). Jack decides. Nothing in america.co's repositories or
   DNS was touched.
3. **Treasury's statement instead of hand-entered CBO figures.** The original's receipt uses eight CBO categories typed
   in for fiscal year 2025. An automated job cannot keep those current: cbo.gov refuses automated requests. Treasury's
   Monthly Treasury Statement has a keyless API, is the government's own record of outlays, and its final September
   statement gives the whole fiscal year. The cost: 19 budget functions instead of 8 friendlier categories, and "mandatory" and
   "discretionary" are no longer lines. The receipt explains both.
4. **No USAspending totals.** The brief suggested them. USAspending's per-agency outlays add up to a larger figure
   than Treasury's total net outlays (about $9.6 trillion against $7.4 trillion for fiscal year 2026, read
   2026-11-10), so they cannot sit on the same receipt. Treasury's agency table ends at the same total as its function
   table. One source, one total.
5. **A year is published only if it adds up.** Function lines, agency lines and receipt lines must each sum to
   Treasury's published totals within a dollar, and the two tables must agree. Otherwise the last good file stays.
6. **Whole cents, largest remainder.** Each share is rounded down to the cent and the leftover cents go to the largest
   remainders, so a receipt always sums to the amount entered. The browser uses exact integer arithmetic (BigInt), and
   a headless-Chrome test compares it with the Python calculation.
7. **Negative lines are shown as negative.** Treasury records some collections as negative outlays. Hiding or netting
   them would change the published figures.
8. **Share links carry the amount after the `#`.** A fragment is not sent to a server or written to its logs.
9. **All open comment periods, from the API.** The original filters the newest 100 documents in the browser. This copy
   asks the Federal Register API for every document whose comment period closes today or later (about 950).
10. **The Federal Register's web pages are for people.** FederalRegister.gov sends scripts that open its web pages to
    a browser check, and Regulations.gov answers 403. The job reads only the API. The weekly link check reports those
    pages as "refused" and never works around it.
11. **Only the API's own comment link.** A "Comment" button appears only when the Federal Register supplies the
    Regulations.gov form address. No comment or docket address is constructed.
12. **Dates are Washington, D.C. dates.** A document leaves the lists the day after it closes. The page script hides
    anything that has closed since the build and warns when a build is more than two days old.
13. **Agency pages need three open documents.** Fewer would be thin pages that appear and vanish.
14. **FOIA: wording, not routing.** Agency names come from the Federal Register's list for convenience only. Where to
    send a request is left to FOIA.gov, because a wrong address is worse than none. The fee-waiver and expedited
    sentences follow the statute's own tests; the page says it is a drafting aid, not legal advice.
15. **No web fonts or third-party scripts.** The original loads Google Fonts. This copy loads nothing from another
    site, and the guard fails a build that does.
16. **Budget-function descriptions are plain summaries** written for this site and labelled as such.

## Questions for Jack (nothing is blocked on them)
- Should these pages go to `tools.america.co`, replace the three original pages, or stay a staged mirror?
- Should the live receipt on america.co move to Treasury's fiscal year 2026 figures? It still shows 2025.
