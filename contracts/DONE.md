# DONE.md

The V7 done contract is defined by `ANTICIPY_V7.md`.

This file exists for compatibility with older scripts that expect a
`contracts/DONE.md` path. It must not define a separate completion standard.
The mechanical V7 done gate is implemented by `scripts/v7/check_done.sh`.

Done means all V7 gates are simultaneously true:

1. The public app at `https://www.anticipy.ai/app` loads.
2. The public DMG installs from the public product path.
3. The installed user-device engine is current and paired.
4. Local main, origin/main, and live `/api/app/state` report the same commit.
5. Public DMG SHA matches `state/builds/manifest.json`.
6. MP3/audio upload passes.
7. Text transcript paste/upload passes.
8. Computer microphone input passes.
9. External microphone input passes through selected-device proof.
10. Real Chrome/user surface proof is used, with no cloned Chrome.
11. 100 or more successful generated-stranger interactions.
12. 20 or more successful verb categories.
13. 5 hard categories are green: canvas, CRM, e-commerce, native, ambient.
14. The most recent 20 interactions all pass.
15. 3 consecutive MP3 evaluations pass.
16. Audio transcript WER is under 5 percent.
17. Runtime cost is under the ceiling.
18. 3 public clean-room installs pass on separate machines or accounts.
19. The inference schema, data path, and eval loop exist and are exercised.
20. No fake receipts, backdoor verifiers, stale-source proofs, or log-only
    claims satisfy proof.

No API credential verifier, fixed fixture library, model assertion, stale
source run, cloned browser profile, or log-only claim can satisfy this
contract.
