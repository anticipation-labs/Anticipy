# Brief 01 — Server-side research arm (roadmap §6)

## Mission
Read-only research goals must run in the WORKER (Railway), never in the
owner's Chrome. The browser extension remains only for jobs that need the
owner's logged-in browser (bookings, forms, purchases), always behind the
confirmation gate.

## Context you must read first
- `brain/anticipy_core.py` — `_READ_ONLY_RE`, `is_consequential`, `_queue_job`.
- `brain/worker.py` — the poll loop, job claiming, owner scoping.
- `backend/pb_migrations/1700000001_jobs.js` — the jobs collection shape.
- `design/PRODUCTION-ROADMAP.md` §3 and §6 — delivery lanes.

## Design constraints (non-negotiable)
- A new job lane: jobs whose goal matches the read-only class get
  `lane="research"`; the extension's claim filter must EXCLUDE that lane so
  it never touches them (older extensions in the wild must also not claim
  them — enforce via the job filter the server applies, not just client code).
- Research executor in the worker: Brave Search API (`BRAVE_API_KEY` env;
  absent key = graceful fallback to the browser lane, never a crash) +
  fetch top results + LLM summarize with citations.
- Results are DESK deliveries: write the result to the job record and a
  conversation entry; do NOT SMS unless the job was explicitly asked for
  over SMS (reply in-thread then).
- No new global state; owner scoping identical to existing jobs.
- Secrets never logged.

## Definition of done
- Offline tests: lane routing (read-only goal -> research lane; consequential
  goal -> browser lane + hold), executor with a mocked Brave client,
  fallback path with no API key.
- All existing suites still green (`python -m pytest` at repo root).
- A live proof script the manager can run: queue "research: opening hours of
  the Vancouver aquarium" and see a summarized, cited answer land WITHOUT
  any browser agent claiming the job.
