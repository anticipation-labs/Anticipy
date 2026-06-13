"""SiteHints test battery — webvoyager's per-host facts moved from code to data
(TARGET v8 STAGE B item 1; the P4 grep gate's target shape is ZERO retailer
hostnames in agent/*.py).

Pins (zero model calls; no network; the FakeLink is never touched):
  - SEED PARITY: data/site_hints_seed.json is byte-equal to the three deleted
    in-code tables (embedded verbatim HERE, where the recipe scan does not reach)
    — 35 hosts, search/cart/product fields, every product pattern compiled re.I.
  - HELPER PARITY: _commerce_search_url/_commerce_cart_url/_commerce_product_pattern
    behave identically through the store (www/m. subdomains, quote_plus, unknown
    host -> ""/None, host pattern AUTHORITATIVE inside _looks_buyable_product_url
    including the macys (?!review/) lookahead surviving the JSON round-trip), and
    no seed domain shadows another (the equivalence argument for the new
    exact-then-longest-suffix matching).
  - OVERLAY: a learned host resolves through the module store; per-field
    overlay-wins merge (learned cart_url overrides seed, seed search_url stays).
  - LEARN BOUNDS: facts already served by seed+overlay are NOT rewritten; invalid
    fields (off-host cart URL, search template without {q}, uncompilable regex)
    are dropped toward seed; product examples dedupe and cap at 5.
  - CORRUPT overlay fails toward the seed: .json.corrupt set-aside, lookups serve.
  - NO-PATH NO-IO: an unconfigured store (the default; every direct WebVoyagerAgent
    construction) never writes; learn() returns False.
  - WIRING: ControlCore configures <data>/site_hints.json (and configure alone
    does no IO); mock-tier BrowserHand completes a cart-shaped job WITHOUT the
    agent ever learning (mock proofs must never pollute the hint store).
  - PROOF SEAM: _learn_from_durable_proof persists the sanitized observed cart URL
    (query stripped) + visited product-page paths, and never raises.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_site_hints.py
"""
import asyncio
import json
import re
import tempfile
import urllib.parse
from pathlib import Path

from anticipy_engine.agent import site_hints, webvoyager as wv
from anticipy_engine.agent.site_hints import SiteHints
from anticipy_engine.core.envelopes import Job, JobStatus
from anticipy_engine.hands.browser_hand import BrowserHand, MODE_MOCK

SEED_FILE = Path(__file__).resolve().parents[1] / "anticipy_engine" / "data" / "site_hints_seed.json"

