# The browser agent is alive and has nothing to do

**Date:** 2026-09-07 · **Branch:** `cloudflare-backend` · **Measured against
PRODUCTION** (`api.anticipy.ai`), owner `qeuy6sv1raof9rw`, via
`python3 proof/e2e_cloudflare.py --owner qeuy6sv1raof9rw` · **exit 2 (UNPROVEN)**

The owner asked, twice: make sure the browser agent is able to take action.
It is not able to, and the reason is not the browser agent.

## What is working

| Fact | Evidence |
|---|---|
| Backend answering | `GET /api/health` → 200 |
| An arm is beating | `agents` row `spocye9giea2gu0` · Chrome/148.0.0.0 · ext/0.15.0 · last_seen `2026-09-07T00:28:23.973Z` |
| Exactly one enabled agent | `overnight/is_it_live.py`: 1 enabled, 0 disabled, 0 removed |
| The phone-shaped POST lands | events `x3ekx41dhl4a45w`, `9mvrrcoxi80tgvr`, `ske55sty0vkbn7g` |
| The brain judges and speaks | `anticipy_says` row `orvkyrqz5htfgbh` |

## Where it breaks, exactly

```
00:28:35  (a) x3ekx41dhl4a45w claimed by the brain
00:28:44  jobs aaqiteuhgo4ghg0 MINTED — awaiting_confirm, lane 'research',
          consequence 'consequential', workflow_id set,
          goal 'update calendar with dentist appointment on Thursdays at 3 PM on Broadway'
00:28:56  (a) decision 'act', addressee 'self'
00:28:56  (b) 9mvrrcoxi80tgvr claimed by the brain
00:29:06  (b) decision 'act', addressee 'assistant',
          goal 'open example.com in the browser, read the page heading, and report it'
          ← NO JOB MINTED, AT ALL
00:29:17  (c) decision 'answer' — correctly no job
```

Line (b)'s text was *"Anticipy, open example.com in my browser and tell me what
the page heading says"*. **The brain understood it correctly and then minted
nothing.** The extension polls for jobs; with no row there is nothing to claim.

**The asymmetry is the clue.** Line (a) was addressee `self` and minted. Line
(b) was addressee `assistant` and did not. Minting demonstrably works — twenty
seconds earlier, for the same owner, in the same run.

Design-table verdicts: `ears -> API` PROVEN, `API -> brain` PROVEN,
`brain -> mouth` PROVEN, **`brain -> hands` NOT PROVEN**, `hands` NOT PROVEN
("nothing to run: no job was minted").

## A second, smaller finding — do not conflate them

`overnight/is_it_live.py` reports the SERVED extension is not the committed
one: 351,059 bytes served against 351,391 committed, differing in
`background.js`, and the difference is one clause:

```
served:  const BROWSER_LANE = 'workflow_id!="" && lane!="research"'
source:  const BROWSER_LANE = 'workflow_id!="" && lane!="research" && lane!="api"'
```

The zips were rebuilt in the repo (`e7fdf8fc`) and not deployed;
`migration/workers/package.json`'s `deploy` runs `stage:assets` first, so a
Worker deploy is what closes it. **This does not explain the missing job.** The
server is the floor — `migration/workers/src/policy/research_lane.ts` refuses a
non-worker claim on lane `api` whatever the extension asks for — so the clause
is a courtesy, not a gate.

## A third thing worth someone's attention

Line (a)'s goal was *"update calendar with dentist appointment"* and it landed
on lane **`research`**. Updating a calendar is not research. Recorded here, not
chased here.

## Open

The cause of the missing mint is under investigation as of this writing. The
instrument that will confirm any fix is this same script, and Law 3 applies:
repo-green is not done, `proof/e2e_cloudflare.py` exiting 0 is.
