# Two Hands — week-1 spike

A second hand for the agent: when the app has an official API and the owner has
connected it, call the API instead of driving the browser.

**This directory is a spike. Nothing in it is imported by `brain/`,
`migration/workers/`, `extension/` or `backend/`.** That is the owner's rule for
week 1 ("nothing here touches the backend until week 2") and it is enforced by a
test, not by good intentions: `test/no_production_imports.test.ts`.

## What is here

| file | what it is |
|---|---|
| `src/contract.ts` | the interfaces every part is written against. Fixed first, on purpose. |
| `src/index.ts` | `makeTwoHands(deps)` — where the seven parts meet, and where the seams between them are fixed |
| `src/signature.ts` | CapabilitySignature: the hand-agnostic description of one step |
| `src/provider_composio.ts` | the Composio adapter behind `Provider` |
| `src/provider_fake.ts` | an in-memory `Provider` so every test runs with no network and no key |
| `src/router.ts` | the five routing rules |
| `src/ledger.ts` | capability_stats, api_candidates, connect_nudges, shadow_runs |
| `src/observer.ts` | the extension-side trace summary (hosts, methods, statuses — never bodies) |
| `src/onboarding.ts` | connect nudges: when to ask, how often, what the link says |
| `tasks/ten_read_tasks.json` | the ten read-only tasks the week-1 gate is measured on |
| `tasks/run_ten.ts` | the live harness. Three states: CLEAN, BROKEN, UNPROVEN. |
| `results/` | the measured runs. Empty until a key exists. |
| `RESULTS.md` | what is proven, what is not, and what the owner must do before the gate can run |

## Running it

Everything except the live harness runs with no account and no key:

    node --experimental-strip-types --test test/*.test.ts

The live harness needs a Composio account, four connected apps, two keys and
the owner's own answers to the `{{TOKENS}}` in the task file. It refuses to
invent numbers without them and names each thing that is missing:

    COMPOSIO_API_KEY=... OPENROUTER_API_KEY=... TWO_HANDS_OWNER=... \
      node --experimental-strip-types tasks/run_ten.ts

Read `RESULTS.md` before running it. Today it exits 2 and prints UNPROVEN,
which is the honest state and not a soft fail.

## The week-1 gate

9 of 10 reads correct, p50 under 3 seconds, cost logged per call. The harness
prints the ten-row table and exits 0 only when both legs are met, 1 when the
run happened and failed, and 2 when it could not happen at all. A run that could
not happen is never reported as a pass — it prints no table, writes no numbers,
and says UNPROVEN.
