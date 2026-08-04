"""The server-side research arm (roadmap §6).

Read-only goals never touch the owner's browser. The 2026-08-02 tab flood
happened because ALL work — even "look up opening hours" — ran through the
paired Chrome extension on his machine. Research belongs here, in the
worker: Brave Search for candidate pages, a plain fetch for the top few,
and the LLM to summarize with citations. The extension keeps only the jobs
that genuinely need HIS logged-in browser (bookings, forms, purchases),
always behind the confirmation gate.

No key, no drama: without BRAVE_API_KEY the caller routes the job to the
browser lane instead — this module never crashes the worker over a missing
secret, and never logs one either.
"""
from __future__ import annotations

import json
import re
from html import unescape
from typing import Callable, Optional

import requests

BRAVE_URL = "https://api.search.brave.com/res/v1/web/search"

# Descriptions alone answer many questions; reading more than a few pages is
# latency without new evidence.
TOP_RESULTS = 5
PAGES_TO_READ = 3
PAGE_CHARS = 4000

RESEARCH_SYSTEM = """You are Anticipy's research arm, answering the owner's
question from web sources gathered for you. Use ONLY the numbered sources
given — never your own knowledge, and never invent an hour, a price, a date
or a name that a source does not state. Answer in 2-5 plain sentences,
specifics first, citing the source number in square brackets after each
claim, e.g. "Open until 5pm daily [2]." If the sources disagree, say which
says what. If they do not contain the answer, say plainly what you did and
did not find. No preamble, no headings — just the answer."""

# The search query is the goal minus its instruction verb — Brave does better
# with "opening hours of the Vancouver aquarium" than with "research: opening
# hours of the Vancouver aquarium".
_QUERY_PREFIX = re.compile(
    r"^\s*(research|look\s*up|find(?:\s+out)?|check|search(?:\s+for)?|"
    r"compare|price|tell\s+me(?:\s+about)?)\s*[:\-—]?\s+",
    re.IGNORECASE)


def query_from_goal(goal: str) -> str:
    g = (goal or "").strip()
    return _QUERY_PREFIX.sub("", g, count=1).strip() or g


class BraveClient:
    """Thin Brave Search wrapper — injectable so tests never hit the network."""

    def __init__(self, api_key: str):
        self._key = api_key

    def search(self, query: str, count: int = TOP_RESULTS) -> list[dict]:
        r = requests.get(
            BRAVE_URL,
            params={"q": query, "count": count},
            headers={"X-Subscription-Token": self._key,
                     "Accept": "application/json"},
            timeout=15,
        )
        r.raise_for_status()
        out = []
        for item in ((r.json().get("web") or {}).get("results") or [])[:count]:
            url = (item.get("url") or "").strip()
            if not url:
                continue
            # Brave decorates descriptions with <strong> markers.
            desc = unescape(re.sub(r"<[^>]+>", "", item.get("description") or ""))
            out.append({"title": (item.get("title") or "").strip(),
                        "url": url, "description": desc.strip()})
        return out

    def __repr__(self):  # the key must never ride into a log line via repr
        return "BraveClient(key=…)"


def fetch_page(url: str) -> str:
    """Visible text of one page, best effort. Empty string on any failure —
    a page that will not load is a missing source, not a crashed job."""
    try:
        r = requests.get(url, timeout=12, headers={
            "User-Agent": "Mozilla/5.0 (compatible; AnticipyResearch/1.0)"})
        if not r.ok or "html" not in (r.headers.get("content-type") or "html"):
            return ""
        html = re.sub(r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>",
                      " ", r.text)
        text = unescape(re.sub(r"(?s)<[^>]+>", " ", html))
        return re.sub(r"\s+", " ", text).strip()[:PAGE_CHARS]
    except Exception:
        return ""


def _summarize(query: str, sources: list[dict], llm=None) -> str:
    if llm is not None and getattr(llm, "live", False):
        try:
            res = llm.chat(RESEARCH_SYSTEM,
                           json.dumps({"question": query, "sources": [
                               {"n": s["n"], "title": s["title"],
                                "url": s["url"], "content": s["content"]}
                               for s in sources]}))
            text = (res.text or "").strip()
            if text:
                return text
        except Exception as e:
            print(f"research: summarize failed ({type(e).__name__}) — "
                  "falling back to the sources' own words")
    # No model (or a broken one): the honest fallback is the sources' own
    # words, attributed — never an invented sentence.
    parts = []
    for s in sources[:3]:
        snippet = (s.get("description") or s.get("content") or "")[:280].strip()
        if snippet:
            parts.append(f"{snippet} [{s['n']}]")
    return " ".join(parts) or f"Couldn't read anything useful about: {query}"


def run_research(goal: str, params: Optional[dict] = None, llm=None,
                 brave: Optional[BraveClient] = None,
                 fetcher: Callable[[str], str] = fetch_page,
                 api_key: Optional[str] = None) -> dict:
    """One research job, end to end: search -> read -> summarize with
    citations. Returns {"ok": bool, "result": str} and never raises — a
    crashed pass would leave the job stuck at `running` forever."""
    query = query_from_goal(goal)
    client = brave or (BraveClient(api_key) if api_key else None)
    if client is None:
        return {"ok": False, "result": "No search backend is configured."}
    try:
        results = client.search(query)
    except Exception as e:
        # Log the class only: exception text can quote the request, and
        # nothing from this call belongs in a log beyond "it failed".
        print(f"research: search failed ({type(e).__name__})")
        return {"ok": False, "result": f"Search failed for: {query}"}
    if not results:
        return {"ok": False, "result": f"Found nothing for: {query}"}
    sources = []
    for i, res in enumerate(results, 1):
        content = fetcher(res["url"]) if i <= PAGES_TO_READ else ""
        sources.append({"n": i, "title": res["title"], "url": res["url"],
                        "description": res["description"],
                        "content": content or res["description"]})
    summary = _summarize(query, sources, llm=llm)
    listed = "\n".join(f"[{s['n']}] {s['title']} — {s['url']}" for s in sources)
    return {"ok": True, "result": f"{summary}\n\nSources:\n{listed}"}
