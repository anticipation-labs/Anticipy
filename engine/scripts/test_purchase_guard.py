"""Browser-arm MONEY backstop (defense-in-depth on the hard stop).

Money is the only hard action stop, and the browser arm is a real path to spend it, so the
WebVoyager agent must STOP before any control that finalizes a payment — yet never false-stop
a cart/navigation control the (cart-only, no-checkout) task legitimately needs. This pins the
two places the agent consults the guard: PURCHASE_GUARD (the regex) and _pick_button (which
must skip a purchase control even when it matches the wanted pattern, webvoyager:776/846), the
same regex the click path uses to stop-for-safety (webvoyager:2189).

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_purchase_guard.py
"""
import re

from anticipy_engine.agent.webvoyager import PURCHASE_GUARD, _pick_button

# Final money-purchase controls — clicking ANY of these spends money. Must be caught.
BLOCK = [
    "Place your order", "Place order", "Buy now", "Buy Now",
    "Complete purchase", "Complete your order", "Complete checkout", "Complete payment",
    "Pay now", "Pay $49.99", "Pay 49", "Pay $1,250",
    "Finish & Pay", "Finish and pay", "Finish payment",
    "Proceed to payment",
    "Submit order", "Submit your order", "Submit payment",
    "Confirm and pay", "Confirm order", "Confirm purchase", "Confirm payment",
    "Reserve and pay", "Place bid", "Place your bid", "Subscribe and pay",
]
# Cart / navigation / generic controls — the cart task needs these; must NOT be stopped.
ALLOW = [
    "Add to cart", "Add to bag", "Add to basket", "Add to Cart",
    "Go to cart", "View cart", "View bag", "Update cart", "Update quantity",
    "Proceed to checkout", "Continue to checkout", "Continue shopping", "Checkout",
    "Submit", "Search", "Sign in", "Log in", "Apply coupon", "Save for later",
    "Pay with PayPal", "Payment method", "Save $10", "Remove", "Edit cart",
]


def main():
    missed = [n for n in BLOCK if not PURCHASE_GUARD.search(n)]
    assert not missed, f"purchase controls NOT blocked (money could be spent): {missed}"
    false_stops = [n for n in ALLOW if PURCHASE_GUARD.search(n)]
    assert not false_stops, f"cart/nav controls FALSE-stopped (task would stall): {false_stops}"

    # _pick_button must skip a purchase control even when it matches the wanted pattern —
    # so the recipe fast-path can never auto-select "Place your order".
    els = [
        {"name": "Place your order", "role": "button"},
        {"name": "Add to cart", "role": "button"},
    ]
    picked = _pick_button(els, re.compile(r"order|cart", re.I))
    assert picked and picked["name"] == "Add to cart", picked

    # if the ONLY pattern match is a purchase control, pick NOTHING (never auto-buy).
    only_buy = [{"name": "Buy now", "role": "button"}]
    assert _pick_button(only_buy, re.compile(r"buy", re.I)) is None

    print(f"PASS purchase_guard: {len(BLOCK)} money controls blocked, {len(ALLOW)} cart/nav "
          "controls allowed, _pick_button skips purchase controls and never auto-selects a buy")


if __name__ == "__main__":
    main()
