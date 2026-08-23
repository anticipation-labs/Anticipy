# Manual proof — browser jobs never take the foreground (brief 03 / roadmap §9)

For the manager's live gate. The claim being proven: **while a research-style
browser job runs, the tab the owner is looking at never changes** — and when a
job needs the owner, it announces itself with a badge + notification instead of
seizing the screen.

Offline suite must already be green: `node extension/tests/run_all.mjs`.

## 0. Before touching Chrome: one command that says which arm is broken

```bash
sh proof/local_rig.sh up          # PocketBase + the brain
node proof/extension_smoke.mjs    # the whole chain, in plain words
```

`proof/extension_smoke.mjs` walks the exact path a real install walks —
register, be claimed by the phone, fetch a model, have a queued job picked up
and run — and prints a numbered PASS/FAIL list. Its exit code is the answer:

| exit | meaning |
| --- | --- |
| 0 | everything worked, including a real Chrome running the job |
| 1 | **the backend** is the problem; the failed check says which part |
| 2 | the backend is fine and **nothing in Chrome** acted on the job |

It also prints every browser paired to this owner with its heartbeat age and
its build (`ext/0.9.0`), which answers "is my Chrome even alive, and is it
running today's code" before you go looking anywhere else. It cleans up after
itself: the probe agent row is deleted and its job is cancelled unless it
finished, so nothing it creates can fire later. `--keep` opts out; `--base=`,
`--owner-ref=`, `--claim-wait=` and `--wait=` override the defaults.

Live run on this Mac, 2026-08-19, against a real Chrome with 0.9.0 loaded:

```
 9. PASS  a Chrome claims the job
         claimed 29s after queueing
         by ac0635b6-c7e5-4144-9776-063390eb2f48 · Chrome/148.0.0.0 ext/0.9.0
10. PASS  the run reaches an ending
         done: Example Domain
```

## Setup (once)

1. Load the extension unpacked. **This has to be done by hand.** Chrome 151
   blocks `--load-extension` on the stable channel, so the old one-line launch
   command silently starts a browser with no extension in it — and every proof
   below then "passes" by never doing anything. `Extensions.loadUnpacked` over
   CDP is not a way round it either: it leaves the service worker unstartable.

   The click path, exactly:

   1. Open Chrome → address bar → `chrome://extensions`
   2. **Developer mode** — the switch at the **top right** of that page → on
   3. **Load unpacked** — the button at the **top left**
   4. Select the folder `extension/` in this repo. In the file picker press
      **Shift-Cmd-G**, paste the absolute path, Enter, then **Select**. Pick
      the folder itself; do not open it first.
   5. A card appears — "Anticipy" — and a setup tab opens with a
      6-digit code. Type that code into Anticipy on the iPhone.

   If you have several Chrome profiles (this Mac has eight), do it in the
   profile you actually browse in — the avatar at the top right is the profile
   you are in now. An extension loaded in "Profile 7" does nothing for you.

   The version on the card must equal the `version` in
   `extension/manifest.json` (0.9.0 as of this writing; do not trust that
   number, read the file). If it does not, hit Reload — an unpacked extension
   never auto-updates, and a stale worker graph is the single most common reason
   the browser arm looks dead.

   After editing the repo: `sh extension/sync-to-chrome.sh`, then Reload. That
   script finds the folder Chrome is *actually* reading (its own private copy,
   or this repo directly), writes into every profile that has the extension,
   and tells you if it cannot find one.
2. Point it at the test backend if not using production. Two ways, and they
   write the same `chrome.storage.local.backendUrl` that `extension/config.js`
   resolves for the whole extension (job polling AND the model proxy — they used
   to read separate literals, so an override reached one and not the other):
   - the backend URL field on the setup/onboarding page, which is where a person
     should do it;
   - or, in the service-worker console,
     `chrome.storage.local.set({backendUrl: "http://127.0.0.1:8090"})`.

   No reload is needed either way: config.js re-resolves on the storage change.
