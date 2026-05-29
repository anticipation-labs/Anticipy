Archived. Not part of the shipping product.

`legacy_extension_v1/`, `legacy_extension_v2/`, `legacy_extension_v3/`
were Chrome extension prototypes from before the architecture moved to
the local Mac app + CDP-against-real-Chrome model that ships today.

Per V2 PRD and per HUMAN_READY_PLAN item 10 (2026-05-29), the product
no longer needs a user-facing browser extension. The Mac DMG at
anticipy.ai/app is the install surface; the engine drives the user's
real Chrome via CDP through a local bridge on port 7777.

These directories are kept here for git history and reference only.
Do not load them into Chrome and do not link to them from new code.

If `installer/install.sh` or `public/install.sh` still references the
extension layout, treat those scripts as legacy too and route new
installs through anticipy.ai/app.
