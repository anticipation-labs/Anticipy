# VERIFIED: the PocketBase filter DSL compiles to safe SQL on Workers

Run 2026-09-04 against `migration/workers/filter-dsl.ts` (794 lines).

## Why this was the decision the whole migration turned on

Five independent clients — the iOS app, the macOS app, the Chrome extension,
`brain/pb.py`, and ~30 proof harnesses — talk to PocketBase's GENERIC
`/api/collections/{name}/records` API and send its filter strings. There was no
purpose-built API layer to swap out, so there were only two options:

  (A) reimplement the records API and its filter grammar on Workers, and change
      no client at all; or
  (B) hand-write endpoints and rewrite all five clients at the same time as the
      database.

(A) lives or dies on whether the filter grammar can be parsed safely. It can.

## Result: 42/42 unit tests, and 0/6 attacks reached SQL

    node --experimental-strip-types migration/workers/test/filter-dsl.test.ts
    42 passed, 0 failed

Adversarial probe, six inputs aimed at the authorization path:

| input | outcome |
|---|---|
| `owner_ref="' OR 1=1 --"` | `("owner_ref" = ?1)`, payload bound as a value |
| `owner_ref="me" \|\| owner_ref!="me"` | compiles, but `provesOwnerScope` → **false** |
| `status="'; DROP TABLE jobs; --"` | `("status" = ?1)`, payload bound |
| `owner_ref="me"; DELETE FROM jobs` | **refused** — `unexpected character ";"` |
| `status~"%' UNION SELECT password FROM owners"` | `LIKE ?1 ESCAPE '\'`, payload bound |
| `secret_column="x"` | **refused** — `unknown field` |

Payloads that reached the SQL string: **0**. Every value is a bind parameter;
identifiers come from a schema allowlist, so a column that does not exist is a
400 rather than an error from SQLite.

## The row that matters most

    owner_ref="me" || owner_ref!="me"   ->   provesOwnerScope: false

That is `guard.pb.js`'s rule, reproduced:

    // `&&` can only narrow the owner set. `||` can widen it back out and is
    // never needed by the phone or the extension.
    return filter.indexOf(`owner_ref="${ownerRef}"`) >= 0
        && filter.indexOf("||") < 0;

The PocketBase version is a substring check — it looks for the literal text and
bans the two characters `||` anywhere in the string. The parser version answers
the actual question: does every branch of this expression constrain the owner?
It is strictly stronger. A filter that mentions `owner_ref` inside an OR passes
the substring test in spirit but is correctly refused here, and a filter that
narrows correctly using a nested parenthesis is accepted where the substring
test would have rejected it for containing `||`.

## What this does NOT prove

- Only the parser is verified. The records API around it — pagination, sort,
  expand, field selection, the record-shaped JSON envelope — is still to be
  built, and each is a place a client can notice a difference.
- PocketBase's `!=` has IS-NOT semantics with respect to NULL
  (`backend/pb_migrations/1700000043:27-30`). The unit suite covers it; a live
  A/B against the two backends is what would settle it.
- Nothing has been run against real D1 with real rows. The compiler emits SQL;
  that SQL returning the SAME rows as PocketBase is what the contract suite is
  for, and that needs ANTICIPY_SERVICE_TOKEN.
