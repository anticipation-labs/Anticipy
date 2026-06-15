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

from anticipy_engine.agent.webvoyager import CHECKOUT_URL_RE, PURCHASE_GUARD, _pick_add_button, _pick_button

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

    # _pick_add_button (the commerce-recipe's SECOND auto-click path) must ALSO skip purchase
    # controls and only ever pick an add-to-cart control.
    add_els = [
        {"name": "Place your order", "role": "button", "inView": True, "idx": 0},
        {"name": "Add to cart", "role": "button", "inView": True, "idx": 1},
    ]
    picked_add = _pick_add_button(add_els, item="shoes")
    assert picked_add and picked_add.get("idx") == 1, picked_add  # skipped 'Place your order'
    # a product page whose ONLY buyable control is a final-pay button -> add nothing (never buy)
    only_buy_page = [{"name": "Buy now", "role": "button", "inView": True, "idx": 0}]
    assert _pick_add_button(only_buy_page, item="shoes") is None

    # CONTEXT-level money guard: the agent STOPS on/at a checkout/payment/order-submit URL regardless
    # of action type — closing the type+enter / navigate-to-pay / out-of-list / generic-label holes.
    PAY_URLS = [
        "https://www.amazon.com/gp/buy/spc/handlers/display.html",
        "https://www.amazon.com/checkout/p/anything",
        "https://shop.example.com/placeorder",
        "https://shop.example.com/place-order",
        "https://store.example.com/payment",
        "https://store.example.com/payment/method",
        "https://store.example.com/billing",
        "https://store.example.com/order-submit",
        "https://store.example.com/order/confirm",
        "https://m.example.com/buy/spc",
        "https://x.example.com/cart?checkout=1",
        "https://anyshopify.example.com/checkouts/c/abc123",   # Shopify hosted checkout (skeptic-found MISS)
        "https://store.example.com/checkouts",
        "https://store.example.com/order/complete",
        "https://store.example.com/place_order",
        "https://store.example.com/purchase",
        "https://store.example.com/spc",
        "https://store.example.com/order-confirmation",
        "https://store.example.com/cart?orderId=Z9",
    ]
    SAFE_URLS = [
        "https://shop.example.com/product/12345",
        "https://shop.example.com/cart",
        "https://shop.example.com/view_cart",
        "https://www.amazon.com/dp/B0XYZ",
        "https://duckduckgo.com/?q=billing+software",
        "https://shop.example.com/s?k=payment+gateway+book",
        "https://store.example.com/account/orders",
        "https://store.example.com/",
        "https://store.example.com/confirm-email",      # generic confirm, not order/checkout -> not money
        "https://store.example.com/complete-profile",
        "https://store.example.com/purchases",          # order history, not the purchase action
        "https://store.example.com/checking-account",   # 'check' but not 'checkout'
    ]
    missed_urls = [u for u in PAY_URLS if not CHECKOUT_URL_RE.search(u)]
    assert not missed_urls, f"checkout/pay URLs NOT caught (money could be spent there): {missed_urls}"
    false_url = [u for u in SAFE_URLS if CHECKOUT_URL_RE.search(u)]
    assert not false_url, f"safe URLs FALSE-stopped (cart task would stall): {false_url}"

    print(f"PASS purchase_guard: {len(BLOCK)} money controls blocked, {len(ALLOW)} cart/nav "
          "controls allowed, _pick_button skips purchase controls and never auto-selects a buy")


if __name__ == "__main__":
    main()
