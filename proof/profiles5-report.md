# 5-profile browser execution (extension 75a30cfb, production backend)

Context (disclosed): the 5 simulated profiles' full-day transcripts were ingested through the
LOCAL brain (multi-user is not in production); triage v2 scored 79/81 with brain commit
c6aca833. This report covers the browser-execution half only: 10 representative agent_goal
jobs from the 25 proposed, run in the REAL extension (commit 75a30cfb — new verifyDone
terminal-state strictness, previously untested) against the PRODUCTION backend
(backend-production-61e0a.up.railway.app). Setup: Chrome-for-Testing 137 on CDP 29229
(auto-relaunched Chrome 133 killed first), extension reloaded, sw_monitor restarted after
reload (/tmp/sw_monitor_v8.log, 200-char truncation), CapSolver key configured (never
printed). All jobs unsteered in background tabs; finished tabs activated only AFTER each job
ended, for screenshots. Wedge cap 420s. Recording continuous.

## Score summary: 5 DONE-verified · 2 done-weak (flagged) · 2 partial · 1 failed

| # | profile | task | job id | status | score |
|---|---|---|---|---|---|
| 1 | maya | YC standard deal terms | 0o7lgtw1k92sfw7 | done | **DONE-verified** |
| 2 | maya | Linear vs Jira pricing (12 ppl) | v5pr436vzklhblp | done | **DONE-verified** |
| 3 | maya | top 3 Hacker News stories | vnf5zq8bcelf3lk | done | **DONE-verified** |
| 4 | james | nursing compression socks price | 1nafvsjc9w3poj0 | done | **DONE-verified** |
| 5 | james | Pfizer vs Moderna fall boosters | k4g0zk20e268ke1 | done | **done-weak** (hedged, goal info missing) |
| 6 | priya | UWorld Step 2 90-day qbank price | 8o2tsp6x504w528 | done | **done-weak** (no price; "visit the purchase page") |
| 7 | carlos | 5-yr fixed mortgage rates, CDN banks | 4mxc4f4wqgajvoa | done | **DONE-verified** |
| 8 | aisha | STWM 2026 date + reg close | r78wmqupgb2gq36 | failed (max steps) | **failed** |
| 9 | aisha | Notion vs Confluence pricing (25 ppl) | qkzlrqrw590a1bq | failed (max steps) | **partial** |
| 10 | priya | subscribe to ALiEM newsletter | drz6umo361zoqnv | failed (max steps) | **partial/needs_user** (Cloudflare wall, undetected) |

Cost: ~10 jobs × ≤32 cheap deepseek steps; no CapSolver spend; well under the $1.00 budget.
No credentials entered, no CAPTCHA manually solved, no steering, no wedge >420s (all jobs
terminated on their own within the cap).

## Headline findings on 75a30cfb (verifyDone terminal-state strictness)

1. **No over-rejection observed.** All 7 `done` verdicts passed the verifier on legitimate
   research completions (tasks 1–7); the rejected-done death spirals of v5/v6 did not recur.
2. **It DID fire correctly once**: task 9's done claim (Notion pricing asserted while only
   the Confluence page was visible) was rejected with "does not show Notion pricing … cannot
   be verified from this page" — exactly the intended behavior.
