// Symbolic postcondition verifier framework — per master prompt L5.
//
// Each skill ships a verifier(world) → "CERTIFIED" | "NOT_CERTIFIED"
// function. The world is whatever the executor extracted post-execution
// (parsed confirmation email body, calendar entry from API, sent-folder
// listing, order-page DOM). The verifier is hand-written deterministic
// JS — NO LLM calls in here. This is the only layer that is mathematically
// reliable.
//
// Pattern from VeriGuard / AgentSpec (arXiv:2510.05156, ICSE 2026): the
// verifier reads ACTUAL world state, not the agent's claim about it.

const VERIFIED = 'CERTIFIED';
const NOT_VERIFIED = 'NOT_CERTIFIED';

class VerifierRegistry {
  constructor() {
    this._byId = new Map();
  }

  register(skillId, verifyFn, compensateFn) {
    if (typeof verifyFn !== 'function') throw new Error(`verify for ${skillId} must be function`);
    this._byId.set(skillId, { verify: verifyFn, compensate: compensateFn || (async () => true) });
    return this;
  }

  verify(skillId, world) {
    const entry = this._byId.get(skillId);
    if (!entry) {
      // No verifier registered → conservative NOT_CERTIFIED. Refusing
      // to certify is always safer than rubber-stamping.
      return { verdict: NOT_VERIFIED, reason: `no_verifier_registered:${skillId}` };
    }
    try {
      const r = entry.verify(world);
      if (typeof r === 'string') return { verdict: r, reason: '' };
      if (r && typeof r.verdict === 'string') return r;
      return { verdict: NOT_VERIFIED, reason: 'verifier_returned_unrecognized_shape' };
    } catch (e) {
      return { verdict: NOT_VERIFIED, reason: `verifier_threw:${e.message || e}` };
    }
  }

  async compensate(skillId, world) {
    const entry = this._byId.get(skillId);
    if (!entry) return { ok: false, reason: `no_compensate_registered:${skillId}` };
    try {
      const r = await entry.compensate(world);
      return { ok: !!r };
    } catch (e) {
      return { ok: false, reason: `compensate_threw:${e.message || e}` };
    }
  }

  has(skillId) { return this._byId.has(skillId); }
  size() { return this._byId.size; }
  ids() { return Array.from(this._byId.keys()); }
}

// Singleton — every skill imported anywhere registers into here.
const registry = new VerifierRegistry();

module.exports = { VerifierRegistry, registry, VERIFIED, NOT_VERIFIED };
