# Changelog

Releases are cut from `cloudflare-backend`. Each entry names the source commit
that was deployed and what a person can verify, and it does not claim more than
that: "deployed" means live and reachable, not proven in front of a real
person. The readiness board in `docs/EOD-READINESS-2026-09-13.md` carries the
evidence and the open items.

## 2026-09-15 — API revision 2a3fdf17, extension 0.18.3, iPhone build 177

**Fixed**

- A browser released or reassigned from the phone kept its previous owner's
  model key, profile and task text when the account row still carried the old
  owner id. An unpaired browser is now treated as ownerless whatever the row
  says.
- One transient refusal from the server could abandon the *next* browser
  errand; the refusal allowance is now per run.
- Hand-back records written by extension 0.18.2 are no longer stamped with
  whoever holds the browser now, which could have shown one owner's parked page
  to another after an upgrade.
- A typed reply that hit a busy or unreachable connection route was retried
  silently forever; it is now bounded, the owner gets a factual notice, and the
  cause is recorded.
- The "text me a code" page said a code had been sent when the send had been
  refused; it now says so, and a mistyped code returns to the same page.
- Every refused re-plan of an API reply now names its reason in the log.

**Changed**

- Extension download aliases now serve 0.18.3 (package sha256
  `a6a8259d95b5d352a9354795210921e7835e151ac83a888e209b4b5cf0652f07`).
- iPhone build 177 is on TestFlight and expects extension 0.18.3.
- Brain fleet deployed at capacity 100 from the same revision.

**Known and not fixed**

- A pendant sequence jump past the half-range window stalls frame assembly
  until the counter laps or the radio reconnects. A repair was reviewed and
  reverted because it could re-origin the stream backwards; the wire format
  needs a session epoch first.
- Two TestFlight invitations have never been accepted, so the audience gate
  stays red for those two people.

**Documentation**

- License (MIT), security policy, contributing guide, architecture, testing
  and release runbooks, and per-component guides were added. Dated session
  notes that used to sit in the repository root now live under
  `research/archive-root-2026-09-15/`; harness output dumps and a raw session
  transcript were removed from the public branch.

## 2026-09-13 — API and brain from a29bcea6, extension 0.18.2, iPhone build 176

Connector, browser, receipt and migration repairs (PRs 63 and 64). See the
readiness board for the evidence recorded that day.
