# INPUT_MODES.md

This contract defines V7 input modes and the same inference boundary.

## Four Input Modes

V7 accepts these four modes:

1. `audio_upload`: MP3/audio upload from the public app or installed engine.
2. `transcript_upload`: text transcript paste/upload.
3. `computer_microphone`: the computer's built-in or selected system mic.
4. `external_microphone`: USB, Bluetooth, line-in, or other external mic input.

Future pendant audio is represented as `external_microphone` with
`source_detail: "pendant"`. It must not create a fifth inference path.

## Same Inference Boundary

Every mode must produce the same normalized input record before inference.
Audio modes pass through ASR first. Text transcript paste/upload enters directly.
After that point, downstream inference must not care which source produced the
transcript except through metadata and confidence fields.

Required normalized input shape:

```json
{
  "schema": "anticipy.normalized_input.v7",
  "input_id": "uuid",
  "account_id": "string",
  "device_id": "string",
  "source_mode": "audio_upload | transcript_upload | computer_microphone | external_microphone",
  "source_detail": "mp3 | wav | aiff | m4a | flac | paste | text_file | built_in_mic | usb_mic | bluetooth_mic | line_in | pendant | other",
  "captured_at": "iso-8601",
  "transcript_text": "string",
  "transcript_sha256": "hex",
  "language": "string",
  "duration_ms": "number | null",
  "asr_confidence": "number | null",
  "audio_artifact_ref": "string | null",
  "text_artifact_ref": "string | null",
  "surface_context_refs": ["string"],
  "public_build": {
    "app_url": "https://www.anticipy.ai/app",
    "build_id": "string",
    "installer_sha256": "hex"
  }
}
```

## Mode-Specific Requirements

`audio_upload` must preserve the uploaded file hash, media type, duration, ASR
artifact reference, transcript text, and transcript quality evaluation when an
evaluation set is available.

`transcript_upload` must preserve the pasted or uploaded text hash and enter the
same inference boundary with perfect input fidelity by definition.

`computer_microphone` must record the selected system input device, permission
state, capture window, transcript, and confidence.

`external_microphone` must record the selected external input device, connection
type where available, permission state, capture window, transcript, and
confidence. Future pendant audio uses this same mode.

## Proof Requirements

Input-mode proof must run against the installed public user-device engine. MP3
or audio upload proof must call the audio upload route with real audio bytes and
observe an `upload-asr-*` ingest id. Transcript proof must observe an
`asr-transcript-*` ingest id. Microphone proof must start the selected device,
observe the stream as on, and then observe a fresh `mic-asr-*` record from that
same device. Device-selection provenance without a fresh `mic-asr` record is not
proof.

## Invalid Shortcuts

- No separate inference branch for uploaded MP3s.
- No separate inference branch for pasted transcripts.
- No pendant-only decision path.
- No fixture transcript presented as live microphone input.
- No log-only proof that a microphone or upload was used.
- No `SwitchAudioSource` or operating-system default-device proof in place of
  a selected-device `mic-asr` receipt.
