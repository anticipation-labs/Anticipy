# Anticipy Action Engine — Decisions Log (locked, 2026-05-10)

This doc records the architecture decisions Omar and I converged on, after a failed overnight benchmark and a long correction conversation. These supersede every prior plan in the repo. If something here conflicts with `PROBLEM_MAP.md` or `PLAN.md`, this wins.

---

## What Anticipy is

A wearable + proactive engine that:
1. Captures ambient audio
2. Decides (via the L0-L6 cascade in `engine/app/proactive/`) what's worth acting on
3. Dispatches the action to a tool — most often the **browser agent**, sometimes calendar/contacts/file-system, etc.
4. Returns a deliverable to wherever the user's workflow lives — their Google Doc, Notion page, calendar event, email draft, clipboard. Per-user, per-task, no fixed format.

The browser agent is one tool in a larger system. The proactive engine is the brain.

---

## Quality is the highest priority. Always.

- **No token compression that hurts quality.** Past attempts dropped quality 50%. We use full Browser Use context with vision unless quality data PROVES a compression doesn't degrade.
- **Speed is secondary.** 10-15 min per task is acceptable. 10-30 sec is great when the task allows.
- **No shortcuts that change the answer the user gets.**

---

## The architecture

### Browser layer — thin relay extension + server brain

- New extension at `extension_v2/`, ~150-200 LOC of pure relay (WebSocket + content script). No LLM client code. No model names. No rate-limit logic. No prompt strings. Nothing.
- All intelligence lives on the server, in Python. Updates push by redeploying the server. **One more extension reload required to install the relay version. After that, never again.**
- Agent works inside a Chrome **tab group** named "Anticipy" (color: blue). User's other tabs are untouched. Closing the group = clean cancel.
- Cancel button is always visible in the popup during an active task. One click → close tab group → server aborts.

### Backend — Railway, not Fly

- Engine deploys to Railway as a single Python FastAPI service.
- Single wss:// URL the extension points at.
- Setup: I drive the user's Chrome via browser tools, he authenticates, I configure the rest.

### Memory & RAG — built for real this time

- `engine_trajectories.task_embedding` (vector(768), pgvector 0.8.0) was already in the schema. NOW: Gemini text-embedding-004 (free) populates it on insert + an HNSW cosine index + a Supabase RPC `engine_trajectories_topk` for similarity search.
- `anticipy_memory.embedding` (vector(768)): added today + HNSW index + RPC `anticipy_memory_topk`.
- `engine/app/memory.py` `search()` method: replaced token-overlap with a real cosine-similarity call to the RPC.
- `engine/app/trajectory_cache.py`: new module. `cache_hit_for(user_id, task)` returns the best match if similarity > 0.92 (high-confidence replay); `get_few_shot_examples` returns looser matches for planner context.
- `engine/backfill_trajectory_embeddings.py`: backfills the 120 existing rows.

### LLM pool — free first, $10/month Gemini cap as safety valve only

| Role | Primary (free) | Fallback | Use of paid Gemini |
|---|---|---|---|
| Executor | Cerebras Qwen3-235B (1M tok/day, ~250ms latency) | Pixtral 12B free vision (1B tok/month) | Never |
| Critic | Pixtral 12B free (vision-capable) | Gemini Flash multi-project free | Edge cases only |
| Planner | Gemini 2.5 Flash multi-project free (5 fresh GCP no-billing projects, ~5000 RPD pooled) | Cerebras | Never |
| Verifier | Code, not LLM (end-state assertions) | — | — |
| Embeddings | Gemini text-embedding-004 free | — | When free 429s |
| Spillover (only when all free hit) | — | — | Gemini Flash paid, capped at $10/month total |

### RPM problem — solved without paid spending

- **Gemini 2.5 Flash free has 1M TPM** (tokens per minute). Burst RPM is rarely the binding constraint there; RPD is. 5 GCP projects × ~1000 RPD = ~5000 RPD pooled.
- **Cerebras 30 RPM** is the real burst ceiling. We solve by: (a) queueing tasks serially with 500ms spacing instead of bursting, (b) trajectory cache so 80%+ of repeat tasks bypass LLM entirely, (c) different roles on different providers so a stuck Cerebras doesn't stall planner+critic.
- **No 5-tier rotation pitch.** That doesn't structurally solve burst. The real answer is cache + queue + role split.