3. Pair it: on first registration the extension POSTs an `agents` record with a
   `pair_code`; simulate the phone by PATCHing that record with
   `{"owner": "<owner-id>", "owner_ref": "<owner-ref>", "paired": true}`.
   `proof/extension_smoke.mjs` does exactly this for its own probe row if you
   want the shape. Wait ~30 s for a heartbeat.
   (Details and pitfalls: `.agents/skills/testing-anticipy/SKILL.md` — note
   `params` must be a JSON-encoded STRING when POSTing jobs with curl. A nested
   object is stored as `""` and the agent then wakes with no task and
   `start_url=about:blank`.)
4. Expect up to ~30 s between queueing a job and Chrome starting on it, and
   know why: `chrome.alarms` will not repeat faster than every half minute, and
   that alarm is the ONLY recurring wake. There is no push channel — grep
   `extension/` for EventSource or WebSocket and you find nothing.

   Two things that follow, both measured live on 2026-08-19:
   - **An open extension page short-circuits it.** The popup and the setup page
     both send `anticipy-ping`, and that handler re-asserts the alarms and polls
     on the spot. With the alarms deliberately deleted and no extension page
     open, a queued job sat untouched for the full 30 s; the same job was
     claimed **194 ms** after the popup was opened.
   - **`persistAcrossSessions` on an alarm is Chrome 150+.** Older Chrome does
     not ignore the unknown key, it throws — so the alarm was never created at
     all, every caller swallowed the rejection, and the browser arm quietly
     became a button you press by opening the popup. `ensureWakeAlarms` now
     falls back to a plain alarm and says so in the worker console. If you are
     ever handed "she only works when I have the popup open", that is the shape
     of it.

   A job that has not moved a minute after queueing is a real failure, not slow
   polling — and `node proof/extension_smoke.mjs` will say which arm.

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

## Nothing is shipped until the backend is deployed

`/anticipy-extension.zip` is what the setup page tells people to download, and
it is served **out of the deployed container's `pb_public`** — not out of this
repo. On 2026-08-19 production was still handing out **0.8.3** while the repo
built 0.9.0. Building and committing the zip changes nothing for a real user;
the deploy is the only thing that does.

### The sequence

```bash
# 1. Build the artifact FROM source. It refuses to emit a zip whose manifest
#    disagrees with extension/manifest.json, and it derives the file list from
#    the manifest's entry points plus every import and every injected file, so
#    a new module cannot be left out.
sh extension/build-zip.sh

# 2. Commit it. The zip is a tracked artifact; the three filenames are aliases
#    carrying identical bytes, so every URL ever given to a customer keeps
#    working.
git add extension backend/pb_public/*.zip && git commit -m "extension 0.9.0"

# 3. Deploy from a CLEAN staging directory, never from backend/ itself.
#    `railway up` from backend/ HANGS at "scheduling build" — the 32MB
#    pocketbase binary and pb_data ride along and .railwayignore does not save
#    you. Copy exactly what the Dockerfile needs and nothing else:
STAGE=$(mktemp -d)
cp -R backend/Dockerfile backend/start.sh \
      backend/pb_migrations backend/pb_hooks backend/pb_public "$STAGE"/
du -sk "$STAGE"        # ~900KB today (three 194KB zip aliases dominate it).
                       # 30MB+ means you copied pb_data or the binary — stop.
(cd "$STAGE" && railway up --service backend)
```

`start.sh` is in that list because the Dockerfile `COPY`s it; HANDOFF.md's
older four-item list predates it, and a stage without it fails the build.

### Verify, because the failure is silent

A failed Railway deploy does not take the site down — **the old container keeps
serving**. The CLI can look fine and nothing will have changed. So never trust
it; check the artifact people download:

```bash
BASE=https://backend-production-61e0a.up.railway.app
curl -s "$BASE/api/health"
curl -s "$BASE/anticipy-extension.zip" -o /tmp/live.zip
unzip -p /tmp/live.zip manifest.json | python3 -c 'import json,sys;print(json.load(sys.stdin)["version"])'
python3 -c 'import json;print(json.load(open("extension/manifest.json"))["version"])'   # must match
shasum -a 256 /tmp/live.zip backend/pb_public/anticipy-extension.zip                    # must match
```

Same deploy, same verification, for anything under `backend/pb_hooks/` — the
hooks are baked into the image, so a guard or SMS-webhook change that is not
deployed is a change that does not exist.

Then, for a person already running an older unpacked build: re-download and
Reload, or `sh extension/sync-to-chrome.sh` if they are working from this repo.
