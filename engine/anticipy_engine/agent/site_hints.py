"""SiteHints — the browser agent's per-host facts (search/cart/product URL shapes)
as DATA, not code. The P4 gate shape is ZERO retailer hostnames in agent/*.py; every
hostname the agent knows lives in two JSON layers:

  seed    : anticipy_engine/data/site_hints_seed.json — the one-time export of the
            old in-code host tables (35 hosts). Packaged with the engine, read-only,
            lazy-loaded (an engine boot must never die on a data file).
  overlay : a per-engine JSON the runtime wires explicitly (ControlCore passes
            <data>/site_hints.json — the pending_path/deferred_path precedent).
            It holds facts LEARNED by verified live runs only: the write-back fires
            solely at the durable cart-proof point, and mock runs never construct
            the agent at all. Overlay wins per-field on merge.

Every failure direction is toward the seed, never toward a wrong hint and never a
crash: a corrupt overlay is set aside as .corrupt with an honest log (seed-only
until relearned); invalid fields (search template without exactly one {q},
off-host URLs, uncompilable or oversized regexes) are dropped per-field; an
unreadable seed degrades known hosts to the agent's generic heuristics with a log.
No overlay path configured (the default for direct construction in tests and for
the module store until ControlCore wires it) means NO overlay IO at all.

Host matching is exact-domain first, then longest-suffix (m.store.test matches
store.test). The seed contains no overlapping domains, so seed-only lookups are
behavior-identical to the old first-match dict iteration they replaced.
"""
from __future__ import annotations

import json
import logging
import os
import re
import urllib.parse
from pathlib import Path
from typing import Optional

log = logging.getLogger("anticipy.site_hints")

SEED_PATH = Path(__file__).resolve().parent.parent / "data" / "site_hints_seed.json"
MAX_URL_CHARS = 500
MAX_PATTERN_CHARS = 400
MAX_PRODUCT_EXAMPLES = 5
_HOST_RE = re.compile(r"[a-z0-9][a-z0-9.-]{1,78}[a-z0-9]")


def host_of(url: str) -> str:
    """Lowercased netloc with one leading 'www.' stripped — identical semantics to
    the lookup key the old in-code tables were matched against."""
    try:
        host = urllib.parse.urlparse(url or "").netloc.lower()
    except Exception:
        return ""
    return host[4:] if host.startswith("www.") else host


def _valid_host(host) -> bool:
    return bool(isinstance(host, str) and "." in host and _HOST_RE.fullmatch(host))


def _url_on_host(url: str, host: str) -> bool:
    h = host_of(url)
    return bool(h) and (h == host or h.endswith("." + host))


def _valid_search_url(v, host: str) -> bool:
    # exactly one {q} and no other braces, so .format(q=...) can never raise
    return (
        isinstance(v, str)
        and 0 < len(v) <= MAX_URL_CHARS
        and v.startswith(("https://", "http://"))
        and v.count("{") == 1
        and v.count("}") == 1
        and "{q}" in v
        and _url_on_host(v.replace("{q}", "x"), host)
    )


def _valid_cart_url(v, host: str) -> bool:
    return (
        isinstance(v, str)
        and 0 < len(v) <= MAX_URL_CHARS
        and v.startswith(("https://", "http://"))
        and _url_on_host(v, host)
    )


def _compile_product_re(v) -> Optional[re.Pattern]:
    if not isinstance(v, str) or not v or len(v) > MAX_PATTERN_CHARS:
        return None
    try:
        # the old tables compiled every pattern with exactly re.I
        return re.compile(v, re.IGNORECASE)
    except re.error:
        return None


def _valid_product_examples(v) -> list:
    if not isinstance(v, list):
        return []
    keep = []
    for p in v:
        if isinstance(p, str) and p.startswith("/") and 1 < len(p) <= 300 and p not in keep:
            keep.append(p)
    return keep[:MAX_PRODUCT_EXAMPLES]


