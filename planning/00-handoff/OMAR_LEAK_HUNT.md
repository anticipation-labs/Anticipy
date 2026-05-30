# OMAR_LEAK_HUNT

Audit of shipped Anticipy product code for Omar-specific leaks.

Scope: `engine/app/` (excluding `engine/tests`, `engine/scripts/*smoke*`), `desktop/src/`, `desktop/src-tauri/src/`, `src/app/`, `public/`, `scripts/v7/` (none referenced from install.sh or DMG, so scope reduced to zero there).

Excluded by directive: `engine/tests/`, `state/`, `proof-artifacts/`, `planning/`, `.anticipy/`, `_archive/`, `archive/`.

Patterns searched: `omarkebrahim`, `omar@`, `hello@anticipy`, `/Users/omarebrahim`, `Omar Ebrahim`, `anticipy-omar`, `omarkebrahim+anticipy-`, `chrome-real-clone`, `+1XXX` phone numbers, supabase UUIDs, `anticipy-test@`, `anticipy-pipeline@`, plus broader follow-on greps for `Omar`, `anticipy-user`, `dil-wearer`, `coldstart`.

---

## Summary counts

- Total raw hits across all patterns: 84
- Real leaks (runtime SCALE bugs that bias decisions or path-pin to Omar): 6
- Test-only / sim fixtures (safe, simulator world or unwired demo): 11
- Acceptable defaults (gated by env, behind admin password, or user-facing brand): 19
- Comment-only references (no runtime effect, but stale wording): 12
- Sanitizer / safety code (filters OUT Omar leaks, NOT a leak): 1
- Founder bio / public-facing brand (legitimate): 3

---

## Real leaks (rank-ordered)

### Leak 1 — `engine/app/audiostack/engine_bridge.py:39`

```
user_id=user_id, name="Omar", role_title="Founder",
what_they_do="runs an AI hardware startup",
mandate="Handle scheduling, dinner bookings and email "
        "proactively. Do not touch payroll or legal.",
people={"the boss": "Dana", "us": "Omar and Priya"},
trajectory_confidence=0.0, days_since_onboard=3
```

Classification: **real-leak (runtime)**. `_ctx()` is called from `engine/app/e2e/flow.py:138` which runs in the shipped `/journey/run` endpoint (`engine/app/server.py:38`) and from `engine/app/desktop_app.py:99`. Every stranger's frozen-engine `ProactiveEngine.decide` call is evaluated against Omar's profile, biasing what counts as an "instruction" for them.

Proposed fix (3 lines):
```python
def _ctx(user_id: str = "wearer"):
    from app.anticipy.seams import UserContext, UserProfile
    from app.product.session_profile import load_active_profile
    prof = load_active_profile() or UserProfile(user_id=user_id, name="",
        role_title="", what_they_do="", mandate="", people={},
        trajectory_confidence=0.0, days_since_onboard=0)
    return UserContext.from_profile(prof)
```

### Leak 2 — `engine/app/proactive_day/pipeline.py:52`

```
user_id="dil-wearer", name="Omar", role_title="Founder",
what_they_do="runs an AI hardware startup",
mandate="Handle scheduling, dinner and email proactively. "
        "Do not touch payroll or legal.",
people={"the boss": "Dana", "us": "Omar and Priya"},
trajectory_confidence=0.0, days_since_onboard=3
```

Classification: **real-leak (runtime)**. `frozen_is_instruction` (uses this ctx) is called from `pipeline.run_day` (`pipeline.py:82`, `:177`), which is called from `_run_pipeline` in `engine/app/product/server.py:2873` and `engine/app/e2e/flow.py:170` (both runtime). Same bias as Leak 1 plus the hardcoded "Dana / Priya" relations leak.

Proposed fix (3 lines):
```python
def _wearer_ctx_for_frozen_engine():
    from app.product.session_profile import load_active_profile
    return UserContext.from_profile(load_active_profile() or UserProfile(
        user_id="wearer", name="", role_title="", what_they_do="",
        mandate="", people={}, trajectory_confidence=0.0,
        days_since_onboard=0))
```
Then replace the inline `UserContext.from_profile(...)` with `_wearer_ctx_for_frozen_engine()`.

### Leak 3 — `engine/app/product/server.py:2883` and `engine/app/e2e/flow.py:169`

