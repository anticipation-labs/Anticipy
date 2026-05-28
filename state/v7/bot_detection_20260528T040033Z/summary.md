# Bot detection canary 20260528T040033Z

Bridge: http://127.0.0.1:7777
CDP: http://127.0.0.1:9222
Wait per site: 15s

## Per-site verdicts

| site | verdict | reason |
|---|---|---|
| sannysoft | REAL_HUMAN_BROWSER | passed=4 failed=0 |
| areyouheadless | NAV_FAILED | bridge navigate failed |
| creepjs | REAL_HUMAN_BROWSER | headless=0% stealth=0% |

## Headline

Anticipy drives real Chrome and appears as: [REAL HUMAN BROWSER]

(real=2 bot=0 inconclusive=1)

## Signals flagged

### sannysoft

```json
{
  "slug": "sannysoft",
  "verdict": "REAL_HUMAN_BROWSER",
  "reason": "passed=4 failed=0",
  "hits": {
    "rows_passed": 4,
    "rows_failed": 0,
    "missing_image_rows": 0,
    "present_rows": 1,
    "webdriver_new_mentioned": false
  },
  "text_chars": 15354
}

```

### areyouheadless

```json
{
  "slug": "areyouheadless",
  "verdict": "NAV_FAILED",
  "reason": "bridge_navigate"
}

```

### creepjs

```json
{
  "slug": "creepjs",
  "verdict": "REAL_HUMAN_BROWSER",
  "reason": "headless=0% stealth=0%",
  "hits": {
    "trust_score_pct": null,
    "headless_pct": 0,
    "stealth_pct": 0,
    "page_rendered": true,
    "bot_term_hits": 3
  },
  "text_chars": 4729
}

```