# ---- the three deleted webvoyager tables, VERBATIM (the one-time export's pin) ----
OLD_SEARCH = {
    "target.com": "https://www.target.com/s?searchTerm={q}",
    "walmart.com": "https://www.walmart.com/search?q={q}",
    "bestbuy.com": "https://www.bestbuy.com/site/searchpage.jsp?st={q}",
    "homedepot.com": "https://www.homedepot.com/s/{q}",
    "lowes.com": "https://www.lowes.com/search?searchTerm={q}",
    "ikea.com": "https://www.ikea.com/us/en/search/?q={q}",
    "officedepot.com": "https://www.officedepot.com/a/search/?q={q}",
    "rei.com": "https://www.rei.com/search?q={q}",
    "petsmart.com": "https://www.petsmart.com/search/?q={q}",
    "containerstore.com": "https://www.containerstore.com/s?source=form&q={q}",
    "bookshop.org": "https://bookshop.org/search?keywords={q}",
    "chewy.com": "https://www.chewy.com/s?query={q}",
    "michaels.com": "https://www.michaels.com/search?q={q}",
    "bhphotovideo.com": "https://www.bhphotovideo.com/c/search?Ntt={q}&N=0&InitialSearch=yes",
    "adorama.com": "https://www.adorama.com/l/?searchinfo={q}",
    "sweetwater.com": "https://www.sweetwater.com/store/search?s={q}",
    "lego.com": "https://www.lego.com/en-us/search?q={q}",
    "guitarcenter.com": "https://www.guitarcenter.com/search?Ntt={q}",
    "newegg.com": "https://www.newegg.com/p/pl?d={q}",
    "harborfreight.com": "https://www.harborfreight.com/search?q={q}",
    "surlatable.com": "https://www.surlatable.com/search?q={q}",
    "gamestop.com": "https://www.gamestop.com/search/?q={q}",
    "ulta.com": "https://www.ulta.com/search?search={q}",
    "wayfair.com": "https://www.wayfair.com/keyword.php?keyword={q}",
    "macys.com": "https://www.macys.com/shop/featured/{q}",
    "dickssportinggoods.com": "https://www.dickssportinggoods.com/search/SearchDisplay?searchTerm={q}",
    "kohls.com": "https://www.kohls.com/search.jsp?search={q}",
    "qvc.com": "https://www.qvc.com/catalog/psearch.html?keyword={q}",
    "worldmarket.com": "https://www.worldmarket.com/search?q={q}",
    "acehardware.com": "https://www.acehardware.com/search?query={q}",
    "thriftbooks.com": "https://www.thriftbooks.com/browse/?b.search={q}",
    "vitaminshoppe.com": "https://www.vitaminshoppe.com/search?search={q}",
    "crateandbarrel.com": "https://www.crateandbarrel.com/search?query={q}",
    "fivebelow.com": "https://www.fivebelow.com/search?q={q}",
    "dickblick.com": "https://www.dickblick.com/search/?q={q}",
}
OLD_CART = {
    "target.com": "https://www.target.com/cart",
    "walmart.com": "https://www.walmart.com/cart",
    "bestbuy.com": "https://www.bestbuy.com/cart",
    "homedepot.com": "https://www.homedepot.com/mycart/home",
    "lowes.com": "https://www.lowes.com/cart",
    "ikea.com": "https://www.ikea.com/us/en/shoppingcart/",
    "officedepot.com": "https://www.officedepot.com/cart/shoppingCart.do",
    "rei.com": "https://www.rei.com/ShoppingCart",
    "petsmart.com": "https://www.petsmart.com/cart/",
    "containerstore.com": "https://www.containerstore.com/cart/list.htm",
    "bookshop.org": "https://bookshop.org/cart",
    "chewy.com": "https://www.chewy.com/app/cart",
    "michaels.com": "https://www.michaels.com/cart",
    "bhphotovideo.com": "https://www.bhphotovideo.com/find/cart.jsp",
    "adorama.com": "https://www.adorama.com/cartview",
    "sweetwater.com": "https://www.sweetwater.com/store/cart.php",
    "lego.com": "https://www.lego.com/en-us/cart",
    "guitarcenter.com": "https://www.guitarcenter.com/cart",
    "newegg.com": "https://secure.newegg.com/shop/cart",
    "harborfreight.com": "https://www.harborfreight.com/checkout/cart",
    "surlatable.com": "https://www.surlatable.com/shopping-bag",
    "gamestop.com": "https://www.gamestop.com/cart/",
    "ulta.com": "https://www.ulta.com/bag",
    "wayfair.com": "https://www.wayfair.com/v/checkout/basket/show",
    "macys.com": "https://www.macys.com/my/bag",
    "dickssportinggoods.com": "https://www.dickssportinggoods.com/OrderItemDisplay",
    "kohls.com": "https://www.kohls.com/checkout/shopping_cart.jsp",
    "qvc.com": "https://www.qvc.com/checkout/cart.html",
    "worldmarket.com": "https://www.worldmarket.com/cart",
    "acehardware.com": "https://www.acehardware.com/cart",
    "thriftbooks.com": "https://www.thriftbooks.com/shopping-cart/",
    "vitaminshoppe.com": "https://www.vitaminshoppe.com/cart/shopping-cart",
    "crateandbarrel.com": "https://www.crateandbarrel.com/checkout/cart",
    "fivebelow.com": "https://www.fivebelow.com/cart",
    "dickblick.com": "https://www.dickblick.com/cart/",
}
OLD_PRODUCT_RE = {
    "target.com": r"/(?:p/|-/A-)",
    "walmart.com": r"/ip/",
    "bestbuy.com": r"/(?:site/.+/\d+\.p|product/[^/?#]+/[^/?#]+(?:/sku/\d+)?)(?:[/?#]|$)",
    "homedepot.com": r"/p/",
    "lowes.com": r"/pd/",
    "ikea.com": r"/p/",
    "officedepot.com": r"/a/products/",
    "rei.com": r"/product/",
    "petsmart.com": r"/(?:dog|cat|fish|bird|reptile|small-pet)/.+\.html$",
    "containerstore.com": r"/\d+d$",
    "bookshop.org": r"/(?:p/books|a/)",
    "chewy.com": r"/(?:.+/dp/|api/event/p/sar/click)",
    "michaels.com": r"/product/",
    "bhphotovideo.com": r"/c/product/[^?#]+\.html$",
    "adorama.com": r"/p/[^/?#]+$",
    "sweetwater.com": r"/store/detail/[^/?#]+$",
    "lego.com": r"/[a-z]{2}-[a-z]{2}/product/[^/?#]+$",
    "guitarcenter.com": r"/[^/?#]+/[^/?#]*\d[^/?#]*\.gc$",
    "newegg.com": r"/p/N[0-9A-Z]+$",
    "harborfreight.com": r"/[^/?#]+-\d+\.html$",
    "surlatable.com": r"/product/[^/?#]+/\d+$",
    "gamestop.com": r"/products/[^/?#]+/\d+\.html$",
    "ulta.com": r"/p/[^/?#]+",
    "wayfair.com": r"/(?:[^/?#]+/)*pdp/[^/?#]+\.html$",
    "macys.com": r"/shop/product/(?!review/)[^/?#]+",
    "dickssportinggoods.com": r"/p/[^/?#]+/[^/?#]+",
    "kohls.com": r"/product/prd-\d+/[^/?#]+\.jsp$",
    "qvc.com": r"/(?:qvc\.product|[^/?#]+\.product)\.[A-Z0-9]+\.html$",
    "worldmarket.com": r"/p/[^/?#]+-\d+\.html$",
    "acehardware.com": r"/departments/[^?#]+/\d+$",
    "thriftbooks.com": r"/w/[^?#]+/\d+/?$",
    "vitaminshoppe.com": r"/p/[^?#]+/[a-z0-9-]+$",
    "crateandbarrel.com": r"/[^/?#]+/s\d+(?:[/?#]|$)",
    "fivebelow.com": r"/products/[^/?#]+",
    "dickblick.com": r"/products/[^/?#]+/?$",
}


