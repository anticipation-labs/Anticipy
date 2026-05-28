# Anticipy Inference Data Bootstrap

The inference dataset starts with synthetic natural conversation, hard negatives, actor/scenario conversation, beta telemetry, corrections, dismissals, acceptances, and missed-positive mining from later user actions.

Each example contains:

- `contains_actionable_want`
- `want_owner`
- `want_type`
- `desired_state`
- `evidence_spans`
- interpretation flags for hypothetical, joke, quote, media reference, third-party want, and already-satisfied state
- `known_surface_exists`
- `known_skill_exists`
- `missing_slots`
- `risk_tier`
- `gold_action_or_decline`

Generated data is never proof that the product works. It is training and calibration material. Product proof still comes from V7 stranger runs on the public installed user-device engine and real user-visible surfaces.
