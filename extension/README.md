# Anticipy Chrome extension

Anticipy's hands on the owner's computer: a Manifest V3 extension that polls
the API for approved browser jobs and runs them in the owner's own logged-in
Chrome, in the background, never foregrounding itself. It needs the iPhone
app: pairing is a six-digit code the phone claims.

## Layout

| File | Role |
| --- | --- |
| `manifest.json` | MV3 manifest; `version` is the release number. |
| `background.js` | The service worker: registration, heartbeat, the poll-and-claim loop, job execution. Carries `ENGINE_BUILD`, which must equal the manifest version. |
| `config.js` | The one resolver for where the backend lives (`DEFAULT_BASE`). |
| `backend_transport.js` | Per-request network deadlines so queue traffic cannot hold the poll lock. |
| `agent_loop.js` | The act loop: indexed page map, a model chooses one action, CDP performs it. |
| `page_map.js` | Injected into the page to build the indexed map of interactive elements; sensitive values redacted. |
| `workflow_state.js` | Deterministic browser-side projection of `brain/workflow.py`; the brain owns plan creation and approval. |
| `reconcile.js` | After a worker crash: did the click go through? |
| `learn.js`, `recipes.js`, `side_trip.js` | Look it up before doing it; repeat a known shape; go get something and come back. |
| `login_wall.js`, `private_places.js`, `supervised_read.js` | The walls that stop an errand, the mailbox door, the one-time supervised read. |
| `source_context.js` | Background evidence kept outside facts and the approved scope. |
| `popup.html`, `popup.js` | The only face on this machine: is the browser hers, can she reach her queue, what is happening. |
| `onboarding.html`, `onboarding.js` | The setup page: the pair code and whether it has landed. |
| `setup_bridge.js` | Bridge to the hosted setup page, only after its origin is confirmed. |
| `theme.js` | Light or dark on both surfaces, decided before first paint. |
| `icons/` | The three icon sizes. |
| `store/LISTING.md` | Chrome Web Store listing package. Not shipped in the ZIP. |
| `tests/` | The offline suite and its fixtures. Not shipped in the ZIP. |

## The package and its three aliases

The ZIP the API serves is built **from** this directory, never edited by
hand:

```sh
sh extension/build-zip.sh
```

It derives the file list from the manifest's entry points and every relative
import and injected script they reach, refuses a package whose manifest
version differs from the source or whose module graph is incomplete,
normalises timestamps so identical source produces an identical SHA-256, and
writes `migration/workers/public/anticipy-claude-version-extension.zip`, then
copies the same bytes to `anticipy-extension.zip` and
`anticipy-codex-version-extension.zip`. **All three names are aliases of one
build**, kept because a URL handed out in any era must still download the
current bytes. Rename none; commit all three; then deploy the API so people
actually get it ([docs/RELEASE.md](../docs/RELEASE.md)).

`python3 proof/audit/check_extension_package.py` proves the committed ZIPs
match the source and each other; the API deploy job runs it too.

## Loading it into a real Chrome

Chrome loads an unpacked extension from the folder you pointed "Load
unpacked" at and, for a downloaded ZIP, from its own private copy; editing the
repository and pressing Reload changes nothing until that copy is updated:

```sh
sh extension/sync-to-chrome.sh
```

It finds every Chrome profile on this Mac that has Anticipy loaded (reading
Chrome's own extension records), rsyncs this directory into each recorded
folder — excluding `tests/`, `store/`, `package.json` and itself — verifies
the version it lands, and tells you to press Reload. If Chrome reads this
checkout directly, it copies nothing. If nothing is loaded, it prints the
Load unpacked steps. Re-pointing Chrome at a new folder changes the extension
id and breaks the pairing, which is why syncing exists.

## Versions that move together

`version` in `manifest.json`, `ENGINE_BUILD` in `background.js`,
`expectedExtensionVersion` in `app/ios/Anticipy/AnticipyApp.swift`, and
`expected` in `app/ios/Tests/StaleExtensionTests.swift`.

## Tests

```sh
node extension/tests/run_all.mjs
```

Offline: an in-memory `chrome` (`tests/chrome_mock.mjs`) that reproduces
Chrome's dangerous behaviours, a hand-built DOM for `page_map.js`
(`tests/fake_page.mjs`), and a service-worker lifecycle rig
(`tests/rig_lifecycle.mjs`). `tests/MANUAL-PROOF-never-foreground.md` is the
manual leg. What the suite does not prove — a real Chrome, the served ZIP, a
real site — is covered by `proof/audit/check_browser_frame_clicks.mjs` and
the installed-extension rig
([proof/audit/installed_extension/README.md](../proof/audit/installed_extension/README.md)).
