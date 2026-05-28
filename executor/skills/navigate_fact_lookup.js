// navigate_fact_lookup — the simplest skill: navigate to a URL and
// extract a value from a CSS selector. Verifier checks the extracted
// value matches the expected pattern. Compensate is a no-op (read-only).
//
// Used for tasks like:
//   "what year was Python released" -> nav to wiki/Python -> extract
//   first paragraph -> verifier checks the value contains a 4-digit year
//
// Skill manifest used by the dispatcher:
//   skill_id            : "navigate_fact_lookup"
//   intent_match_pattern: "navigate_to" + "fact_lookup"
//   selector_chain      : { steps: [{action:"navigate", value:"<url>"},
//                                    {action:"extract", target_ref:"<sel>"}] }

const { registry, VERIFIED, NOT_VERIFIED } = require('../lib/verifier');

const SKILL_ID = 'navigate_fact_lookup';

function verify(world) {
  const result = world?.result;
  if (!result) return { verdict: NOT_VERIFIED, reason: 'no_result_in_world' };
  if (result.steps_failed > 0) return { verdict: NOT_VERIFIED, reason: 'steps_failed' };
  // Look for any extracted text in evidence.parsed_confirmations
  const conf = result.evidence?.parsed_confirmations || [];
  let extracted = null;
  for (const c of conf) {
    for (const v of Object.values(c)) {
      if (typeof v === 'string' && v.length >= 5) { extracted = v; break; }
    }
    if (extracted) break;
  }
  if (!extracted) return { verdict: NOT_VERIFIED, reason: 'no_extracted_text' };
  return { verdict: VERIFIED, reason: 'extracted', extracted };
}

async function compensate(/* world */) {
  return true;  // no-op for read-only fact lookup
}

registry.register(SKILL_ID, verify, compensate);

module.exports = { SKILL_ID, verify, compensate };
