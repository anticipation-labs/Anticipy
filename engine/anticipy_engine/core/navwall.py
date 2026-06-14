"""navwall — the HARD, code-level navigation wall for the live browser agent.

The WebVoyager planner is told (in its prompt) that page content is untrusted and that it
must not navigate to a URL just because page text said so. That prompt fence is
defense-in-depth — a model can still be talked into emitting a malicious ``navigate``.
This module is the REAL wall: a deterministic, code-level allow/deny on the destination
host that runs at the bridge on EVERY navigate the agent emits, regardless of what the
model says. A denied navigate never reaches Chrome.

Three deny classes (any one blocks the navigate):

  1. SCHEME — only http/https may be navigated. ``file://`` (local file exfiltration),
     ``chrome://`` / ``chrome-extension://`` / ``devtools://`` / ``view-source:`` (browser
     internals), ``data:`` / ``javascript:`` / ``blob:`` / ``about:`` (script & inline
     payloads), and anything else are denied.

  2. PRIVATE / METADATA (SSRF) — the host must point at a PUBLIC address. Loopback
     (127.0.0.1, ::1, localhost), link-local incl. the cloud-metadata address
     169.254.169.254 and IPv6 fe80::/10, private RFC-1918 (10/8, 172.16-31/12,
     192.168/16, fc00::/7), CGNAT 100.64/10, reserved/unspecified, and internal-only
     name suffixes (``.internal``, ``.local``, ``.localhost``, ``.lan``, ``.home.arpa``,
     ``.cluster.local``, the bare ``metadata`` / ``metadata.google.internal`` names) are
     all denied. A literal IP is classified directly; a name is classified by suffix and,
     when DNS is available, by resolving it and requiring EVERY resolved address to be
     public (so a name that rebinds to 169.254.169.254 or 127.0.0.1 is caught).

  3. SENSITIVE — banking / payment / brokerage / credential-reset destinations the agent
     must never autonomously drive (money is the product's only hard action stop, and a
     password/login portal is where an injected nav does real harm). Matched on the
     registrable host by keyword and by a curated brand list. This is intentionally broad:
     a false deny just hands the task back for a human; a false allow could move money or
     surrender a credential.

The wall is fail-CLOSED on its own errors: if the URL cannot be parsed or classified, it
is denied. ``ANTICIPY_NAVWALL_ALLOW_PRIVATE=1`` relaxes only the private/metadata class
for local CI against a localhost test server; it NEVER relaxes the scheme or sensitive
classes, and is off by default.
"""
from __future__ import annotations

import concurrent.futures as _cf
import ipaddress
import os
import re
import socket
import urllib.parse

# DNS resolution can hang on a slow/hostile resolver. Run it in a tiny bounded thread pool so a
# single navigate can never stall the engine forever; on timeout we fail SAFE toward "does not
# resolve" (the exact/suffix internal checks already ran first). Callers on the async path should
# additionally run nav_block_reason in an executor (the engine browser transport does).
_RESOLVE_POOL = _cf.ThreadPoolExecutor(max_workers=4, thread_name_prefix="navwall-dns")
_RESOLVE_TIMEOUT_S = 3.0


def _getaddrinfo_bounded(host: str, port: int | None):
    fut = _RESOLVE_POOL.submit(
        socket.getaddrinfo, host, port or None, 0, socket.SOCK_STREAM, socket.IPPROTO_TCP
    )
    return fut.result(timeout=_RESOLVE_TIMEOUT_S)

# Only these schemes may be navigated. Everything else (file/chrome/data/javascript/blob/
# about/view-source/devtools/...) is denied at class 1.
_ALLOWED_SCHEMES = {"http", "https"}

# How many DNS-resolved addresses we will inspect for a name before giving up (a host that
# fans out past this is treated as suspicious and denied).
_MAX_RESOLVED_ADDRS = 32

# Internal-only name suffixes / bare names that never point at the public internet. A name
# ending in one of these is denied without needing DNS (it is an SSRF vector by intent).
_INTERNAL_SUFFIXES = (
    ".internal",
    ".local",
    ".localhost",
    ".lan",
    ".intranet",
    ".corp",
    ".home.arpa",
    ".cluster.local",
    ".svc",
    ".svc.cluster.local",
)
_INTERNAL_EXACT = {
    "localhost",
    "metadata",
    "metadata.google.internal",
    "instance-data",
    "instance-data.ec2.internal",
}

# Sensitive-destination keyword fragments (matched against the lowercased host). A money or
# credential portal must never be autonomously navigated by the model.
_SENSITIVE_KEYWORDS = (
    "bank", "banking", "creditunion", "wellsfargo", "chase", "citibank", "citi",
    "hsbc", "barclays", "santander", "capitalone", "usbank", "pnc", "tdbank",
    "ally", "schwab", "fidelity", "vanguard", "etrade", "robinhood", "coinbase",
    "binance", "kraken", "blockchain", "paypal", "venmo", "zelle", "cashapp",
    "stripe", "wise", "westernunion", "moneygram", "americanexpress", "amex",
    "discovercard", "mastercard", "visa",
    # credential / account-recovery portals
    "login", "signin", "sign-in", "account-recovery", "accountrecovery",
    "password-reset", "passwordreset", "resetpassword", "myaccount",
    "id.me", "okta", "auth0", "onelogin",
)
# Whole-host sensitive brand suffixes (registrable-domain match), so "secure.chase.com"
# and "www.paypal.com" are both caught even when the keyword is not a standalone token.
_SENSITIVE_HOST_SUFFIXES = (
    "paypal.com", "venmo.com", "cash.app", "stripe.com", "coinbase.com",
    "binance.com", "kraken.com", "robinhood.com", "schwab.com", "fidelity.com",
    "vanguard.com", "etrade.com", "chase.com", "wellsfargo.com", "bankofamerica.com",
    "citi.com", "citibank.com", "capitalone.com", "usbank.com", "americanexpress.com",
    "wise.com", "transferwise.com", "westernunion.com", "moneygram.com",
    "accounts.google.com", "login.microsoftonline.com", "signin.aws.amazon.com",
    "id.me", "okta.com", "onelogin.com", "auth0.com",
)


