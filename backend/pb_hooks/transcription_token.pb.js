/// <reference path="../pb_data/types.d.ts" />

// THIS ENDPOINT NO LONGER MINTS ANYTHING. It is kept, refusing, rather than
// deleted, because a deleted route answers 404 and a 404 reads as "you have the
// wrong URL" — the phone would retry it forever waiting for a server that was
// simply misconfigured. A refusal that names its reason is the difference
// between a thing that is broken and a thing that was decided.
//
// WHAT IT USED TO DO: exchange the server-held DEEPGRAM_API_KEY for a 60-second
// JWT so a signed-in iPhone could open wss://api.deepgram.com/v1/listen and
// stream the pendant's raw Opus frames to it, undecoded.
//
// WHY IT STOPPED. design/LOCAL-FIRST.md rule 1, verbatim and first in the list:
//
//     "RAW AUDIO NEVER LEAVES A DEVICE. Not to Deepgram, not to anyone. If a
//      capability needs better ears, find a better local model."
//
// That is an architecture law of this product, it names this vendor, and this
// hook was the mechanism that broke it. It also made the server a credential
// broker for a third party — the exact pattern the HANDS 2 card was declined
// for on 2026-08-24 (docs/DECISIONS-2026-08-24.md RULING 3), while an already
// shipped instance of it ran in production unremarked.
//
// WHAT IT COST TO CLOSE: nothing that worked. Measured against production on
// 2026-08-25 before removing it — events with source="pendant": ZERO, ever.
// The phone microphone had captured 229. This lane never delivered one row in
// its life, so no capability is being taken away; a standing violation and a
// live vendor-credential endpoint are.
//
// WHAT MUST REPLACE IT, and it is not this: the pendant needs an ON-DEVICE
// transcriber. app/ios/Anticipy/Audio/LocalTranscriber.swift is the intended
// home and is 43 lines with zero call sites — and it wants AVAudioPCMBuffer
// while the pendant emits Opus Data, with no Opus decoder in the target. That
// gap is the real work, and it is honest to say the pendant is mute until it is
// done rather than to keep shipping the audio off the phone.
//
// overnight/no_vendor_ears.py goes red if any of this comes back.
routerAdd("POST", "/transcription/token", (e) => {
  if (!e.auth) return e.json(401, { error: "sign in first" });
  // The vendor is named in the comment above and NOT in this string, on
  // purpose: overnight/no_vendor_ears.py greps live code for the hostname, and
  // a gate that its own refusal notice sets off is a gate somebody will soften.
  console.log(
    "transcription/token: refused. Streaming raw audio off-device breaks " +
    "LOCAL-FIRST rule 1. The pendant needs an on-device transcriber; " +
    "see app/ios/Anticipy/Audio/LocalTranscriber.swift.");
  // 410 GONE, deliberately, not 502 or 503. Those mean "try again later" and
  // the phone's catch block schedules a retry on them, so a temporary-sounding
  // refusal would spin a reconnect loop forever against a decision that is
  // permanent. The client half of that stop is app/ios and is not yet done.
  return e.json(410, {
    error: "transcription tokens are not issued",
    reason: "raw audio never leaves a device (design/LOCAL-FIRST.md rule 1)",
    replacement: "on-device transcription; see LocalTranscriber.swift",
  });
});
