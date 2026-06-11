"""shared/storesite test — store-name -> site derivation battery.

People say "at Target" / "on Amazon", never hostnames; the derivation turns a
product-shaped memory line's single-word capitalized store name into the
<brand>.com convention, and every deny bound fails toward "" (a junk derivation
would point a real browser somewhere wrong). Deterministic; zero model calls.

Run: PYTHONPATH=engine engine/.venv/bin/python engine/scripts/test_storesite.py
"""
import sys

from anticipy_engine.shared.storesite import derive_store_site

# (memory line, expected site) — non-bank sentences on purpose.
BATTERY = [
    # ---- derivable: product-shaped line + single capitalized store name ----
    ("Was comparing ring lights at Walmart last week - liked the Neewer kit best.",
     "https://www.walmart.com"),
    ("Was looking at a cast iron pan on Etsy yesterday; the 12-inch one.",
     "https://www.etsy.com"),
    ("Was shopping for a rug at Wayfair over the weekend.",
     "https://www.wayfair.com"),
    ("Found a decent monitor arm on Newegg, the silver one.",
     "https://www.newegg.com"),
    # the store name can end the sentence (followed by punctuation, not a word)
    ("Was checking out standing desks from Costco.",
     "https://www.costco.com"),
    # ---- deny: not a product-shaped line (no shopping context verb/noun) ----
    ("Stopped at Walmart on the way home.", ""),
    ("Dropped the kids at Riverside this morning.", ""),
    # ---- deny: multi-word proper noun (next token capitalized/numeric) ----
    ("Was looking at backpacks at Lincoln Elementary for the fundraiser.", ""),
    ("Was comparing the Hoka Bondi 9 shoes for long shifts, the wide fit.", ""),
    ("Was looking at gift cards from Best Buy last week.", ""),
    # ---- deny: possessive = a person's place, not a storefront ----
    ("Was looking at rings at Bob's last weekend.", ""),
    # ---- deny: closed-class non-store capitalized words ----
    ("Was comparing flights on Friday morning.", ""),
    ("Was comparing decorations at Christmas last year.", ""),
    ("Was shopping for school supplies at School pickup.", ""),
    # ---- deny: brand follows a lowercase determiner, not the preposition ----
    ("Was looking at the DeWalt 20V kit with two batteries last week.", ""),
    ("Was comparing document cameras; settled on the IPEVO V4K as the one.", ""),
    # ---- disclosed residual: mixed/upper-case brands miss by design ----
    ("Was checking out jackets on eBay last night.", ""),
    ("Was looking at bookshelves from IKEA last week.", ""),
    # ---- never fires on empty/None-ish input ----
    ("", ""),
]


def main():
    fails = []
    for line, want in BATTERY:
        got = derive_store_site(line)
        status = "ok  " if got == want else "FAIL"
        print(f"  {status} {got or '(none)':<28} <- {line[:70]}")
        if got != want:
            fails.append((line, want, got))

    print(f"==== STORESITE: {len(BATTERY) - len(fails)}/{len(BATTERY)} ====")
    if fails:
        for line, want, got in fails:
            print(f"   - want {want!r} got {got!r}: {line}")
        sys.exit(1)
    print("==== PASS ====")


if __name__ == "__main__":
    main()