### Quality scaffolding

- **Planner / Executor / Critic / Verifier**, each on a DIFFERENT model (single-model self-criticism degenerates per research). All re-enabled, all wired into the new architecture.
- **End-state assertion verifier** (NOT LLM trust): when the agent says "done", we check the actual world state. Gmail → re-fetch Sent folder. Calendar → re-fetch events. Cart → re-fetch cart. Comment → re-fetch comments. This is the +25-40 point quality lever per research.
- **Dynamic step limit**: replace `MAX_STEPS=60` with a self-evaluation each step ("am I making progress?"). Agent decides when to stop. User-cancel is the hard stop.
- **DOM-drift detection**: before replaying a cached action, hash the AxTree against the one captured. Mismatch → invalidate cache, re-plan.
- **Idempotency keys** on irreversible writes (send_email, post_comment, place_order). Server refuses duplicates within 60s.

### Output destination — per task, per user

- Agent emits a `deliverable: {text, format, dest}` structure.
- Routing module places it: Google Doc API, Notion API, Drive, Gmail draft, Calendar event, clipboard.
- Per-user defaults at signup. Per-task overrides from proactive engine context.

---

## Wedge vs. competitors

- **Manus / ChatGPT Agent / Devin / Genspark**: run server-side in their own sandbox. They CANNOT do "send THIS email from MY Gmail" or "create THIS event in MY calendar" — they have no access to the user's authenticated browser.
- **Anticipy CAN**, because we run inside the user's actual Chrome tab group with the user's actual cookies and sessions.
- **Plus** wearable / proactive audio input — none of them have this. We do.

That's the moat.

---

## What I will NOT do

- Pitch the 5-tier LLM provider rotation as the RPM fix. It's been tried, it doesn't work.
- Claim a feature is built when only the skeleton exists ("scaffolded" ≠ "done").
- Compress observation in a way that drops quality — even if it cuts cost.
- Set `MAX_STEPS=60` or any other arbitrary hard cap.
- Burn through paid spending. $10/month Gemini cap is the absolute ceiling. Will respect.
- Lump MiniMax (a model provider) with Manus (an agent product). They are different categories.
- Tell Omar to "open Railway and create a project" — I drive his Chrome.
- Pitch chrome.debugger / yellow-bar architecture. Off the table.

---

## Open dependencies before we ship

- Embeddings/cache/memory work being done by build agent A (in flight)
- `extension_v2/` relay being built by build agent B (in flight)
- Agent-product competitive research being done by research agent C (in flight)
- Railway deploy: requires Omar at the keyboard for auth. Pending.
- Chrome Web Store submission of `extension_v2`: pending after build agent B finishes.
- Multi-project Gemini setup: needs 5 fresh GCP projects without billing. Pending.

---

## Honest current state at 2026-05-10 morning

- Last night's overnight benchmark: 0/35 real wins. Wall was the locked agent.js, not Cerebras itself.
- Today's codespace smoke: 1 task PASS via local Browser Use + Groq llama-4-scout, before TPD ceiling killed it.
- Memory infra: schema applied today, embedding wiring in flight (build agent A).
- Extension v2: in flight (build agent B).
- Engine on Railway: not yet.
- Trajectory cache: schema there, code in flight.
- Quality scaffolding: routes exist (currently disabled), need re-enabling with the different-models rule.
- Output deliverable router: not built.

**Nothing in this list is "done" until Omar can run a task in his actual Chrome and see a real deliverable land in the right place.** Until that happens, I don't say "done."

---

## What I commit to

- Stop claiming done when not done.
- Don't half-ship. If a task isn't shippable today, say so explicitly.
- Don't burn money. $10/month is the cap. I write a `cost_watch.py` that logs every paid call to Supabase so Omar can audit.
- Use the agent team. Parallelize. Don't grind solo.
- Tell Omar what I'm doing in plain English, not "I have an idea" loops.
