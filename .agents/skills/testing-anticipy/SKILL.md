---
name: testing-anticipy
description: How to run hands-off end-to-end tests of the Anticipy pendant assistant (PocketBase backend, brain, Chrome extension agent loop) on this box.
---

# Testing Anticipy end-to-end

## Services
- Backend: PocketBase at http://127.0.0.1:8090 (start: `cd /home/ubuntu/anticipy_app/backend && setsid nohup ./pocketbase serve --http 127.0.0.1:8090 &`; health `/api/health`). Collections: jobs, events, agents, pendants.
- Python: use the repo venv `/home/ubuntu/anticipy_app/.venv/bin/python` (system python3 lacks requests/httpx).
- LLM key: `OPENROUTER_API_KEY` in `/home/ubuntu/anticipy_app/.env` (load into env before constructing `brain.llm.LLM`). Model default deepseek/deepseek-v3.2.

## Chrome extension (the "action arm")
- Loaded unpacked from `/home/ubuntu/anticipy_app/extension` in Chrome for Testing (profile `/home/ubuntu/.browser_data_dir`, remote debugging port 29229). Reload it in chrome://extensions whenever background.js changes.
- If Chrome dies, relaunch: `/opt/.devin/chrome/chrome/linux-137.0.7118.2/chrome-linux64/chrome --user-data-dir=/home/ubuntu/.browser_data_dir --remote-debugging-port=29229 --restore-last-session`.
- On first registration it POSTs an agents record with a 6-digit `pair_code`; simulate phone pairing by PATCHing `owner` + `paired:true` on that record. Extension picks up owner via heartbeat (~10s) and then claims only owner-scoped/unowned jobs.
- Autonomous jobs: goal `agent_goal`, params `{"task": ..., "start_url": ...}`. Held jobs sit at `awaiting_confirm`; simulate user YES by PATCHing status to `queued`.
- Use `curl http://localhost:29229/json` to list agent tab URLs without steering the browser.

## Pitfalls learned
- duckduckgo.com is BLOCKED by this box's network (ERR_CONNECTION_TIMED_OUT); google.com serves reCAPTCHA to the datacenter IP. Prefer direct-target start_urls (e.g. news.ycombinator.com, example.com, books.toscrape.com) for agent tasks; verify reachability with curl first.
- deepseek-v3.2 agent steps take ~8-10s; maxSteps=20 means a job can legitimately run ~3+ min. Don't set wall-clock caps below ~250s or you'll kill honest runs.
- Watch for duplicate job claims (multiple identical Anticipy tab groups per job) — claimJob is racy across SSE/alarm polls; count tab groups per job as a leak/cost check.
- Extension service-worker state (activeJobs) is in-memory; a Chrome restart mid-job orphans `running` jobs until the stale sweep requeues them.
- Cost control: PATCH any stuck job to `failed` and/or toggle the extension OFF in chrome://extensions to immediately stop LLM spend.

## Devin Secrets Needed
- OPENROUTER_API_KEY (already present in repo .env; also stored in extension chrome.storage as `openrouterKey`).
