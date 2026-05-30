# Resend Research for Anticipy

Read-only. All citations are official Resend docs. anticipy.ai DNS state captured via `dig` on 2026-05-30.

---

## 1. Domain setup on anticipy.ai

### Records (recommended subdomain pattern `send.anticipy.ai`)

| Type | Host | Value | Purpose |
|---|---|---|---|
| MX | `send` | `feedback-smtp.us-east-1.amazonses.com` priority `10` | Return-Path for bounces. Region string varies by selected Resend region. |
| TXT | `send` | `"v=spf1 include:amazonses.com ~all"` | SPF for the send subdomain. |
| TXT | `resend._domainkey` | `p=<base64 RSA pubkey>` (Resend generates, 1024-bit) | DKIM. |

DMARC, optional but recommended, on the apex:

| TXT | `_dmarc` | `v=DMARC1; p=none; rua=mailto:dmarcreports@anticipy.ai;` |
|---|---|---|

Start `p=none`, escalate to `quarantine` then `reject` once Postmaster Tools shows passing. ([dmarc.md](https://resend.com/docs/dashboard/domains/dmarc.md))

### Subdomain vs root

Use a subdomain (`send.anticipy.ai`, `mail.anticipy.ai`) not the apex: reputation isolation (quarantine a compromised subdomain) and sending-purpose transparency (Gmail/Outlook triage receipts vs marketing vs auth). Avoid lookalike domains (`anticipy-mail.com`); spam filters flag them. ([subdomain doc](https://resend.com/docs/knowledge-base/is-it-better-to-send-emails-from-a-subdomain-or-the-root-domain.md))

### Verification timeline

Resend rechecks DNS up to 72h. With Porkbun TTL=600 usually completes in minutes. Status: `not_started` → `pending` → `verified` (or `failed`). ([domains intro](https://resend.com/docs/dashboard/domains/introduction.md))

---

## 2. API basics

- **Base URL**: `https://api.resend.com`, HTTPS only.
- **Auth**: `Authorization: Bearer re_xxxxxxxxx`.
- **User-Agent**: required on raw HTTP. SDKs set it. Missing UA returns 403 code 1010.
- **Rate limit**: 5 req/sec per team across all keys. 429 when exceeded. Higher caps on request.
- **Idempotency**: `Idempotency-Key` header (max 256 chars). 24-hour dedupe window. Errors: 400 invalid key, 409 same-key-different-payload, 409 concurrent in flight.

Sources: [api intro](https://resend.com/docs/api-reference/introduction), [idempotency](https://resend.com/docs/dashboard/emails/idempotency-keys).

---

## 3. React Email templates

- `npx create-email@latest` scaffolds an `emails/` project with hot-reload preview at `localhost:3000`. Components: `Html`, `Head`, `Body`, `Container`, `Heading`, `Text`, `Button`, `Tailwind` (use `pixelBasedPreset` for client compat).
- **Server render**: Node SDK takes `react: <Welcome firstName="Omar"/>` directly. Resend renders to email-safe HTML and **auto-generates plain-text** unless you set `text: ""` (opt out) or `text: "..."` (custom).
- **Variables**: plain React props. For per-recipient at volume, render once per recipient or use `POST /emails/batch` (up to 100 per request, 1 rate-limit hit).
- Apple-feel: `pixelBasedPreset` Tailwind, system fonts, generous spacing, single dark CTA. Preview has Linter/Compatibility/Spam tabs.
- **Hosted Templates**: `npx react-email@latest resend setup` uploads them so Python can call by ID. ([react email guide](https://resend.com/docs/knowledge-base/template-emails-with-react-email.md))

---

## 4. Reply tracking + inbound webhooks

- **Inbound domain**: free `*.resend.app` or your own with MX. Use dedicated `reply.anticipy.ai`.
- **Per-goal reply-to**: any local-part is captured (e.g. `goal-abc123@reply.anticipy.ai`). Filter on `event.data.to[0]` to route back to the goal id.
- **Webhook `email.received`** carries metadata only (`email_id`, `message_id`, `from`, `to`, `subject`, attachment meta). Body/headers are NOT in the webhook (serverless body limits). Call `GET /emails/{id}` for content.
- **Signature**: Svix headers (`svix-id`, `svix-timestamp`, `svix-signature`). Verify with `resend.webhooks.verify({...})`.
- **Retry**: 5s, 5m, 30m, 2h, 5h, 10h. Emails persist in dashboard so nothing is lost if your endpoint is down.
- **Threading**: reply with header `In-Reply-To: <message_id>` and subject `Re: <original>`. Multi-turn: add `References` header concatenating all prior message_ids space-separated. ([reply-to-emails](https://resend.com/docs/dashboard/receiving/reply-to-emails.md))
- **Webhook source IPs** to allowlist: `44.228.126.217`, `50.112.21.217`, `52.24.126.164`, `54.148.139.208`, `2600:1f24:64:8000::/52`.

---

## 5. Cost model

Live from resend.com/pricing on 2026-05-30:

| Tier | Price | Emails/mo | Daily cap | Overage |
|---|---|---|---|---|
| Free | $0 | 3,000 | 100/day | n/a |
| Pro | $20/mo | 50,000 | none | $0.90 / 1,000 |
| Scale | $90/mo | 100,000 | none | $0.90 / 1,000 |
| Enterprise | custom | flexible | none | custom |

Add-on: Dedicated IP $30/mo (needed >500/day on Scale). Inbound emails included. Automations $0.0015/run beyond 10k free.

### Anticipy projection

Cost ceiling is $200/user/year (`project_cost_ceiling_200_per_user_year.md`). Assume 5,000 receipts/user/year (subset of 20-40k tasks; many actions are silent):
- 5,000 × $0.0009 = **$4.50/user/year**
- 10,000 × $0.0009 = **$9/user/year**

At 1,000 paying users sending 5k each = 5M emails/mo on Scale: 5M × $0.0009 + $90 base = $4,590/mo = **~$55/user/year**. Below 30% of the $200 ceiling. Below ~110k/mo (≈100 users), Pro+overage is cheaper than Scale.

---

## 6. anticipy.ai DNS + Vercel coexistence

Live `dig` on 2026-05-30:

- **Nameservers**: 4 × `*.ns.porkbun.com`. DNS is at **Porkbun**, not Cloudflare and not Vercel.
- **Apex A**: `76.76.21.21` (Vercel anycast). `www` is `cname.vercel-dns.com`. Vercel hosts the site; Porkbun manages DNS.
- **Apex MX**: `fwd1.porkbun.com`, `fwd2.porkbun.com` (free Porkbun forwarder). Forwards `omar@anticipy.ai` to a personal mailbox.
- **Apex TXT (SPF)**: `v=spf1 include:_spf.porkbun.com ~all`.
- **DMARC**: `_dmarc.anticipy.ai = "v=DMARC1; p=none;"` already present. Add `rua=mailto:...` later.

**No conflict** with Vercel: Vercel owns `A`/`AAAA`/`CNAME` on apex and `www`; Resend wants `MX`+`TXT` on `send.anticipy.ai` and `TXT` at `resend._domainkey.anticipy.ai`. Different types, different hosts.

**Watch**: do NOT put Resend MX on the apex; would break the Porkbun forwarder. Stick with `send.` for sending and `reply.` for inbound. ([Porkbun guide](https://resend.com/docs/knowledge-base/porkbun.md))

---

## 7. Code integration

- **Node SDK** `resend` v6.12.4 (MIT, 913 stars, last release 2026-05-25).
  ```ts
  const resend = new Resend(process.env.RESEND_API_KEY);
  await resend.emails.send({
    from: 'Anticipy <donna@send.anticipy.ai>',
    to, subject,
    react: <Receipt {...} />,
    replyTo: `goal-${id}@reply.anticipy.ai`,
    headers: { 'Idempotency-Key': `goal/${id}` },
  });
  ```
- **Python SDK** `resend` v2.30.1 (MIT, 121 stars, last release 2026-05-13). No `react=` param (Node only); pass `html=...`.

### Direct from engine vs broker through website

**Recommendation: broker through a Next.js route on anticipy.ai**, same shape as the Twilio relay.

1. React Email lives in `src/emails/` next to the website's brand colors (#0C0C0C, #F5F0EB, #C8A97E). Python sidecar cannot render React.
2. One `RESEND_API_KEY` on Vercel; zero per-Mac key distribution risk. Engine runs on each user's Mac; an API key on every Mac is a credential-leak surface.
3. Rate-limit, idempotency, SMS preconfirm (`feedback_sms_pre_confirm.md`), and the no-real-send allowlist (`feedback_no_real_send_testing.md`) all enforced in one place.
4. Hidden quota/billing; engine never sees it.

Engine calls `POST https://anticipy.ai/api/email/receipt` with `{ to, template, props, goal_id }`. Route renders React, sets idempotency key, sets per-goal reply-to, calls Resend.

---

## Gotchas

- **camelCase vs snake_case**: `reply_to` in HTTP body, `replyTo` in Node SDK.
- **Auto plain-text**: HTML-only sends auto-generate a text part unless you set `text: ""`. Verify in React Email Spam tab.
- **Idempotency window is 24h**: same key on day 2 is a fresh send.
- **Inbound webhook is metadata only**: `GET /emails/{id}` for body. Plan the round-trip.
- **MX priority collision**: if anything else lands at priority 10 on `send.anticipy.ai`, only one wins (random). Keep priorities unique.
- **DKIM 1024-bit is default and fine**. Request 2048 only if compliance demands.
- **Rate limit 5/sec per team across all keys**. Burst of 100 receipts will 429; use `POST /emails/batch` (100/request, 1 rate hit).
- **Free tier**: 100/day cap, 1 domain. Move to Pro before launch.
- **Inbound retries cap at ~17h** (6 attempts). After, use Replay.
- **Apex MX currently points to Porkbun forwarder**. Do not delete or override; only add under `send.` and `reply.`.

---

## Sources

- [API Introduction](https://resend.com/docs/api-reference/introduction)
- [Send Email](https://resend.com/docs/api-reference/emails/send-email.md)
- [Idempotency keys](https://resend.com/docs/dashboard/emails/idempotency-keys)
- [Managing Domains](https://resend.com/docs/dashboard/domains/introduction.md)
- [Implementing DMARC](https://resend.com/docs/dashboard/domains/dmarc.md)
- [Subdomain vs root](https://resend.com/docs/knowledge-base/is-it-better-to-send-emails-from-a-subdomain-or-the-root-domain.md)
- [MX conflict guide](https://resend.com/docs/knowledge-base/how-do-i-avoid-conflicting-with-my-mx-records.md)
- [Porkbun setup](https://resend.com/docs/knowledge-base/porkbun.md)
- [Receiving Emails](https://resend.com/docs/dashboard/receiving/introduction.md)
- [Reply threading](https://resend.com/docs/dashboard/receiving/reply-to-emails.md)
- [Webhooks](https://resend.com/docs/dashboard/webhooks/introduction)
- [React Email templates](https://resend.com/docs/knowledge-base/template-emails-with-react-email.md)
- [Next.js quickstart](https://resend.com/docs/send-with-nextjs)
- [Python quickstart](https://resend.com/docs/send-with-python)
- [Pricing](https://resend.com/pricing)
- GitHub: [resend/resend-node](https://github.com/resend/resend-node) v6.12.4 MIT
- GitHub: [resend/resend-python](https://github.com/resend/resend-python) v2.30.1 MIT
