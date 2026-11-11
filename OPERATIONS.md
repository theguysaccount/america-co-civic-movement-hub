# OPERATIONS

Everything runs on GitHub Actions in `theguysaccount/america-co-civic-movement-hub`. No human has a job here.

- Staged copy: https://theguysaccount.github.io/america-co-civic-movement-hub/ (noindex).
- Live original: https://america.co (`/taxpayer-receipt`, `/public-comment-deadlines`, `/foia-request-builder`), on
  Vercel. Not touched, and its repositories are not this one.

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

## Cutover: taking this out of staging (Jack decides)

Current state, checked 2026-11-10: `america.co` uses Vercel nameservers (`ns1/ns2.vercel-dns.com`). The apex has
`A 216.150.1.1`, `www` is a CNAME to a Vercel address, and a wildcard sends every other name (including
`tools.america.co`) to `cname.vercel-dns-0.com.`, where nothing answers. The three original tools are paths on the
main site, so this static site cannot replace them by DNS alone; it goes beside them on a subdomain.

1. **DNS** (Vercel → the team that owns `america.co` → Domains → `america.co` → DNS Records): add
   `CNAME  tools  →  theguysaccount.github.io.`
   A named record takes precedence over the wildcard. Change nothing else.
2. **GitHub Pages:** repository Settings → Pages → Custom domain → `tools.america.co` → Save. Wait for the
   certificate, then tick "Enforce HTTPS".
   CLI: `gh api -X PUT repos/theguysaccount/america-co-civic-movement-hub/pages -f cname=tools.america.co`
3. **The base-URL setting:**
   `gh variable set SITE_URL --body "https://tools.america.co" -R theguysaccount/america-co-civic-movement-hub`
4. **The indexing setting:**
   `gh variable set SITE_INDEXABLE --body true -R theguysaccount/america-co-civic-movement-hub`
5. Actions → Refresh and deploy → Run workflow (refresh unticked). Canonical links, sitemap, robots.txt, the feed,
   the calendar file, share links, the embed snippet and IndexNow all follow the two settings. The weekly checks
   confirm the live state matches.
6. **In america.co's own repository (not this one, and not by this job):** redirect `/taxpayer-receipt`,
   `/public-comment-deadlines` and `/foia-request-builder` to the matching pages here, so the two do not compete in
   search. Until then, leave `SITE_INDEXABLE` unset.
7. **Roll back:** delete the `tools` CNAME, clear the Pages custom domain, delete the two variables, run the workflow.

## Keys Jack can turn later

1. **Custom domain / cutover.** Above. Other owned names that fit: `notaxation.org` (the taxpayer receipt),
   `civicsight.io` (the government-data tools). Either can be the Pages custom domain instead of `tools.america.co`
   with the same four steps.
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
6. **Search Console** after cutover: verify the domain with a DNS TXT record and submit `/sitemap.xml`.

## Costs
$0. Public repository, GitHub-hosted runners (about two minutes a day), GitHub Pages, no keys.
