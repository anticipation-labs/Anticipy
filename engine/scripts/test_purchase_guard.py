"""Browser-arm SAFETY-MODE money guard (regex contract).

The purchase/checkout guard is no longer always-on: it fires only in SAFETY MODE
(ANTICIPY_BROWSER_UNLOCKED=0); by default the brain decides and the hands act (see
test_browser_safety_loop.py for the in-loop flag contract). This test pins the two REGEXES the
safety-mode guard relies on so that, WHEN armed, it recognises every final-pay control/URL and
never false-stops a benign cart/navigation control:
  - PURCHASE_GUARD  — matches final-purchase button labels, not cart/nav labels;
  - CHECKOUT_URL_RE — matches checkout/payment/order-submit URLs, not safe browse/cart URLs.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_purchase_guard.py
"""
from anticipy_engine.agent.webvoyager import CHECKOUT_URL_RE, PURCHASE_GUARD

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

    print(f"PASS purchase_guard (safety-mode regex contract): {len(BLOCK)} money controls matched, "
          f"{len(ALLOW)} cart/nav controls allowed, {len(PAY_URLS)} pay URLs matched, "
          f"{len(SAFE_URLS)} safe URLs allowed")


if __name__ == "__main__":
    main()
