# Anticipy v-final-prototype — CHANGELOG

Append-only ledger of every approach attempted and outcome. Do not re-attempt anything that has already failed here. Read at the start of every phase.

---

## 2026-05-13 — Session start

### Attempted approaches (this session)

- **WebSearch / WebFetch through the Claude Code harness** — currently broken with `API Error: 400 This model does not support the effort parameter`. Workaround: direct `curl` to public APIs (Hugging Face `/api/models`, Mistral `/v1/models`, DeepSeek `/v1/models`, Cerebras `/v1/models`). All worked. Do not retry WebSearch/WebFetch this session.

### Confirmed-and-still-broken approaches (carried over from prior rounds, per AUTONOMY_LOG.md and STATUS.md)

- **Cerebras 30 RPM free tier as the executor primary**, shipped in `extension/agent.js` with 2 s call spacing → guaranteed 429 cascade. Killed 0/35 overnight benchmark. Do not re-attempt without a paid Cerebras tier OR a server-driven call-spacing throttle delivered to the extension at runtime.
- **Server-driven `system_prompt` updates** can change the agent's prompt but cannot change tier order, spacing, model selection, or retry budget — those are baked into the shipped extension JS. Re-architecture requires an extension reload.
- **Patchright/Chromium subprocess on the wearer's machine** — explicitly off the table (cop-out #25). Wearer's actual Chrome only, via extension or `chrome.debugger`.
- **5-tier LLM provider rotation as the RPM fix** — tried, didn't work. The real fix is cache + queue + role split + (eventually) paid tier on one provider.
- **Single-model self-criticism in the executor** — degenerates per published research. Critic must run on a different model from the executor.

### Confirmed dead model/provider references in the codebase

These names still appear in code but the providers are explicitly forbidden by the prompt's provider whitelist:
- `claude*` (any version, Anthropic) — forbidden
- `kimi*`, `moonshot*` — forbidden
- `gpt-*`, `openai` — forbidden
- `deepgram` — forbidden (replaced by Parakeet local OR Mistral voxtral-mini)

Phase 2 archives every file that imports these.

