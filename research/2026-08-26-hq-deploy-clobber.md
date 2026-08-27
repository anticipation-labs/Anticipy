# HQ deploy clobber — 2026-08-26

## Incident

The active Railway `backend` deployment served `pb_public/internal.html`, but
did not contain `pb_hooks/internal_hq.pb.js` or any of the HQ migrations. The
page therefore loaded while every fresh login failed: `POST /internal/login`
returned 404, including for the correct team key.

The deployment matched the active `jose_anticipy_system` backend files, whose
branch did not carry the HQ source. This was the same shared-backend collision
class recorded on 2026-08-25: deploying a feature branch that lacks another
live lane removes that lane from the image even though its database remains on
the Railway volume.

## Recovery

Production was restored from an exact archive of the active container, with
only these changes overlaid:

- `pb_hooks/internal_hq.pb.js`
- the six HQ migrations through Notes
- the last known-good `pb_public/internal.html`

All other active hooks, migrations, public files, and `start.sh` stayed
byte-identical. Railway deployment `f2bc1a95-00a7-40c1-9bef-cb129724a247`
completed successfully.

## Live proof

- `/internal/health` returned `ok: true`, `gated: true`, `version: hq-2`.
- A wrong key returned 401; the configured team key returned 200.
- `/internal/state` returned the live people, tracks, tasks, Notes, and
  Passwords collections.
- The restored `internal.html` hash matched the source byte-for-byte.
- Chrome loaded Today and Notes through `https://www.anticipy.ai/internal`
  with the existing Omar session and no application console errors.

## Guardrail

Every backend deployment must be a union of the active product lanes. Before
shipping, compare the proposed archive with the active container and treat a
missing live hook or migration as a rollback, even when Railway reports the
deployment as successful.
