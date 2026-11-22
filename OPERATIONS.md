# OPERATIONS

Everything runs on GitHub Actions in `theguysaccount/america-co-civic-movement-hub`. No human has a job here.

- This site: https://theguysaccount.github.io/america-co-civic-movement-hub/. Staged (noindex) on 2026-11-22 and
  without an address of its own yet. It sits beside the original and never replaces it.
- The original: https://america.co (`/taxpayer-receipt`, `/public-comment-deadlines`, `/comment-calendar`,
  `/foia-request-builder`), on Vercel. Not touched, and its repositories are not this one.

## Automated jobs

| Workflow | When (UTC) | What it does | How it fails safely |
|---|---|---|---|
| **Refresh and deploy** `refresh.yml` | Daily 11:17, backstop 17:43; every push to `main`; by hand | 1. `civictools.refresh`: the Federal Register API (every document whose comment period closes today or later; one request), Treasury's Monthly Treasury Statement (tables 9 and 3, final September statements; two requests), the Federal Register agency list (weekly). 2. Tests. 3. Build. 4. Share cards. 5. Guard: the arithmetic, a source and date on every number page, no closed document listed, no outside resources, links. 6. Headless-Chrome check: the browser's receipt against the Python calculation, the comment search, the FOIA builder. 7. Commit `data/`. 8. Deploy. 9. Check the live site. A push skips step 1. | Each source runs on its own: a failure keeps that source's last good file and is recorded in `data/status.json`; pages keep showing the date it was read and say when the latest attempt failed. A Treasury statement whose lines do not add up to its totals, or whose latest year goes backwards, is refused. A comment list under 60 documents, or 60% smaller than the documents still open in the last good list, is refused. Any failure in steps 2 to 6 stops before deploy, so the last good site stays live. |
| **Weekly checks** `weekly.yml` | Mon 13:29; by hand | Tests; the live site: key pages, all 19 spending-line pages, and the receipt recomputed from the published `data/federal-outlays.json` against the build's own figures; `refresh --check-fresh` (fails if the comment list has had no good read in 60 hours, Treasury in 10 days, the agency list in about 17 days); reference links, one request each. If the live build is over 60 hours old or the comment list is stale, it starts **Refresh and deploy**. Keep-alive. | Read-only apart from starting a refresh. Sites that refuse automated requests are listed as "refused" and never worked around. The link step fails only on a link that is gone (404 or 410). A failure emails the repository owner. |
| **Tests** `test.yml` | Pull requests, other branches | Tests on Python 3.9 and 3.12, build, guard, browser check. | Never deploys. |

**Safe to re-run.** A source read a short while ago is not asked again (comments 3 hours, Treasury 20 hours, agency
list 6 days), so the backstop slot and repeat runs only rebuild. A rebuild with no new read still drops documents
whose comment period has closed.

**Even with no runs at all** the pages stay honest for a while: the page script hides documents that have closed
since the build and shows a warning once the build is more than two days old.

**Keep-alive.** The daily data commit keeps the schedules alive. As a backstop each scheduled run calls
`.github/scripts/keepalive.sh` (re-enables workflows GitHub paused for inactivity; empty commit after 45 quiet days).

**GitHub skips scheduled runs on this account.** Two daily slots, per-source read times and the weekly stale check
mean no run has to fire at a set time. The times in the table are the earliest a run can start, and a new or changed
schedule can take hours to start at all: on 2026-11-10 the first scheduled runs of both workflows started about eight
hours after their schedules were last pushed. Both passed. A run that finds every source read recently asks nothing
and commits nothing.

## What to watch
- **Actions → Refresh and deploy.** Red means the site was not updated; the previous site is still live. The failing
  step says why. Guard prints each problem.
- **A deploy that times out.** GitHub Pages sometimes stalls while taking in a build. The deploy job offers the same
  build a second time before failing, and the previous site stays live either way. If both attempts fail, re-run the
  failed job from the Actions tab.