class SiteHints:
    """Seed + overlay hint store. overlay_path=None -> seed-only, no overlay IO."""

    def __init__(self, overlay_path=None, seed_path=None) -> None:
        self.seed_path = Path(seed_path) if seed_path is not None else SEED_PATH
        self.overlay_path = Path(overlay_path) if overlay_path is not None else None
        self._seed: Optional[dict] = None      # lazy; host -> sanitized entry
        self._overlay: dict = {}
        self._overlay_stamp = None             # (mtime_ns, size) of the loaded file

    # ---- loading -------------------------------------------------------------
    def _sanitize(self, hosts, origin: str) -> dict:
        clean: dict = {}
        dropped = 0
        for host, entry in (hosts or {}).items():
            if not _valid_host(host) or not isinstance(entry, dict):
                dropped += 1
                continue
            e: dict = {}
            v = entry.get("search_url")
            if v is not None:
                if _valid_search_url(v, host):
                    e["search_url"] = v
                else:
                    dropped += 1
            v = entry.get("cart_url")
            if v is not None:
                if _valid_cart_url(v, host):
                    e["cart_url"] = v
                else:
                    dropped += 1
            v = entry.get("product_url_re")
            if v is not None:
                pat = _compile_product_re(v)
                if pat is not None:
                    e["product_url_re"] = v
                    e["_product_pattern"] = pat
                else:
                    dropped += 1
            examples = _valid_product_examples(entry.get("product_url_examples"))
            if examples:
                e["product_url_examples"] = examples
            if e:
                clean[host] = e
        if dropped:
            log.warning("site_hints %s: dropped %d invalid host(s)/field(s); valid fields kept", origin, dropped)
        return clean

    def _load_seed(self) -> dict:
        if self._seed is None:
            try:
                raw = json.loads(self.seed_path.read_text())
                self._seed = self._sanitize((raw or {}).get("hosts"), "seed")
            except Exception as exc:  # a data file must never kill an engine boot
                log.warning("site_hints seed unreadable (%s); known-host hints disabled", exc)
                self._seed = {}
        return self._seed

    def _refresh_overlay(self) -> None:
        if self.overlay_path is None:
            return
        try:
            st = self.overlay_path.stat()
            stamp = (st.st_mtime_ns, st.st_size)
        except OSError:
            self._overlay, self._overlay_stamp = {}, None
            return
        if stamp == self._overlay_stamp:
            return
        try:
            raw = json.loads(self.overlay_path.read_text())
            hosts = (raw or {}).get("hosts") if isinstance(raw, dict) else None
            if not isinstance(hosts, dict):
                raise ValueError("overlay must be an object with a 'hosts' object")
            self._overlay = self._sanitize(hosts, "overlay")
            self._overlay_stamp = stamp
        except Exception as exc:
            # fail toward the seed, honestly: set the unreadable file aside (never
            # silently delete it) and serve seed-only until something relearns
            corrupt = self.overlay_path.with_suffix(self.overlay_path.suffix + ".corrupt")
            try:
                self.overlay_path.rename(corrupt)
                log.warning("site_hints overlay corrupt (%s); set aside at %s; seed-only", exc, corrupt)
            except OSError:
                log.warning("site_hints overlay corrupt (%s); could not set it aside; seed-only", exc)
            self._overlay, self._overlay_stamp = {}, None

    # ---- lookup ----------------------------------------------------------------
    def _entry(self, url: str) -> dict:
        host = host_of(url)
        if not host:
            return {}
        seed = self._load_seed()
        self._refresh_overlay()
        best = ""
        for domain in set(seed) | set(self._overlay):
            if host == domain:
                best = domain
                break
            if host.endswith("." + domain) and len(domain) > len(best):
                best = domain
        if not best:
            return {}
        entry = dict(seed.get(best) or {})
        entry.update(self._overlay.get(best) or {})
        return entry

    def search_url(self, start_url: str, item: str) -> str:
        template = self._entry(start_url).get("search_url") or ""
        if not template:
            return ""
        return template.format(q=urllib.parse.quote_plus(item))

    def cart_url(self, start_url: str) -> str:
        return self._entry(start_url).get("cart_url") or ""

    def product_pattern(self, url: str) -> Optional[re.Pattern]:
        return self._entry(url).get("_product_pattern")

    # ---- learned write-back ------------------------------------------------------
    def learn(self, host: str, *, cart_url=None, search_url=None,
              product_url_examples=None) -> bool:
        """Persist verified facts for a host into the overlay. Returns False and
        never raises when there is no overlay path, nothing validates, or nothing
        is new (a fact already served by seed+overlay is not rewritten) — the
        browse path must not crash on hint IO, and an invalid fact must never be
        stored. Write is atomic (tmp + os.replace, the repo's persistence law)."""
        if self.overlay_path is None or not _valid_host(host):
            return False
        self._load_seed()
        self._refresh_overlay()
        effective = dict((self._seed or {}).get(host) or {})
        effective.update(self._overlay.get(host) or {})
        current = dict(self._overlay.get(host) or {})
        changed = False
        if cart_url is not None and _valid_cart_url(cart_url, host) \
                and effective.get("cart_url") != cart_url:
            current["cart_url"] = cart_url
            changed = True
        if search_url is not None and _valid_search_url(search_url, host) \
                and effective.get("search_url") != search_url:
            current["search_url"] = search_url
            changed = True
        if product_url_examples:
            known = list(effective.get("product_url_examples") or [])
            merged = list(current.get("product_url_examples") or [])
            for p in _valid_product_examples(product_url_examples):
                if p not in known and p not in merged:
                    merged.append(p)
                    changed = True
            if merged:
                current["product_url_examples"] = merged[-MAX_PRODUCT_EXAMPLES:]
        if not changed:
            return False
        overlay = {h: {k: v for k, v in e.items() if not k.startswith("_")}
                   for h, e in self._overlay.items()}
        overlay[host] = {k: v for k, v in current.items() if not k.startswith("_")}
        payload = {"version": 1, "hosts": overlay}
        try:
            self.overlay_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.overlay_path.with_suffix(self.overlay_path.suffix + ".tmp")
            tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            os.replace(tmp, self.overlay_path)
        except OSError as exc:
            log.warning("site_hints learn write failed (%s); hint not persisted", exc)
            return False
        self._overlay_stamp = None      # reload from what was actually written
        self._refresh_overlay()
        return True


# ---- module store (explicit wiring; ControlCore owns the overlay path) ----------
_STORE = SiteHints()


def configure(overlay_path) -> None:
    """Wire the runtime overlay path (ControlCore passes <data>/site_hints.json).
    Explicit like pending_path/deferred_path — agent code never reads env and never
    invents a default path. The module store is process-global, so the last
    constructed core owns it (the same semantics an env var would have); pass None
    to drop back to seed-only."""
    global _STORE
    new_path = Path(overlay_path) if overlay_path is not None else None
    if _STORE.overlay_path != new_path:
        _STORE = SiteHints(overlay_path=new_path)


def store() -> SiteHints:
    return _STORE
