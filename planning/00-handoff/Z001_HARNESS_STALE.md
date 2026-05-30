# Z-001 harness needs update

Discovered 2026-05-30 during the OUT-OF-MOCK engine restart cycle.

## What changed
The website auth flow used to be:
1. Engine mints handoff token
2. Browser navigates to /app/download?token=...
3. Token exchange returns signup form (email + password)
4. User creates account
5. Returns to /app/download for DMG

Now:
1. Engine mints handoff token
2. Browser navigates to /app/download?token=...
3. Token exchange auto-creates Supabase user if email not seen before
4. User lands directly on /app/download

## Why Z-001 fails
`scripts/v7/z001_e2e_harness.py` step `browser_signup` waits 25s for `email + password` input fields. The new flow renders /app/download directly with no form, so the wait times out + FAIL.

## Product impact
ZERO. Real strangers get a smoother experience (one less form). The harness needs to be updated to match the new flow:
- Use a Supabase admin API to pre-create the throwaway user, OR
- Check for the post-signin /app/download state directly and consider it a PASS

## Suggested fix
Replace `browser_signup` step with `verify_already_signed_in` that just checks the URL is `/app/download` + the page title is "Anticipy App".

## Side findings
- tab leakage from us = 0 (engine respecting QUIET mode + tab ownership map)
- bridge + Chrome + engine all healthy after restart
