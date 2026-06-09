"""WebVoyagerAgent — a Task-State Controller around observe -> decide -> act.

General machinery for any site (no site-specific logic):
  PLAN     : the model writes an ordered subgoal checklist from the task.
  STATE    : injected tight each step (plan + current subgoal + last 5 actions
             + filtered marked elements + progress label). Older history summarized.
  PROGRESS : code labels each act PROGRESS / NO_CHANGE / REGRESSION from state deltas.
  ANTI-LOOP: code tracks visited-state signatures + action history; on STUCK it
             forbids the repeated action and nudges; 3 stuck on a subgoal -> fail it.
  COMMIT   : once a target is chosen for a subgoal, don't re-pick (kills re-search).
  AD-SKIP  : de-prioritize Sponsored/Ad elements; the judge rejects a sponsored pick.
  BUDGETS  : per-subgoal step cap + higher overall budget.
  REFLECT  : one brief why-did-that-fail, only after NO_CHANGE / REGRESSION.
  DECIDE   : low temperature + structured JSON, for run-to-run stability.
Never fakes done; genuinely blocked pages hand off; never clicks a purchase control.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import urllib.parse
from typing import List, Optional

from ..core.browser_link import BrowserLink
from ..core.envelopes import new_id
from ..core.gateway import CHEAP, SMART, ModelGateway
from .handoff import ask_message, classify_wall

PLAN_SYS = """Break the task into 3-6 ordered subgoals a browser agent completes in sequence
(e.g., reach the target page; find the target item; select it; perform the action; verify/stop).
Reply ONLY JSON: {"subgoals":["...","..."]}"""

AGENT_MAX_TOKENS = 16
ADD_CLICK_SETTLE_SECONDS = 2.0

ACT_SYS = """You control a REAL browser through a numbered set-of-marks overlay (the screenshot shows numbered boxes).
Advance the CURRENT SUBGOAL. Reply ONLY JSON:
{"thought":"one line","action":"click|type|scroll|navigate|answer","index":<int>,"text":"<for type>","enter":<true to submit>,"dir":"down|up","url":"<for navigate>","subgoal_done":<true if the current subgoal is now achieved>,"answer":"<final result, only with action=answer>"}
Rules:
- Use the shortest valid JSON. Omit unused keys and omit "thought" if space is tight.
- If SEARCH_TEXT is provided and you need to type it, use "text":"$ITEM" exactly.
- Pick a NUMBER shown on the screenshot; never invent one.
- To search: action=type on the search box's index, with text and enter=true.
- AVOID elements marked [AD] (sponsored) — prefer organic results.
- If the target isn't visible, action=scroll (dir=down) then look again.
- Obey the PROGRESS label and any STUCK note: NEVER repeat an action that caused no change; do something different.
- VERIFY, don't assume: the LAST STEP label says whether your previous action actually changed the page. If it did not, your approach was wrong — try something else.
- When stuck, change the KIND of action (scroll to reveal new options, press enter to submit, or choose a different element) — not merely a different number.
- Set subgoal_done=true the moment the CURRENT subgoal is achieved. Use action=answer only when the WHOLE task is done."""

# Real purchase-confirm controls only. NOT "submit order" (that's a generic form
# submit, e.g. demo forms) — too broad a match was false-stopping legit tasks.
PURCHASE_GUARD = re.compile(
    r"place\s+(your\s+)?order|buy\s*now|complete\s+(your\s+)?purchase|pay\s+now|confirm\s+(and\s+)?(order|purchase|pay)",
    re.I,
)
BLOCK_MARKERS = ("enter the characters you see", "type the characters", "captcha",
                 "are you a robot", "are you a human", "unusual traffic", "verify you are human",
                 "press & hold", "access denied", "checking your browser")
LOGIN_URL_RE = re.compile(r"/(?:login|signin|sign-in)(?:[/?#]|$)|[?&](?:login|signin|sign_in)\b", re.I)
COMMERCE_STOP = {
    "the", "and", "for", "with", "that", "this", "thing", "item", "product", "cart", "basket",
    "bag", "add", "added", "shipping", "pickup", "delivery", "cheapest", "lowest", "least",
    "expensive", "price", "priced", "budget", "affordable",
}
COMMERCE_SEARCH_URLS = {
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
}
COMMERCE_CART_URLS = {
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
}
ADD_TO_CART_RE = re.compile(
    r"\b(add|put)\b.{0,50}\b(cart|basket|bag)\b|"
    r"\badd\b.{0,30}\b(ship|shipping|pickup|delivery)\b|^\s*add\s+",
    re.I,
)
GENERIC_ADD_LABEL_RE = re.compile(
    r"^\s*add\s+(?:(?:this\s+)?item\s+)?(?:to\s+)?(?:cart|basket|bag)\s*"
    r"(?:(?:[^a-z0-9]+|\s+)(?:usd\s*)?\$?\s*\d{1,4}(?:[.,]\d{2})?)?\s*$|"
    r"^\s*add\s+for\s+(?:ship|shipping|pickup|delivery)\s*$",
    re.I,
)
VIEW_CART_RE = re.compile(r"\b(view|go to|open)\b.{0,30}\b(cart|basket|bag)\b|^\s*(cart|basket|bag)\s*$", re.I)
CART_URL_RE = re.compile(
    r"/(?:(?:checkout/)?cart(?:\.(?:php|html))?|cartview|shoppingcart|shopping-cart|shopping_cart\.jsp|shopping-bag|basket|bag|my/bag|"
    r"OrderItemDisplay)(?:[/?#]|$)",
    re.I,
)
REGION_US_RE = re.compile(r"^\s*(united\s+states|u\.?s\.?a?\.?)\s*$", re.I)
CART_DURABILITY_READS = max(1, int(os.environ.get("ANTICIPY_CART_DURABILITY_READS", "5")))
CART_DURABILITY_DELAY_SECONDS = max(0.0, float(os.environ.get("ANTICIPY_CART_DURABILITY_DELAY_SECONDS", "5.0")))
SEARCH_RESULTS_URL_RE = re.compile(
    r"/(?:search|s|beta-search|browse)(?:[/?#]|$)|/site/searchpage\.jsp(?:[/?#]|$)|"
    r"/keyword\.php(?:[/?#]|$)|/shop/featured(?:[/?#]|$)|"
    r"[?&](?:q|query|keyword|keywords|search|b\.search|searchTerm|searchinfo|st)=",
    re.I,
)
CONTENT_URL_RE = re.compile(
    r"/(?:rooms|ideas|how-to|inspiration|services|help|blog|article|articles|cat)(?:[/?#]|$)|"
    r"/(?:rooms|ideas|how-to|inspiration|services|help|blog|article|articles|cat)/",
    re.I,
)
COMMERCE_PRODUCT_URL_RE = {
    "target.com": re.compile(r"/(?:p/|-/A-)", re.I),
    "walmart.com": re.compile(r"/ip/", re.I),
    "bestbuy.com": re.compile(r"/(?:site/.+/\d+\.p|product/[^/?#]+/[^/?#]+(?:/sku/\d+)?)(?:[/?#]|$)", re.I),
    "homedepot.com": re.compile(r"/p/", re.I),
    "lowes.com": re.compile(r"/pd/", re.I),
    "ikea.com": re.compile(r"/p/", re.I),
    "officedepot.com": re.compile(r"/a/products/", re.I),
    "rei.com": re.compile(r"/product/", re.I),
    "petsmart.com": re.compile(r"/(?:dog|cat|fish|bird|reptile|small-pet)/.+\.html$", re.I),
    "containerstore.com": re.compile(r"/\d+d$", re.I),
    "bookshop.org": re.compile(r"/(?:p/books|a/)", re.I),
    "chewy.com": re.compile(r"/(?:.+/dp/|api/event/p/sar/click)", re.I),
    "michaels.com": re.compile(r"/product/", re.I),
    "bhphotovideo.com": re.compile(r"/c/product/[^?#]+\.html$", re.I),
    "adorama.com": re.compile(r"/p/[^/?#]+$", re.I),
    "sweetwater.com": re.compile(r"/store/detail/[^/?#]+$", re.I),
    "lego.com": re.compile(r"/[a-z]{2}-[a-z]{2}/product/[^/?#]+$", re.I),
    "guitarcenter.com": re.compile(r"/[^/?#]+/[^/?#]*\d[^/?#]*\.gc$", re.I),
    "newegg.com": re.compile(r"/p/N[0-9A-Z]+$", re.I),
    "harborfreight.com": re.compile(r"/[^/?#]+-\d+\.html$", re.I),
    "surlatable.com": re.compile(r"/product/[^/?#]+/\d+$", re.I),
    "gamestop.com": re.compile(r"/products/[^/?#]+/\d+\.html$", re.I),
    "ulta.com": re.compile(r"/p/[^/?#]+", re.I),
    "wayfair.com": re.compile(r"/(?:[^/?#]+/)*pdp/[^/?#]+\.html$", re.I),
    "macys.com": re.compile(r"/shop/product/(?!review/)[^/?#]+", re.I),
    "dickssportinggoods.com": re.compile(r"/p/[^/?#]+/[^/?#]+", re.I),
    "kohls.com": re.compile(r"/product/prd-\d+/[^/?#]+\.jsp$", re.I),
    "qvc.com": re.compile(r"/(?:qvc\.product|[^/?#]+\.product)\.[A-Z0-9]+\.html$", re.I),
    "worldmarket.com": re.compile(r"/p/[^/?#]+-\d+\.html$", re.I),
    "acehardware.com": re.compile(r"/departments/[^?#]+/\d+$", re.I),
    "thriftbooks.com": re.compile(r"/w/[^?#]+/\d+/?$", re.I),
    "vitaminshoppe.com": re.compile(r"/p/[^?#]+/[a-z0-9-]+$", re.I),
    "crateandbarrel.com": re.compile(r"/[^/?#]+/s\d+(?:[/?#]|$)", re.I),
}
PRODUCT_URL_RE = re.compile(r"/(?:product|products|p|ip|pd)(?:/|$)", re.I)
NON_PRODUCT_RE = re.compile(
    r"\b(add to|cart|basket|bag|checkout|sponsored|ad|sign in|log in|create account|"
    r"pickup|delivery|shipping|see more|show more|how-to|how to|category|"
    r"shopping list|wish list|wishlist|favorites?|registry|save for later|remove|unselect)\b",
    re.I,
)
GENERIC_PRODUCT_LABEL_RE = re.compile(
    r"^\s*(?:(?:multiple\s+)?(?:product\s+)?options(?:\s+available)?|"
    r"(?:choose|select|see|show|view|more)\s+(?:product\s+)?options|"
    r"shop\s+now|view\s+details|product\s+image)\s*$",
    re.I,
)
HREF_ONLY_RE = re.compile(r"^(?:https?://\S+|/[^\s]+)$", re.I)
PRODUCT_VARIANT_WORDS = {
    "bundle",
    "calendar",
    "cfexpress",
    "compactflash",
    "companion",
    "edition",
    "guide",
    "kid",
    "kids",
    "kit",
    "micro",
    "microsd",
    "microsdxc",
    "pack",
    "summary",
    "workbook",
}


def _is_generic_product_label(name: str) -> bool:
    normalized = re.sub(r"\s+", " ", name or "").strip()
    return GENERIC_PRODUCT_LABEL_RE.match(normalized) is not None


def _parse_json(raw: str) -> Optional[dict]:
    if not raw:
        return None
    s = re.sub(r"```(json)?", "", raw).strip()
    try:
        return json.loads(s)
    except Exception:
        pass
    start = s.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(s)):
        if s[i] == "{":
            depth += 1
        elif s[i] == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(s[start:i + 1])
                except Exception:
                    return None
    return None


async def _think(gw: ModelGateway, task: str, tier: str, caller: str, image: Optional[str] = None,
                 json_mode: bool = False, temperature: Optional[float] = None,
                 max_tokens: Optional[int] = None) -> str:
    try:
        return await gw.think(task, tier=tier, caller=caller, image=image, json_mode=json_mode,
                              temperature=temperature, max_tokens=max_tokens)
    except TypeError as exc:
        if "max_tokens" not in str(exc):
            raise
        return await gw.think(task, tier=tier, caller=caller, image=image, json_mode=json_mode,
                              temperature=temperature)


def _clean_action(a: dict, item_text: str = "") -> dict:
    out = {"action": a.get("action")}
    for k in ("index", "text", "url", "dir", "enter"):
        if k in a and a[k] is not None:
            out[k] = item_text if k == "text" and str(a[k]).strip() in {"$ITEM", "<ITEM>"} else a[k]
    return out


VAGUE_ITEM_RE = re.compile(
    r"\b(earlier|looked at|looking at|that\s+(thing|one|item|product)|"
    r"this\s+(thing|one|item|product)|the\s+(thing|one|item|product)|"
    r"the\s+one|that\s+one|the\s+item|the\s+product)\b",
    re.I,
)
SITE_TAIL_RE = re.compile(
    r"\s+\b(?:on|from|at)\s+(?:https?://\S+|www\.\S+|[a-z0-9.-]+\.[a-z]{2,})(?:\s.*)?$",
    re.I,
)


def _usable_item(raw: str) -> str:
    item = re.sub(r"\s+", " ", raw or "").strip(" \"'.,:;-")
    item = SITE_TAIL_RE.sub("", item).strip(" \"'.,:;-")
    item = re.sub(r"^(?:please\s+)?(?:a|an|the|my|your)\s+", "", item, flags=re.I).strip()
    item = re.sub(
        r"^(?:cheapest|lowest(?:\s+priced|\s+price)?|least\s+expensive|budget|affordable)\s+",
        "",
        item,
        flags=re.I,
    ).strip()
    if not item or VAGUE_ITEM_RE.search(item):
        return ""
    toks = _item_tokens(item)
    if len(toks) < 1 or all(tok in COMMERCE_STOP for tok in toks):
        return ""
    if len(toks) == 1 and toks[0] in {"one", "thing", "item", "product", "stuff"}:
        return ""
    return item if 3 <= len(item) <= 180 else ""


def _search_text(task: str) -> str:
    patterns = (
        r"\bfind\s+(?P<item>.+?)\s+and\s+add\b",
        r"\bsearch\s+for\s+(?P<item>.+?)\b(?:and|then|$)",
        r"\b(?:add|put)\s+(?P<item>.+?)\s+(?:to|in)\s+(?:my\s+|your\s+|the\s+)?(?:cart|basket|bag)\b",
        r"\b(?:grab|get|snag)\s+(?P<item>.+?)\s+and\s+(?:add|put)\b",
    )
    for pat in patterns:
        m = re.search(pat, task or "", re.I)
        if m:
            item = _usable_item(m.group("item"))
            if item:
                return item
    return ""


def _host(url: str) -> str:
    try:
        host = urllib.parse.urlparse(url or "").netloc.lower()
    except Exception:
        return ""
    return host[4:] if host.startswith("www.") else host


def _commerce_search_url(start_url: str, item: str) -> str:
    host = _host(start_url)
    q = urllib.parse.quote_plus(item)
    for domain, template in COMMERCE_SEARCH_URLS.items():
        if host == domain or host.endswith("." + domain):
            return template.format(q=q)
    return ""


def _commerce_cart_url(start_url: str) -> str:
    host = _host(start_url)
    for domain, url in COMMERCE_CART_URLS.items():
        if host == domain or host.endswith("." + domain):
            return url
    return ""


def _looks_search_results_url(url: str) -> bool:
    return SEARCH_RESULTS_URL_RE.search(url or "") is not None


def _looks_content_url(url: str) -> bool:
    return CONTENT_URL_RE.search(url or "") is not None


def _same_site(start_url: str, candidate_url: str) -> bool:
    start_host = _host(start_url)
    candidate_host = _host(candidate_url)
    if not start_host or not candidate_host:
        return True
    return (
        start_host == candidate_host
        or start_host.endswith("." + candidate_host)
        or candidate_host.endswith("." + start_host)
    )


def _commerce_product_pattern(start_url: str) -> Optional[re.Pattern]:
    start_host = _host(start_url)
    for domain, pattern in COMMERCE_PRODUCT_URL_RE.items():
        if start_host == domain or start_host.endswith("." + domain):
            return pattern
    return None


def _looks_buyable_product_url(url: str, start_url: str = "") -> bool:
    absolute = _absolute_site_url(start_url, url) if start_url else (url or "")
    if not absolute or not _same_site(start_url, absolute):
        return False
    parsed = urllib.parse.urlparse(absolute)
    if re.search(r"\b(review|reviews|qa|q-and-a|ask-question)\b", parsed.fragment or "", re.I):
        return False
    if re.search(r"/(?:cart|basket|bag|checkout|login|signin|sign-in)(?:[/?#]|$)", absolute, re.I):
        return False
    pattern = _commerce_product_pattern(start_url or absolute)
    if pattern is not None:
        if pattern.search(parsed.path) is not None:
            return True
        return False
    if _looks_search_results_url(absolute) or _looks_content_url(absolute):
        return False
    return PRODUCT_URL_RE.search(parsed.path) is not None


def _absolute_site_url(start_url: str, href: str) -> str:
    href = (href or "").strip()
    if not href:
        return ""
    if href.startswith("http://") or href.startswith("https://"):
        return href
    parsed = urllib.parse.urlparse(start_url or "")
    origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else ""
    return urllib.parse.urljoin(origin + "/", href.lstrip("/")) if origin else ""


def _product_url_near_index(
    elements: list[dict],
    item: str,
    target_idx: int,
    start_url: str,
    *,
    before: int = 8,
    after: int = 2,
) -> str:
    tokens = _item_tokens(item)
    if not tokens:
        return ""
    required = _required_product_hits(tokens)
    target_el = None
    for el in elements or []:
        try:
            if int(el.get("idx")) == target_idx:
                target_el = el
                break
        except Exception:
            continue
    target_order = _element_order(target_el) if target_el else target_idx
    nearby = []
    for el in elements or []:
        try:
            idx = int(el.get("idx"))
        except Exception:
            continue
        order = _element_order(el)
        if order > target_order + after or target_order - order > before:
            continue
        name = (el.get("name") or "").strip()
        href = (el.get("href") or "").strip()
        if not href and HREF_ONLY_RE.match(name):
            href = name
        if not href:
            continue
        if _is_generic_product_label(name):
            continue
        absolute = _absolute_site_url(start_url, href)
        if not _looks_buyable_product_url(absolute, start_url):
            continue
        hay = f"{name} {href}"
        if not _numbers_match(hay, item):
            continue
        hits = _token_hits(hay, tokens)
        if not _has_distinctive_required_tokens(hay, tokens):
            continue
        if hits < required:
            continue
        nearby.append((order, hits, 1 if _looks_buyable_product_url(absolute, start_url) else 0, href))
    if not nearby:
        return ""
    _, _, _, href = max(nearby, key=lambda row: (row[2], row[1], row[0]))
    return _absolute_site_url(start_url, href)


def _product_url_near_add(elements: list[dict], item: str, add_idx: int, start_url: str) -> str:
    return _product_url_near_index(elements, item, add_idx, start_url, before=8, after=0)


def _pick_adjacent_result_add(
    elements: list[dict],
    product: dict,
    item: str,
    start_url: str,
) -> Optional[dict]:
    tokens = _item_tokens(item)
    if not tokens:
        return None
    try:
        product_idx = int(product.get("idx"))
    except Exception:
        return None
    product_order = _element_order(product)
    product_name = (product.get("name") or "").strip()
    product_href = _absolute_site_url(start_url, product.get("href") or "")
    if product_href and not _looks_buyable_product_url(product_href, start_url):
        return None
    required = _required_product_hits(tokens)
    product_identity = f"{product_name} {product_href}"
    if not _has_distinctive_required_tokens(product_identity, tokens):
        return None
    if _token_hits(product_identity, tokens) < required:
        return None

    for el in sorted(elements or [], key=_element_order):
        try:
            idx = int(el.get("idx"))
        except Exception:
            continue
        order = _element_order(el)
        if order <= product_order:
            continue
        if order > product_order + 10:
            break
        href = _absolute_site_url(start_url, el.get("href") or "")
        if href and href != product_href and _looks_buyable_product_url(href, start_url):
            if order > product_order + 1 and _token_hits(el.get("name") or "", tokens) >= required:
                break
        add = _pick_add_button([el], item, allow_generic=True)
        if add:
            return add
    return None


def _element_order(el: Optional[dict]) -> int:
    if not el:
        return 0
    for key in ("docIndex", "documentIndex", "sourceIndex", "idx"):
        try:
            return int(el.get(key))
        except Exception:
            continue
    return 0


def _item_tokens(text: str) -> list[str]:
    toks = re.findall(r"\d+(?:\.\d+)?|[a-z0-9]+", (text or "").lower())
    keep = []
    for tok in toks:
        if tok in COMMERCE_STOP:
            continue
        if re.fullmatch(r"\d+(?:\.\d+)?", tok) or len(tok) >= 3 or tok in {"oz", "ml", "qt", "lb"}:
            keep.append(tok)
    return keep


def _number_tokens(text: str) -> list[str]:
    return re.findall(r"\d+(?:\.\d+)?", (text or "").lower())


def _quantity_pairs(text: str) -> list[tuple[str, str]]:
    units = {
        "ounce": "oz", "ounces": "oz", "oz": "oz",
        "cup": "cup", "cups": "cup",
        "count": "ct", "counts": "ct", "ct": "ct",
        "quart": "qt", "quarts": "qt", "qt": "qt",
        "milliliter": "ml", "milliliters": "ml", "ml": "ml",
        "pound": "lb", "pounds": "lb", "lb": "lb",
        "gallon": "gal", "gallons": "gal", "gal": "gal",
    }
    out = []
    for m in re.finditer(
        r"(?P<num>\d+(?:\.\d+)?)[\s-]*(?:fl[\s-]*)?"
        r"(?P<unit>ounces?|oz|cups?|counts?|ct|quarts?|qt|milliliters?|ml|pounds?|lb|gallons?|gal)\b",
        (text or "").lower(),
    ):
        out.append((m.group("num"), units.get(m.group("unit"), m.group("unit"))))
    return out


def _numbers_match(candidate: str, item: str) -> bool:
    nums = _number_tokens(item)
    if not nums:
        return True
    item_pairs = _quantity_pairs(item)
    if item_pairs:
        candidate_pairs = set(_quantity_pairs(candidate))
        return all(pair in candidate_pairs for pair in item_pairs)
    hay = " " + re.sub(r"[^a-z0-9.]+", " ", (candidate or "").lower()) + " "
    return all(re.search(rf"(?<!\d){re.escape(num)}(?!\d)", hay) for num in nums)


def _word_matches_token(word: str, tok: str) -> bool:
    if re.fullmatch(r"\d+(?:\.\d+)?", tok):
        return re.match(rf"{re.escape(tok)}(?!\d)", word or "") is not None
    if word == tok or (len(tok) >= 5 and tok in (word or "")):
        return True
    return len(tok) >= 4 and ((word or "").startswith(tok) or (word or "").endswith(tok))


def _token_hits(name: str, tokens: list[str]) -> int:
    words = re.findall(r"[a-z0-9.]+", (name or "").lower())
    hits = 0
    for tok in tokens:
        if any(_word_matches_token(word, tok) for word in words):
            hits += 1
    return hits


def _ordered_item_score(name: str, tokens: list[str]) -> int:
    if not name or len(tokens) < 2:
        return 0
    words = re.findall(r"[a-z0-9.]+", (name or "").lower())
    positions = []
    start_at = 0
    for tok in tokens:
        found = None
        for idx in range(start_at, len(words)):
            if _word_matches_token(words[idx], tok):
                found = idx
                break
        if found is None:
            return 0
        positions.append(found)
        start_at = found + 1
    span = positions[-1] - positions[0] + 1
    score = len(tokens) * 2 + max(0, len(tokens) * 3 - span)
    if span == len(tokens):
        score += 8
    return score


def _unrequested_variant_penalty(name: str, tokens: list[str]) -> int:
    token_set = set(tokens)
    words = set(re.findall(r"[a-z0-9]+", (name or "").lower()))
    return 16 * sum(1 for word in PRODUCT_VARIANT_WORDS if word in words and word not in token_set)


def _compact_visible_product_match(name: str, tokens: list[str]) -> bool:
    if not name or len(tokens) < 3:
        return False
    visible_hits = [tok for tok in tokens if _token_hits(name, [tok])]
    if len(visible_hits) < 2:
        return False
    return _ordered_item_score(name, visible_hits) > 0


def _search_result_identity_ok(name: str, href: str, item: str, tokens: list[str], required: int) -> bool:
    hay = f"{name} {href}"
    if not _numbers_match(hay, item):
        return False
    name_hits = _token_hits(name, tokens)
    if _has_distinctive_required_tokens(hay, tokens) and name_hits >= required:
        return True
    if not href or not _compact_visible_product_match(name, tokens):
        return False
    if _number_tokens(item) and name_hits >= 2:
        return True
    return _token_hits(hay, tokens) >= required


def _required_product_hits(tokens: list[str]) -> int:
    n = len(tokens)
    if n <= 2:
        return n
    if n >= 5:
        return max(4, int(n * 0.8 + 0.999))
    return max(2, int(n * 0.6 + 0.999))


def _distinctive_required_tokens(tokens: list[str]) -> list[str]:
    if len(tokens) < 4:
        return []
    return tokens[:2]


def _has_distinctive_required_tokens(text: str, tokens: list[str]) -> bool:
    required = _distinctive_required_tokens(tokens)
    if not required:
        return True
    return _token_hits(text, required) == len(required)


def _price_cents(text: str) -> Optional[int]:
    prices = []
    for m in re.finditer(r"(?:[$]|usd\s*)\s*(?P<dollars>\d{1,4})(?:[,.](?P<cents>\d{2}))?", text or "", re.I):
        prior = (text or "")[max(0, m.start() - 16):m.start()].lower()
        if re.search(r"\b(save|coupon|rebate|discount|off)\b", prior):
            continue
        prices.append(int(m.group("dollars")) * 100 + int(m.group("cents") or "0"))
    return min(prices) if prices else None


def _wants_lowest_price(text: str) -> bool:
    return re.search(r"\b(cheapest|lowest(?:\s+priced|\s+price)?|least\s+expensive|budget|affordable)\b",
                     text or "", re.I) is not None


CONTEXT_HINTS_RE = re.compile(r"\b(?:memory\s+)?context\s+hints?\s*:\s*(?P<hints>[^.]+)", re.I)


def _context_hint_tokens(task: str, item: str = "") -> list[str]:
    m = CONTEXT_HINTS_RE.search(task or "")
    if not m:
        return []
    item_tokens = set(_item_tokens(item))
    hints = []
    for tok in _item_tokens(m.group("hints") or ""):
        if tok in item_tokens or tok in hints:
            continue
        hints.append(tok)
    return hints[:6]


def _pick_product(
    elements: list[dict],
    item: str,
    prefer_lowest: bool = False,
    start_url: str = "",
    context_hints: Optional[list[str]] = None,
    allow_query_fallback: bool = False,
) -> Optional[dict]:
    tokens = _item_tokens(item)
    if not tokens:
        return None
    required = _required_product_hits(tokens)
    context_hints = context_hints or []
    candidates = []
    for el in elements or []:
        name = (el.get("name") or "").strip()
        href = (el.get("href") or "").strip()
        if (not name or el.get("sponsored") or HREF_ONLY_RE.match(name)
                or _is_generic_product_label(name)
                or NON_PRODUCT_RE.search(name)):
            continue
        productish_url = bool(href and _looks_buyable_product_url(href, start_url or href))
        if href and not productish_url:
            continue
        role = (el.get("role") or "").lower()
        if role not in {"a", "button"} and "link" not in role:
            continue
        if not href and "link" not in role and role != "a":
            continue
        if not _search_result_identity_ok(name, href, item, tokens, required):
            continue
        hits = max(_token_hits(name, tokens), _token_hits(f"{name} {href}", tokens) - 1)
        hint_hits = _token_hits(f"{name} {href}", context_hints)
        ordered_score = _ordered_item_score(name, tokens)
        variant_penalty = _unrequested_variant_penalty(name, tokens)
        score = (
            hits * 3
            + ordered_score
            + hint_hits * 5
            + (4 if productish_url else 0)
            + (2 if el.get("inView") else 0)
            - variant_penalty
        )
        candidates.append((_price_cents(name), hint_hits, score, el))
    if not candidates and allow_query_fallback:
        seen_hrefs: set[str] = set()
        for pos, el in enumerate(elements or []):
            name = (el.get("name") or "").strip()
            href = (el.get("href") or "").strip()
            if (not name or el.get("sponsored") or HREF_ONLY_RE.match(name)
                    or _is_generic_product_label(name) or NON_PRODUCT_RE.search(name)
                    or not _numbers_match(f"{name} {href}", item)):
                continue
            productish_url = bool(href and _looks_buyable_product_url(href, start_url or href))
            if not productish_url or href in seen_hrefs:
                continue
            role = (el.get("role") or "").lower()
            if role not in {"a", "button"} and "link" not in role:
                continue
            hay = f"{name} {href}"
            hits = _token_hits(hay, tokens)
            if (not _has_distinctive_required_tokens(hay, tokens)
                    and not _compact_visible_product_match(name, tokens)):
                continue
            if len(tokens) >= 4 and hits < required:
                continue
            seen_hrefs.add(href)
            hint_hits = _token_hits(f"{name} {href}", context_hints)
            ordered_score = _ordered_item_score(name, tokens)
            variant_penalty = _unrequested_variant_penalty(name, tokens)
            score = (
                ordered_score
                + hint_hits * 5
                + (2 if el.get("inView") else 0)
                - pos / 1000
                - variant_penalty
            )
            candidates.append((_price_cents(name), hint_hits, score, el))
    if not candidates:
        return None
    pool = candidates
    if prefer_lowest:
        priced = [c for c in pool if c[0] is not None]
        if priced:
            return min(priced, key=lambda c: (c[0], -c[2], -c[1]))[3]
    return max(pool, key=lambda c: (c[2], c[1]))[3]


def _pick_button(elements: list[dict], pattern: re.Pattern) -> Optional[dict]:
    for el in elements or []:
        name = (el.get("name") or "").strip()
        if not name or el.get("sponsored") or PURCHASE_GUARD.search(name):
            continue
        role = (el.get("role") or "").lower()
        if role not in {"button", "a", "input"} and "button" not in role and "link" not in role and "search" not in role:
            continue
        if pattern.search(name):
            return el
    return None


def _pick_region_button(elements: list[dict]) -> Optional[dict]:
    has_country_choices = any(
        re.fullmatch(r"\s*(canada|united\s+states|u\.?s\.?a?\.?)\s*", (el.get("name") or ""), re.I)
        for el in elements or []
    )
    if not has_country_choices:
        return None
    return _pick_button(elements, REGION_US_RE)


def _generic_add_points_at_unrelated_product(
    elements: list[dict],
    add_idx: int,
    item: str,
    start_url: str,
) -> bool:
    if not start_url:
        return False
    tokens = _item_tokens(item)
    if not tokens:
        return False
    required = _required_product_hits(tokens)
    add_el = None
    for el in elements or []:
        try:
            if int(el.get("idx")) == add_idx:
                add_el = el
                break
        except Exception:
            continue
    add_order = _element_order(add_el) if add_el else add_idx
    for el in sorted(elements or [], key=_element_order):
        try:
            idx = int(el.get("idx"))
        except Exception:
            continue
        order = _element_order(el)
        if order <= add_order or order > add_order + 12:
            continue
        href = _absolute_site_url(start_url, el.get("href") or "")
        if not href or not _looks_buyable_product_url(href, start_url):
            continue
        identity = f"{el.get('name') or ''} {href}"
        if _token_hits(identity, tokens) >= required and _has_distinctive_required_tokens(identity, tokens):
            return False
        return True
    return False


def _pick_add_button(
    elements: list[dict],
    item: str,
    allow_generic: bool = True,
    skip_names: Optional[set[str]] = None,
    start_url: str = "",
) -> Optional[dict]:
    item_tokens = _item_tokens(item)
    skip_names = skip_names or set()
    for el in elements or []:
        name = (el.get("name") or "").strip()
        if not name or el.get("sponsored") or PURCHASE_GUARD.search(name):
            continue
        if name.lower() in skip_names:
            continue
        if el.get("inView") is False:
            continue
        if re.search(r"\b(add to list|registry|wish list|favorite)\b", name, re.I):
            continue
        if not ADD_TO_CART_RE.search(name):
            continue
        # If the real site exposes a variant number in the add control, it must
        # match the remembered item. Generic "Add to cart" controls are allowed.
        if _number_tokens(name) and not _numbers_match(name, item):
            continue
        generic = GENERIC_ADD_LABEL_RE.match(name) is not None
        if generic and not allow_generic:
            continue
        try:
            idx = int(el.get("idx"))
        except Exception:
            idx = -1
        if generic and idx >= 0 and _generic_add_points_at_unrelated_product(elements, idx, item, start_url):
            continue
        if not generic:
            hits = _token_hits(name, item_tokens)
            required = _required_product_hits(item_tokens)
            if hits < required:
                continue
        role = (el.get("role") or "").lower()
        if role not in {"button", "a", "input"} and "button" not in role and "link" not in role:
            continue
        return el
    return None


CART_MARKER_RE = re.compile(
    r"added\s+to\s+(?:cart|bag|basket)|item\s+added|in\s+your\s+(?:cart|bag|basket)|"
    r"\b[1-9]\d*\s+in\s+(?:cart|basket|bag)\b|"
    r"\b(?:shopping\s+)?(?:cart|bag|basket),?\s*[1-9]\d*\s+items?\b|"
    r"\b(?:cart|bag|basket)\s+with\s+[1-9]\d*\s+items?\b",
    re.I,
)
POST_CART_NOISE_RE = re.compile(
    r"\b(recommend(?:ed|ations?)?|you\s+may\s+also\s+like|similar\s+items?|sponsored|"
    r"related\s+items?|more\s+to\s+consider|order\s+summary|continue\s+to\s+checkout|"
    r"everyday\s+essentials\s+for\s+you)\b",
    re.I,
)
PRODUCT_IDENTITY_NOISE_RE = re.compile(
    r"\b(recommend(?:ed|ations?)?|you\s+may\s+also\s+like|similar\s+items?|sponsored|"
    r"related\s+items?|more\s+to\s+consider|customers?\s+also|frequently\s+bought|"
    r"review(?:s|ed)?|ratings?|questions?\s+and\s+answers?)\b",
    re.I,
)
CART_COUNT_RE = re.compile(
    r"\b(?:shopping\s+)?(?:cart|bag|basket),?\s*(?:with\s+)?(\d+)\s+items?\b|"
    r"\b(\d+)\s+(?:items?\s+)?in\s+(?:your\s+)?(?:cart|bag|basket)\b|"
    r"\b(?:cart|bag|basket)\s*\((\d+)\)",
    re.I,
)
CART_STRUCTURE_RE = re.compile(
    r"\b(checkout|order\s+summary|subtotal|estimated\s+total|cart\s+summary|"
    r"quantity|qty|remove|save\s+for\s+later|shipping|pickup|delivery)\b",
    re.I,
)
CART_ITEM_STRUCTURE_RE = re.compile(r"\b(quantity|qty|remove|save\s+for\s+later)\b", re.I)
CART_ITEM_QUANTITY_RE = re.compile(
    r"\b(?:qty|quantity)\s*(?:[:#-]\s*)?(?P<qty>\d{1,3})\b|"
    r"\b(?P<qty2>\d{1,3})\s+(?:qty|quantity)\b",
    re.I,
)


def _cart_count(out: dict) -> Optional[int]:
    text = (out or {}).get("text") or ""
    for marker in CART_COUNT_RE.finditer(text):
        for value in marker.groups():
            if value is not None:
                try:
                    return int(value)
                except ValueError:
                    return None
    return None


def _primary_cart_text(text: str) -> str:
    return POST_CART_NOISE_RE.split(text or "", maxsplit=1)[0]


def _cart_item_windows(text: str, item: str) -> list[dict]:
    tokens = _item_tokens(item)
    if not tokens:
        return []
    required = _required_product_hits(tokens)
    cart_text = _primary_cart_text(text or "")
    spans: list[tuple[int, int]] = []
    for tok in tokens:
        pattern = re.compile(rf"(?<![a-z0-9]){re.escape(tok)}(?![a-z0-9])", re.I)
        for match in pattern.finditer(cart_text):
            start = max(0, match.start() - 120)
            end = min(len(cart_text), match.end() + 220)
            spans.append((start, end))
    if not spans:
        return []
    spans.sort()
    merged_spans: list[tuple[int, int]] = []
    for start, end in spans:
        if not merged_spans or start > merged_spans[-1][1] + 24:
            merged_spans.append((start, end))
        else:
            prev_start, prev_end = merged_spans[-1]
            merged_spans[-1] = (prev_start, max(prev_end, end))

    windows: list[dict] = []
    for start, end in merged_spans:
        window = cart_text[start:end]
        if not _numbers_match(window, item):
            continue
        hits = _token_hits(window, tokens)
        if hits < required:
            continue
        quantity = None
        qty_match = CART_ITEM_QUANTITY_RE.search(window)
        if qty_match:
            raw_qty = qty_match.group("qty") or qty_match.group("qty2")
            try:
                quantity = int(raw_qty)
            except (TypeError, ValueError):
                quantity = None
        local_structure = CART_ITEM_STRUCTURE_RE.search(window) is not None
        windows.append(
            {
                "token_hits": hits,
                "required_hits": required,
                "quantity": quantity,
                "local_structure": local_structure,
            }
        )
    windows.sort(
        key=lambda row: (row["local_structure"], row["quantity"] is not None, row["token_hits"]),
        reverse=True,
    )
    return windows


def _cart_item_evidence(out: dict, item: str) -> dict:
    windows = _cart_item_windows((out or {}).get("text") or "", item)
    best = windows[0] if windows else {}
    required = _required_product_hits(_item_tokens(item)) if _item_tokens(item) else 0
    return {
        "matched": bool(windows),
        "window_count": len(windows),
        "token_hits": int(best.get("token_hits") or 0),
        "required_hits": int(best.get("required_hits") or required),
        "quantity": best.get("quantity") if isinstance(best.get("quantity"), int) else None,
        "local_structure": bool(best.get("local_structure")),
    }


def _cart_element_item_evidence(out: dict, item: str) -> dict:
    tokens = _item_tokens(item)
    required = _required_product_hits(tokens) if tokens else 0
    url = (out or {}).get("url") or ""
    if not tokens or CART_URL_RE.search(url) is None:
        return {"matched": False, "token_hits": 0, "required_hits": required, "element_index": None}

    text = (out or {}).get("text") or ""
    empty = re.search(r"\b(?:cart|bag|basket)\s+is\s+empty\b|\byour\s+(?:cart|bag|basket)\s+is\s+empty\b", text, re.I)
    if empty:
        token_positions = [
            match.start()
            for tok in tokens
            for match in re.finditer(rf"(?<![a-z0-9]){re.escape(tok)}(?![a-z0-9])", text, re.I)
        ]
        if not token_positions or empty.start() < min(token_positions):
            return {"matched": False, "token_hits": 0, "required_hits": required, "element_index": None}

    elements = (out or {}).get("elements") or []
    for pos, el in enumerate(elements):
        if pos >= 18:
            break
        name = (el.get("name") or "").strip()
        href = (el.get("href") or "").strip()
        if not name or not href:
            continue
        if _is_generic_product_label(name) or NON_PRODUCT_RE.search(name):
            continue
        if not _looks_buyable_product_url(href, url):
            continue
        hay = f"{name} {href}"
        if not _numbers_match(hay, item):
            continue
        hits = max(_token_hits(name, tokens), _token_hits(hay, tokens) - 1)
        if hits < required or not _has_distinctive_required_tokens(hay, tokens):
            continue
        nearby_names = " ".join(
            (nearby.get("name") or "") for nearby in elements[max(0, pos - 8):pos + 4]
        )
        nearby_cart_item_structure = CART_ITEM_STRUCTURE_RE.search(nearby_names) is not None
        if _price_cents(name) is None and pos > 4 and not nearby_cart_item_structure:
            continue
        return {
            "matched": True,
            "token_hits": hits,
            "required_hits": required,
            "element_index": pos,
        }
    return {"matched": False, "token_hits": 0, "required_hits": required, "element_index": None}


def _cart_marker_item_match(text: str, item: str) -> bool:
    tokens = _item_tokens(item)
    if not tokens:
        return False
    for marker in CART_MARKER_RE.finditer(text or ""):
        start = max(0, marker.start() - 360)
        end = min(len(text or ""), marker.end() + 520)
        window = POST_CART_NOISE_RE.split((text or "")[start:end], maxsplit=1)[0]
        if not _numbers_match(window, item):
            continue
        hits = _token_hits(window, tokens)
        if hits >= (2 if len(tokens) >= 3 else 1):
            return True
    return False


def _cart_verified(out: dict, item: str) -> bool:
    text = (out or {}).get("text") or ""
    low = text.lower()
    url = ((out or {}).get("url") or "").lower()
    added = CART_MARKER_RE.search(low) is not None
    cart_url = CART_URL_RE.search(url) is not None
    count = _cart_count(out)
    tokens = _item_tokens(item)
    if count == 0:
        return False
    if not (added or cart_url) or not tokens:
        return False
    element_evidence = _cart_element_item_evidence(out, item)
    if cart_url and element_evidence["matched"]:
        return True
    if cart_url and not CART_STRUCTURE_RE.search(text):
        return False
    if added and not cart_url:
        return _cart_marker_item_match(text, item)
    evidence = _cart_item_evidence(out, item)
    if cart_url:
        return bool(evidence["matched"] and evidence["local_structure"])
    return bool(evidence["matched"])


def _is_cart_url(out: dict) -> bool:
    return CART_URL_RE.search(((out or {}).get("url") or "").lower()) is not None


def _cart_page_verified(out: dict, item: str) -> bool:
    return _is_cart_url(out) and _cart_verified(out, item)


def _cart_signal_score(out: dict, item: str) -> int:
    text = (out or {}).get("text") or ""
    url = ((out or {}).get("url") or "").lower()
    score = 0
    count = _cart_count(out)
    item_evidence = _cart_item_evidence(out, item)
    element_evidence = _cart_element_item_evidence(out, item)
    if CART_URL_RE.search(url):
        score += 20
    if CART_MARKER_RE.search(text):
        score += 30
    if _cart_marker_item_match(text, item):
        score += 60
    if _cart_verified(out, item):
        score += 120
    if item_evidence["matched"] and (not CART_URL_RE.search(url) or item_evidence["local_structure"]):
        score += 40 + min(20, item_evidence["token_hits"] * 5)
    if element_evidence["matched"]:
        score += 55 + min(20, element_evidence["token_hits"] * 5)
    if count == 0:
        score -= 25
    elif count is not None:
        score += min(15, count)
    score += min(10, _token_hits(text, _item_tokens(item)))
    return score


def _product_identity_segments(out: dict) -> tuple[str, str]:
    text = (out or {}).get("text") or ""
    primary_text = PRODUCT_IDENTITY_NOISE_RE.split(text, maxsplit=1)[0][:2200]
    element_names = []
    for el in (out or {}).get("elements") or []:
        name = (el.get("name") or "").strip()
        if not name or ADD_TO_CART_RE.search(name) or VIEW_CART_RE.search(name) or NON_PRODUCT_RE.search(name):
            continue
        element_names.append(name[:120])
        if len(element_names) >= 12:
            break
    visible = " ".join([
        (out or {}).get("title") or "",
        primary_text,
        " ".join(element_names),
    ])
    total = " ".join([visible, (out or {}).get("url") or ""])
    return visible, total


def _product_item_evidence(out: dict, item: str, start_url: str = "") -> dict:
    tokens = _item_tokens(item)
    required = _required_product_hits(tokens) if tokens else 0
    visible_identity, total_identity = _product_identity_segments(out)
    visible_hits = _token_hits(visible_identity, tokens)
    total_hits = _token_hits(total_identity, tokens)
    distinctive = _has_distinctive_required_tokens(visible_identity, tokens) if tokens else False
    numbers = _numbers_match(total_identity, item)
    surface = _surface_kind(out, start_url)
    matched = bool(
        tokens
        and surface == "product"
        and numbers
        and distinctive
        and visible_hits >= required
    )
    return {
        "matched": matched,
        "token_hits": visible_hits,
        "total_token_hits": total_hits,
        "required_hits": required,
        "distinctive_matched": bool(distinctive),
        "numbers_matched": bool(numbers),
        "surface_kind": surface,
    }


def _state_digest(out: dict) -> str:
    o = out or {}
    text = re.sub(r"\s+", " ", (o.get("text") or "").lower())[:3000]
    names = "\n".join(
        re.sub(r"\s+", " ", (el.get("name") or "").lower())[:120]
        for el in (o.get("elements") or [])[:80]
    )
    return hashlib.sha1(f"{text}\n{names}".encode()).hexdigest()[:12]


def _commerce_mutation(before: dict, after: dict, item: str) -> dict:
    before_signal = _cart_signal_score(before, item)
    after_signal = _cart_signal_score(after, item)
    url_changed = ((before or {}).get("url") or "") != ((after or {}).get("url") or "")
    title_changed = ((before or {}).get("title") or "") != ((after or {}).get("title") or "")
    digest_changed = _state_digest(before) != _state_digest(after)
    signal_improved = after_signal > before_signal
    return {
        "changed": bool(url_changed or title_changed or digest_changed or signal_improved),
        "url_changed": url_changed,
        "title_changed": title_changed,
        "digest_changed": digest_changed,
        "signal_improved": signal_improved,
        "before_cart_signal": before_signal,
        "after_cart_signal": after_signal,
        "cart_verified": _cart_verified(after, item),
    }


def _commerce_wall_kind(out: dict) -> str:
    url = (out or {}).get("url") or ""
    if LOGIN_URL_RE.search(url):
        return "login"
    text = ((out or {}).get("text") or "").lower()
    if any(k in text for k in BLOCK_MARKERS):
        return classify_wall(text)
    return ""


def _surface_kind(out: dict, start_url: str = "") -> str:
    url = (out or {}).get("url") or ""
    if CART_URL_RE.search(url):
        return "cart"
    if _looks_buyable_product_url(url, start_url or url):
        return "product"
    if _looks_search_results_url(url):
        return "search"
    if _looks_content_url(url):
        return "content"
    return "unknown"


def _page_state(
    stage: str,
    out: dict,
    item: str,
    action: str = "",
    *,
    start_url: str = "",
    mutation: Optional[dict] = None,
) -> dict:
    elements = []
    for el in (out or {}).get("elements") or []:
        name = (el.get("name") or "").strip()
        if not name:
            continue
        elements.append({
            "idx": el.get("idx"),
            "role": el.get("role"),
            "name": name[:90],
            "href": (el.get("href") or "")[:140],
            "inView": bool(el.get("inView")),
            "sponsored": bool(el.get("sponsored")),
        })
        if len(elements) >= 18:
            break
    item_evidence = _cart_item_evidence(out, item)
    element_evidence = _cart_element_item_evidence(out, item)
    product_evidence = _product_item_evidence(out, item, start_url)
    state = {
        "stage": stage,
        "action": action,
        "url": (out or {}).get("url"),
        "title": (out or {}).get("title"),
        "surface_kind": _surface_kind(out, start_url),
        "item_token_hits": _token_hits((out or {}).get("text") or "", _item_tokens(item)),
        "cart_item_match": item_evidence["matched"],
        "cart_item_window_count": item_evidence["window_count"],
        "cart_item_token_hits": item_evidence["token_hits"],
        "cart_item_required_hits": item_evidence["required_hits"],
        "cart_item_quantity": item_evidence["quantity"],
        "cart_item_local_structure": item_evidence["local_structure"],
        "cart_element_match": element_evidence["matched"],
        "cart_element_token_hits": element_evidence["token_hits"],
        "cart_element_required_hits": element_evidence["required_hits"],
        "cart_element_index": element_evidence["element_index"],
        "cart_count": _cart_count(out),
        "cart_signal": _cart_signal_score(out, item),
        "cart_verified": _cart_verified(out, item),
        "cart_page_verified": _cart_page_verified(out, item),
        "product_item_match": product_evidence["matched"],
        "product_item_token_hits": product_evidence["token_hits"],
        "product_item_total_token_hits": product_evidence["total_token_hits"],
        "product_item_required_hits": product_evidence["required_hits"],
        "product_item_distinctive": product_evidence["distinctive_matched"],
        "product_item_numbers": product_evidence["numbers_matched"],
        "cartish": any(k in ((out or {}).get("text") or "").lower() for k in ("added to cart", "cart", "basket", "bag")),
        "buyable_product_links": sum(
            1 for el in (out or {}).get("elements") or []
            if _looks_buyable_product_url(el.get("href") or "", start_url or (out or {}).get("url") or "")
        ),
        "elements": elements,
    }
    if mutation is not None:
        state["mutation"] = mutation
    return state


def _sig(url, title, els) -> str:
    key = (url or "").split("?")[0] + "|" + (title or "")[:60] + "|" + ",".join((e.get("name") or "")[:18] for e in els[:8])
    return hashlib.sha1(key.encode()).hexdigest()[:12]


class TaskState:
    def __init__(self, subgoals: List[str]) -> None:
        self.subgoals = [{"text": s, "status": "pending"} for s in subgoals]
        self.i = 0

    @property
    def current(self):
        return self.subgoals[self.i] if self.i < len(self.subgoals) else None

    def advance(self):
        if self.current:
            self.current["status"] = "done"
        self.i += 1

    def fail_current(self):
        if self.current:
            self.current["status"] = "failed"
        self.i += 1

    def done(self) -> bool:
        return self.i >= len(self.subgoals)

    def render(self) -> str:
        out = []
        for k, g in enumerate(self.subgoals):
            mark = "x" if g["status"] == "done" else ("!" if g["status"] == "failed" else (">" if k == self.i else " "))
            out.append(f"  [{mark}] {g['text']}")
        return "\n".join(out)


class WebVoyagerAgent:
    def __init__(self, link: BrowserLink, gateway: ModelGateway, max_steps: int = 28,
                 per_subgoal: int = 8, notifier=None) -> None:
        self.link = link
        self.gw = gateway
        self.max_steps = max_steps
        self.per_subgoal = per_subgoal
        self.notifier = notifier  # async callable(str)->None; texts the user on a wall (None = log only)

    async def _observe(self, url: Optional[str] = None):
        r = await self.link.send_browse(new_id(), "observe", {"url": url} if url else {}, timeout=60.0)
        return (r.get("output") or {}), (r.get("proof") or {}).get("screenshot")

    @staticmethod
    def _empty_obs(out) -> bool:
        # An observation we cannot act on: no actionable elements AND no page
        # identity. Heavy sites return this if we look before they're ready.
        o = out or {}
        return not (o.get("elements") or []) and not o.get("url") and not (o.get("text") or "")

    @staticmethod
    def _unactionable_obs(out) -> bool:
        o = out or {}
        return not (o.get("elements") or []) and not (o.get("text") or "").strip()

    async def _observe_ready(self, url: Optional[str] = None, tries: int = 4):
        # GENERAL fix (no site logic): never decide on a not-ready page, and never
        # let a slow/hung observe crash the run. If the observation is empty (or the
        # observe times out), wait a beat and re-look (same tab, no re-nav).
        async def _try(u=None):
            try:
                return await self._observe(u)
            except Exception:
                return {}, None  # timeout / transport hiccup -> treat as not-ready
        out, shot = await _try(url)
        n = 0
        while (self._empty_obs(out) or (url is not None and self._unactionable_obs(out))) and n < tries:
            await asyncio.sleep(1.2 + 0.6 * n)
            out, shot = await _try()
            n += 1
        return out, shot

    async def _act(self, action: dict):
        # An act that hangs/times out must NOT crash the run. Fail fast (20s); the
        # next observe shows no change and the anti-loop guard recovers or hands off.
        try:
            return await self.link.send_browse(new_id(), "act", action, timeout=20.0)
        except Exception:
            return {"status": "error"}

    async def _act_add_and_observe(self, action: dict):
        await self._act(action)
        await asyncio.sleep(ADD_CLICK_SETTLE_SECONDS)
        return await self._observe_ready()

    def _fresh_probe_agent(self) -> Optional["WebVoyagerAgent"]:
        factory = getattr(self.link, "fresh_probe", None)
        if not callable(factory):
            return None
        try:
            return type(self)(
                factory(),
                self.gw,
                max_steps=1,
                per_subgoal=1,
                notifier=self.notifier,
            )
        except Exception:
            return None

    async def _observe_fresh_probe(self, url: str):
        probe = self._fresh_probe_agent()
        if probe is None:
            return await self._observe_ready(url)
        return await probe._observe_ready(url)

    async def _observe_cart_ready(self, url: str, item: str, *, fresh_probe: bool = False):
        agent = self._fresh_probe_agent() if fresh_probe else self
        if agent is None:
            agent = self
        out, shot = await agent._observe_ready(url)
        best_out, best_shot = out, shot
        for _ in range(4):
            if _cart_page_verified(best_out, item):
                break
            if not _is_cart_url(out):
                break
            await agent._act({"action": "scroll", "dir": "down"})
            out, shot = await agent._observe_ready()
            if _cart_signal_score(out, item) >= _cart_signal_score(best_out, item):
                best_out, best_shot = out, shot
        return best_out, best_shot

    async def _observe_durable_cart_confirmation(self, url: str, item: str):
        best_out: dict = {}
        best_shot = None
        for read_idx in range(CART_DURABILITY_READS):
            if read_idx:
                await asyncio.sleep(CART_DURABILITY_DELAY_SECONDS)
            out, shot = await self._observe_cart_ready(url, item, fresh_probe=True)
            if out and (not best_out or _cart_signal_score(out, item) >= _cart_signal_score(best_out, item)):
                best_out = out
                best_shot = shot or best_shot
            if not _cart_page_verified(out, item):
                return out, shot, False
        return best_out, best_shot, True

    async def _plan(self, task: str) -> List[str]:
        if _search_text(task):
            return [
                "search for the remembered item on the site",
                "open the matching non-sponsored product",
                "add the item to the cart",
                "verify the cart contains the item",
            ]
        raw = await _think(self.gw, PLAN_SYS + f"\n\nTASK: {task}", tier=SMART, caller="agent",
                           json_mode=True, temperature=0.2, max_tokens=AGENT_MAX_TOKENS)
        subs = (_parse_json(raw) or {}).get("subgoals") or [task]
        return [str(s) for s in subs][:6]

    def _done(self, out, step, history, **extra):
        return {"steps": step, "final_url": (out or {}).get("url"), "history": history[-40:],
                "final_shot": getattr(self, "_cur_shot", None), **extra}

    async def _verify_known_cart_url(self, start_url: str, item: str, history: list[str],
                                     states: list[dict], steps: int, stage: str) -> tuple[dict, int]:
        cart_url = _commerce_cart_url(start_url)
        if not cart_url:
            return {}, steps
        expected_path = urllib.parse.urlparse(cart_url).path.rstrip("/") or "/"
        out, shot = await self._observe_cart_ready(cart_url, item)
        durable_confirmed = False
        for attempt in range(5):
            if attempt:
                await asyncio.sleep(0.6 + attempt * 0.35)
                out, shot = await self._observe_ready()
            current_path = urllib.parse.urlparse((out or {}).get("url") or "").path.rstrip("/") or "/"
            if _cart_page_verified(out, item):
                await asyncio.sleep(0.8)
                confirm_out, confirm_shot, durable_confirmed = await self._observe_durable_cart_confirmation(
                    cart_url, item
                )
                if confirm_out:
                    out = confirm_out
                if confirm_shot:
                    shot = confirm_shot
                if durable_confirmed:
                    break
            if current_path == expected_path and attempt == 4:
                break
        self._cur_shot = shot
        durable = " durable" if durable_confirmed else ""
        history.append(f"recipe: {stage} navigated known cart url{durable} for {_host(start_url)}")
        states.append(_page_state(stage, out, item, history[-1], start_url=start_url))
        return out, steps + 2 if durable_confirmed else steps + 1

    async def _confirm_current_cart_page(self, out: dict, start_url: str, item: str,
                                         history: list[str], states: list[dict],
                                         steps: int, stage: str) -> tuple[dict, int, bool]:
        if not _cart_page_verified(out, item):
            return out, steps, False
        cart_url = _commerce_cart_url(start_url) or ((out or {}).get("url") or "")
        if not cart_url:
            return out, steps, False
        await asyncio.sleep(0.5)
        confirm_out, confirm_shot, durable_confirmed = await self._observe_durable_cart_confirmation(cart_url, item)
        if confirm_shot:
            self._cur_shot = confirm_shot
        checked = confirm_out if confirm_out else out
        status = "verified" if durable_confirmed else "rejected"
        history.append(f"recipe: {stage} fresh_probe {status} cart page for {_host(start_url)}")
        states.append(_page_state(stage, checked, item, history[-1], start_url=start_url))
        return checked, steps + 1, durable_confirmed

    async def _notify(self, msg: str) -> None:
        if not self.notifier:
            return
        try:
            await self.notifier(msg)
        except Exception:
            pass  # a notify failure must never crash the run

    async def _handoff(self, out, step, history, wall_kind: str, detail: str) -> dict:
        # pause -> ask the human (text) -> resume later via /agent/resume. We stop
        # observing here, so we never screenshot what the user types at the wall.
        ask = ask_message(wall_kind, (out or {}).get("url") or "")
        await self._notify(ask)
        return self._done(out, step, history, answer="", needs_human=True, paused=True,
                          wall_kind=wall_kind, ask=ask, resume_token=new_id(), reason=detail)

    async def _try_commerce_recipe(self, task: str, start_url: str) -> Optional[dict]:
        item = _search_text(task)
        if not item or not re.search(r"\b(cart|basket|bag)\b", task or "", re.I):
            return None

        history: List[str] = []
        states: list[dict] = []
        steps = 0
        context_hints = _context_hint_tokens(task, item)

        preflight_out, steps = await self._verify_known_cart_url(
            start_url, item, history, states, steps, "known_cart_preflight"
        )
        if preflight_out:
            wall_kind = _commerce_wall_kind(preflight_out)
            if wall_kind:
                return await self._handoff(preflight_out, steps, history, wall_kind,
                                           "wall during known-cart preflight")
            if _cart_page_verified(preflight_out, item):
                return self._done(
                    preflight_out,
                    steps,
                    history,
                    answer=f"Verified cart already contains {item}; no duplicate add needed.",
                    page_states=states,
                    commerce_recipe=True,
                    already_in_cart=True,
                )

        search_url = _commerce_search_url(start_url, item)
        if search_url:
            out, shot = await self._observe_ready(search_url)
            self._cur_shot = shot
            history.append(f"recipe: navigate search url for item on {_host(start_url)}")
        else:
            out, shot = await self._observe_ready(start_url)
            self._cur_shot = shot
            history.append("recipe: observe start page")
            search_box = _pick_button(out.get("elements") or [], re.compile(r"\bsearch\b", re.I))
            if search_box:
                await self._act({"action": "type", "index": search_box.get("idx"), "text": item, "enter": True})
                out, shot = await self._observe_ready()
                self._cur_shot = shot
                history.append(f"recipe: typed item into site search idx={search_box.get('idx')}")
                steps += 1

        if self._unactionable_obs(out):
            for attempt in range(3):
                await asyncio.sleep(0.8 + attempt * 0.4)
                if _looks_search_results_url((out or {}).get("url") or ""):
                    await self._act({"action": "scroll", "dir": "down"})
                    history.append(f"recipe: scroll unactionable search surface {attempt + 1}")
                else:
                    history.append(f"recipe: re-observe unactionable search surface {attempt + 1}")
                out, shot = await self._observe_ready()
                self._cur_shot = shot
                states.append(_page_state(
                    f"search_unactionable_retry_{attempt + 1}",
                    out,
                    item,
                    history[-1],
                    start_url=start_url,
                ))
                steps += 1
                if not self._unactionable_obs(out):
                    break
        if self._unactionable_obs(out):
            states.append(_page_state("unactionable_search_surface", out, item, history[-1], start_url=start_url))
            return self._done(out, steps + 1, history, answer="",
                              reason="commerce recipe found no actionable browser elements",
                              page_states=states, commerce_recipe=True)

        states.append(_page_state("search_results", out, item, history[-1], start_url=start_url))
        prefer_lowest = _wants_lowest_price(task)
        wall_kind = _commerce_wall_kind(out)
        if wall_kind:
            return await self._handoff(out, steps + 1, history, wall_kind,
                                       "wall during commerce recipe")
        out, steps, durable_cart = await self._confirm_current_cart_page(
            out, start_url, item, history, states, steps, "fresh_cart_after_search_results"
        )
        if durable_cart:
            return self._done(out, steps + 1, history, answer=f"Verified cart contains {item}.",
                              page_states=states, commerce_recipe=True)

        if _token_hits(out.get("text") or "", _item_tokens(item)) == 0:
            region_button = _pick_region_button(out.get("elements") or [])
            if region_button:
                label = (region_button.get("name") or "")[:80]
                await self._act({"action": "click", "index": region_button.get("idx")})
                out, shot = await self._observe_ready()
                self._cur_shot = shot
                history.append(f"recipe: selected store region idx={region_button.get('idx')} '{label}'")
                states.append(_page_state("after_region_selection", out, item, history[-1], start_url=start_url))
                steps += 1
                wall_kind = _commerce_wall_kind(out)
                if wall_kind:
                    return await self._handoff(out, steps + 1, history, wall_kind,
                                               "wall after store region selection")
                out, steps, durable_cart = await self._confirm_current_cart_page(
                    out, start_url, item, history, states, steps, "fresh_cart_after_region_selection"
                )
                if durable_cart:
                    return self._done(out, steps + 1, history, answer=f"Verified cart contains {item}.",
                                      page_states=states, commerce_recipe=True)
                if search_url and _token_hits(out.get("text") or "", _item_tokens(item)) == 0:
                    out, shot = await self._observe_ready(search_url)
                    self._cur_shot = shot
                    history.append("recipe: reloaded search after store region selection")
                    states.append(_page_state("search_after_region_selection", out, item, history[-1], start_url=start_url))
                    steps += 1

        opened_product_from_results_add = False
        if (_looks_buyable_product_url(out.get("url") or "", start_url)
                and _product_item_evidence(out, item, start_url)["matched"]):
            opened_product_from_results_add = True
            history.append("recipe: search landed on matching product page")
            states.append(_page_state(
                "product_page_from_search_redirect",
                out,
                item,
                history[-1],
                start_url=start_url,
            ))
        search_elements = out.get("elements") or []
        add_from_results = None
        if not opened_product_from_results_add:
            add_from_results = _pick_add_button(
                out.get("elements") or [], item, allow_generic=False, start_url=start_url
            )
        if add_from_results:
            label = (add_from_results.get("name") or "")[:80]
            before_add = out
            out, shot = await self._act_add_and_observe({"action": "click", "index": add_from_results.get("idx")})
            self._cur_shot = shot
            mutation = _commerce_mutation(before_add, out, item)
            history.append(
                f"recipe: clicked item-specific add from results idx={add_from_results.get('idx')} "
                f"'{label}' changed={mutation['changed']} signal={mutation['after_cart_signal']}"
            )
            states.append(_page_state(
                "post_add_from_results",
                out,
                item,
                history[-1],
                start_url=start_url,
                mutation=mutation,
            ))
            steps += 1
            wall_kind = _commerce_wall_kind(out)
            if wall_kind:
                return await self._handoff(out, steps + 1, history, wall_kind,
                                           "wall after item-specific search-results add")
            out, steps, durable_cart = await self._confirm_current_cart_page(
                out, start_url, item, history, states, steps, "fresh_cart_after_results_add"
            )
            if durable_cart:
                return self._done(out, steps + 1, history, answer=f"Verified cart contains {item}.",
                                  page_states=states, commerce_recipe=True)
            view_cart = _pick_button(out.get("elements") or [], VIEW_CART_RE)
            if view_cart:
                cart_label = (view_cart.get("name") or "")[:80]
                await self._act({"action": "click", "index": view_cart.get("idx")})
                out, shot = await self._observe_ready()
                self._cur_shot = shot
                history.append(f"recipe: opened cart after results add idx={view_cart.get('idx')} '{cart_label}'")
                states.append(_page_state("cart_page_after_results_add", out, item, history[-1], start_url=start_url))
                steps += 1
                out, steps, durable_cart = await self._confirm_current_cart_page(
                    out, start_url, item, history, states, steps, "fresh_cart_after_results_view_cart"
                )
                if durable_cart:
                    return self._done(out, steps + 1, history, answer=f"Verified cart contains {item}.",
                                      page_states=states, commerce_recipe=True)
            cart_out, steps = await self._verify_known_cart_url(
                start_url, item, history, states, steps, "known_cart_page_after_results_add"
            )
            if cart_out and _cart_page_verified(cart_out, item):
                return self._done(cart_out, steps + 1, history, answer=f"Verified cart contains {item}.",
                                  page_states=states, commerce_recipe=True)
            if cart_out:
                out = cart_out
            product_url = _product_url_near_add(
                search_elements, item, int(add_from_results.get("idx") or -1), start_url
            )
            if not product_url:
                return self._done(out, steps + 1, history, answer="",
                                  reason="item-specific search-results add did not verify the cart artifact",
                                  page_states=states, commerce_recipe=True)
            out, shot = await self._observe_ready(product_url)
            self._cur_shot = shot
            history.append("recipe: opened same product after unverified results add")
            states.append(_page_state(
                "same_product_page_after_results_add_failure",
                out,
                item,
                history[-1],
                start_url=start_url,
            ))
            steps += 1
            wall_kind = _commerce_wall_kind(out)
            if wall_kind:
                return await self._handoff(out, steps + 1, history, wall_kind,
                                           "wall while opening same product after results add")
            opened_product_from_results_add = True

        if not opened_product_from_results_add:
            product = None
            for scrolls in range(4):
                product = _pick_product(
                    out.get("elements") or [],
                    item,
                    prefer_lowest=prefer_lowest,
                    start_url=start_url,
                    context_hints=context_hints,
                    allow_query_fallback=_looks_search_results_url(out.get("url") or ""),
                )
                if product:
                    break
                if scrolls >= 3:
                    break
                await self._act({"action": "scroll", "dir": "down"})
                out, shot = await self._observe_ready()
                self._cur_shot = shot
                history.append(f"recipe: scroll search results {scrolls + 1}")
                states.append(_page_state(
                    f"search_results_scroll_{scrolls + 1}",
                    out,
                    item,
                    history[-1],
                    start_url=start_url,
                ))
                steps += 1

            if product:
                label = (product.get("name") or "")[:80]
                product_url = _product_url_near_index(
                    out.get("elements") or [], item, int(product.get("idx") or -1), start_url
                )
                result_add = None
                if _looks_search_results_url(out.get("url") or ""):
                    result_add = _pick_adjacent_result_add(out.get("elements") or [], product, item, start_url)
                if result_add:
                    add_label = (result_add.get("name") or "")[:80]
                    before_add = out
                    out, shot = await self._act_add_and_observe({"action": "click", "index": result_add.get("idx")})
                    self._cur_shot = shot
                    mutation = _commerce_mutation(before_add, out, item)
                    history.append(
                        f"recipe: clicked adjacent add from results idx={result_add.get('idx')} "
                        f"'{add_label}' changed={mutation['changed']} signal={mutation['after_cart_signal']}"
                    )
                    states.append(_page_state(
                        "post_adjacent_add_from_results",
                        out,
                        item,
                        history[-1],
                        start_url=start_url,
                        mutation=mutation,
                    ))
                    steps += 1
                    wall_kind = _commerce_wall_kind(out)
                    if wall_kind:
                        return await self._handoff(out, steps + 1, history, wall_kind,
                                                   "wall after adjacent search-results add")
                    cart_out, steps = await self._verify_known_cart_url(
                        start_url, item, history, states, steps, "known_cart_page_after_adjacent_results_add"
                    )
                    if cart_out and _cart_page_verified(cart_out, item):
                        return self._done(cart_out, steps + 1, history, answer=f"Verified cart contains {item}.",
                                          page_states=states, commerce_recipe=True)
                    if cart_out:
                        out = cart_out
                    return self._done(out, steps + 1, history, answer="",
                                      reason="adjacent search-results add did not verify the cart artifact",
                                      page_states=states, commerce_recipe=True)
                await self._act({"action": "click", "index": product.get("idx")})
                out, shot = await self._observe_ready()
                self._cur_shot = shot
                history.append(f"recipe: opened product idx={product.get('idx')} '{label}'")
                states.append(_page_state("product_page", out, item, history[-1], start_url=start_url))
                steps += 1
                wall_kind = _commerce_wall_kind(out)
                if wall_kind:
                    return await self._handoff(out, steps + 1, history, wall_kind,
                                               "wall after opening product page")
                if (product_url and _looks_search_results_url(out.get("url") or "")
                        and not _looks_buyable_product_url(out.get("url") or "", start_url)):
                    out, shot = await self._observe_ready(product_url)
                    self._cur_shot = shot
                    history.append("recipe: navigated adjacent product url after product click stayed on search")
                    states.append(_page_state(
                        "product_page_from_adjacent_url",
                        out,
                        item,
                        history[-1],
                        start_url=start_url,
                    ))
                    steps += 1
                    wall_kind = _commerce_wall_kind(out)
                    if wall_kind:
                        return await self._handoff(out, steps + 1, history, wall_kind,
                                                   "wall after adjacent product URL navigation")
            else:
                return self._done(out, steps + 1, history, answer="",
                                  reason="commerce recipe could not identify a matching product",
                                  page_states=states, commerce_recipe=True)

        out, steps, durable_cart = await self._confirm_current_cart_page(
            out, start_url, item, history, states, steps, "fresh_cart_before_product_add"
        )
        if durable_cart:
            return self._done(out, steps + 1, history, answer=f"Verified cart contains {item}.",
                              page_states=states, commerce_recipe=True)

        tried_add_names: set[str] = set()
        refreshed_product_identity = False
        refreshed_product_add_controls = False
        for attempt in range(5):
            out, steps, durable_cart = await self._confirm_current_cart_page(
                out, start_url, item, history, states, steps, "fresh_cart_product_loop_start"
            )
            if durable_cart:
                return self._done(out, steps + 1, history, answer=f"Verified cart contains {item}.",
                                  page_states=states, commerce_recipe=True)
            product_evidence = _product_item_evidence(out, item, start_url)
            if not product_evidence["matched"]:
                if not refreshed_product_identity:
                    out, shot = await self._observe_ready()
                    self._cur_shot = shot
                    refreshed_product_identity = True
                    history.append("recipe: refreshed product page for item identity")
                    states.append(_page_state(
                        "product_identity_refresh",
                        out,
                        item,
                        history[-1],
                        start_url=start_url,
                    ))
                    steps += 1
                    continue
                if attempt < 4:
                    await self._act({"action": "scroll", "dir": "down"})
                    out, shot = await self._observe_ready()
                    self._cur_shot = shot
                    history.append(f"recipe: scroll product for item identity {attempt + 1}")
                    states.append(_page_state(
                        f"product_identity_scroll_{attempt + 1}",
                        out,
                        item,
                        history[-1],
                        start_url=start_url,
                    ))
                    steps += 1
                    continue
                history.append(
                    "recipe: rejected product page before add "
                    f"hits={product_evidence['token_hits']}/{product_evidence['required_hits']} "
                    f"distinctive={product_evidence['distinctive_matched']} "
                    f"numbers={product_evidence['numbers_matched']} "
                    f"surface={product_evidence['surface_kind']}"
                )
                states.append(_page_state(
                    "product_identity_rejected_before_add",
                    out,
                    item,
                    history[-1],
                    start_url=start_url,
                ))
                return self._done(out, steps + 1, history, answer="",
                                  reason="product page identity did not match the remembered item strongly enough to add safely",
                                  page_states=states, commerce_recipe=True)
            add = _pick_add_button(
                out.get("elements") or [], item, skip_names=tried_add_names, start_url=start_url
            )
            if not add and not refreshed_product_add_controls:
                out, shot = await self._observe_ready()
                self._cur_shot = shot
                refreshed_product_add_controls = True
                history.append("recipe: refreshed product page for add controls")
                states.append(_page_state(
                    "product_add_refresh",
                    out,
                    item,
                    history[-1],
                    start_url=start_url,
                ))
                steps += 1
                out, steps, durable_cart = await self._confirm_current_cart_page(
                    out, start_url, item, history, states, steps, "fresh_cart_after_product_refresh"
                )
                if durable_cart:
                    return self._done(out, steps + 1, history, answer=f"Verified cart contains {item}.",
                                      page_states=states, commerce_recipe=True)
                add = _pick_add_button(
                    out.get("elements") or [], item, skip_names=tried_add_names, start_url=start_url
                )
            if not add:
                await self._act({"action": "scroll", "dir": "down"})
                out, shot = await self._observe_ready()
                self._cur_shot = shot
                history.append(f"recipe: scroll product for add control {attempt + 1}")
                states.append(_page_state(
                    f"product_scroll_{attempt + 1}",
                    out,
                    item,
                    history[-1],
                    start_url=start_url,
                ))
                steps += 1
                out, steps, durable_cart = await self._confirm_current_cart_page(
                    out, start_url, item, history, states, steps, "fresh_cart_after_product_scroll"
                )
                if durable_cart:
                    return self._done(out, steps + 1, history, answer=f"Verified cart contains {item}.",
                                      page_states=states, commerce_recipe=True)
                continue
            label = (add.get("name") or "")[:80]
            before_add = out
            out, shot = await self._act_add_and_observe({"action": "click", "index": add.get("idx")})
            self._cur_shot = shot
            mutation = _commerce_mutation(before_add, out, item)
            history.append(
                f"recipe: clicked add control idx={add.get('idx')} '{label}' "
                f"changed={mutation['changed']} signal={mutation['after_cart_signal']}"
            )
            states.append(_page_state(
                "post_add",
                out,
                item,
                history[-1],
                start_url=start_url,
                mutation=mutation,
            ))
            steps += 1
            wall_kind = _commerce_wall_kind(out)
            if wall_kind:
                return await self._handoff(out, steps + 1, history, wall_kind,
                                           "wall after product-page add")
            out, steps, durable_cart = await self._confirm_current_cart_page(
                out, start_url, item, history, states, steps, "fresh_cart_after_product_add"
            )
            if durable_cart:
                return self._done(out, steps + 1, history, answer=f"Verified cart contains {item}.",
                                  page_states=states, commerce_recipe=True)
            if not mutation["changed"]:
                tried_add_names.add(label.lower())
                continue
            break

        out, steps, durable_cart = await self._confirm_current_cart_page(
            out, start_url, item, history, states, steps, "fresh_cart_after_add_loop"
        )
        if durable_cart:
            return self._done(out, steps + 1, history, answer=f"Verified cart contains {item}.",
                              page_states=states, commerce_recipe=True)

        view_cart = _pick_button(out.get("elements") or [], VIEW_CART_RE)
        if view_cart:
            label = (view_cart.get("name") or "")[:80]
            await self._act({"action": "click", "index": view_cart.get("idx")})
            out, shot = await self._observe_ready()
            self._cur_shot = shot
            history.append(f"recipe: opened cart idx={view_cart.get('idx')} '{label}'")
            states.append(_page_state("cart_page", out, item, history[-1], start_url=start_url))
            steps += 1
            out, steps, durable_cart = await self._confirm_current_cart_page(
                out, start_url, item, history, states, steps, "fresh_cart_after_view_cart"
            )
            if durable_cart:
                return self._done(out, steps + 1, history, answer=f"Verified cart contains {item}.",
                                  page_states=states, commerce_recipe=True)

        cart_out, steps = await self._verify_known_cart_url(
            start_url, item, history, states, steps, "known_cart_page_after_product_add"
        )
        if cart_out and _cart_page_verified(cart_out, item):
            return self._done(cart_out, steps + 1, history, answer=f"Verified cart contains {item}.",
                              page_states=states, commerce_recipe=True)
        if cart_out:
            out = cart_out

        return self._done(out, steps + 1, history, answer="",
                          reason="commerce recipe did not verify the cart artifact",
                          page_states=states, commerce_recipe=True)

    async def run(self, task: str, start_url: str) -> dict:
        recipe_result = await self._try_commerce_recipe(task, start_url)
        if recipe_result is not None:
            return recipe_result

        state = TaskState(await self._plan(task))
        history: List[str] = []
        visited: dict = {}
        committed: Optional[str] = None
        sub_steps = 0
        sub_stuck = 0
        reflection = ""
        last_thought = ""  # carry the model's own reasoning forward one step (scratchpad)
        forbid = None  # (action, index) forbidden this step after a STUCK
        item_text = _search_text(task)

        out, shot = await self._observe_ready(start_url)
        self._cur_shot = shot
        if self._unactionable_obs(out):
            return self._done(out, 1, history, answer="",
                              reason="browser surface returned no actionable elements or readable text")
        prev_sig = _sig(out.get("url"), out.get("title"), out.get("elements") or [])
        visited[prev_sig] = 1
        progress = "START"

        for step in range(self.max_steps):
            text = (out.get("text") or "").lower()
            if any(k in text for k in BLOCK_MARKERS):
                return await self._handoff(out, step + 1, history, classify_wall(text),
                                           "captcha / anti-bot wall — handed back with the page open")

            all_in = [e for e in (out.get("elements") or []) if e.get("inView")]
            organic = [e for e in all_in if not e.get("sponsored")]
            sponsored = [e for e in all_in if e.get("sponsored")]
            els = (organic + sponsored)[:45]  # organic first; ads last (and labelled)

            subgoal_text = state.current["text"] if state.current else "Provide the final answer (action=answer)."
            stuck_note = ""
            if forbid is not None:
                stuck_note = (f"STUCK on this subgoal: you repeated {forbid} with no progress. Pick a DIFFERENT "
                              f"element that advances the subgoal, or scroll for new options. Do NOT repeat {forbid}.")
            el_lines = "\n".join(
                f'[{e["idx"]}]{" [AD]" if e.get("sponsored") else ""} {e.get("role","")} "{(e.get("name") or "")[:80]}"'
                + (f' ({e["state"]})' if e.get("state") else "")
                for e in els
            )
            prompt = (
                ACT_SYS
                + f"\n\nTASK: {task}\nPLAN:\n{state.render()}\nCURRENT SUBGOAL: {subgoal_text}\n"
                + f"URL: {out.get('url')}\nTITLE: {out.get('title')}\nLAST STEP: {progress}\n"
                + (f"SEARCH_TEXT: {item_text}\n" if item_text else "")
                + (f"COMMITTED TARGET (act on this; don't re-pick): {committed}\n" if committed else "")
                + (f"REFLECTION: {reflection}\n" if reflection else "")
                + (f"YOUR LAST THOUGHT: {last_thought}\n" if last_thought else "")
                + (stuck_note + "\n" if stuck_note else "")
                + "RECENT ACTIONS:\n" + ("\n".join(history[-5:]) or "(none)") + "\n\n"
                + "VISIBLE ELEMENTS:\n" + el_lines + "\n\nNext action JSON:"
            )
            # two-tier ladder: cheap by default; escalate to smart only when stuck
            # (no progress last step, or an action was forbidden by the anti-loop guard)
            escalate = (sub_stuck >= 1) or (forbid is not None)
            tier = SMART if escalate else CHEAP
            raw1 = await _think(self.gw, prompt, tier=tier, caller="agent", image=shot,
                                json_mode=True, temperature=0.1, max_tokens=AGENT_MAX_TOKENS)
            if not (raw1 or "").strip() and shot:
                # Some model/provider paths return empty content for image+JSON.
                # The prompt already carries the set-of-marks element list, so a
                # text-only retry keeps the same planner in the loop without faking.
                raw1 = await _think(self.gw, prompt, tier=tier, caller="agent", image=None,
                                    json_mode=True, temperature=0.1, max_tokens=AGENT_MAX_TOKENS)
            if not (raw1 or "").strip():
                raw1 = await _think(self.gw, prompt, tier=tier, caller="agent", image=None,
                                    json_mode=False, temperature=0.1, max_tokens=AGENT_MAX_TOKENS)
            action = _parse_json(raw1)
            raw2 = ""
            if not action or not action.get("action"):
                raw2 = await _think(  # a non-answer always escalates to smart
                    self.gw,
                    prompt + "\n\nReturn ONE JSON action now with an \"action\" field.",
                    tier=SMART, caller="agent", image=shot, json_mode=True, temperature=0.1,
                    max_tokens=AGENT_MAX_TOKENS)
                if not (raw2 or "").strip() and shot:
                    raw2 = await _think(
                        self.gw,
                        prompt + "\n\nReturn ONE JSON action now with an \"action\" field.",
                        tier=SMART, caller="agent", image=None, json_mode=True, temperature=0.1,
                        max_tokens=AGENT_MAX_TOKENS)
                if not (raw2 or "").strip():
                    raw2 = await _think(
                        self.gw,
                        prompt + "\n\nReturn ONE JSON action now with an \"action\" field.",
                        tier=SMART, caller="agent", image=None, json_mode=False, temperature=0.1,
                        max_tokens=AGENT_MAX_TOKENS)
                action = _parse_json(raw2)
            if not action or not action.get("action"):
                return self._done(out, step + 1, history, answer="", reason="no parseable action after retry",
                                  last_raw=((raw1 or "<empty>")[:220] + " ||RETRY|| " + (raw2 or "<empty>")[:220]))

            last_thought = (action.get("thought") or "")[:160]  # scratchpad for the next step

            if action.get("action") == "answer":
                return self._done(out, step + 1, history, answer=action.get("answer", ""))

            if action.get("action") == "click":
                el = next((e for e in els if e.get("idx") == action.get("index")), None)
                if el and PURCHASE_GUARD.search(el.get("name", "") or ""):
                    return self._done(out, step + 1, history, stopped_for_safety=True,
                                      answer=f"STOPPED before a purchase control ('{el.get('name')}'). "
                                             "Did NOT place the order — handed back for your confirmation.")
                if el and committed is None:
                    committed = (el.get("name") or "")[:48]  # commit to this target for the subgoal

            sig_here = (action.get("action"), action.get("index"))
            if forbid is not None and sig_here == forbid:
                # the model ignored the STUCK warning; skip this action, force a rethink next step
                history.append(f"{step}: BLOCKED repeat {sig_here}")
                forbid = None
                continue

            prev_url = out.get("url")
            label = next((e.get("name", "") for e in els if e.get("idx") == action.get("index")), action.get("text", ""))
            await self._act(_clean_action(action, item_text))
            out, shot = await self._observe_ready()
            self._cur_shot = shot
            sub_steps += 1

            new_sig = _sig(out.get("url"), out.get("title"), out.get("elements") or [])
            if new_sig == prev_sig:
                progress = "NO_CHANGE"
            elif new_sig in visited:
                progress = "REGRESSION"
            else:
                progress = "PROGRESS"
            visited[new_sig] = visited.get(new_sig, 0) + 1
            history.append(f"{step}: {action.get('action')} idx={action.get('index')} "
                           f"'{(label or '')[:26]}' -> {progress} ({(out.get('url') or '')[:48]})")

            # subgoal completion
            if action.get("subgoal_done") and state.current:
                state.advance()
                committed, sub_steps, sub_stuck, forbid, reflection = None, 0, 0, None, ""
                prev_sig = new_sig
                continue

            # anti-loop + reflection on failure
            if progress in ("NO_CHANGE", "REGRESSION"):
                sub_stuck += 1
                forbid = sig_here if action.get("action") == "click" else None
                reflection = await self._reflect(task, subgoal_text, history)
            else:
                sub_stuck = 0
                forbid = None
                reflection = ""

            # per-subgoal budget / stuck escalation -> fail subgoal -> alternative or handoff
            if (sub_stuck >= 3 or sub_steps >= self.per_subgoal) and state.current:
                state.fail_current()
                history.append(f"{step}: subgoal failed ('{subgoal_text[:40]}') -> moving on")
                committed, sub_steps, sub_stuck, forbid, reflection = None, 0, 0, None, ""
                if state.done():
                    return await self._handoff(out, step + 1, history, classify_wall(out.get("text", "")),
                                               "could not complete a subgoal after retries — handed back")
            prev_sig = new_sig

        return self._done(out, self.max_steps, history, answer="", exhausted=True)

    async def _reflect(self, task: str, subgoal: str, history: List[str]) -> str:
        raw = await _think(
            self.gw,
            f"Web agent on subgoal '{subgoal}' for task '{task}'. Last actions:\n" + "\n".join(history[-4:])
            + "\nThe last action did not progress. In ONE sentence: what likely went wrong and what DIFFERENT thing to try.",
            tier=SMART, caller="agent", temperature=0.3, max_tokens=AGENT_MAX_TOKENS)
        return (raw or "").strip()[:200]


async def judge(gw: ModelGateway, task: str, result: dict, image: Optional[str] = None) -> dict:
    prompt = (
        "You are grading a web agent, with the FINAL page screenshot attached. "
        "Reply ONLY JSON {\"success\":true|false,\"reason\":\"...\"}.\n"
        f"TASK: {task}\nAGENT ANSWER: {result.get('answer')!r}\nFINAL URL: {result.get('final_url')}\n"
        "Decide ONLY from substance: does the answer, corroborated by what is visible in the final screenshot, "
        "satisfy what the task asked for? Judge on correctness, not phrasing, and apply the SAME standard to every "
        "site. If the task itself instructed the agent to stop at a particular step, stopping there is success."
    )
    # temperature=0 so identical (answer, screenshot) gets an identical verdict —
    # the general judge must be deterministic, not flip on a re-grade.
    raw = await _think(gw, prompt, tier=SMART, caller="agent", image=image, json_mode=True, temperature=0,
                       max_tokens=AGENT_MAX_TOKENS)
    j = _parse_json(raw) or {}
    return {"success": bool(j.get("success")), "reason": j.get("reason", "")}
