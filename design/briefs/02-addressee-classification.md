# Brief 02 — Addressee classification (roadmap §7.1)

## Mission
Before triage decides ignore/ask/act, answer: WHO is the owner talking to?
- `assistant` — addressing Anticipy directly
- `person` — talking to another human
- `dictation` — dictating to a machine (voice-to-text, e.g. Wispr Flow:
  long fluent runs of instruction-like prose with no interlocutor)
- `self` — mumbling/thinking aloud

Dictation and person-directed speech must default to the ambient lane:
remembered, researched quietly if valuable, but NEVER spawning texts or
confirmation prompts. This kills the false "On it" fires seen live on
2026-08-04 when the owner dictated messages to another AI.

## Context you must read first
- `brain/anticipy_core.py` — `hear()`, `_decide()`.
- `brain/orchestrator.py` — TRIAGE_SYSTEM.
- `brain/segmenter.py` — segment context (a classification should be sticky
  within a segment; people don't switch addressee mid-breath).
- `design/PRODUCTION-ROADMAP.md` §3 and §7.

## Design constraints
- One extra LLM stage is too expensive per line: fold the classification
  INTO the triage prompt (one call, one JSON) with an `addressee` field,
  plus a deterministic pre-filter for obvious cases (very long fluent
  instruction-prose = dictation candidates).
- Sticky within a segment: carry the previous classification as context;
  require positive evidence to switch.
- Fail open to today's behavior: if the field is missing/invalid, treat as
  before (no regression when the model misbehaves).
- The decision and addressee must be logged on the event record so
  misclassifications are auditable.

## Definition of done
- Offline tests with a scripted fake LLM: dictation lines produce no
  notify_owner calls and no held jobs; direct asks still act; person-to-
  person planning is remembered and may research (lane ambient) but never
  texts.
- All existing suites green.
- A transcript replay test using the actual 2026-08-04 false-fire lines
  (see screenshots content quoted in the roadmap) shows zero "On it".
