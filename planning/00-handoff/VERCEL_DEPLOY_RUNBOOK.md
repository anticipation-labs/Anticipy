# Vercel Deploy Runbook (Twilio Broker)
Deploys `/api/twilio/relay` to anticipy.ai. Vercel project lives in DEV-FINAL repo. Run in order.

## 1. Set Vercel env vars

WHY: The relay reads three secrets at request time. Without them the route returns 503.

HOW: Vercel dashboard, project "anticipy" (DEV-FINAL). Settings, Environment Variables, Add New. Add each, check Production + Preview + Development:
- `TWILIO_BROKER_SID` (starts `AC...`)
- `TWILIO_BROKER_TOKEN` (32 hex chars)
- `TWILIO_BROKER_FROM` (E.164, e.g. `+1XXXXXXXXXX`)

VERIFY:
```bash
vercel env ls production | grep TWILIO_BROKER
```

## 2. Apply Supabase migration

WHY: Audit table `anticipy_twilio_sends` must exist or every send logs a console error (broker still works, audit is best effort).

HOW: Supabase dashboard, project `handlit` (ref `ogbxpqkmsdrcuilafycn`), SQL Editor, paste contents of `src/app/api/twilio/relay/MIGRATION.sql`, Run. CLI alternative:
```bash
supabase db push --project-ref ogbxpqkmsdrcuilafycn --file src/app/api/twilio/relay/MIGRATION.sql
```

VERIFY:
```bash
supabase db query --project-ref ogbxpqkmsdrcuilafycn \
  "select count(*) from public.anticipy_twilio_sends"
```

## 3. Push the deploy branch

WHY: Vercel auto-deploys `deploy/preorder-to-main` (configured as production branch). Push triggers the build.

HOW: From DEV-FINAL working copy:
```bash
cd /Users/omarebrahim/Developer/Anticipy-DEV-FINAL
git push origin deploy/preorder-to-main
```

VERIFY: Watch the build at vercel.com/<team>/anticipy/deployments. Wait for Ready status.

## 4. Smoke-test the broker

WHY: Confirms auth gate, validation, and Twilio path each respond correctly.

HOW + VERIFY (run each, check status code):
```bash
# 4a. No token, expect 401
curl -s -o /dev/null -w "%{http_code}\n" -X POST https://www.anticipy.ai/api/twilio/relay

# 4b. Invalid token, expect 401
curl -s -o /dev/null -w "%{http_code}\n" -X POST https://www.anticipy.ai/api/twilio/relay \
  -H "Authorization: Bearer not_a_real_jwt"

# 4c. Valid token, missing body, expect 400
SUPA_JWT="<paste a fresh Supabase session JWT>"
curl -s -o /dev/null -w "%{http_code}\n" -X POST https://www.anticipy.ai/api/twilio/relay \
  -H "Authorization: Bearer $SUPA_JWT" -H "Content-Type: application/json" -d '{}'

# 4d. Success path, expect 200 and a sid
curl -sS -X POST https://www.anticipy.ai/api/twilio/relay \
  -H "Authorization: Bearer $SUPA_JWT" -H "Content-Type: application/json" \
  -d '{"to":"+1XXXOWNERPHONE","body":"Anticipy broker smoke","kind":"preconfirm"}'
```

## 5. Rollback

WHY: If the deploy breaks anticipy.ai, demote it back to the prior good build in under a minute.

HOW: Vercel dashboard, project anticipy, Deployments, find the previous Ready build, three-dot menu, Promote to Production.

VERIFY:
```bash
curl -s -o /dev/null -w "%{http_code}\n" https://www.anticipy.ai/
# 200 means the promoted build is live.
```