3. **But it still soft-passes "deferred" research dones**: task 6 ended `done` while the
   result itself says the price "is not directly listed … one would need to visit the UWorld
   purchase page directly" — with the agent sitting ON uworld.com/app/index.html#/pricing/,
   one click from the STEP 2 CK price list. Task 5 similarly ended `done` with generic
   2021-era approval facts and an explicit admission that the fall-booster specifics were
   "not fully detailed in the visible snippets". The terminal-state rule as written targets
   *navigation* claims ("would lead to"), not *information-goal* claims ("the answer isn't
   here, go look elsewhere"). Suggested tightening: for research goals, verified=false if the
   claimed result states the requested information was NOT found.
4. **NEW BUG — duplicate-tab regression at scale.** Nearly every Bing research run left 4–30
   duplicate tabs (8× linear.app, 12× uworld, ~30 tabs in task 8, 18 in task 9). The
   28dce8e6 exit cleanup (openerTabId === agent tab) is not catching these — likely they are
   spawned by the in-run adoption path (click → spawn → adopt) faster than it closes them, or
   openerTabId isn't set for Bing's target=_blank results. Harness closed them between jobs.
5. **NEW BUG — Cloudflare interstitial not detected.** Task 10: aliem.com served the
   Cloudflare "Performing security verification / Verify you are human" page. The mapped page
   text contains "verifies you are not a bot" and the title is "Just a moment..." — neither
   matches looksLikeCaptcha(), and the "Verify you are human" string lives inside the
   challenge iframe (not mapped). Result: 32 consecutive `wait` steps, 0 CapSolver calls, no
   needs_user hand-back, max-steps fail. Suggested additions to the regex: "just a moment",
   "performing security verification", "verifies you are not a bot". (Honest failure — no
   fabricated subscription; the dummy email was never entered anywhere.)

## Per-task detail

### 1. maya — YC standard deal terms — DONE-verified
Job `0o7lgtw1k92sfw7`, status `done`. Result (verbatim): "YC's current standard deal terms:
Y Combinator invests $500,000 in total. This consists of $125,000 for a fixed 7% equity
stake, and the remaining $375,000 is invested via an uncapped MFN (Most Favored Nation)
SAFE. The deal is standard for every company accepted into YC." Final page:
https://www.ycombinator.com/deal/ — the official page shows exactly $500K = $125K for 7% +
$375K uncapped MFN SAFE. (A Chrome "Restore pages?" popup was dismissed by the harness AFTER
the job ended, before the screenshot.)

![Task 1 — ycombinator.com/deal corroborates the result](https://app.devin.ai/attachments/698f145e-aa55-4f04-90ae-dba5942bb7a3/ss_941afccd.png)

### 2. maya — Linear vs Jira pricing for 12 — DONE-verified
Job `v5pr436vzklhblp`, status `done`. Result (verbatim): "Linear pricing for a 12-person
team: Business plan at $16 per user/month (billed yearly) totals $192/month. Jira pricing
for a 12-person team: Standard plan at $7.91 per user/month totals $94.92/month; Premium
plan at $14.54 per user/month totals $174.48/month. Both Jira plans are billed annually
(switch to Monthly billing shows higher rates)." Final pages: linear.app/pricing (×8
duplicate tabs — see bug 4) and atlassian.com/software/jira/pricing, which visibly shows
$7.91 Standard / $14.54 Premium per user/month; ×12 math correct. Minor caveat: the Jira
page's billing-toggle wording doesn't cleanly support "billed annually" (prices shown under
the Monthly toggle), but no number is contradicted.

![Task 2 — Jira pricing page shows $7.91 / $14.54 per user](https://app.devin.ai/attachments/bed1d117-bdb4-4525-b696-abc0c98e08d2/ss_5ee9fcaf.png)

### 3. maya — top 3 Hacker News stories — DONE-verified (known-good canary)
Job `vnf5zq8bcelf3lk`, status `done`. Result (verbatim): "Top 3 Hacker News stories: 1.
'Physicists Solve a Muon Mystery. Now, Old Results Don't Add Up' (quantamagazine.org) with
70 points, 2. 'Gemini Robotics 2 brings whole body intelligence to robots' (deepmind.google)
with 218 points, 3. 'The Economic Benefit of Refactoring' (martinfowler.com) with 78
points." Final page: news.ycombinator.com — ranks 1–3 match exactly, including domains and
point counts (70/218/78).

![Task 3 — HN front page ranks 1–3 match the result exactly](https://app.devin.ai/attachments/c5250033-8fed-4ffd-b56c-d2036a6008cb/ss_f8512047.png)

### 4. james — nursing compression socks price — DONE-verified
Job `1nafvsjc9w3poj0`, status `done`. Result (verbatim): "A decent pair of nursing
compression socks typically costs between $10.99 and $34.99, depending on brand, compression
level, and quantity. For example, Nurse Mates Butterfly socks are $10.99, Nurse Mates
Stethoscope Hearts are $14.99, and a 3-pack of Nurse Mates Rainbow socks is $34.99.
Multi-pair sets from brands like Hello Momoya (8 pairs) are $19.99, offering a lower
per-pair price." Final page: Bing shopping results — every quoted price/product visible on
the cards ($10.99 Butterfly, $14.99 Stethoscope, $34.99 Rainbow 3-pack, $19.99 Hello Momoya).

![Task 4 — Bing shopping cards match every quoted price](https://app.devin.ai/attachments/63ecde38-efbd-42b5-b051-93964e5e75d2/ss_d8538d61.png)

### 5. james — Pfizer vs Moderna fall boosters — done-weak (flagged)
Job `k4g0zk20e268ke1`, status `done`. Result (verbatim): "The search results show that both
Pfizer (Comirnaty) and Moderna (Spikevax) are mRNA vaccines with similar high efficacy
(~95%) against COVID-19. Key differences: Pfizer received full FDA approval for ages 16+ in
August 2021, while Moderna received full approval for ages 18+ in January 2022. Both are
used as boosters, but specific details on the updated fall boosters (e.g., bivalent
formulations, age authorizations, dosing intervals) are not fully detailed in the visible
snippets. Further clicking into authoritative sources like Yale Medicine or Mayo Clinic
would provide more current comparisons of the fall booster versions." Final page: Yale
Medicine vaccine-comparison article (×6 duplicate tabs). Nothing is contradicted by the
page, but the goal's actual subject (the UPDATED FALL boosters) is explicitly admitted to be
missing — the strict verifier passed it anyway (finding 3).

![Task 5 — final page: Yale Medicine comparison article](https://app.devin.ai/attachments/ede34c49-afbf-4fff-a536-3119842ffcfe/ss_faec5721.png)

### 6. priya — UWorld Step 2 90-day qbank price — done-weak (flagged)
Job `8o2tsp6x504w528`, status `done`. Result (verbatim): "The search results indicate that
UWorld does not publicly post a single flat rate for all exams; pricing is tiered by subject
area and subscription duration. The specific current price for the UWorld Step 2 90-day
question bank is not directly listed in the visible page text. To obtain the exact price,
one would need to visit the UWorld purchase page directly." Final pages:
medical.uworld.com/usmle/usmle-step-2-ck/ (×6) and uworld.com/app/index.html#/pricing/ (×6)
— i.e. the agent WAS on the pricing app with a "STEP 2 CK" pricing link one click away, and
still returned "visit the purchase page directly". done without the requested price; the
75a30cfb terminal-state rule did not catch this deferred-information done (finding 3).

![Task 6 — agent stopped on the UWorld pricing app without clicking STEP 2 CK](https://app.devin.ai/attachments/a55d8977-bdfb-4c73-baf8-eb2dc1b119d5/ss_1f8ab384.png)

### 7. carlos — 5-year fixed mortgage rates at major Canadian banks — DONE-verified
Job `4mxc4f4wqgajvoa`, status `done`. Result (verbatim): "The search results show current
5-year fixed mortgage rates from major Canadian banks. According to Ratehub.ca, the lowest
available 5-year fixed rate is 4.04% (as of the search date). The results also include links
to compare rates from RBC, TD, Scotiabank, BMO, and CIBC via mortgagetoolscanada.ca and
Rates.ca, which are updated regularly (within the last day)." Final page:
mortgagetoolscanada.ca/rates.php, which lists Big-5 posted 5-yr fixed rates (RBC 5.34%, TD
5.39%, Scotiabank 5.34%, BMO 5.39%, CIBC 5.34%) plus the BoC 6.09% benchmark — consistent
with (and richer than) the claim; nothing contradicted.

![Task 7 — mortgagetoolscanada.ca rates page](https://app.devin.ai/attachments/fa6a510c-5294-4e26-8854-7e5857a020e9/ss_c7ff3699.png)

### 8. aisha — STWM 2026 date + registration close — failed
Job `r78wmqupgb2gq36`, status `failed` ("max steps reached; last steps: step 30:
click 18 | step 31: click 48 | retried click 48 via element handler"). The agent bounced
across marathonscout.com, torontowaterfrontmarathon.com, lurkify.com and raceroster.com,
leaving ~30 duplicate tabs (worst case of bug 4). The final marathon site page renders
almost empty (JS-heavy) and never visibly showed the 2026 race date or a registration-close
date, so no partial credit — scored **failed**.

![Task 8 — final marathon page, no date/reg info visible; note the tab pile](https://app.devin.ai/attachments/278b21e2-399d-4f36-b462-cc7bf937bcf4/ss_17195207.png)

### 9. aisha — Notion vs Confluence pricing for 25 — partial
Job `qkzlrqrw590a1bq`, status `failed` (max steps). The agent found Notion pricing
(notion.com/pricing, "Business $20 per member/month" per its rejected claim) and ended on
atlassian.com/software/confluence/pricing. At step 31 it claimed done; **the 75a30cfb
verifier correctly rejected it** ("The page shows Confluence pricing but does not show
Notion pricing, so the claim … cannot be verified from this page") — the one clean positive
firing of the new strictness. The step budget then ran out. Info was substantially gathered
but never consolidated into a verified done → **partial**. Note: a sponsored Bing click also
opened an unrelated cursor.com tab; 18 duplicate tabs total.

![Task 9 — Confluence pricing page at job end](https://app.devin.ai/attachments/682a56e7-b542-4971-9fd2-76f9a77b9066/ss_101f8bcb.png)

### 10. priya — subscribe to free ALiEM newsletter — partial/needs_user (expected-hard)
Job `drz6umo361zoqnv`, status `failed` ("max steps reached; last steps: wait | wait |
wait"). aliem.com served a Cloudflare interstitial ("Performing security verification /
Verify you are human" checkbox). The agent issued 32 consecutive `wait` actions; CapSolver
was never invoked (0 solver calls in /tmp/sw_monitor_v8.log) and no needs_user hand-back
occurred, because looksLikeCaptcha() matched nothing: the mapped text says "verifies you are
not a bot", the title is "Just a moment...", and the "Verify you are human" string is inside
the challenge iframe (bug 5). Correctly honest in one sense — no subscription was fabricated
and the dummy email anticipy.test@example.com was never entered — but the ideal outcome was
a needs_user (or a CapSolver attempt). Scored **partial/needs_user-shaped failure**.

![Task 10 — undetected Cloudflare wall on aliem.com](https://app.devin.ai/attachments/a25fbb89-0cef-4409-92da-a9daf25a74ce/ss_57c5362b.png)

## Disclosures
- Finished agent tabs were activated by the harness only after each job's terminal status,
  to take screenshots; duplicate tabs were closed between jobs. No active job was steered.
- Task 1 ran before a Chrome "Restore pages?" popup was dismissed (post-job, pre-screenshot).
- sw_monitor truncation stayed at 200 chars throughout (verifier-rejection text in task 9 is
  from the job result string, which the backend stores untruncated).
- CapSolver key configured; zero CapSolver invocations this round (no wall was ever
  *detected*; one wall was served but missed — bug 5).
- Evidence: decision log /home/ubuntu/anticipy_agent_decisions.jsonl, monitor log
  /tmp/sw_monitor_v8.log, plan /home/ubuntu/anticipy_profiles5_exec_plan.md.
