#!/usr/bin/env python3
"""Parse visible-page text scraped from a bot-detection probe site.

Invoked by scripts/v7/bot_detection_canary.sh.
Usage: _bot_detection_parse.py <text_file> <slug>
Emits JSON on stdout with verdict in {REAL_HUMAN_BROWSER, BOT_DETECTED,
INCONCLUSIVE, INCONCLUSIVE_NO_TEXT, UNKNOWN}.
"""
from __future__ import annotations
import json, re, sys
from pathlib import Path


def parse(text: str, slug: str) -> dict:
    low = text.lower()
    hits: dict = {}
    verdict = "UNKNOWN"
    reason = ""
    if slug == "sannysoft":
        passed = len(re.findall(r"\bpassed\b", low))
        failed = len(re.findall(r"\bfailed\b", low))
        hits = {
            "rows_passed": passed,
            "rows_failed": failed,
            "missing_image_rows": len(re.findall(r"missing image", low)),
            "present_rows": len(re.findall(r"\bpresent\b", low)),
            "webdriver_new_mentioned": "webdriver (new)" in low,
        }
        if passed > 0 and failed <= 2:
            verdict, reason = "REAL_HUMAN_BROWSER", f"passed={passed} failed={failed}"
        elif failed > passed:
            verdict, reason = "BOT_DETECTED", f"failed={failed} >= passed={passed}"
        elif passed + failed == 0:
            verdict = "INCONCLUSIVE_NO_TEXT"
        else:
            verdict, reason = "INCONCLUSIVE", f"passed={passed} failed={failed}"
    elif slug == "areyouheadless":
        m_false = bool(re.search(r"are you headless\??\s*[:\-]?\s*false", low))
        m_true = bool(re.search(r"are you headless\??\s*[:\-]?\s*true", low))
        not_h = ("you are not chrome headless" in low) or ("not chrome headless" in low)
        is_h = ("you are chrome headless" in low) and not not_h
        hits = {"match_false": m_false, "match_true": m_true,
                "you_are_not_headless": not_h, "you_are_headless": is_h}
        if m_false or not_h:
            verdict, reason = "REAL_HUMAN_BROWSER", "site says headless=false"
        elif m_true or is_h:
            verdict, reason = "BOT_DETECTED", "site says headless=true"
        else:
            verdict = "INCONCLUSIVE"
    elif slug == "creepjs":
        trust = re.search(r"trust\s*score[^0-9%]*([0-9]{1,3})\s*%?", low)
        # creepjs Headless section emits e.g. "0% headless" / "0% stealth".
        # High percentages here = bot-like; 0% = clean.
        m_headless_pct = re.search(r"(\d{1,3})\s*%\s*headless\b", low)
        m_stealth_pct = re.search(r"(\d{1,3})\s*%\s*stealth\b", low)
        bot_terms = sum(low.count(t) for t in ("bot", "headless", "automation"))
        score = int(trust.group(1)) if trust else None
        hl_pct = int(m_headless_pct.group(1)) if m_headless_pct else None
        st_pct = int(m_stealth_pct.group(1)) if m_stealth_pct else None
        page_rendered = bool(re.search(r"\bfp\s*id\b", low))
        hits = {"trust_score_pct": score, "headless_pct": hl_pct,
                "stealth_pct": st_pct, "page_rendered": page_rendered,
                "bot_term_hits": bot_terms}
        if score is not None and score >= 60:
            verdict, reason = "REAL_HUMAN_BROWSER", f"trust_score={score}%"
        elif score is not None and score < 30:
            verdict, reason = "BOT_DETECTED", f"trust_score={score}%"
        elif hl_pct is not None and st_pct is not None and hl_pct <= 10 and st_pct <= 10:
            verdict, reason = "REAL_HUMAN_BROWSER", \
                f"headless={hl_pct}% stealth={st_pct}%"
        elif (hl_pct is not None and hl_pct >= 50) or (st_pct is not None and st_pct >= 50):
            verdict, reason = "BOT_DETECTED", \
                f"headless={hl_pct}% stealth={st_pct}%"
        elif page_rendered and bot_terms <= 6:
            verdict, reason = "REAL_HUMAN_BROWSER", "page rendered, low bot mentions"
        else:
            verdict = "INCONCLUSIVE"
    return {"slug": slug, "verdict": verdict, "reason": reason,
            "hits": hits, "text_chars": len(text)}


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: _bot_detection_parse.py <text_file> <slug>", file=sys.stderr)
        return 2
    p = Path(sys.argv[1])
    text = p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""
    print(json.dumps(parse(text, sys.argv[2])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
