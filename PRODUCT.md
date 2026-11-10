# PRODUCT: America.co Public Tools (static edition)

**User.** Someone who wants to see the record for themselves: a taxpayer at filing time, a resident or advocate who
cares about one rule, a reporter or citizen who needs a document from an agency.

**The painful jobs.**
- "Where do my taxes go?" has no official itemized answer for one person's amount.
- Comment periods close quietly. The official search is built for people who already know the docket.
- A first FOIA request is a blank page, and vague requests get slow or empty answers.

**Promise.** Follow the money, read the rule, find the record: three tools that work in ten seconds with no account,
and show the source and the date for every number.

**Wedge.** Searches such as "where do my taxes go", "federal taxpayer receipt", "[agency] rules open for comment",
"comment deadline federal register", "FOIA request template". The receipt's share link, text download and embed, the
deadline calendar file and feed, and the FOIA letter are outputs people pass on.

**Why now.** Treasury and the Federal Register both publish keyless APIs, so the tools can be exact and current with
no server. Fiscal year 2026 closed on September 30, 2026 and its final statement is out.

**What it will not do (v1).**
- Estimate anyone's taxes, or claim a payment was earmarked for anything.
- Take a side on a spending line, a rule, an agency, a party or an official.
- Submit a comment or a FOIA request, or store anything a visitor types.
- Give tax, legal or financial advice.

**Activation metric.** A visitor finishes one output: changes the receipt amount, follows a document or comment link,
or copies or downloads a FOIA request. Counted only if `GOATCOUNTER_URL` is set; no events are sent today.

**First revenue event (key, off).** None on this site: GitHub Pages is non-commercial. One marked sponsor slot shows a
supporter's name and link when `SPONSOR_URL` and `SPONSOR_NAME` are set (a grant-maker or sponsor Jack arranges).