class FakeLink:
    """Never-touched stand-in; the battery must not need a browser."""
    connected = False

    async def send_browse(self, *a, **k):
        raise AssertionError("the hint battery must never touch a browser link")


def fresh_store(tmp: Path) -> SiteHints:
    return SiteHints(overlay_path=tmp / "site_hints.json")


def test_seed_parity():
    seed = json.loads(SEED_FILE.read_text())["hosts"]
    assert set(seed) == set(OLD_SEARCH) == set(OLD_CART) == set(OLD_PRODUCT_RE)
    assert len(seed) == 35
    for host, entry in seed.items():
        assert entry["search_url"] == OLD_SEARCH[host], host
        assert entry["cart_url"] == OLD_CART[host], host
        assert entry["product_url_re"] == OLD_PRODUCT_RE[host], host
    # no seed domain shadows another -> exact/longest-suffix matching is provably
    # equivalent to the old first-match dict iteration on every possible host
    for a in seed:
        for b in seed:
            assert a == b or not a.endswith("." + b), (a, b)
    print("PASS seed parity: 35 hosts byte-equal to the deleted in-code tables")


def test_helper_parity():
    for host in OLD_SEARCH:
        for prefix in (f"https://www.{host}", f"https://{host}", f"https://m.{host}"):
            url = prefix + "/aisle"
            q = urllib.parse.quote_plus("desk lamp 4.0")
            assert wv._commerce_search_url(url, "desk lamp 4.0") == OLD_SEARCH[host].format(q=q)
            assert wv._commerce_cart_url(url) == OLD_CART[host]
            pat = wv._commerce_product_pattern(url)
            assert pat is not None and pat.pattern == OLD_PRODUCT_RE[host]
            assert pat.flags == re.I | re.U, "the old tables compiled with exactly re.I"
    assert wv._commerce_search_url("https://www.unknown.example/x", "lamp") == ""
    assert wv._commerce_cart_url("https://www.unknown.example/x") == ""
    assert wv._commerce_product_pattern("https://www.unknown.example/x") is None
    assert wv._commerce_search_url("", "lamp") == "" and wv._commerce_cart_url("") == ""
    # host pattern is AUTHORITATIVE in _looks_buyable_product_url (no generic fallback)
    assert wv._looks_buyable_product_url("https://www.containerstore.com/123d",
                                         "https://www.containerstore.com")
    assert not wv._looks_buyable_product_url("https://www.containerstore.com/product/foo",
                                             "https://www.containerstore.com")
    assert wv._looks_buyable_product_url("https://shop.example/product/foo", "https://shop.example")
    # the macys negative lookahead survived the JSON round-trip
    assert wv._looks_buyable_product_url("https://www.macys.com/shop/product/nice-shirt",
                                         "https://www.macys.com")
    assert not wv._looks_buyable_product_url("https://www.macys.com/shop/product/review/nice-shirt",
                                             "https://www.macys.com")
    print("PASS helper parity: identical lookups through the store, unknown hosts unchanged")


