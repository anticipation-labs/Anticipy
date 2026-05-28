# Bot detection canary 20260527T143853Z

Bridge: http://127.0.0.1:7777
CDP: http://127.0.0.1:9222
Wait per site: 12s

## Per-site verdicts

| site | verdict | reason |
|---|---|---|
| sannysoft | INCONCLUSIVE_NO_TEXT |  |
| areyouheadless | INCONCLUSIVE |  |
| creepjs | INCONCLUSIVE |  |

## Headline

Anticipy drives real Chrome and appears as: [INCONCLUSIVE]

(real=0 bot=0 inconclusive=3)

## Signals flagged

### sannysoft

```json
{
  "slug": "sannysoft",
  "verdict": "INCONCLUSIVE_NO_TEXT",
  "reason": "",
  "hits": {
    "rows_passed": 0,
    "rows_failed": 0,
    "missing_image_rows": 0,
    "present_rows": 0,
    "webdriver_new_mentioned": false
  },
  "text_chars": 0
}

```

### areyouheadless

```json
{
  "slug": "areyouheadless",
  "verdict": "INCONCLUSIVE",
  "reason": "",
  "hits": {
    "match_false": false,
    "match_true": false,
    "you_are_not_headless": false,
    "you_are_headless": false
  },
  "text_chars": 0
}

```

### creepjs

```json
{
  "slug": "creepjs",
  "verdict": "INCONCLUSIVE",
  "reason": "",
  "hits": {
    "trust_score_pct": null,
    "bot_term_hits": 0,
    "fingerprint_mentioned": false
  },
  "text_chars": 0
}

```

