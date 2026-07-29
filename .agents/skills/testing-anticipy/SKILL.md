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
- PITFALL: when POSTing jobs with curl/raw HTTP, `params` must be a JSON-ENCODED STRING (`"params": "{\"task\": ...}"`), not a nested object — PocketBase silently stores `""` for objects and the agent then runs with start_url=about:blank, burning 20 no-op steps to `failed: max steps reached`. The Python drivers already encode correctly.
- Hard policies live in extension/agent_loop.js: `BLOCKED_DOMAINS` (banking → `awaiting_confirm` with "refused: <domain> is a protected financial site", pre-LLM) and `looksLikeCaptcha()` (→ "stopped at a CAPTCHA/robot check"). Google may or may not serve reCAPTCHA to this box — CAPTCHA-path tests are opportunistic.
- Use `curl http://localhost:29229/json` to list agent tab URLs without steering the browser.

## Pitfalls learned
- duckduckgo.com is BLOCKED by this box's network (ERR_CONNECTION_TIMED_OUT); google.com serves reCAPTCHA to the datacenter IP. Prefer direct-target start_urls (e.g. news.ycombinator.com, example.com, books.toscrape.com) for agent tasks; verify reachability with curl first.
- deepseek-v3.2 agent steps take ~8-10s; maxSteps=20 means a job can legitimately run ~3+ min. Don't set wall-clock caps below ~250s or you'll kill honest runs.
- Watch for duplicate job claims (multiple identical Anticipy tab groups per job) — claimJob is racy across SSE/alarm polls; count tab groups per job as a leak/cost check.
- Extension service-worker state (activeJobs) is in-memory; a Chrome restart mid-job orphans `running` jobs until the stale sweep requeues them.
- Cost control: PATCH any stuck job to `failed` and/or toggle the extension OFF in chrome://extensions to immediately stop LLM spend.

## Devin Secrets Needed
- OPENROUTER_API_KEY (already present in repo .env; also stored in extension chrome.storage as `openrouterKey`).

## NOT-ME evidence & on-screen driver output
- `proof/sw_monitor.py` attaches via CDP to the extension service worker and writes a timestamped JSONL of every agent LLM decision + job PATCH (needs `websockets` in the repo venv) — use it as proof the agent, not a human, drove the browser.
- Run test drivers inside an xterm (`sudo apt-get install -y xterm`, launch with `DISPLAY=:0`) so screen recordings show brain/backend stages alongside the browser.

- After any extension reload, restart proof/sw_monitor.py — monitors attach to a specific service worker and go silently stale on reload.
- Datacenter IP gets CAPTCHA on Bing AND Brave — research scenarios need a direct-site start_url or residential egress.
- If jobs sit queued unclaimed or an agent freezes after 1 step, the SW/tab is wedged — reload via proof/reload_ext.py and consider relaunching Chrome with tab-freezing disabled (/tmp/launch_chrome.sh).
