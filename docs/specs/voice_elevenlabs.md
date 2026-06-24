# Spec: Premium real-time voice — ElevenLabs via Twilio ConversationRelay

Status: BUILD CHECKLIST. File-level. Cite line numbers when you touch code.
Scope: give the two-way voice line a premium ElevenLabs voice instead of Twilio's default Polly/Amazon TTS. Nothing about the brain, the safety contract, or the decider changes — only the voice that speaks the brain's already-rendered reply.

---

## 0. The one true premise correction (read before you build)

The prompt said "add the /cr websocket route." **It already exists.** Do not add it again.

- `engine/anticipy_engine/main.py:1663` — `@app.websocket("/cr")` / `async def conversation_relay(ws)` is the full two-way turn loop. It is auth-gated (`main.py:1681` calls `_owner_ws_authorized`), capped (turns `main.py:1694`, duration `main.py:1695`), and already speaks: on a `{type:"prompt", voicePrompt}` frame it runs `brain.turn(...)` (`main.py:1724`) and streams the reply back as `{type:"text", token, last}` frames (`main.py:1728-1731`), closing with `{type:"end", handoffData}` (`main.py:1746`).
- `engine/anticipy_engine/channels/call.py:56` `conversation_relay_twiml(ws_url, greeting)` emits `<Connect><ConversationRelay url=... welcomeGreeting=.../></Connect>` (lines 71-77).
- `engine/anticipy_engine/channels/call.py:79` `call_twiml(message)` picks the relay TwiML when `ANTICIPY_CR_WSS_URL` starts with `wss://` (lines 84-87), else the one-shot `<Say>` fallback (`call.py:41` `twiml`).
- `engine/anticipy_engine/channels/conversation_relay.py:78` `ConversationRelayBrain` is the seam to the proactive `Decider`; `turn()` (line 102) returns a `RelayTurn` whose `.reply` is the spoken sentence.

So the transport is DONE. **The single missing piece is telling Twilio ConversationRelay to render that text with an ElevenLabs voice.** With ConversationRelay, the engine never streams audio — Twilio owns ASR+TTS and the engine only ever exchanges *text* JSON. Switching to ElevenLabs is therefore a **TwiML attribute change + one Twilio dashboard credential**, NOT a new audio websocket.

There is ZERO ElevenLabs code in the repo today (verified). This spec is greenfield on top of a finished transport.

---

## 1. How Twilio ConversationRelay does ElevenLabs (the mechanism)

Twilio ConversationRelay supports pluggable TTS providers via attributes on the `<ConversationRelay>` element:

- `ttsProvider="ElevenLabs"` (default is `Google`/`Amazon`).
- `voice="<ElevenLabs voice id>"` (e.g. a Rachel/Donna-style voice id from the ElevenLabs voice library).
- optional `ttsLanguage`, and ElevenLabs model selection via the voice config.

The ElevenLabs API key itself is **NOT** put in TwiML and **NOT** held by our engine. It is stored once in the **Twilio Console → Voice → Settings → ConversationRelay → TTS providers → ElevenLabs API key** (a Twilio "credential" for the provider). Twilio calls ElevenLabs server-to-server with that stored key; our `<ConversationRelay>` only names the provider + voice id.

**Consequence for us:** the engine needs to add two attributes to the TwiML in `call.py`, plus two env vars to carry the voice id and (optionally) provider. The actual ElevenLabs secret lives in Twilio, not in our process.

---

## 2. The SINGLE credential Omar must hand over

**The ElevenLabs API key (`xi-api-key`), pasted ONCE into the Twilio Console ConversationRelay TTS settings — not into our `.env`, not into the engine.**

That is the only secret. Everything else Omar provides is non-secret config (a voice id string, a public wss URL) that already has a home in env vars. Omar does NOT hand the engine an ElevenLabs key, because ConversationRelay terminates the TTS call at Twilio's edge.