```
world = W.populated()
res = pipeline.run_day(manifest, world)
```

Classification: **real-leak (runtime)**. `W.populated()` returns a SimWorld populated with synthetic contacts ("dana@investor.example", "priya@home.example", "the boss", calendar items "investor sync with Dana", files like "the q3 deck"). Every stranger's `_run_pipeline` (called from the listen pipeline's actionish handler) is evaluated against Omar's fictional life rather than their own contacts/calendar/files.

Proposed fix (3 lines):
```python
from app.product.session_world import build_world_from_session
world = build_world_from_session() or W.SimWorld()
res = pipeline.run_day(manifest, world)
```
(Empty `SimWorld()` is the SAFE default. Each stranger's real dossier should populate `contacts`, `calendar`, `files` through the existing dossier loader.)

### Leak 4 — `engine/app/coldstart/ramp.py:61`

```
user_id="coldstart", name="Omar", role_title="Founder",
what_they_do="runs an AI hardware startup",
mandate="Handle scheduling and email proactively.",
```

Classification: **real-leak (dormant but ships)**. `frozen_threshold` is currently uncalled in non-test runtime, but it ships in the engine and any wiring change immediately propagates the bias. The line above contradicts the file's own docstring ("the FROZEN engine already owns the validated progressive ramp").

Proposed fix (1 line per branch):
```python
return float(act_threshold(UserContext.from_profile(UserProfile(
    user_id="coldstart", name="(wearer)", role_title="(role)",
    what_they_do="(what they do)", mandate="(mandate)",
    days_since_onboard=max(0, int(days_since_onboard)),
    trajectory_confidence=max(0.0, min(1.0, float(trajectory_confidence)))))))
```
(Generic placeholders avoid biasing the ramp toward "Founder" priors.)

### Leak 5 — `engine/app/product/calendar_prep.py:513`

```
loader = DossierLoader("anticipy-user")
```

Classification: **real-leak (runtime)**. Hardcodes Omar's launchctl `ANTICIPY_ACCOUNT_ID` value as the dossier loader account, ignoring the rest of the multi-tenant resolution chain (env > USER_ID > machine_id). A stranger user's calendar prep will load Omar's dossier, OR nothing if the path doesn't exist.

Proposed fix (3 lines):
```python
from app.product.server import _default_account_id
loader = DossierLoader(_default_account_id() or "wearer")
```

### Leak 6 — `engine/app/product/failure_recovery.py:545`

```
rec = _tq.enqueue(
    instruction or f"recovery: {failure_kind}",
    metadata={...},
)
```

Classification: **real-leak (runtime)**. Calls `enqueue()` without `account_id=`, so the default kwarg `"anticipy-user"` from `engine/app/task_queue/store.py:343` fires. Every stranger's failure-recovered task is enqueued under Omar's account_id.

Proposed fix (1 line addition):
```python
rec = _tq.enqueue(
    instruction or f"recovery: {failure_kind}",
    account_id=USER_ID,
    metadata={...},
)
```
(Already imported elsewhere in this module; `USER_ID` is the runtime account_id.)

---

## Acceptable / gated / test-only

### Test-only sim fixtures (safe)

- `engine/app/proactive_day/world.py:111-119` — dana@investor.example, priya@home.example, etc. RFC 2606 reserved `.example` domain. Sim world fixtures.
- `engine/app/anticipy/compound.py:32-47` — `_FIXED_INTAKE` scripted onboarding answers ("I'm Omar, founder of an AI hardware startup..."). The `p9_compound` workflow is registered but no shipped route triggers it.

Acceptable as-is (these are demo / replayable scenarios), but worth a comment that they're fixtures and must not seed real wearer profiles.

### Gated by environment

- `engine/app/product/server.py:480` — `CHROME_REAL_CLONE_TOKEN = "chrome-real-clone"` and `server.py:657` — `~/.anticipy/chrome-real-clone` path returned only when `ANTICIPY_ENABLE_LEGACY_CLONE_CDP=1` (off by default per V7).
- `desktop/src-tauri/src/lib.rs:69` — `CHROME_PROFILE_DIR_NAME = "chrome-real-clone"` constant, explicitly documented "off by default in V7 because cloned Chrome cannot count as product proof."
- `engine/app/product/sms_pre_confirm.py:47` and `engine/app/product/server.py:9148` — reserved test number `+15555550100` (IANA RFC 7042) inside docstring examples.

### Sanitizer (NOT a leak)

- `engine/app/task_queue/store.py:631` — `r"omarkebrahim\+anticipy-|"` is part of `_DEV_TEST_RECIPIENT_RE`, a sanitizer that PURGES Omar's dev-test plus addresses from production task queues. Keep as-is.

### Behind password gate `/internal` or `/analytics` (gated)

- `src/app/internal/docs/packaging/page.tsx:18` and `src/app/internal/docs/assembly/page.tsx:18` — `Contact: omar@anticipy.ai`.
- `src/app/internal/page.tsx:239` — Vercel dashboard URL `vercel.com/omar-ebrahims-projects-022b18ec/anticipy`.
- `src/app/analytics/page.tsx:191` — Vercel analytics URL.

These are gated by `PasswordGate` (`src/app/internal/PasswordGate.tsx`) and `isAnalyticsAuthed` cookie (`src/app/analytics/page.tsx:63`). Acceptable since the surfaces are non-public, but consider rotating `omar@anticipy.ai` to `hello@anticipy.ai` for consistency with the public brand.

### Acceptable defaults (admin email fallback)

- `src/app/api/admin/backfill-sessions/route.ts:7` — `const ADMIN_EMAIL = "omar@anticipy.ai"`. Used to skip the admin-copy recipient when backfilling sessions. Function-correct but not generic. Recommend env var.
- `src/app/api/engine/analyze/route.ts:889` — `const adminEmail = process.env.ADMIN_EMAIL || "omar@anticipy.ai"`. Has env override, fallback is to Omar.

These work correctly today but the fallback hardcodes Omar's email. Recommend dropping the literal and requiring `process.env.ADMIN_EMAIL`.

### Founder / brand surfaces (legitimate, keep)

- `src/app/funded/page.tsx:580,586` — `Omar Ebrahim` founder bio on `/funded` (public investor page). Legitimate.
- `src/app/funded/page.tsx:22-23` — `cal.com/omar-anticipy` Cal links. Legitimate founder booking link.
- `src/app/pre-orders/agreement/page.tsx`, `src/app/privacy/page.tsx`, `src/app/terms/page.tsx` — many `hello@anticipy.ai` contact links. Public brand contact. Keep.

### Comment-only references (no runtime effect)

- `engine/app/product/server.py:8518` — stale comment "falling back to omarkebrahim@gmail.com which is the active wearer of this dev engine". The fix already shipped (returns `""` when no env set); only the comment still mentions the old default. Recommend deleting the parenthetical.
- `engine/app/product/server.py:406, 416, 721, 4383` — Omar's launchctl referenced in design comments. Recommend rewording.
- `engine/app/product/server.py:2997, 3036, 3308, 3381, 3517, 3611, 3627, 3735, 4371, 8968` — `Omar 2026-05-26 directive: ...` style author tags inside docstrings.
- `engine/app/middle/policy.py:49` — `(sub-$5 reorder of consumables Omar buys monthly, e.g.)`.
- `engine/app/proactive/reversibility.py:4` — `Per Omar's directive 2026-05-01: NO keyword tables...`
- `engine/app/product/dossier_endpoints.py:216` — `{"key": "name", "value": "Omar"}` in a docstring example.

These have zero runtime effect but leak the founder's name into docstrings shipped in the engine binary. Recommend a global sweep replacing "Omar" with "the wearer" and "Omar 2026-MM-DD directive" with "Per directive 2026-MM-DD" in shipped Python.

---

## Top 3 real leaks (one-line recap)

1. `engine/app/audiostack/engine_bridge.py:39` — `_ctx()` hardcodes name="Omar" / role="Founder" / people={Dana, Priya}; called by `/journey/run` and `desktop_app.py` for every wearer.
2. `engine/app/proactive_day/pipeline.py:52` — `frozen_is_instruction` evaluates every wearer's utterance against Omar's profile; called by `_run_pipeline` in shipped server.
3. `engine/app/product/server.py:2883` (and `e2e/flow.py:169`) — `W.populated()` injects Omar's fictional contacts/calendar/files into every wearer's pipeline run.

---

## Note

The task directive says "DO NOT apply patches yet". This audit catalogs and proposes; no source files were modified.
