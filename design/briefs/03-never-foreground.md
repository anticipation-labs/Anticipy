# Brief 03 — Browser jobs never take the foreground (roadmap §9)

## Mission
Nothing the extension does may steal focus or surface a tab/window while
the owner is using Chrome. Background always; the owner should be able to
forget she is working.

## Context you must read first
- `extension/agent_loop.js` — tab creation, the needs_user hand-back,
  spawned-tab sweep (0.2.3), tab groups.
- `extension/background.js` — pairing page, polling, notifications.
- `extension/manifest.json` — permissions.

## Design constraints
- Audit EVERY `chrome.tabs.create`, `chrome.tabs.update`,
  `chrome.windows.create/update`, `chrome.tabs.group` call for focus
  side-effects; all must be `active:false` / `focused:false`.
- The needs_user hand-back must NOT `tabs.update({active:true})`. Instead:
  set a badge on the extension icon + a chrome.notifications message
  ("I need you on <site> — click to open"), and only focus the tab when
  the owner clicks the notification/badge.
- Links the page opens itself (target=_blank) inherit focus: keep the
  sweep, and re-assert the working tab's background state after each step.
- The pairing/onboarding page (explicit user action) MAY open focused —
  that is the owner's own click.
- Bump manifest version; `node --check` both files as .mjs.

## Definition of done
- Grep proof: zero focus-stealing calls outside the pairing path.
- Manual proof script for the manager: run a research-style browser job
  while a different tab is active; the active tab never changes.
- No regression to job completion (the e2e example.com job still passes).