def test_memory_resolved_start_page_identity():
    out = {
        "url": "https://demowebshop.tricentis.com/computing-and-internet",
        "title": "Demo Web Shop. Computing and Internet",
        "text": "Computing and Internet Price: 10.00 Add to cart",
        "elements": [
            {"idx": 0, "name": "Add to cart", "role": "input", "inView": True, "href": ""},
        ],
    }
    assert not wv._looks_buyable_product_url(out["url"], "https://demowebshop.tricentis.com"), \
        "unknown product paths should not become generally buyable URL patterns"
    assert wv._start_page_product_identity_match(out, "Computing and Internet",
                                                 "https://demowebshop.tricentis.com/computing-and-internet")
    assert not wv._start_page_product_identity_match(
        {**out, "url": "https://demowebshop.tricentis.com/search?q=Computing+and+Internet"},
        "Computing and Internet",
        "https://demowebshop.tricentis.com/computing-and-internet",
    )
    print("PASS start-page identity: memory-resolved product URL can proceed without widening URL hints")


def test_cart_link_labels():
    elements = [
        {"idx": 6, "name": "shopping cart", "role": "a", "inView": True},
        {"idx": 10, "name": "Shopping cart (2)", "role": "a", "inView": True},
    ]
    assert wv._pick_button(elements, wv.VIEW_CART_RE)["idx"] == 6
    assert wv._pick_button(elements[1:], wv.VIEW_CART_RE)["idx"] == 10
    assert wv._pick_button([{"idx": 11, "name": "Checkout", "role": "a", "inView": True}],
                           wv.VIEW_CART_RE) is None
    print("PASS cart labels: simple shopping-cart links are navigation targets, checkout is not")


def test_overlay_learn_and_merge(tmp: Path):
    hints = fresh_store(tmp)
    # learn a brand-new host (the P4 no-hints direction)
    assert hints.learn("store.test", cart_url="https://www.store.test/cart",
                       product_url_examples=["/products/wide-shoes-9"]) is True
    on_disk = json.loads((tmp / "site_hints.json").read_text())
    assert on_disk["hosts"]["store.test"]["cart_url"] == "https://www.store.test/cart"
    assert hints.cart_url("https://www.store.test/x") == "https://www.store.test/cart"
    assert hints.product_examples("https://www.store.test/x") == ["/products/wide-shoes-9"]
    site_hints.configure(tmp / "site_hints.json")
    try:
        assert wv._looks_buyable_product_url("https://www.store.test/products/wide-shoes-9",
                                             "https://www.store.test")
    finally:
        site_hints.configure(None)
    # per-field overlay-wins: learned cart_url overrides seed; seed search_url stays
    assert hints.learn("target.com", cart_url="https://www.target.com/cart/list") is True
    assert hints.cart_url("https://www.target.com/x") == "https://www.target.com/cart/list"
    assert hints.search_url("https://www.target.com/x", "lamp") == OLD_SEARCH["target.com"].format(q="lamp")
    pat = hints.product_pattern("https://www.target.com/x")
    assert pat is not None and pat.pattern == OLD_PRODUCT_RE["target.com"]
    # a fresh store over the same file sees the same facts (durability)
    again = fresh_store(tmp)
    assert again.cart_url("https://www.store.test/x") == "https://www.store.test/cart"
    assert again.cart_url("https://www.target.com/x") == "https://www.target.com/cart/list"
    print("PASS overlay: learned hosts resolve; per-field overlay-wins merge; durable")


