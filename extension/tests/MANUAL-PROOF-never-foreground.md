# Manual proof — browser jobs never take the foreground (brief 03 / roadmap §9)

For the manager's live gate. The claim being proven: **while a research-style
browser job runs, the tab the owner is looking at never changes** — and when a
job needs the owner, it announces itself with a badge + notification instead of
seizing the screen.

Offline suite must already be green: `node extension/tests/run_all.mjs`.

## Setup (once)

1. Load the extension unpacked from `extension/` (chrome://extensions, Developer
   mode). Version shown must be **0.2.4** — if not, hit reload.
2. Point it at the test backend if not using production:
   in the service-worker console, `chrome.storage.local.set({backendUrl: "http://127.0.0.1:8090"})`.
3. Pair it: on first registration the extension POSTs an `agents` record with a
   `pair_code`; simulate the phone by PATCHing that record with
   `{"owner": "<owner-id>", "paired": true}`. Wait ~10 s for a heartbeat.
   (Details and pitfalls: `.agents/skills/testing-anticipy/SKILL.md` — note
   `params` must be a JSON-encoded STRING when POSTing jobs with curl.)

## Proof 1 — the active tab never changes during a research job

1. Open a tab on any site you'd actually read (e.g. news.ycombinator.com) and
   **leave it active**. Note which tab is focused.
2. Queue a research job (books.toscrape.com avoids datacenter CAPTCHAs):

   ```bash
   curl -s -X POST "$BASE/api/collections/jobs/records" -H 'Content-Type: application/json' -d '{
     "goal": "agent_goal", "status": "queued", "owner": "<owner-id>",
     "params": "{\"task\": \"find the price of the first book on the page and report it\", \"start_url\": \"https://books.toscrape.com/\", \"authorized\": true}"
   }'
   ```

3. Watch the browser for the whole run (~1–3 min):
   - **The focused tab must never change.** The job works in a collapsed
     yellow "Anticipy" group behind you.
   - No new window may open; no tab may flash to the front, including any
     target=_blank tabs the site spawns (they are swept, and if one grabs
     focus it is handed straight back).
4. Job row ends `done` with the price; the working tab is gone.

## Proof 2 — needs_user badges and notifies instead of seizing the screen

1. Keep your reading tab active. Queue a job that hands back instantly (the
   financial blocklist fires before the model even runs):

   ```bash
   curl -s -X POST "$BASE/api/collections/jobs/records" -H 'Content-Type: application/json' -d '{
     "goal": "agent_goal", "status": "queued", "owner": "<owner-id>",
     "params": "{\"task\": \"check my balance\", \"start_url\": \"https://www.paypal.com/\", \"authorized\": true}"
   }'
   ```

2. When the job flips to `needs_user`:
   - **Your focused tab has not changed.**
   - The extension icon shows a badge ("1"); a Chrome notification reads
     "I need you on paypal.com — click to open."
   - The kept tab is still parked in the collapsed Anticipy group.
3. Click the notification (or the extension icon → **Open the page**):
   **only now** does the tab come forward, ungrouped. Badge and notification
   clear.

## Proof 3 — no regression: the e2e example.com job still passes

```bash
curl -s -X POST "$BASE/api/collections/jobs/records" -H 'Content-Type: application/json' -d '{
  "goal": "agent_goal", "status": "queued", "owner": "<owner-id>",
  "params": "{\"task\": \"open example.com and report the page heading\", \"start_url\": \"https://example.com/\", \"authorized\": true}"
}'
```

Must end `done` with a result naming "Example Domain", working tab closed,
no tabs leaked (count tabs before/after), and — throughout — the focused tab
unchanged.

## Pass condition

All three: job completes, focus never moves on its own, and the only way an
Anticipy tab ever comes forward is the owner clicking the notification, the
popup button, or the pairing page on install.
