# Anticipy DECISIONS: founder-only calls (MH-D1, MH-D2)

These are NOT engineering decisions and they are NOT decided here.
This file surfaces the real options, the tradeoffs, and a
recommended default for two questions only the founder (with
counsel) can bind. Nothing in this file is a binding policy. The
agent did not and will not invent one.

## Research honesty caveat (read first)

The session-wide web tooling (WebSearch / WebFetch / research
subagent) was infra-down for this entire build (recorded in
PROGRESS.md, multiple distinct attempts, same 400 error). The
legal framework summarized below is long-established, stable law
(US wiretap/eavesdrop consent doctrine and standard data-lifecycle
practice), presented from documented knowledge as of the training
cutoff (Jan 2026). It is NOT live-verified against current
statutes or 2026 case law. Before any of this is bound as policy
it MUST be verified with qualified privacy counsel for every
operating jurisdiction. Treat the specifics as orientation, not
legal advice.

================================================================
MH-D1: privacy, consent, recording non-consenting people
================================================================

The hard problem: an always-listening wearable captures the voice
of people who never agreed to be recorded (a spouse, a colleague,
a waiter, a stranger). Whether, where, and how that is lawful is
jurisdiction-dependent and is a founder/legal decision, not a code
default.

The landscape (documented, verify with counsel):
- One-party-consent jurisdictions: recording a conversation is
  generally lawful if at least one party (the wearer) consents.
  Most US states and US federal law follow this.
- All-party / two-party-consent jurisdictions: every party to the
  conversation must consent. A well-known set of US states
  (commonly cited examples include California, Florida,
  Illinois, Pennsylvania, Washington, and others) plus many
  non-US jurisdictions (much of the EU under GDPR has a stricter
  lawful-basis regime entirely). The exact list and the
  "expectation of privacy" tests change; counsel must confirm.
- Comparable products converge on: explicit wearer onboarding
  consent; a visible/disclosed recording indicator; data
  minimization (process transient audio, do not retain raw audio
  of bystanders); on-device or ephemeral handling of non-wearer
  speech; and a clear, accessible disclosure the wearer is
  responsible for honoring in two-party contexts.

Options:
  A. Wearer-consent-only, one-party model. Simplest, lawful in
     one-party jurisdictions. Risk: unlawful in all-party
     jurisdictions; reputational and legal exposure; bystanders
     have no agency.
  B. Geofenced consent model. Detect jurisdiction; enforce
     all-party behavior (no retention, no processing of non-wearer
     speech, or hard mute) where required. Lower legal risk;
     significant engineering + a hard dependency on reliable
     jurisdiction detection; still imperfect.
  C. Wearer-only processing by construction. Never persist or act
     on a non-wearer's words at all; the speaker anchor already
     gates this in the stack (non-wearer speech is demoted to
     life-log and never an action). Strongest privacy posture,
     closest to the existing architecture, narrows the product
     surface (it cannot act on "your boss told you to ...").
  D. Hybrid: C as the global default, B's geofencing only to
     decide whether even transient non-wearer processing /
     life-log is allowed, A nowhere.

Recommended default (a recommendation, NOT a binding decision):
Option D. It matches what the system already does (the enrolled-
wearer anchor demotes all non-wearer speech; nothing acts on a
bystander), adds jurisdiction-aware suppression of even transient
non-wearer handling where all-party law requires it, and pairs
with explicit wearer onboarding consent + a disclosed recording
state. This minimizes legal and ethical exposure while preserving
the core value (acting on the WEARER's own words and commitments).
The binding choice, the exact jurisdiction list, the consent copy,
and the retention specifics are the founder's call with counsel.

================================================================
MH-D2: data lifecycle (retention, deletion, export, wipe-on-cancel,
encryption at rest)
================================================================

What the build already does (facts, not decisions): cookies /
profiles / the offline buffer / tokens are Fernet-encrypted at
rest with the existing key scheme (no new credential); the memory
layer has decay + a non-promotable invariant; per-user isolation
refuses cross-tenant reads. What is NOT decided: how long anything
is kept, what deletion guarantees are promised, export format, and
what "cancel my account" must irreversibly destroy.

Options (each a founder/legal call):
  Retention
    R1 Minimal: keep only durable facts + open commitments;
       transient transcripts and life-log decay fast (days).
       Best privacy, weakest "remember everything" capability.
    R2 Tiered: durable facts indefinite (until deleted),
       episodic memory medium TTL, raw transcript ephemeral.
       Balanced; the decay engine already supports this shape.
    R3 Long: retain to improve personalization. Strongest
       product, highest exposure; likely unacceptable in strict
       jurisdictions.
  Deletion / wipe-on-cancel
    D-a Soft delete + scheduled purge. Operationally easy;
        "deleted" is not immediately true.
    D-b Hard, synchronous, verifiable wipe across the store +
        backups + the offline buffer on cancel, with a
        confirmation artifact. Strongest user trust; more
        engineering and backup-handling care.
  Export
    E-a Structured JSON export of durable facts + history on
        request (right-to-access friendly).
  Encryption at rest
    Already Fernet for local stores; the open decision is the
    production store: per-tenant keys vs one service key, and
    key custody/rotation. Per-tenant keys + documented rotation
    is the stronger posture; it is a real ops decision.

Recommended default (recommendation, NOT binding): R2 tiered
retention + D-b hard verifiable wipe-on-cancel + E-a export +
per-tenant encryption keys with a written rotation policy. This
matches the architecture already built (decay, isolation, Fernet)
and is the most defensible against strict-jurisdiction
requirements without gutting personalization. Exact TTLs, the
backup-wipe guarantee wording, and key custody are the founder's
call with counsel and an ops owner.

================================================================
Status
================================================================

MH-D1 and MH-D2 are SURFACED here with researched options, honest
tradeoffs, and a recommended default. They are explicitly NOT
bound by the agent and do NOT block any other phase. The founder
must make the binding calls with privacy counsel, and the
research substrate must be live-verified once the web tooling
outage is over or via counsel.