def test_learn_bounds(tmp: Path):
    hints = fresh_store(tmp)
    # a fact already served by the seed is NOT rewritten (no overlay file appears)
    assert hints.learn("target.com", cart_url=OLD_CART["target.com"]) is False
    assert not (tmp / "site_hints.json").exists(), "seed-equal facts must not write"
    # invalid facts are refused: off-host cart, no-{q} search, junk host
    assert hints.learn("target.com", cart_url="https://evil.example/cart") is False
    assert hints.learn("target.com", search_url="https://www.target.com/s?searchTerm=lamp") is False
    assert hints.learn("not a host", cart_url="https://www.store.test/cart") is False
    assert not (tmp / "site_hints.json").exists()
    # examples dedupe and cap at 5
    assert hints.learn("store.test", product_url_examples=["/p/1", "/p/1", "/p/2"]) is True
    assert hints.learn("store.test", product_url_examples=["/p/1"]) is False, "known example must not rewrite"
    for k in range(3, 9):
        hints.learn("store.test", product_url_examples=[f"/p/{k}"])
    stored = json.loads((tmp / "site_hints.json").read_text())["hosts"]["store.test"]
    assert len(stored["product_url_examples"]) == 5, stored
    print("PASS learn bounds: seed-equal/invalid facts refused; examples dedupe + cap")


def test_overlay_validation_drops_toward_seed(tmp: Path):
    path = tmp / "site_hints.json"
    path.write_text(json.dumps({"version": 1, "hosts": {
        "target.com": {"cart_url": "https://evil.example/cart",          # off-host -> drop
                       "search_url": "https://www.target.com/s?x=1",     # no {q} -> drop
                       "product_url_re": "/(?:p/|-/A-["},                # uncompilable -> drop
        "store.test": {"cart_url": "https://www.store.test/cart"},       # valid -> kept
    }}))
    hints = fresh_store(tmp)
    assert hints.cart_url("https://www.target.com/x") == OLD_CART["target.com"], \
        "an invalid overlay field must fail toward the seed, never toward a wrong hint"
    assert hints.search_url("https://www.target.com/x", "lamp") == OLD_SEARCH["target.com"].format(q="lamp")
    assert hints.product_pattern("https://www.target.com/x").pattern == OLD_PRODUCT_RE["target.com"]
    assert hints.cart_url("https://www.store.test/x") == "https://www.store.test/cart"
    print("PASS validation: invalid overlay fields drop per-field toward the seed")


def test_corrupt_overlay_set_aside(tmp: Path):
    path = tmp / "site_hints.json"
    path.write_text("{not json at all")
    hints = fresh_store(tmp)
    assert hints.cart_url("https://www.target.com/x") == OLD_CART["target.com"]
    assert not path.exists() and path.with_suffix(".json.corrupt").exists(), \
        "the unreadable overlay must be set aside, never silently deleted"
    # learning afterwards recreates a clean overlay
    assert hints.learn("store.test", cart_url="https://www.store.test/cart") is True
    assert json.loads(path.read_text())["hosts"]["store.test"]["cart_url"] == "https://www.store.test/cart"
    print("PASS corrupt: overlay set aside as .corrupt; seed serves; relearn works")