(Out of scope but adjacent: the engine still needs the existing `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` / `TWILIO_FROM` / `OWNER_PHONE` to place the call at all — those are already wired, see `call.py:33-35` and `main.py:218`. They are not new.)

---

## 3. Env vars

| Env var | New? | Where read | Value | Purpose |
|---|---|---|---|---|
| `ANTICIPY_CR_WSS_URL` | exists | `call.py:84`, `main.py:219` | `wss://<public-host>/cr` | The public wss URL Twilio dials for `/cr`. Already gates relay-vs-`<Say>` and is the string the Twilio request-signature is checked against (`main.py:215-227`). Must be a real public tunnel/host (ngrok/Cloudflare/deploy), because `127.0.0.1` is unreachable from Twilio. |
| `ANTICIPY_CR_TTS_PROVIDER` | NEW | new read in `call.py` | `ElevenLabs` | Names the ConversationRelay TTS provider. Default to `ElevenLabs` only when a voice id is set; otherwise omit the attribute so Twilio's default TTS still works (no-key dev path stays green). |
| `ANTICIPY_CR_VOICE_ID` | NEW | new read in `call.py` | ElevenLabs voice id (e.g. `21m00Tcm4TlvDq8ikWAM`) | The premium voice. When unset, fall back to the current Polly path so nothing regresses. |
| `TWILIO_AUTH_TOKEN` | exists | `main.py:218` | (secret) | Already used to verify the Twilio signature on the `/cr` upgrade — unchanged, just noted because it is what lets the public `/cr` accept Twilio without an owner token (`main.py:244`). |

No `ELEVENLABS_API_KEY` env var is introduced in the engine. (If a future direct-API path is ever built, that is a separate spec.)

---

## 4. The one code change: `<ConversationRelay>` attributes in call.py

`conversation_relay_twiml` at `call.py:56` currently emits exactly:

```
<Response><Connect><ConversationRelay url="..." welcomeGreeting="..." /></Connect></Response>
```

Change it to conditionally add `ttsProvider` and `voice` when a voice id is configured. Keep the XML-escaping discipline already there (`call.py:71-72`) and keep the result under Twilio's 4000-char Twiml cap (the existing test `test_conversation_relay.py:67-68` asserts `< 4000` — it must still pass).

Concrete shape (read the current function first; do not blind-replace):

```python
@staticmethod
def conversation_relay_twiml(ws_url: str, greeting: str) -> str:
    url = escape(ws_url, {'"': "&quot;"})
    greet = escape(greeting[:1500], {'"': "&quot;"})
    voice_id = (os.environ.get("ANTICIPY_CR_VOICE_ID") or "").strip()
    tts = ""
    if voice_id:
        provider = (os.environ.get("ANTICIPY_CR_TTS_PROVIDER") or "ElevenLabs").strip()
        tts = (f' ttsProvider="{escape(provider, {chr(34): "&quot;"})}"'
               f' voice="{escape(voice_id, {chr(34): "&quot;"})}"')
    return (
        "<Response><Connect>"
        f'<ConversationRelay url="{url}" welcomeGreeting="{greet}"{tts} />'
        "</Connect></Response>"
    )
```

That is the ENTIRE engine-side code delta. `call_twiml` (`call.py:79`), the `/cr` loop (`main.py:1663`), `ConversationRelayBrain`, and `stream_tokens` (`conversation_relay.py:129`) are untouched — the text frames the engine already streams are exactly what ElevenLabs renders.

---

## 5. Message flow: Twilio <-> engine <-> ElevenLabs

