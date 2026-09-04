# SPIKE: can workerd verify PocketBase's existing bcrypt hashes?

Run 2026-09-03 against a real workerd (`wrangler dev --local`, wrangler 4.129.0,
`compatibility_flags: ["nodejs_compat"]`), library `bcryptjs@3`.

## Why this had to be answered first

`owners` is the only auth collection. Its `password` column holds bcrypt digests
written by Go's `golang.org/x/crypto/bcrypt` (PocketBase's identity engine).
If a Worker cannot verify those exact digests, the cutover locks out every
existing account and the only remedy is a forced password reset for all of them
-- by SMS, through `password_reset.pb.js`, which is itself being ported. The
audit could not confirm it and marked it UNVERIFIED. This spike settles it.

## Result: YES

    verify_2a_correct: true      <- $2a$, the prefix PocketBase writes
    verify_2a_wrong:   false
    verify_2b_correct: true
    verify_2b_wrong:   false

Both bcrypt versions verify correctly, and both reject a wrong password. No
WASM, no native module, no polyfill beyond `nodejs_compat`. Existing users keep
their logins.

(`$2a$` vs `$2b$` differ only in handling of passwords over 255 bytes, so a
short-password digest verifies identically under either label. The test asserts
both rather than assuming.)

## The finding that came with it: ~50ms CPU per verify

202ms for 4 compares at cost factor 10 -- Go's `bcrypt.DefaultCost`, which is
what wrote the production hashes. That is CPU, not wall time; bcrypt is
deliberately compute-bound and cannot be made cheaper without lowering the cost
factor, which would weaken every stored hash.

CONSEQUENCE FOR THE MIGRATION: the login path needs a Workers plan whose CPU
limit is above 50ms per request. The free tier's 10ms CPU ceiling is not enough
and login would fail there -- not slowly, but with an exceeded-CPU error, on
every attempt. This is a plan requirement, not a code problem, and it is
independent of D1/R2 which are also paid at any real volume.

Do NOT "fix" this by lowering the cost factor. Re-hashing at a lower cost is a
silent downgrade of every user's password security, and it cannot be undone
without knowing the plaintext.

## What this does NOT prove

- That the rest of PocketBase's auth contract ports: token issue/refresh keyed
  on `tokenKey`, invalidation on delete, and `@request.auth.id` rule semantics
  are all still to be built. Only the password check is settled.
- Throughput under concurrency. One verify was measured, not many at once.
