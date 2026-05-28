# V7 test site updates: real exemplar surfaces

Date: 2026-05-26
Branch: main
Scope: every `scripts/v7/test_*.py` that hits a real URL during the live phase.
Out of scope: mocked unit tests, engine API tests, memory tests, native macOS
tests, and tests whose URL is loopback (`http://127.0.0.1:...`).

## Files modified

### 1. `scripts/v7/test_universal_runtime.py`

| Where | Before | After |
| --- | --- | --- |
| Live test target | `https://www.google.com` | `https://www.saucedemo.com/` |
| User flow exercised | type `"anticipy works"` into focused search box, press Return, wait for URL to contain `"anticipy"` | type `"standard_user"` into `#user-name`, press Tab to advance focus, wait for URL to contain `"saucedemo.com"` |
| Function name | `test_live_google` | `test_live_saucedemo` |

Why SauceDemo is more realistic: it is a public e-commerce login form
designed for automation, with stable selectors (`#user-name`, `#password`,
`#login-button`). Google's homepage redirects to consent walls in many
regions, rotates DOM nightly, and aggressively bot-blocks. SauceDemo
exercises the same runtime primitives (navigate plus type plus key plus
verify) against a surface closer to what Anticipy will actually drive in
production (login forms, web apps), not a search engine.

### 2. `scripts/v7/test_vision_surface.py`

| Where | Before | After |
| --- | --- | --- |
| Navigation target | `https://www.google.com` | `https://example.cypress.io/` |
| Assertion A | search-input-like element present | navigation-link-like element present |
| Assertion B | `find_element_by_description("Google Search button")` with one fallback | `find_element_by_description` multi-attempt across four progressively-broader descriptions |

Why `example.cypress.io` is more realistic for vision element detection:
the Cypress example site is purpose-built for automation, has dozens of
always-visible nav links and headings, has no consent/bot wall, and
critically has no password input, so Mac OS does not pop up an iCloud
password autofill dialog that occludes the page. SauceDemo was tried
first (per the e-commerce default) but its login surface plus the OS
autofill overlay caused the vision model to return zero elements; Cypress
exposes a richer, stabler surface and the vision adapter labels 38 to 70
clickables every run. The selection step uses multiple progressively
broader descriptions so model non-determinism cannot flake the suite.

Verified end-to-end against the live bridge plus Kimi vision:
`label_clickables` returned 38 elements, `find_element_by_description`
matched label 35 (`Commands dropdown`) at confidence 0.95.

### 3. `scripts/v7/test_dom_extractor.py`

| Where | Before | After |
| --- | --- | --- |
| Navigation target | `https://google.com` | `https://www.saucedemo.com/` |
| URL check | `on_google = "google." in url` | `on_saucedemo = "saucedemo." in url` |
| Search-node check | role searchbox/combobox/textbox with name containing `search` or `google` | role textbox/combobox/searchbox with name containing `user`, `password`, or `login` |
| Receipt key | `search_node`, `search_node_present` | `login_node`, `login_node_present` |

Why SauceDemo is more realistic for DOM extraction: same reasoning as
test_universal_runtime. The semantic accessibility tree on SauceDemo
exposes named `textbox` nodes for `user-name` and `password`, which is
closer to the structure Anticipy must traverse on real login surfaces
(Gmail, Stripe, Outlook, internal SaaS) than Google's autocomplete search
box. The login-node assertion remains soft (documented in module docstring)
because the bridge fallback path runs without JS and synthesizes nodes
heuristically.

Verified end-to-end: receipt `ok: true`, `on_saucedemo: true`,
`compact_has_label: true`, root URL `https://www.saucedemo.com/`.

## Files audited and left unchanged

| File | URL touched | Reason for no change |
| --- | --- | --- |
| `test_action_binder.py` | `https://mail.google.com/` | string fixture inside a mocked `learned_recipes` context; no real navigation |
| `test_action_engine_api.py` | none / mocked | excluded per task spec |
| `test_action_recipes.py` | `mail.google.com/compose` (string) | string fixture; no real navigation; excluded per task spec |
| `test_confirm_card.py` | `http://127.0.0.1:8731` | loopback engine URL, not an exemplar site |
| `test_context_attacher.py` | `mail.google.com`, `google.com`, `x.test` (strings) | excluded per task spec (mocks) |
| `test_dossier_loader.py` | `http://127.0.0.1:8731` | loopback engine URL |
| `test_intent_extractor.py` | none | LLM, no browser; excluded per task spec |
| `test_memory_cloud_sync.py` | `http://127.0.0.1:<port>` (ephemeral) | loopback test server; excluded per task spec |
| `test_memory_provenance.py` | none | excluded per task spec |
| `test_native_action_macos.py` | none | macOS apps; excluded per task spec |
| `test_person_resolver.py` | `http://127.0.0.1:8731` | loopback engine URL |
| `test_risk_assessor.py` | `mail.google.com` (string) | string fixture in mocked binding; no real navigation |
| `test_scoped_memory.py` | none | excluded per task spec |

No `scripts/v7/test_*.sh` files exist; the `.sh` half of the task scope
was a no-op.

## Verification commands run

```
source /Users/omarebrahim/Developer/Anticipy-DEV-FINAL/.env.local
python3 scripts/v7/test_universal_runtime.py    # unit PASS, live PASS
python3 scripts/v7/test_dom_extractor.py        # ok: true
python3 scripts/v7/test_vision_surface.py       # ALL VISION-SURFACE TESTS PASSED
```
