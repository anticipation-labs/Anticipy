# New-user signup was dead on the Worker, and the same hole was filling D1 with landfill

2026-09-04. Found by diffing the PRODUCT surface — what the iPhone, the
extension and brain/ call — rather than HQ, which is all the 146 green tests
had ever exercised.

## Two failures, one cause

`src/pb/records.ts` had a single generic `create()` for every collection. It
did not know that `owners` is an AUTH collection, so:

**Signup could not succeed.** The iPhone sends email + password +
passwordConfirm + legacy_uuid (AnticipyBackend.swift:444). `passwordConfirm` is
not a COLUMN, so the generic writer refused the whole request with
`unknown_field`. Every new account on the Worker would have failed at the door.
Nothing in the suite noticed, because no test creates an account the way the
app does.

**And signup could not fail.** A POST with an EMPTY BODY was accepted and wrote
a row: null email, no password, no tokenKey. Unauthenticated, from anywhere.
Production refuses the identical request with `validation_required`.

An account with no password can never be signed into and can never be deleted
by its owner. It is landfill with a row id. **24 of them accumulated in D1 in
one afternoon**, purely from probing, and each one is a row an attacker could
have created a million of.

## The contract, measured rather than assumed

Both origins, side by side:

    {}                             password, passwordConfirm  validation_required
                                                              "Cannot be blank."
    {password, passwordConfirm}    email                      validation_required
    password "abc"                 password  validation_min_text_constraint
                                             "Must be at least 8 character(s)."
    confirm mismatch               passwordConfirm  validation_values_mismatch
                                                    "Values don't match."
    envelope   {"data":…,"message":"Failed to create record.","status":400}

**Validation ORDER is part of the contract and it is not the obvious one.** On
a blank body production reports only the two password fields and says nothing
about the missing email; the email error appears only once the passwords are
filled in. Collecting all three at once looked tidier and was wrong: the iPhone
shows one message at a time, so the field named first is the field the person
is sent to fix. All four cases are now byte-identical between the two backends.

Uniqueness reports under `email`, `phone` and `legacy_uuid` because
AnticipyBackend.swift:459-462 branches on exactly those keys to tell a taken
address from a taken number from a taken device.

## Verified round trip

    create (as the iPhone sends it)      200, and neither password nor tokenKey
                                         appears in the response
    auth-with-password                   OK, 189-char token
    auth-refresh with that token         200  ← proves tokenKey was minted right
    wrong password                       400
    duplicate email                      validation_not_unique, under "email"

The digest is bcrypt `$2a$` at cost 10 — Go's `bcrypt.DefaultCost` — so an
account created here is one PocketBase would also accept if traffic ever moved
back. That matters for rollback, not just tidiness.

## Still to do, and it needs a hand

25 junk owner rows remain in D1 (blank-email rows plus the `@example.invalid`
probes). Verified safe to remove: they own **zero** jobs and **zero** events,
and the 8 real rows left behind are a strict SUBSET of production's 9 — the one
extra on production is `qenh9gbgs028rtq`, the row created there by an earlier
careless probe that the owner chose to leave.

The DELETE was refused by the permission gate, correctly, and is left for the
owner:

    npx wrangler d1 execute anticipy-backend --remote --command \
      "DELETE FROM owners WHERE email IS NULL OR email = '' OR email LIKE '%@example.invalid'"

It cannot refill: blank creation is now refused.

## Why HQ testing could never have found this

Every one of the 146 green legs exercised `/internal/*` or the four collections
the skeleton happened to define. Signup lives on `/api/collections/owners/records`,
which the suite only ever called with a *valid* body on an origin that already
worked. Third time today the same lesson has paid: **diff the surface the
CLIENTS use, not the one the tests already cover.**
