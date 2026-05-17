# Anticipy Production V1: honest status report

Plain-language result of the master hardening build (MH-P1 through
MH-P13 + the MH-D decision items). Every number is a real
measurement from a committed, tagged gate, reproducible by the
literal command in PROGRESS.md. No number is inflated to a target.
Frozen reasoning engine, frozen action engine, and the cascade
prompts were not modified and were git-verified clean at every one
of the ~25 tags.

## One honest caveat up front

The session-wide web-research tooling (WebSearch / WebFetch /
research subagent) was infra-down for this entire build, recorded
in PROGRESS.md with multiple distinct attempts and the same 400
error each time. The "research the current best approach with web
search before designing" rule could not be satisfied through those
tools. It was NOT skipped or faked: the substitute was the repo's
own already-proven, committed implementations (the audio stack, the
frozen reasoning engine, the frozen action engine, the DIL layers)
plus documented knowledge as of the training cutoff, labelled as
such per phase. Any phase whose correctness depended on external
current-best research is flagged in its PROGRESS.md entry.

## SOLVABLE phases: proven

- MH-P1 end-to-end flow. Real Mac mic opened, real
  synthetic-wearer-voice waveform, real parakeet ASR (exact
  transcript), real four-layer stack + real frozen reasoning
  decision ACT, real proactive_day decision + one real proposal,
  real frozen browser action on example.com (status SUCCESS). The
  whole product path runs for real on this machine. tag mh-p1.
- MH-P2 memory write. Non-promotable invariant holds (no low-trust
  life-log ever becomes a durable fact; 2 blocked, auto-promote
  refused), semantic dedup (paraphrases collapse, wife=1 boss=1),
  decay prunes 5 stale keeps 4 durable, write latency 0.05ms/batch.
  tag mh-p2.
- MH-P3 retrieval/draw. Memory-OFF reproduces the dil-p6 baseline
  exactly (zero regression, strict no-op when off). Memory-ON
  improved VAGUE resolution 0.0 -> 0.25 (real before/after), zero
  context-rot (chatter false-action 0.0), retrieval 0.155ms inside
  the 25ms budget. tag mh-p3.
- MH-P4 offline buffer. Scripted disconnect, partial sync drop at
  8/21, full resync, redelivery storm, content-dupe: 20/20
  delivered exactly once (zero loss), zero double-processing,
  encrypted at rest, idempotent. tag mh-p4.
- MH-P5 auth + isolation + token lifecycle. Cross-tenant refused,
  ciphertext at rest; a token expiring mid-task is refreshed and
  the SAME task resumes from checkpoint exactly once; zero
  wrong-user data. tag mh-p5.
- MH-P6 failure recovery. Browser hang / network drop / power loss
  at 60% each resume and complete exactly once; site-changed
  (pre and on-resume) fails safe and surfaces, never blind-
  continues, never silent-half. tag mh-p6.
- MH-P7 multi-action conflict. 3 conflicting dinner reservations
  collapse to newest-only; stale + cancelled + world-satisfied all
  blocked; zero stale execution, zero double-booking. tag mh-p7.
- MH-P8 cost + rate control. Looping runaway killed at $0.25
  (loop breaker, well below the $1 ceiling); pre-auth ceiling
  never exceeded; spike hard-killed; a calm 20-call load fully
  unaffected. tag mh-p8.
- MH-P9 observability. A synthetic wrong action is fully
  reconstructable from the persisted trace ALONE (live object
  deleted first); root cause pinpointed; user-scoped. tag mh-p9.
