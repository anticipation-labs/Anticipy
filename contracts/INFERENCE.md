# INFERENCE.md

This contract defines the V7 inference boundary, event schema, decision schema,
and required data/eval artifacts.

## Boundary

The V7 inference boundary receives one `anticipy.normalized_input.v7` record and
the current user surface context. All four input modes from
`contracts/INPUT_MODES.md` enter here.

The boundary decides whether there is an actionable intent and whether Anticipy
should act, ask, decline, or stay silent. It does not get a special path for
MP3/audio upload, transcript paste/upload, computer microphone, external
microphone, or future pendant input.

## Inference Event Schema

Every normalized input writes an append-only event:

```json
{
  "schema": "anticipy.inference_event.v7",
  "event_id": "uuid",
  "input_id": "uuid",
  "account_id": "string",
  "device_id": "string",
  "created_at": "iso-8601",
  "boundary": "normalized_transcript_and_surface_context_v7",
  "source_mode": "audio_upload | transcript_upload | computer_microphone | external_microphone",
  "transcript_ref": "string",
  "transcript_sha256": "hex",
  "surface_context_refs": ["string"],
  "candidate_intents": [
    {
      "intent_id": "uuid",
      "summary": "string",
      "evidence_quotes": ["string"],
      "required_slots": ["string"],
      "missing_slots": ["string"],
      "risk_level": "low | medium | high",
      "confidence": "number"
    }
  ],
  "model_route": {
    "runtime_family": "string",
    "local_steps": ["string"],
    "remote_steps": ["string"],
    "cost_usd": "number"
  },
  "public_build": {
    "app_url": "https://www.anticipy.ai/app",
    "build_id": "string",
    "installer_sha256": "hex",
    "source_captured_at": "iso-8601"
  },
  "status": "observed | candidate | no_action"
}
```

## Decision Schema

Every act, ask, decline, or silent no-op writes an append-only decision:

```json
{
  "schema": "anticipy.decision.v7",
  "decision_id": "uuid",
  "event_id": "uuid",
  "input_id": "uuid",
  "account_id": "string",
  "device_id": "string",
  "created_at": "iso-8601",
  "decision": "act | ask | decline | silent",
  "reason": "string",
  "evidence": [
    {
      "kind": "transcript_quote | dom_read | ax_read | screenshot | file_hash | permission_state | installer_hash | evaluator",
      "ref": "string",
      "summary": "string"
    }
  ],
  "target_surface": {
    "surface_type": "chrome | native_app | file_system | system_permission | none",
    "name": "string",
    "url_or_bundle": "string | null",
    "real_user_surface": true
  },
  "planned_steps": ["string"],
  "result": {
    "state": "pending | succeeded | asked | declined | silent | blocked | failed",
    "proof_refs": ["string"],
    "visible_state_diff_ref": "string | null"
  },
  "requires_user_confirmation": "boolean",
  "policy": {
    "risk_level": "low | medium | high",
    "confirmation_required": "boolean",
    "decline_reason": "string | null"
  }
}
```

## Required Data Artifacts

Each public clean-room run and evaluator run must retain:

- `normalized_inputs.jsonl`.
- `inference_events.jsonl`.
- `decisions.jsonl`.
- `surface_context/manifest.json`.
- `proofs/manifest.json`.
- `eval_runs/<run_id>/manifest.json`.

Each manifest must include public app URL, build id, installer hash, capture
time, account id or redacted account id, device id, source-mode coverage, schema
validation result, and evaluator verdict.

## Required Eval Artifacts

Evaluators must check:

- Schema validity for normalized input, inference event, and decision records.
- Input-mode parity across MP3/audio upload, text transcript paste/upload,
  computer microphone, and external microphone.
- Same inference boundary for all four modes.
- Real Chrome or real native user surface proof when a surface is involved.
- Action, ask, decline, and silent decision quality.
- Transcript quality for audio modes where ground truth exists.
- Source freshness against the current public app state and installer hash.
- No fake receipts/stale-source proofs.

Any evaluator that cannot inspect current surface proof must fail the proof gate
instead of accepting logs.