```
Owner phone
   |  (PSTN audio)
Twilio ConversationRelay  ── ASR (speech->text) ──┐
   |  welcomeGreeting spoken via ElevenLabs        |
   |  JSON text frames over the wss /cr socket     |
   v                                               |
Engine /cr  (main.py:1663)                         |
   <- {type:"setup", ...}            ack only (main.py:1734)
   <- {type:"prompt", voicePrompt}   one owner utterance (main.py:1714)
        brain.turn(voicePrompt)       SAME Decider, ACT/ASK/SILENT (conversation_relay.py:102)
   -> {type:"text", token, last:false} * N   reply streamed (main.py:1730)
   -> {type:"text", token:"", last:true}     turn done (main.py:1731)
   <- {type:"interrupt"|"dtmf"}      barge-in, ack only (main.py:1734)
   -> {type:"end", handoffData}      on hang-up (main.py:1746)
   |
Twilio ConversationRelay  ── TTS (text->speech) ──┘
   |  renders each {type:"text"} token by calling
   |  ElevenLabs server-to-server with the key stored in Twilio Console,
   |  using ttsProvider="ElevenLabs" + voice=ANTICIPY_CR_VOICE_ID from our TwiML
   v
Owner phone hears the ElevenLabs voice
```

Key correctness points:
- The engine sends only text. ElevenLabs is invoked **by Twilio**, never by us — so our latency/cost surface is just the brain, and no audio buffers cross our process.
- `welcomeGreeting` (the `message` passed through `call_twiml` -> `conversation_relay_twiml`) is also spoken by ElevenLabs, so the opening line and the turn replies share one voice.
- Safety is unchanged: money still ASK, vents still SILENT, nothing executes inline (`conversation_relay.py:49-62` ground truth). Switching TTS cannot widen what the voice may claim.

---

## 6. Build checklist (do in order)

1. **Code:** edit `conversation_relay_twiml` (`call.py:56`) per §4. No other engine file changes.
2. **Test (no creds):** run `engine/scripts/test_conversation_relay.py`. With `ANTICIPY_CR_VOICE_ID` unset the TwiML must be byte-identical to today (no `ttsProvider`/`voice` attrs) so `test_twiml` (`test_conversation_relay.py:47`) stays green. Add one assertion: with `ANTICIPY_CR_VOICE_ID` set, the TwiML contains `ttsProvider="ElevenLabs"` and `voice="..."` and is still `< 4000` chars.
3. **Suite:** `bash scripts/run_suite.sh` — must stay all-green (the change is additive + env-gated).
4. **Twilio Console (Omar):** paste the ElevenLabs `xi-api-key` into Voice → ConversationRelay TTS providers → ElevenLabs. This is the SINGLE credential. Pick a voice in the ElevenLabs library, copy its voice id.
5. **Env (deploy host):** set `ANTICIPY_CR_WSS_URL=wss://<public-host>/cr`, `ANTICIPY_CR_VOICE_ID=<voice id>`, `ANTICIPY_CR_TTS_PROVIDER=ElevenLabs`, plus the existing `TWILIO_*` + `OWNER_PHONE` + `ANTICIPY_CHANNELS_MODE=live`.
6. **Public reachability:** confirm `/cr` is reachable at `ANTICIPY_CR_WSS_URL` from the internet (tunnel/deploy) — `127.0.0.1` will NOT work; Twilio dials it directly and the signature is checked against this exact string (`main.py:215`).
7. **Live smoke:** place a real outbound call (the `call_twiml` path, `call.py:79`), confirm the greeting + replies are in the ElevenLabs voice, and that money/vent lines still ASK/SILENT.

---

## 7. Non-goals / guardrails

- Do NOT put an ElevenLabs key in the engine env or in TwiML — it belongs in Twilio.
- Do NOT add a second audio websocket or a direct ElevenLabs streaming client; ConversationRelay already owns TTS.
- Do NOT touch the brain, `ConversationRelayBrain`, `stream_tokens`, or the safety ground-truth — voice is a rendering choice, not a judgment change.
- Keep the no-key dev/CI path identical: when `ANTICIPY_CR_VOICE_ID` is unset, emit today's exact TwiML so the deterministic suite and the `<Say>` fallback are untouched.
