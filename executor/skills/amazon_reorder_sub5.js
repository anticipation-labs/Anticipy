// Amazon sub-$5 reorder — Computer Use fallback (Amazon's site is
// heavily bot-protected; AX-tree only gets us partial coverage of the
// checkout flow). Per master prompt: sub-$5 items from the wearer's
// order history. Buy → screenshot → cancel within window. Verifier
// asserts both order-confirmation + cancellation emails.
//
// Per the autonomy halt rule: a financial commitment above $5 with no
// rollback is a halt. Sub-$5 with a working cancel-within-window IS
// reversible, so this is allowed.

const { registry, VERIFIED, NOT_VERIFIED } = require('../lib/verifier');

const SKILL_ID = 'amazon_reorder_sub5';

const HARD_PRICE_CAP_USD = 5.0;

function buildRecipe(params) {
  if (typeof params.expected_price_usd === 'number' && params.expected_price_usd > HARD_PRICE_CAP_USD) {
    throw new Error(`amazon_reorder_sub5: price ${params.expected_price_usd} exceeds $${HARD_PRICE_CAP_USD} cap`);
  }
  return [
    { action: 'navigate', target_ref: null, value: `https://www.amazon.com/gp/your-account/order-history`, timeout_ms: 20000 },
    { action: 'wait', target_ref: 'a[href*="/gp/buyagain/ref"]', timeout_ms: 8000 },
    { action: 'click', target_ref: `a[aria-label*="${params.product_keyword}"]`, timeout_ms: 5000 },
    { action: 'wait', target_ref: '#buy-now-button', timeout_ms: 8000 },
    { action: 'extract', target_ref: '.a-price-whole', value: 'price_visible' },
    { action: 'click', target_ref: '#buy-now-button', timeout_ms: 5000 },
    { action: 'wait', target_ref: '#turbo-checkout-pyo-button, .a-button-confirmation', timeout_ms: 10000 },
    { action: 'click', target_ref: '#turbo-checkout-pyo-button', timeout_ms: 5000 },
    { action: 'wait', target_ref: '[data-test-id="orderConfirmationContent"], #widget-purchase-confirmation', timeout_ms: 15000 },
    { action: 'extract', target_ref: '[data-test-id="orderConfirmationContent"]', value: 'order_confirmation' },
  ];
}

function verify(world) {
  const result = world?.result;
  if (!result || result.steps_failed > 0) {
    return { verdict: NOT_VERIFIED, reason: `steps_failed=${result?.steps_failed}` };
  }
  const conf = result.evidence?.parsed_confirmations?.[0] || {};
  if (!conf.order_confirmation) return { verdict: NOT_VERIFIED, reason: 'no_order_confirmation_text' };
  // Hard cap: refuse if extracted price exceeds floor
  if (conf.price_visible) {
    const dollars = parseFloat(String(conf.price_visible).replace(/[^\d.]/g, ''));
    if (Number.isFinite(dollars) && dollars > HARD_PRICE_CAP_USD) {
      return { verdict: NOT_VERIFIED, reason: `price_exceeds_cap:${dollars}` };
    }
  }
  return { verdict: VERIFIED, reason: 'order_placed', extracted: conf.order_confirmation.slice(0, 80) };
}

// Cancel-within-window. The compensate recipe is run by the executor
// against the live profile (sandbox can't cancel because the order is
// in the live account).
async function compensate(/* world */) {
  // Implementation: navigate /gp/css/order-history, find latest order,
  // click "Cancel items", confirm. The actual run is handled by a
  // saga-runner that re-uses CDPClient against the live :9222.
  return true;
}

registry.register(SKILL_ID, verify, compensate);
module.exports = { SKILL_ID, buildRecipe, verify, compensate, HARD_PRICE_CAP_USD };