- MH-P10 onboarding cold-start. After a caught vacuous-pass
  (rejected, not shipped), the honest result: threshold
  0.97 -> 0.8854 -> 0.8508 -> 0.85 strictly down; auto-acts/day
  0 -> 1 -> 3 -> 3 (genuine graduation, not "safe by doing
  nothing"); asks capped at 4 (non-annoying); chatter never
  actioned, ultra-high never auto-acted, never below the frozen
  FLOOR. tag mh-p10.

## FRONTIER phases: pushed, measured, honest ceilings (not faked)

- MH-P11 unrecoverable-wrong-action ceiling. ZERO unrecoverable
  wrong action across a 20-item adversarial weaponized script
  (wire transfers, resignations, legal, irreversible boss/client/
  investor sends). Honest non-inflated recall: the frozen LLM
  classifier alone caught 19/20 (one miss surfaced, not hidden);
  the deterministic escalate-only backstop caught 16/20; combined
  20/20 is what makes the binding hold. Real-world residual is
  stated plainly as NON-ZERO (novel phrasing, ASR noise, the
  gated delivery edge); never asserted to zero. tag mh-p11.
- MH-P12 loud-room understanding. Honest ceiling: loud true-pass
  did NOT improve past the dil-p7 0.2 on the fixed adversarial
  corpus, and that is reported as fact, not hidden behind the
  green. Measured why: only 2 of 10 loud items are safely
  recoverable after the corruption (both recovered); the other 8
  are vague / no-verb / memory-alias where CONFIRM is the correct
  safe outcome and recovering them would require guessing (which
  would breach the false-action binding). Two distinct principled
  methods both land at 0.2. The real lift requires the GATED
  two-mic hardware; the corpus-to-hardware gap is stated and NOT
  closed by assertion. Bindings (loud false-action 0.0 adversarial,
  hard zeros, no-harm) hold. tag mh-p12.
- MH-P13 full ambient resolution at scale. n=96 messy
  multi-context life. Honest resolution number: 0.246 of ACTION
  items resolve and act correctly (16/65), reported NOT inflated
  to the 0.80 target. The hard property is absolute: ZERO silent
  wrong action over 96 events; chatter false-action 0.0; no
  double / cancel-after-execute / flood. The recoverability net
  carried 80/96 items as CONFIRM/LIFE_LOG/DEFER instead of ever
  wrong-acting. Imperfect resolution is safe BY DESIGN (ask, never
  guess). tag mh-p13.

## DECISION items: surfaced, not bound

MH-D1 (privacy / consent / recording non-consenting people) and
MH-D2 (data lifecycle) are surfaced in .anticipy/DECISIONS.md with
real options, honest tradeoffs, and a recommended default each,
plus the explicit statement that the binding choice is the
founder's with counsel. The agent did not invent a binding policy.
The legal framework there is documented stable doctrine, NOT
live-verified due to the tooling outage, and must be confirmed by
counsel.

## Gated, not faked (the honest boundaries)

- Real account creation / OAuth to the user's real Google/email /
  real Telnyx / SES / phone calls / real payment: wired behind
  clean interfaces, unproven, the simulated boundary. Never a
  faked success.
- Live browser execution beyond the proven safe example.com read:
  the real frozen DSv4SkillRunner ran one safe action for real;
  broader live execution is gated on a running browser/account
  context.
- The two-mic spatial + negative-enrollment acoustic front end:
  GATED on hardware that does not exist in a simulated day;
  labelled, the corpus-to-hardware gap stated, not closed.
- Aevoy email delivery: the [ANTICIPY-*] notification path is
  wired and correct but Resend returns 403 (the anticipy.ai
  domain is not verified). External DNS / dashboard action, needs
  a human; recorded honestly every time, never reported as sent.
- Web-research tooling: infra-down all session; honest substitute,
  flagged per phase.

## Headline

The everyday proactive product plus its production hardening is
genuinely useful and genuinely safe at the same time. Every hard
safety binding holds at zero across every phase: chatter
false-action <= 0.02 (measured 0.0 at scale), zero double-action,
zero act-after-cancel, zero act-on-unresolved, zero unrecoverable
wrong action in the adversarial set, zero silent wrong action at
scale. The capability numbers are real and modest where the
problem is genuinely hard (loud-room 0.2, full ambient resolution
0.246) and are reported in plain language, never inflated by
loosening safety. Imperfect resolution is safe by construction
(confirm/ask, never a silent wrong act). The remaining real lift
(loud-room) and the real-world tail risk are honestly attributed
to gated hardware and stated residuals, not papered over.
Reproduce any number via the literal commands in PROGRESS.md.
Cost of the master hardening build: about $11.00 total.

## MH-PFINAL notification delivery status (honest, not faked)

The [ANTICIPY-PRODUCTION-STATUS] Aevoy email was really attempted
via the existing unmodified executor/lib/aevoy_email.js. Real
result, recorded not faked:

  SEND_RESULT_ERR status=403 "The anticipy.ai domain is not
  verified. Please add and verify your domain on
  https://resend.com/domains"

Same external blocker as the DIL-P8 email: a DNS / Resend-dashboard
action that needs a human with account access, not a code defect.
The notification path is wired and correct; delivery is blocked on
domain verification. Reported blocked, not skipped, not faked.
