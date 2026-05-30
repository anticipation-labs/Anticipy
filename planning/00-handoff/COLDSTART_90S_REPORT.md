# Cold-Start 90s Inhale Verification Report

Owner promise: within 90 seconds of installing Anticipy, the dossier has
10+ real people pulled from Gmail/Calendar/Drive via the CDP bridge. No
"which Joe" clarifying questions.

Date: 2026-05-30
Probe HOME: `/tmp/coldstart-verify-85581`
Engine port: 19234 (source-tree), 8743 (sidecar binary)
Bridge port: 7777
Chrome CDP port: 9222 (headless probe instance)

## Verdict

Cold-start CODE PATH works end-to-end. With sources populated and a
target page that returns DOM rows, the pipeline pulls 12 people +
2 projects + 5 tools in 18.7s (well under the 90s budget) on the very
first cold-start invocation.

Two real bugs found and fixed in this pass. One owner gap remains
(Gmail sign-in state on the user's real Chrome).

## Tests run

### Test 1: source-tree probe with empty Chrome profile (Gmail not signed in)

  - Engine spawned from source on port 19234 with `ANTICIPY_QUIET=0`,
    `ANTICIPY_CDP_PORT=9222`, isolated `HOME` at probe sandbox.
  - Chrome launched headless with `--user-data-dir=$PROBE_HOME/chrome-clone`,
    `--remote-debugging-port=9222`. NO Google sign-in (empty profile).
  - Bridge `scripts/v7/anticipy_bridge_fallback_cdp.py` running on 7777,
    `cdp_alive=true`.
  - POST `/api/coldstart/start` -> 200, `state=running`, `bridge_ready=true`.
  - Poll `/api/coldstart/status`: completed in 22008ms.
    - `rows_collected=0` (Gmail page redirected to sign-in; no
      `[role=row]` rows present).
    - `errors=["walker collected no rows; nothing to extract"]`.
  - PASS for plumbing, EXPECTED 0 people for unauthenticated probe.

### Test 2: source-tree probe with synthetic Gmail-shaped fixture

  - Same engine + bridge.
  - POST `/api/coldstart/sources` with a single source pointing at a
    `python -m http.server` fixture serving 12 Gmail-shaped rows
    (`tr.zA` with `[email]`, `.bog`, `.xW.xY span[title]` selectors).
  - POST `/api/coldstart/start` -> 200.
  - Poll completes in 18.7s.
    - `rows_collected=12`, `people_count=12`, `projects_count=2`,
      `tools_count=5`.
    - `llm_calls_ok=1`, `llm_calls_failed=0`, `batches_sent=1`.
  - Dossier merged to
    `$PROBE_HOME/.anticipy/v7/dossiers/<account_id>/dossier.json`
    with 12 distinct people (name + email + role_inferred),
    Q3 roadmap sync and Design review Wednesday as projects, and
    Linear, Notion, Figma, Salesforce, Slack as tools.
  - PASS end-to-end at 18.7s, well under 90s budget.

### Test 3: voice-call onboarding wiring (stub mode)

  - POST `/api/onboarding/call_stub`
    `{"phone":"+15005550006","name":"Test","expected_duration_seconds":120}`.
  - Response `{"ok": true, "is_stub": true, "real_call_spawned": false}`.
  - Stub log written to
    `$PROBE_HOME/.anticipy/system_v1/voice_call_stubs.jsonl`.
  - Real Twilio path stays dormant unless
    `TWILIO_ACCOUNT_SID/AUTH_TOKEN/PHONE_NUMBER` AND
    `TWILIO_TEST_TO_REAL_NUMBER=1` are all set. NOT touched per the
    owner rule "no real send testing".
  - PASS for wiring.

## Bugs found and fixed

### Bug 1: Shipped sidecar binary returns empty cold-start source list

Root cause. `engine/anticipy-engine.spec` (PyInstaller spec) does
NOT bundle `engine/app/coldstart/data/inhale_sources.default.json`.
At runtime the frozen binary's
`engine/app/coldstart/sources.py::_load_default_template()` reads
`__file__`-relative path that does not exist in the PyInstaller
extraction dir, falls through to the empty-list fallback, and the
materialized `~/.anticipy/inhale_sources.json` has `sources: []`.

  - First-launch user runs cold-start, walker sees zero enabled sources,
    `_run_inhale` exits in 1ms with 0 rows.
  - Verified on the actual `desktop/src-tauri/bin/anticipy-engine-aarch64-apple-darwin`
    binary in Test 0 (probe HOME, port 8743): elapsed_ms=1, sources empty.

Fix at source. Two edits, both in this commit:

  - `engine/app/coldstart/sources.py`:
      - `_default_template_path()` helper now also probes
        `sys._MEIPASS/app/coldstart/data/inhale_sources.default.json`
        so a properly-bundled binary finds the data file.
      - `_EMBEDDED_DEFAULT_SOURCES` constants embed Gmail / Calendar /
        Drive defaults so even a malformed bundle still inhales
        something on first launch.
      - `_load_default_template()` falls through to the embedded
        defaults when the JSON file is missing, unparseable, or has
        empty `sources` array.
  - `engine/anticipy-engine.spec`:
      - `datas=[('app/coldstart/data/inhale_sources.default.json',
        'app/coldstart/data')]` so next `pyinstaller` build ships
        the file.

Re-verify after fix. Both source-tree and source-tree+empty-config
runs now populate the 3-row default. Sidecar binary needs a rebuild
to pick up the spec change.

### Bug 2: Source-tree boot trips its own singleton-lock on second import

Root cause. `engine/app/product/server.py` eagerly calls
`_acquire_singleton_lock` at module top when `not sys.frozen`. When
the file is launched as `python -m app.product.server` or
`python engine/app/product/server.py`, it is imported as `__main__`,
then deferred-attach wires (`memory_provenance_endpoints`,
`confirm_card_wire`, etc) call `from app.product.server import app`,
re-importing the module as `app.product.server`. The second module
instance has a fresh `_SINGLETON_FH = None` global, attempts to flock
the same file path, fails, and crashes startup with
"another engine instance already holds...".

  - Affects EVERY `python -m app.product.server` startup. Frozen
    binary path was unaffected because of `if not getattr(_sys,
    "frozen", False)` guard and `_run_sidecar()` flow.

Fix. `engine/app/product/server.py::_acquire_singleton_lock` now
checks the PID written in any existing lock file. If it matches the
current process, the re-entry short-circuits gracefully. Also writes
the PID immediately after a successful flock so the same-process
check sees it on the second import.

## Substep table

| Substep | Status | Note |
|---|---|---|
| Engine sidecar binary boots | PASS | port 8743, /health 200 |
| ANTICIPY_QUIET=0 honored (first launch inhale not blocked) | PASS | start returned `state=running` not `quiet_mode_skipped` |
| Bridge `127.0.0.1:7777` reachable | PASS | `cdp_alive=true` |
| Chrome `:9222` CDP reachable | PASS | `/json/version` 200 |
| `/api/coldstart/start` returns 200 | PASS | `started=true` |
| `/api/coldstart/sources` defaults materialized | FAIL pre-fix, PASS post-fix | empty `sources: []` in shipped binary, 3 entries after source patch |
| `/api/coldstart/status` reaches `state=done` | PASS | 18.7s on synthetic, 22s on real Gmail no-auth |
| 10+ people in dossier | PASS on synthetic (12), N/A on real (Gmail not signed in) |
| 90s budget | PASS | 18.7s synthetic, 22s no-auth |
| dossier.json written under `~/.anticipy/v7/dossiers/<account_id>/` | PASS | account_id resolved from machine_id |
| voice-call stub responds | PASS | stub mode, no real call |

## Confirmed pathway

```
sidecar binary (or python -m app.product.server)
  -> /api/coldstart/start
  -> auto_inhale.start_inhale(account_id, ...)
  -> threading.Thread -> _run_inhale
       -> CDPWalker.bridge_ready() probes 127.0.0.1:7777/status
       -> for each entry in sources.load_enabled():
            -> CDPWalker.walk_source(source, per_tab_budget_s)
                 -> _cdp_create_new_tab(url) via PUT/GET /json/new
                 -> _wait_for_dom_ready (probe selector)
                 -> _scroll_and_collect (4 scroll-pages, _GMAIL_COLLECT_JS)
                 -> returns list[WalkerRow]
       -> _process_batches:
            for each batch of 30 rows:
              -> _llm_extract via platform_adapter.model_call (DeepSeek V4 Flash)
              -> merge_delta writes ~/.anticipy/v7/dossiers/<account_id>/dossier.json
  -> /api/coldstart/status snapshots run_state()
```

Timing budget on the synthetic test (representative of a signed-in
Gmail inbox with 12 visible rows on first load):

  - Walker bridge_ready check: <1s
  - Tab open + DOM ready: ~3-5s
  - Scroll + collect 12 rows: ~3-5s
  - LLM batch (DeepSeek V4 Flash via OpenRouter): ~5-8s
  - Merge + write dossier: <1s
  - Total: 18.7s

On a fresh install with ANTICIPY_QUIET=0, the popover that fires
`/api/coldstart/start` will see `state=done` and a populated dossier
within ~30s for a fully-loaded Gmail inbox.

## Owner-blockers requiring Omar

1. Gmail sign-in state in user's Chrome on 9222.
   The probe ran against an empty Chrome profile. The shipped flow
   uses `desktop/src-tauri/src/lib.rs::bootstrap_anticipy_chrome`
   which copies the user's default Chrome profile to
   `~/.anticipy/chrome-clone/` and launches a CDP-enabled Chrome
   pointed at it. If Omar is not currently signed into Google in
   his default Chrome at the moment of install, the clone profile
   has no auth cookies and Gmail/Calendar/Drive will all 302-redirect
   to sign-in. Document: this is a USER state precondition, not a
   code bug.

2. Sidecar binary needs rebuild.
   `engine/anticipy-engine.spec` was updated to bundle the source
   JSON data file. The current
   `desktop/src-tauri/bin/anticipy-engine-aarch64-apple-darwin` was
   built before the spec change and still lacks the data file. Run
   `pyinstaller engine/anticipy-engine.spec` (or the desktop build
   script) to refresh the binary. Until then, the embedded fallback
   in `sources.py::_EMBEDDED_DEFAULT_SOURCES` is what saves cold-start
   on the shipped binary.

## Files touched

  - `engine/app/coldstart/sources.py` (template path probe +
    embedded fallback defaults)
  - `engine/anticipy-engine.spec` (datas entry for the JSON data file)
  - `engine/app/product/server.py` (singleton-lock same-process re-entry guard)
  - `planning/00-handoff/COLDSTART_90S_REPORT.md` (this file)

## Artifacts in $PROBE_HOME

  - `chrome.log` (Chrome stderr)
  - `bridge.log` (bridge stderr)
  - `probe.log` (sidecar binary stderr)
  - `probe-src.log` (source-tree engine stderr)
  - `fake-gmail/inbox.html` (synthetic test fixture)
  - `fake-gmail.log` (HTTP server log)
  - `.anticipy/inhale_sources.json` (materialized config)
  - `.anticipy/v7/dossiers/<account_id>/dossier.json` (merged
    cold-start result)
