// MAKER voter layer — atomic-decision k=5 parallel voting across
// free-tier providers. Per the v-final-prototype master prompt's L4
// layer (and arXiv:2511.09030, MAKER paper).
//
// For each atomic decision (one step in a recipe — "click this AX node",
// "type this string"), fan out parallel calls to Cerebras / Mistral /
// Gemini / Groq / DeepSeek (when keys present), wait until ONE answer
// leads by 3, return that. Red-flag rejection on structurally weird
// outputs (malformed JSON, refused-action, hedged-action).
//
// Cost target: ~$0.0001 per atomic decision. The free tiers are the
// budget — Cerebras has 1M tok/day, Groq 14400 RPD, Mistral free,
// Gemini free, DeepSeek paid as last resort.

const axios = require('axios');

// Provider pool. Each entry returns a Promise resolving to a STRING
// answer (the model's response). The voter parses each into a
// canonical form for comparison.
const PROVIDERS = {
  cerebras: async ({ system, user, key }) => {
    const r = await axios.post(
      'https://api.cerebras.ai/v1/chat/completions',
      {
        model: 'qwen-3-235b-a22b-instruct-2507',
        messages: [
          { role: 'system', content: system },
          { role: 'user', content: user },
        ],
        temperature: 0.1,
        max_tokens: 256,
        response_format: { type: 'json_object' },
      },
      { headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' }, timeout: 12000 }
    );
    return r.data?.choices?.[0]?.message?.content || '';
  },
  mistral: async ({ system, user, key }) => {
    const r = await axios.post(
      'https://api.mistral.ai/v1/chat/completions',
      {
        model: 'mistral-small-latest',
        messages: [
          { role: 'system', content: system },
          { role: 'user', content: user },
        ],
        temperature: 0.1,
        max_tokens: 256,
        response_format: { type: 'json_object' },
      },
      { headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' }, timeout: 12000 }
    );
    return r.data?.choices?.[0]?.message?.content || '';
  },
  groq: async ({ system, user, key }) => {
    const r = await axios.post(
      'https://api.groq.com/openai/v1/chat/completions',
      {
        model: 'llama-3.3-70b-versatile',
        messages: [
          { role: 'system', content: system },
          { role: 'user', content: user },
        ],
        temperature: 0.1,
        max_tokens: 256,
        response_format: { type: 'json_object' },
      },
      { headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' }, timeout: 12000 }
    );
    return r.data?.choices?.[0]?.message?.content || '';
  },
  gemini: async ({ system, user, key }) => {
    const r = await axios.post(
      `https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=${key}`,
      {
        contents: [
          { role: 'user', parts: [{ text: `${system}\n\n${user}` }] },
        ],
        generationConfig: {
          temperature: 0.1,
          maxOutputTokens: 256,
          responseMimeType: 'application/json',
        },
      },
      { timeout: 12000 }
    );
    const parts = r.data?.candidates?.[0]?.content?.parts || [];
    return parts.map((p) => p.text || '').join('');
  },
  deepseek: async ({ system, user, key }) => {
    const r = await axios.post(
      'https://api.deepseek.com/v1/chat/completions',
      {
        model: 'deepseek-chat',
        messages: [
          { role: 'system', content: system },
          { role: 'user', content: user },
        ],
        temperature: 0.1,
        max_tokens: 256,
        response_format: { type: 'json_object' },
      },
      { headers: { Authorization: `Bearer ${key}`, 'Content-Type': 'application/json' }, timeout: 12000 }
    );
    return r.data?.choices?.[0]?.message?.content || '';
  },
};

// Canonicalise the model's response so we can compare for "same answer"
// across providers. Strategy: parse JSON, then collapse to the canonical
// shape:
//   { "action": "<verb>" }              ← always present
//   plus any keys listed in canonicalKeys (e.g. ["target", "selector"])
// then sort keys + stringify.
//
// For atomic decisions the verb is the load-bearing field; targets vary
// in wording across providers (e.g. "first result link" vs "<a class=
// result>"). The voter ships with action-only canonical by default; the
// caller can pass canonicalKeys to vote() to widen the comparison.
function canonical(raw, canonicalKeys = []) {
  if (raw == null) return null;
  const text = String(raw).trim();
  const cleaned = text.replace(/^```json\s*/i, '').replace(/```\s*$/, '').trim();
  let obj;
  try { obj = JSON.parse(cleaned); } catch {
    const m = cleaned.match(/\{[\s\S]*\}/);
    if (!m) return null;
    try { obj = JSON.parse(m[0]); } catch { return null; }
  }
  if (!obj || typeof obj !== 'object') return null;
  // Build the canonical shape.
  const shape = {};
  if (obj.action !== undefined) shape.action = String(obj.action).toLowerCase();
  for (const k of canonicalKeys) {
    if (obj[k] !== undefined) {
      // Normalise common target casing/whitespace.
      shape[k] = String(obj[k]).trim().toLowerCase();
    }
  }
  return JSON.stringify(shape, Object.keys(shape).sort());
}

// Red-flag: structurally weird answers we reject before voting.
// - Refused-action: model said "I can't do that"
// - Hedged-action: contains "maybe" / "should" / "probably"
// - Empty action
function redFlag(raw) {
  if (!raw) return true;
  const lc = String(raw).toLowerCase();
  if (lc.includes("can't") || lc.includes('refuse') || lc.includes("don't")) return true;
  if (/\b(maybe|probably|might|could|should)\b/.test(lc)) return true;
  return false;
}

class MakerVoter {
  constructor({ env = process.env, leadBy = 3, voterCount = 5, timeoutMs = 15000 } = {}) {
    this.env = env;
    this.leadBy = leadBy;
    this.voterCount = voterCount;
    this.timeoutMs = timeoutMs;
  }

  // Build the active provider list from env keys.
  _activeProviders() {
    const out = [];
    if (this.env.CEREBRAS_API_KEY) out.push({ name: 'cerebras', fn: PROVIDERS.cerebras, key: this.env.CEREBRAS_API_KEY });
    if (this.env.MISTRAL_API_KEY) out.push({ name: 'mistral', fn: PROVIDERS.mistral, key: this.env.MISTRAL_API_KEY });
    if (this.env.GROQ_API_KEY) out.push({ name: 'groq', fn: PROVIDERS.groq, key: this.env.GROQ_API_KEY });
    if (this.env.GOOGLE_API_KEY) out.push({ name: 'gemini', fn: PROVIDERS.gemini, key: this.env.GOOGLE_API_KEY });
    if (this.env.DEEPSEEK_API_KEY) out.push({ name: 'deepseek', fn: PROVIDERS.deepseek, key: this.env.DEEPSEEK_API_KEY });
    return out.slice(0, this.voterCount);
  }

  // Fan-out k providers, return the canonical answer that leads by `leadBy`.
  // canonicalKeys widens what counts as "same answer" — pass [] for action-only
  // (default) or e.g. ["selector"] when target identity matters.
  // Returns { answer (parsed object), votes (per-provider count), latencyMs, redFlagged (count) }.
  async vote({ system, user, canonicalKeys = [] }) {
    const providers = this._activeProviders();
    if (providers.length < this.leadBy) {
      throw new Error(`MAKER voter needs ≥${this.leadBy} providers; only ${providers.length} configured`);
    }
    const startMs = Date.now();
    const tally = new Map(); // canonical -> count
    const winners = new Map(); // canonical -> raw object for return
    let redFlagged = 0;
    let resolved = false;
    let resolveOuter;
    let rejectOuter;
    const outer = new Promise((res, rej) => { resolveOuter = res; rejectOuter = rej; });

    const timer = setTimeout(() => {
      if (!resolved) {
        resolved = true;
        // Best-effort: return the highest-tally answer if any.
        if (tally.size > 0) {
          let best = null, bestCount = 0;
          for (const [k, v] of tally) if (v > bestCount) { best = k; bestCount = v; }
          resolveOuter({
            answer: JSON.parse(best),
            votes: { [JSON.parse(best).action || 'unknown']: bestCount },
            latencyMs: Date.now() - startMs,
            redFlagged,
            timedOut: true,
          });
        } else {
          rejectOuter(new Error('MAKER voter timed out with no votes'));
        }
      }
    }, this.timeoutMs);

    providers.forEach(({ name, fn, key }) => {
      fn({ system, user, key })
        .then((raw) => {
          if (resolved) return;
          if (redFlag(raw)) {
            redFlagged++;
            return;
          }
          const c = canonical(raw, canonicalKeys);
          if (!c) {
            redFlagged++;
            return;
          }
          tally.set(c, (tally.get(c) || 0) + 1);
          winners.set(c, JSON.parse(c));
          // Check lead-by-N
          for (const [cKey, count] of tally) {
            const others = [...tally.entries()].filter(([k]) => k !== cKey).map(([, v]) => v);
            const maxOther = others.length ? Math.max(...others) : 0;
            if (count - maxOther >= this.leadBy) {
              resolved = true;
              clearTimeout(timer);
              resolveOuter({
                answer: winners.get(cKey),
                votes: Object.fromEntries(tally),
                latencyMs: Date.now() - startMs,
                redFlagged,
                timedOut: false,
              });
              return;
            }
          }
        })
        .catch((e) => {
          // Provider error counts as a non-vote, not a red flag.
          if (!resolved) console.warn(`[maker_voter] ${name} error: ${e.message || e}`);
        });
    });

    return outer;
  }
}

module.exports = { MakerVoter, canonical, redFlag };
