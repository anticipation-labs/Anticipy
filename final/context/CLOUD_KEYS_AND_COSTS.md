# Memory cloud stack — costs + keys (verified live 2026-07-03 via browser)

## ✅ STATUS (2026-07-03): both keys LIVE + wired + verified — $0/month
- **Gemini** (embeddings + brain): key created, in `.env.local` as `GOOGLE_API_KEY`/`GEMINI_API_KEY`,
  verified against the live API (model list returned). Uses Omar's existing billing.
- **Neo4j graph**: adopted the existing empty AuraDB **Free** instance `0e12b0c0`; creds in
  `.env.local` (`NEO4J_URI`/`NEO4J_USERNAME`=`0e12b0c0`/`NEO4J_PASSWORD`/`NEO4J_DATABASE`); connected
  live (`RETURN 1 = 1`, 0 nodes, ready). Free tier.
- Skipped Turbopuffer ($16/mo) — Neo4j's native vector index + Gemini embeddings cover it, $0.
- **Next:** build Phase 1 (Gemini embeddings behind the store facade) + Phase 4 (Graphiti/Neo4j
  temporal graph), then flip stub→live and prove on `context_eval` with paraphrase + multi-hop cases.
- Secrets live only in git-ignored `.env.local` (+ `.env.local.bak*`, also ignored). Railway env
  gets them when the integration ships to the hosted engine.


## The bottom line: the whole memory cloud stack can be **$0/month**
The only paid piece in the originally-chosen stack is Turbopuffer ($16/mo); a free vector DB
replaces it. Everything else has a real free tier. Nothing needs a credit card on the lowest-price
path.

## Verified pricing (read off each vendor's page today)
| Component | Vendor | Free tier | Paid | Verdict |
|---|---|---|---|---|
| Embeddings | **Voyage** (`voyage-4`) | **First 200M tokens FREE** | then $0.06/M | FREE for one user, years |
| Embeddings (alt) | **Google Gemini** | Free tier (generous) | usage after | FREE — env already has a (currently invalid) key slot |
| Reranker | **Voyage** (`rerank-2.5`) | **First 200M tokens FREE** | then $0.05/M | FREE |
| Vector store | **Turbopuffer** | ❌ none | **$16/mo minimum** | the only paid piece — avoidable |
| Vector store (free alt) | **Qdrant Cloud** | **Free forever** (1GB/4GB, no card) | usage after | FREE — replaces Turbopuffer |
| Graph | **Neo4j AuraDB Free** | **$0, no credit card** | Pro $65/GB/mo | FREE |

## Recommended lowest-price stack ($0/month)
- **Embeddings:** Voyage `voyage-4` (free 200M) — or Gemini free.
- **Reranker:** Voyage `rerank-2.5` (free 200M) — or skip at first.
- **Vector store:** Qdrant Cloud Free (or Supabase pgvector free) — NOT Turbopuffer.
- **Graph:** Neo4j AuraDB Free. (Bonus: Aura Free has a native vector index, so it could even do
  graph + vectors together — 2 accounts total.)

## Keys — what Omar must do (Claude cannot create accounts, log in, or pay)
No payment required on this path — all free-tier signups. Claude opens the page; Omar signs up +
generates the key + provides it.
1. **Neo4j Aura Free** → https://console.neo4j.io → sign in (Google) → Create Instance → Free →
   copy the **Connection URI + username + generated password**. No card.
2. **Voyage** → https://dashboard.voyageai.com → sign up → API Keys → create. Free 200M tokens.
3. **Gemini** (alt to Voyage) → https://aistudio.google.com/apikey → Create API key. Free.
4. **Qdrant Cloud Free** → https://cloud.qdrant.io → sign up → free cluster → API key + URL. No card.

Provide the keys and Claude wires them into the engine `.env` behind the store facade, then flips
memory stub → live (Phases 1 & 4). Also worth refreshing: the existing GEMINI_API_KEY in the env is
**invalid** — a valid one lets the Phase-2 "smart decider" run on a real model.

## Hosted (Railway) deploy — status + the two blockers (2026-07-03)
- ✅ Env vars SET on Railway (anticipy-engine/production/engine): Gemini key, NEO4J_* (4), and the
  flags ANTICIPY_EMBED_PROVIDER=gemini + ANTICIPY_GRAPH=neo4j. Ready for when the code lands.
- ✅ `neo4j>=5` added to engine/requirements.cloud.txt (Gemini embedder needs NO new dep — it uses stdlib urllib).
- ⛔ BLOCKER 1 — repo mismatch: Railway builds from **omize10/Anticipy**, but the memory code lives in
  **omize10/Anticipy-executor-working** (this clone, branch hoe/build). The code must reach the
  Railway source repo (or point Railway at this repo, or `railway up` the local dir).
- ✅ BLOCKER 2 (code-side RESOLVED 2026-07-04) — the ROOT `/Dockerfile` (context = repo root) now has
  `COPY final ./final` placed while `WORKDIR /app` is active (right after `COPY web ./web`, BEFORE
  `WORKDIR /app/engine`), so final/ lands at `/app/final`. This matches control_core.py's fail-open
  import, which resolves `parents[3]` of `.../engine/anticipy_engine/core/control_core.py` to `/app`
  and imports `final.context` from `/app/final`. WITHOUT this line the import fails open and cloud
  memory is SILENTLY OFF (self.context stays None). `.railwayignore` does NOT exclude final/ (only
  its `__pycache__`/`.pyc`, which the import doesn't need). The deploy itself (Railway Root Dir =
  repo root, or `railway up` from repo root) is still done supervised — this task was code-only.
  Original blocker (for history): build context was **engine/** while **final/** sits at repo root
  outside it; the fix is (a) Railway Root Dir = repo root + the root Dockerfile COPY paths above.
- ⇒ LOCAL cloud memory is fully working + proven now; HOSTED needs this deploy restructure as its own task.
