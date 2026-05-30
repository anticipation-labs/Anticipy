"""Sector detector.

Given a coldstart dossier dict, score each candidate sector based on
distinctive signal hits in the dossier (signed-in tabs, top-emailed
addresses, calendar event titles, recent threads, browser history).
Return the sector with the highest hit count, or ``generic`` if nothing
scores above the threshold.

Scoring works in two passes:

  1. For each sector, build a keyword bag from ``common_tools`` and
     salient phrases (2-3 grams) pulled out of ``detection_signals``.
  2. Drop any keyword that appears in more than one sector's bag (it
     is not distinctive). What is left is the per-sector distinctive
     keyword set. The generic profile contributes here too, so tools
     like "Amazon" or "Gmail" that live in both vertical and generic
     bags get filtered from BOTH and stop driving any decision.

The match is then a substring or word-boundary search against the
flattened dossier text. The detector NEVER hardcodes "if dossier
contains X then sector = Y" branches; it reads everything from the
YAML profiles.

Confidence: a sector wins if it has the most hits and either has at
least 2 hits or a (hits / distinctive_total) ratio of 0.3+. Otherwise
the fallback is ``generic``.
"""

from __future__ import annotations

import re
import threading
from typing import Any, Iterable

from .loader import KNOWN_SECTORS, load_hints

# Minimum (matched / distinctive_total) ratio for a sector to beat generic
# when it only has a single hit. With 2+ hits this floor does not apply.
_MIN_CONFIDENCE = 0.3

# Words that should never be treated as a sector keyword on their own
# (too generic, too short, or scaffolding from the signal sentences).
_STOPWORDS = frozenset(
    {
        # articles / prepositions / conjunctions
        "a", "an", "the", "and", "or", "but", "if", "of", "to", "for",
        "in", "on", "at", "by", "with", "from", "into", "over", "than",
        "out", "off", "up", "down", "as", "is", "are", "was", "were",
        "be", "been", "being", "do", "does", "did", "this", "that",
        "these", "those", "their", "theirs", "them", "they", "it",
        "its", "his", "her", "hers", "him", "she", "he",
        # signal sentence scaffolding
        "tab", "tabs", "scraped", "signed", "browser", "history",
        "active", "recent", "open", "frequent", "session", "sessions",
        "portal", "portals", "dashboard", "dashboards", "account",
        "accounts", "page", "pages", "url", "title", "email", "emails",
        "calendar", "event", "events", "during", "across",
        "vertical", "verticals", "tools", "tool", "signal", "signals",
        "data", "user", "users", "limited", "no", "any", "all", "many",
        "few", "some", "specialty",
        # extension / domain noise
        "com", "co", "io", "net", "org", "ai", "gov", "edu", "app",
        "www", "https", "http", "html",
        # number words / units
        "two", "three", "four", "five", "six", "seven", "eight", "nine",
        "ten", "twenty", "thirty", "fifty", "hundred",
        "year", "years", "day", "days", "week", "weeks",
        "month", "months", "minute", "minutes", "hour", "hours",
        "ago", "before", "after", "next", "last", "first",
        # vague nouns
        "company", "companies", "people", "person", "team", "owner",
        "manager", "lead",
        "site", "sites", "places", "stuff", "kind", "kinds", "type",
        "types", "thing", "things",
        # adjectives / generic descriptors
        "new", "old", "first", "next", "low", "high", "small", "large",
        "very", "less", "more", "good", "bad", "personal", "mixed",
        "casual", "professional", "single", "strong", "weak", "without",
        "where", "what", "who", "looking", "running", "still",
        "around", "back", "every", "each",
        "etc", "and",
        # human role nouns that sneak in
        "engineer", "engineers", "engineering", "team", "user",
        "shopping", "reading", "habits", "downloads", "download",
        # punctuation-stripped artifacts
        "freq", "freqs",
    }
)


def _normalize(s: str) -> str:
    """Lowercase and collapse non-alphanumerics to single spaces."""
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _phrases_from_signal(signal: str) -> list[str]:
    """Pull distinctive 2-3 word grams from a signal string.

    1-grams are excluded because lone words like "amazon" or "inbox"
    appear in multiple profiles' tool lists and would cause false
    cross-sector matches. The dedup-across-sectors pass would catch
    most of those, but skipping them at extraction is cheaper and
    keeps the keyword bag focused.
    """
    norm = _normalize(signal)
    if not norm:
        return []
    words = norm.split()
    grams: list[str] = []
    n = len(words)
    for i in range(n):
        # 2-grams
        if i + 1 < n:
            two = (words[i], words[i + 1])
            if not all(t in _STOPWORDS for t in two):
                grams.append(" ".join(two))
        # 3-grams
        if i + 2 < n:
            three = (words[i], words[i + 1], words[i + 2])
            non_stop = [t for t in three if t not in _STOPWORDS]
            if len(non_stop) >= 2:
                grams.append(" ".join(three))
    # dedupe preserving order
    seen: set[str] = set()
    out: list[str] = []
    for g in grams:
        if g not in seen:
            seen.add(g)
            out.append(g)
    return out