- **`data/status.json`** (also on the site's Sources page): per source `ok`, `last_success`, `error`, `note`.
- **October and November.** Treasury publishes the September statement about mid-October. The receipt moves to the
  new fiscal year by itself on the next daily run. Check that the new year's negative lines still read sensibly in
  the note on the receipt page, and add a description to `config/functions.json` if Treasury ever adds a function.
- **A Treasury refusal ("Mismatch").** The statement's layout changed (a new heading or a split department). Fix the
  parser in `civictools/treasury.py` against the new rows; the tests use the same layout.
- **Weekly link report.** `federalregister.gov` web pages and `regulations.gov` always show "refused"; that is
  expected. "gone" means a reference page moved: update the link in `civictools/build.py`.
- **Federal holidays and shutdowns.** No Federal Register is published; the list simply does not change.

## Manual levers
- **Run now:** Actions → Refresh and deploy → Run workflow. Untick "refresh" to only rebuild; tick "force" to read
  every source again at once.
- **Locally:** `python3 -m civictools.refresh --only comments --force`, then commit `data/`.
- **Limits:** `config/site.json` (`min_comment_documents`, `max_comment_drop_share`, `min_agency_list`,
  `stale_after_hours`, `max_receipt_amount`).
- **Line descriptions:** `config/functions.json`.

## Where the site lives, and how to give it its own address

**Standing rule: never replace, only build on top.** This site goes beside America.co on a name of its own. Nothing
here points America.co's hostnames at this site or redirects its pages here, and no step below asks for that.

Current state, checked 2026-11-22:
- The site is served at its github.io address. No Pages custom domain and no repository variables are set.
- `america.co` uses Vercel nameservers (`ns1/ns2.vercel-dns.com`). The apex and `www` go to Vercel, and a wildcard
  sends every other name, `tools.america.co` included, to `cname.vercel-dns-0.com.`, where nothing answers.
- So the DNS record below has to be added in Vercel, by someone who can sign in to the team that owns `america.co`.
  That is the one human step, and it is why the site is still at github.io.

**One setting moves the site: the Pages custom domain.** Every workflow run asks GitHub which address the site is
served at (`.github/scripts/site-url.sh`) and builds each link, canonical, share link, embed snippet, the feed, the
calendar file, robots.txt and the sitemap for it. The repository variable `SITE_URL` is used instead when it is
set, so leave it unset.

To give the site `tools.america.co` (any other name works the same way):

1. **DNS** (Vercel → the team that owns `america.co` → Domains → `america.co` → DNS Records): add
   `CNAME  tools  →  theguysaccount.github.io.`
   A named record takes precedence over the wildcard. Change nothing else. This Mac's resolver caches, so check
   from outside it:
   `curl -s "https://dns.google/resolve?name=tools.america.co&type=CNAME"`
2. **Pages custom domain:**
   `gh api -X PUT repos/theguysaccount/america-co-civic-movement-hub/pages -f cname=tools.america.co`
3. **Wait for the certificate, then enforce HTTPS.** Repeat the first command until it prints `approved`:
   `gh api repos/theguysaccount/america-co-civic-movement-hub/pages --jq .https_certificate.state`
   `gh api -X PUT repos/theguysaccount/america-co-civic-movement-hub/pages -F https_enforced=true`
4. **Rebuild for the new address:**
   `gh workflow run "Refresh and deploy" -R theguysaccount/america-co-civic-movement-hub -f refresh=false`
   From step 2 until this run finishes, the new name serves the old build, whose stylesheet and links still point
   at the github.io address. Do steps 2 to 4 in one sitting.
5. **Check:**
   `gh workflow run "Weekly checks" -R theguysaccount/america-co-civic-movement-hub`
   It fails if the live pages, robots.txt or sitemap are not what this repository is configured for.

Moving the address does not index the site. That is a separate switch, below.

To go back to the github.io address: clear the custom domain with
`gh api -X PUT repos/theguysaccount/america-co-civic-movement-hub/pages --input - <<< '{"cname":null}'`, run step 4, then remove the DNS record.

A name on a domain whose DNS is at Namecheap (`notaxation.org` and `civicsight.io` are owned and fit) needs no Vercel
sign-in: add the same CNAME there and use that name in steps 2 to 5.

## What search engines may index

- **Today: nothing.** `"indexable": false` in `config/site.json` and no `SITE_INDEXABLE` variable, so every page is
  `noindex`, robots.txt disallows everything, there is no sitemap and IndexNow is skipped.
- **One switch indexes the pages only this site has:**
  `gh variable set SITE_INDEXABLE --body true -R theguysaccount/america-co-civic-movement-hub`, then
  `gh workflow run "Refresh and deploy" -R theguysaccount/america-co-civic-movement-hub -f refresh=false`. It works at the github.io address and at the site's
  own. Deleting the variable and running the workflow again takes the site back out. Nothing on America.co has to
  change first: the pages that repeat America.co stay out of search by themselves.
- **Pages America.co already serves stay `noindex` even then.** They also stay out of the sitemap and are
  never sent to IndexNow, and each shows a line that points to America.co's page. They are listed in
  `config/site.json` under `duplicates_of_original`:
  - `/taxpayer-receipt/`, because America.co has `/taxpayer-receipt`;
  - every page under `/comment-deadlines/`, because America.co has `/public-comment-deadlines` and, since November
    2026, `/comment-calendar` with a page per agency, per month and per notice;
  - `/foia-request-builder/`, because America.co has `/foia-request-builder`.
- **Indexable because only this site has them:** the home page (America.co's `/tools` is an unclaimed placeholder),
  the 19 spending-line pages with their history since fiscal year 2015 (America.co's `/taxpayer-receipt/<line>`
  answers 404), sources, about and data. That is 23 pages.
- **When America.co starts serving something this site indexes**, such as a page per spending line, add that path to
  `duplicates_of_original` and push. A key ending in `*` covers every path under it. The guard refuses an indexable
  build in which a listed duplicate is indexable or in the sitemap, or an indexable page is missing from the sitemap.
  America.co grows quickly: its comment calendar did not exist when this site was built two weeks earlier.

## Keys Jack can turn later

1. **The site's own address.** Above. It needs one DNS record in Vercel, or a name on `notaxation.org` (the taxpayer
   receipt) or `civicsight.io` (the government-data tools), which are owned and whose DNS a session can reach.
2. **Money: a sponsor or grant.** One marked slot at the foot of every page, off until both are set:
   `gh variable set SPONSOR_URL --body "https://<sponsor>" -R theguysaccount/america-co-civic-movement-hub`
   `gh variable set SPONSOR_NAME --body "<Sponsor name>" -R theguysaccount/america-co-civic-movement-hub`
   The slot says sponsors have no say over the data or wording. GitHub Pages is non-commercial: no checkout here.
3. **Analytics.** `gh variable set GOATCOUNTER_URL --body "https://<code>.goatcounter.com/count" -R …` after creating a
   GoatCounter site (needs an account). Without it the site counts nothing.
4. **Unified States explainers.** Not included. They are a separate Next.js site on Vercel with its own domain. A
   scheduled Claude routine could turn its nine sourced cost cases into static pages here, with each source re-checked,
   and open a pull request; nothing here depends on it.
5. **FOIA office addresses.** FOIA.gov's agency API needs a free api.data.gov key. With a `FOIA_API_KEY` secret the
   daily job could fetch each office's submission address so the builder fills in "To:". Not built: it adds a secret,
   and a wrong address is worse than a link to FOIA.gov.
6. **Search Console**, once the site has its own address: verify the name and submit `/sitemap.xml`. Needs a Google
   account, so it is a human step.

## Costs
$0. Public repository, GitHub-hosted runners (about two minutes a day), GitHub Pages, no keys.