def test_no_path_no_io(tmp: Path):
    hints = SiteHints()
    assert hints.overlay_path is None
    assert hints.cart_url("https://www.target.com/x") == OLD_CART["target.com"]
    assert hints.learn("store.test", cart_url="https://www.store.test/cart") is False
    assert list(tmp.iterdir()) == [], "no overlay path -> no IO at all"
    print("PASS no-path: seed-only lookups, learn refuses, zero files")


def test_module_wiring(tmp: Path):
    # ControlCore wires <data>/site_hints.json (import here: constructing the core
    # is the pin, not a dependency of the rest of the battery)
    from anticipy_engine.core.control_core import ControlCore
    core = ControlCore(data_dir=tmp)
    assert site_hints.store().overlay_path == tmp / "site_hints.json"
    assert not (tmp / "site_hints.json").exists(), "configure alone must do no IO"
    # mock-tier cart-shaped job completes WITHOUT the agent or the hint store running
    hand = BrowserHand(FakeLink(), mode=MODE_MOCK)
    r = asyncio.get_event_loop().run_until_complete(hand.handle(Job(intent="browse_task", args={
        "task": "On https://store.test, find wide shoes and add to the cart. Do not checkout.",
        "url": "https://store.test", "resolved_from_memory": True})))
    assert r.status == JobStatus.success and r.proof["mock"] is True
    assert not (tmp / "site_hints.json").exists(), \
        "a mock proof must NEVER write learned hints (mock never constructs the agent)"
    # webvoyager helpers read through the configured store
    site_hints.store().learn("store.test", cart_url="https://www.store.test/cart")
    assert wv._commerce_cart_url("https://www.store.test/x") == "https://www.store.test/cart"
    # drop back to seed-only for the rest of the suite/process
    site_hints.configure(None)
    assert site_hints.store().overlay_path is None
    assert wv._commerce_cart_url("https://www.store.test/x") == ""
    print("PASS wiring: ControlCore configures the overlay; mock never learns; "
          "helpers read the configured store; configure(None) restores seed-only")


def test_learn_from_durable_proof_seam(tmp: Path):
    site_hints.configure(tmp / "site_hints.json")
    try:
        agent = wv.WebVoyagerAgent(FakeLink(), gateway=None)
        states = [
            {"stage": "search", "url": "https://www.store.test/search?q=shoes", "surface_kind": "search"},
            {"stage": "product_page", "url": "https://www.store.test/products/wide-shoes-9?ref=r",
             "surface_kind": "product"},
            {"stage": "post_add", "url": "https://www.store.test/products/wide-shoes-9",
             "surface_kind": "product"},
        ]
        cart_out = {"url": "https://www.store.test/my-cart?session=abc123&junk=1"}
        agent._learn_from_durable_proof("https://www.store.test", cart_out, states)
        stored = json.loads((tmp / "site_hints.json").read_text())["hosts"]["store.test"]
        assert stored["cart_url"] == "https://www.store.test/my-cart", \
            "the observed cart URL must be sanitized to scheme+host+path"
        assert stored["product_url_examples"] == ["/products/wide-shoes-9"], \
            "visited product paths dedupe; query junk stripped"
        # never raises, even on garbage
        agent._learn_from_durable_proof("", {}, None)
        agent._learn_from_durable_proof("https://www.store.test", {"url": "::bad::"}, [{}])
    finally:
        site_hints.configure(None)
    print("PASS proof seam: durable proof persists sanitized verified facts; never raises")


def main():
    tmp = lambda: Path(tempfile.mkdtemp(prefix="anticipy-sitehints-"))
    test_seed_parity()
    test_helper_parity()
    test_memory_resolved_start_page_identity()
    test_cart_link_labels()
    test_overlay_learn_and_merge(tmp())
    test_learn_bounds(tmp())
    test_overlay_validation_drops_toward_seed(tmp())
    test_corrupt_overlay_set_aside(tmp())
    test_no_path_no_io(tmp())
    test_module_wiring(tmp())
    test_learn_from_durable_proof_seam(tmp())
    print("ALL SITE-HINTS TESTS PASSED")


if __name__ == "__main__":
    main()