def _sector_keywords_raw(sector_name: str) -> list[str]:
    """All candidate keywords for a sector before distinctive filtering."""
    hints = load_hints(sector_name)
    kw: dict[str, None] = {}
    for tool in hints.get("common_tools", []):
        norm = _normalize(tool)
        if not norm:
            continue
        # tools are taken whole (multi-word stays multi-word, single
        # words are kept; the dedup pass below removes any that show
        # up in multiple sectors).
        if norm not in _STOPWORDS:
            kw[norm] = None
    for sig in hints.get("detection_signals", []):
        for g in _phrases_from_signal(sig):
            kw[g] = None
    return list(kw.keys())


_DISTINCT_CACHE: dict[str, list[str]] = {}
_DISTINCT_LOCK = threading.Lock()


def _build_distinctive_keywords() -> dict[str, list[str]]:
    """Compute per-sector keywords that don't appear in any other sector."""
    raw_per_sector: dict[str, list[str]] = {
        n: _sector_keywords_raw(n) for n in KNOWN_SECTORS
    }
    # count how many sectors each keyword shows up in
    counts: dict[str, int] = {}
    for kws in raw_per_sector.values():
        for kw in set(kws):
            counts[kw] = counts.get(kw, 0) + 1
    distinctive: dict[str, list[str]] = {}
    for name, kws in raw_per_sector.items():
        distinctive[name] = [kw for kw in kws if counts.get(kw, 0) == 1]
    return distinctive


def _sector_keywords(sector_name: str) -> list[str]:
    """Return the cached distinctive keyword list for a sector.

    Thread-safe; computes once across all sectors and caches.
    """
    with _DISTINCT_LOCK:
        if not _DISTINCT_CACHE:
            for name, kws in _build_distinctive_keywords().items():
                _DISTINCT_CACHE[name] = kws
        return _DISTINCT_CACHE.get(sector_name, [])


def _reset_keyword_cache() -> None:
    """Test hook to clear the distinctive-keyword cache."""
    with _DISTINCT_LOCK:
        _DISTINCT_CACHE.clear()


def _dossier_haystack(dossier: dict[str, Any]) -> str:
    """Flatten dossier text content into one searchable, normalized string."""
    if not isinstance(dossier, dict):
        return ""
    pieces: list[str] = []

    def _walk(obj: Any) -> None:
        if isinstance(obj, str):
            pieces.append(obj)
        elif isinstance(obj, dict):
            for k, v in obj.items():
                if isinstance(k, str):
                    pieces.append(k)
                _walk(v)
        elif isinstance(obj, (list, tuple, set)):
            for item in obj:
                _walk(item)
        elif isinstance(obj, (int, float, bool)) or obj is None:
            return
        else:
            pieces.append(str(obj))

    _walk(dossier)
    return _normalize(" ".join(pieces))


def _count_hits(keywords: Iterable[str], haystack: str) -> int:
    """Count how many distinct keywords appear in the haystack."""
    if not haystack:
        return 0
    hits = 0
    for kw in keywords:
        if not kw:
            continue
        # multi-word phrases: substring search (haystack is space-normalized)
        if " " in kw:
            if kw in haystack:
                hits += 1
        else:
            # single tokens: word-boundary match to avoid partial collisions
            pat = re.compile(rf"\b{re.escape(kw)}\b")
            if pat.search(haystack):
                hits += 1
    return hits


def _score_sector(sector_name: str, haystack: str) -> tuple[int, int, float]:
    """Return (hits, distinctive_total, ratio) for a sector."""
    keywords = _sector_keywords(sector_name)
    if not keywords:
        return (0, 0, 0.0)
    hits = _count_hits(keywords, haystack)
    ratio = hits / len(keywords)
    return (hits, len(keywords), ratio)


def detect_sector(dossier: dict[str, Any] | None) -> str:
    """Pick the best matching sector for a dossier.

    Returns one of the nine names in ``KNOWN_SECTORS``. If no concrete
    sector scores above the confidence threshold, returns ``generic``.
    """
    if not dossier:
        return "generic"
    haystack = _dossier_haystack(dossier)
    if not haystack:
        return "generic"

    best_name = "generic"
    best_hits = 0
    best_ratio = 0.0

    for name in KNOWN_SECTORS:
        if name == "generic":
            continue
        hits, _total, ratio = _score_sector(name, haystack)
        if hits == 0:
            continue
        if hits > best_hits or (hits == best_hits and ratio > best_ratio):
            best_name = name
            best_hits = hits
            best_ratio = ratio

    if best_hits == 0:
        return "generic"
    # Require at least 2 distinctive hits OR a 0.3+ confidence ratio
    # when only one keyword landed. Otherwise we treat the signal as
    # too weak and fall back to generic.
    if best_hits >= 2 or best_ratio >= _MIN_CONFIDENCE:
        return best_name
    return "generic"
