# Which brain hears an owner — Railway or Cloudflare — and when it flips

Written 2026-09-05 after two facts collided. The completeness audit (F45, F48,
F49) said: before TestFlight the Cloudflare brain cap must cover every real
owner, or the phone that installs build 124 posts speech to a backend with no
brain for it. The 16:58Z deploy said: with the cap above zero, real owners had
a Cloudflare brain AND their Railway brain, each holding the same Twilio
credentials, each able to send the clock's texts from the same memory —
duplicates by construction. Both are right, at different moments.

## The rule

An owner is heard by exactly one brain: the one attached to the backend their
phone posts to.

- A phone on build ≤123 posts to Railway → Railway's brain, and only it.
- A phone on the api-pointed build (124+) posts to Cloudflare → that owner
  gets a Cloudflare brain, and only it; Railway's brain has nothing to hear
  for them (no speech lands there) but would still run the clock from stale
  memory — so at the same moment that owner is REMOVED from Railway's serve
  set (`ANTICIPY_MAX_OWNER_WORKERS` / the Railway worker's owner list) or
  the Railway worker is stopped once every owner has moved.

That is a per-owner choice, so it is an allowlist, not a cap:
`ANTICIPY_SERVE_OWNERS` on the brain Worker names the owners on Cloudflare;
`ANTICIPY_MAX_OWNER_WORKERS=0` keeps discovery from adding anyone else.
`parseCap` now reads 0 as 0 (the 16:58Z deploy read it as 100).

## Today (2026-09-05, 17:1xZ)

- Cloudflare: cap 0, allowlist = the probe `qeuy6sv1raof9rw` only.
- Railway: every real owner, as before.
- No duplicate text left during the ~8 minutes four real owners had two
  brains: the Cloudflare four wrote nothing to D1 (no speech there to hear).

## At TestFlight time (the step to run WITH the dispatch)

1. The owner installs build 124/125 on their phone → their account posts to
   Cloudflare from the first line.
2. Set `ANTICIPY_SERVE_OWNERS="qeuy6sv1raof9rw,<that owner's id>"` in
   `migration/config/wrangler.brain.jsonc` and dispatch the brain deploy
   (cap stays 0).
3. Remove that owner from Railway's brain (or stop the Railway worker if it
   is the last owner there).
4. Prove it: `proof/e2e_cloudflare.py --owner <that id>` is not the tool (it
   posts synthetic lines); the proof is the owner speaking and
   `overnight/are_the_ears_live.py` + `is_the_brain_live.py` going green for
   a real device_id, then a text arriving from the Sendblue number.

Known ids (masked in every log): the owner's own account `sxkotd1h02qb6gw`;
the phone that carried speech on Railway `4i2vafx1g01nlia`; the first real
owner by id `43dl3t9oz7q34qc`.