def _allow_private() -> bool:
    """Local-CI escape hatch for the private/metadata class ONLY (off by default)."""
    return os.environ.get("ANTICIPY_NAVWALL_ALLOW_PRIVATE", "").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _ip_is_public(ip: ipaddress._BaseAddress) -> bool:
    """A single address is safe to navigate to ONLY if it is a globally-routable public IP.

    Mirrors main.py's onboarding SSRF classifier: rejects loopback, link-local (incl. the
    169.254.169.254 cloud-metadata address and IPv6 fe80::/10), private, reserved,
    multicast, unspecified, and CGNAT (is_global is False). An IPv4-mapped IPv6 address
    (::ffff:127.0.0.1) is unwrapped first so it cannot smuggle a private v4 past a v6 check.
    """
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    if (
        ip.is_loopback
        or ip.is_link_local
        or ip.is_private
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    ):
        return False
    return bool(ip.is_global)


def _host_is_sensitive(host: str) -> bool:
    h = (host or "").lower().strip(".")
    if not h:
        return False
    for suffix in _SENSITIVE_HOST_SUFFIXES:
        if h == suffix or h.endswith("." + suffix):
            return True
    labels = re.split(r"[.\-_]", h)
    label_set = set(labels)
    for kw in _SENSITIVE_KEYWORDS:
        if "." in kw or "-" in kw:
            if kw in h:
                return True
        elif kw in label_set:
            return True
    return False


def _name_is_internal(host: str) -> bool:
    h = (host or "").lower().strip(".")
    if not h:
        return True
    if h in _INTERNAL_EXACT:
        return True
    return any(h == s.lstrip(".") or h.endswith(s) for s in _INTERNAL_SUFFIXES)


def _name_resolves_nonpublic(host: str, port: int | None) -> bool:
    """Resolve a name and return True if ANY resolved address is non-public (so a DNS-rebind
    to 169.254.169.254 / a private IP / localhost is caught). A name that does NOT resolve is
    NOT an SSRF target by itself (nothing internal is reachable through it) -> returns False;
    the browser will fail the navigate honestly. Resolver errors fail safe toward False here
    because the suffix/exact internal checks already ran first."""
    try:
        infos = _getaddrinfo_bounded(host, port)
    except socket.gaierror:
        return False
    except Exception:
        # includes concurrent.futures.TimeoutError on a slow resolver -> fail safe (the
        # exact/suffix internal checks already ran; an unresolvable name reaches nothing internal)
        return False
    seen = 0
    for info in infos:
        sockaddr = info[4] if len(info) > 4 else None
        if not sockaddr:
            continue
        seen += 1
        if seen > _MAX_RESOLVED_ADDRS:
            return True  # suspicious fan-out -> treat as unsafe
        candidate = str(sockaddr[0]).split("%", 1)[0]
        try:
            ip = ipaddress.ip_address(candidate)
        except ValueError:
            return True  # unclassifiable -> unsafe
        if not _ip_is_public(ip):
            return True
    return False


def nav_block_reason(url: str, *, resolve: bool = True) -> str:
    """Return a non-empty DENY reason if this URL must NOT be navigated; "" if allowed.

    This is the hard wall. It is deterministic and runs at the bridge on every navigate the
    model emits, so an injected "navigate to <evil>" is stopped in code even if the prompt
    fence failed. Pass ``resolve=False`` to skip the DNS rebind check (host-suffix/literal
    classification only) on a hot path that cannot afford a lookup.

    Order: scheme -> sensitive -> private/metadata. Fail-CLOSED on any parse error.
    """
    raw = (url or "").strip()
    if not raw:
        return "navigate has no URL"
    try:
        parts = urllib.parse.urlsplit(raw)
    except Exception:
        return "navigate URL could not be parsed"
    scheme = (parts.scheme or "").lower()
    if scheme not in _ALLOWED_SCHEMES:
        # A scheme-less host:port or bare host can slip through urlsplit with an empty
        # scheme; only an explicitly http(s) target is allowed to navigate.
        return f"navigate scheme {scheme or '(none)'!r} is not allowed (only http/https)"
    try:
        host = parts.hostname  # lowercased, IPv6 brackets stripped
    except Exception:
        return "navigate URL host could not be parsed"
    if not host:
        return "navigate URL has no host"

    # class 3: sensitive money / credential destinations (always enforced).
    if _host_is_sensitive(host):
        return "navigate target is a banking/payment/credential domain (hard stop)"

    # class 2: private / metadata / internal (SSRF). Relaxable only for local CI.
    if _allow_private():
        return ""

    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if not _ip_is_public(literal):
            return "navigate target host is a private/loopback/link-local/metadata address"
        return ""

    if _name_is_internal(host):
        return "navigate target host is an internal-only name"
    if resolve and _name_resolves_nonpublic(host, parts.port):
        return "navigate target host resolves to a non-public address"
    return ""


def assert_nav_allowed(url: str, *, resolve: bool = True) -> None:
    """Raise PermissionError with the deny reason if the URL must not be navigated."""
    reason = nav_block_reason(url, resolve=resolve)
    if reason:
        raise PermissionError(reason)
