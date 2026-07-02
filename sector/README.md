# sector/ — the one walking skeleton

This is the thin **assembly layer** that makes Anticipy ONE thing instead of 20 scattered parts.
It reimplements nothing. `wire.py` imports the single best module per system (per `CANON/THE_MAP.md`);
`skeleton.py` orchestrates them into one line — **hear → infer → decide → remember → act → warm
check-in → learn**. `proof/thin_path_test.py` is the sector's own failable gate.

**The acceptance test for the whole product is `overnight/done_gate.py`.** Legs 1–4 pass today;
leg 5 (a real cold stranger carried through a real day) is the finish. Every step of the
order-of-attack in `CANON/THE_MAP.md` *widens this one line* — never forks it.

Run the skeleton's gate:
```
ANTICIPY_MODEL_PROVIDER=stub PYTHONPATH=engine engine/.venv/bin/python sector/proof/thin_path_test.py
```

Deferred by Omar's explicit call: **security/safety** (only `harm.py`'s money/irreversible stop
stays — it's load-bearing). One final security-wire pass at the very end, never before.
