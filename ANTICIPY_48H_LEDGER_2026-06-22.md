# Anticipy 48-Hour Ledger

Generated: June 22, 2026 UTC / June 21, 2026 Vancouver evening

This is the working ledger for getting Anticipy from "many moving pieces" to one supervised local system that can be tested, secured, connected to hardware, and used for targeted distribution.

## Current State

- Local engine is live on `127.0.0.1:8787`.
- Owner app is live on `127.0.0.1:3000`.
- Full local suite is green: `107 passed, 0 failed`.
- Production Next build is green after a clean `.next` rebuild.
- Browser bridge is connected.
- Google/Arcade and Twilio report live-ready.
- Owner app requires the owner key before exposing private controls.
- Remaining readiness gap: Apple signing/notarization needs connection.
- Inbound polling is disabled: `ANTICIPY_INBOUND_POLL_SECONDS=0`.
- Current pending approvals: 3.

## Micro Goal 1: Local Software Functioning

Status: Mostly done for local supervised use.

Done:
- Engine readiness/status endpoints respond.
- Owner app builds and serves locally.
- Owner gate works in browser.
- Main dashboard renders after owner unlock.
- Main text input accepts and clears text without frontend runtime errors.
- Harm-line, inbound, voice, proactive outreach, owner auth, product path, and premium-copy checks are green.

Next:
- Keep `http://127.0.0.1:3000` running for local demos.
- Run one supervised owner ingest from the dashboard.
- Review the 3 pending approvals and resolve or archive them.
- Package the app only after Apple Developer signing is connected.

## Micro Goal 2: Security Systems

Status: Strong local baseline; public exposure still gated by setup.

Done:
- Owner app no longer bypasses a configured owner token just because the request is local.
- Money/payment/send/purchase hard-stop tests are green.
- Prompt-injection/browser navigation wall tests are green.
- Premium-copy leak scan is clean.
- Owner API auth tests are green.

Required before any public deploy:
- Set `ANTICIPY_APP_OWNER_TOKEN` for the app.
- Set `ANTICIPY_OWNER_API_TOKEN` for engine/private proxies.
- Put public webhooks behind authenticated routes and provider signature verification.
- Keep payment, purchase, external-send, account changes, uploads, and destructive actions under explicit approval.
- Do not run autonomous posting, mass outreach, covert persuasion, or platform ToS evasion. Use agents for research, drafts, ranking, scheduling, and reply prep with human approval.

## Micro Goal 3: Hardware Connection

Status: Architecture is ready; physical transcript bridge is the next unknown.

Target path:
- Treat the pendant/Omi/phone/hardware as a transcript source first, not as a new decision engine.
- Bridge transcript text into `POST /api/owner/ingest`.
- Preserve source metadata: device, timestamp, confidence, speaker if available.
- Do not enable external sends or purchases from hardware input without the same owner approval gates.

Next hardware work:
- Identify actual transcript output path: local socket, file, stdout, mobile relay, webhook, or vendor API.
- Build the smallest bridge from that output into owner ingest.
- Run text-only capture for 30 minutes.
- Confirm Anticipy creates the same cards from hardware transcripts as from pasted transcripts.
- Only then add live listening, wake behavior, and push/SMS owner interrupts.

Reserved slot:
- `capture/pendant_phone.py` appears to be the intended bridge area if the source is phone/pendant based.

## Micro Goal 4: Enable Everything Once Hardware Works

Activation order:
1. Mock channel pass: transcript in, cards out, no external effects.
2. Local live pass: dashboard ingest, owner approvals only.
3. Twilio supervised pass: one text ask, one YES/NO response with code.
4. Inbound webhook pass: expose only the required webhook, verify auth/signatures.
5. Browser bridge pass: one read-only browse, then one reversible form/cart prep with no checkout.
6. Five-day owner run: daily review of false positives, missed asks, annoying interrupts, and any unsafe card.

Do not enable:
- Payments or checkout.
- Bulk messaging.
- Unapproved email/SMS/social posting.
- Background scraping of private accounts beyond the owner-approved task.

## Distribution And Marketing

Status: Needs focus and a human approval loop, not more tooling first.

Core positioning:
- Anticipy is an owner-supervised assistant that listens to your day, catches what matters, and stops before anything risky.
- The proof is not "AI agent magic"; the proof is safe local execution plus real receipts.

Organic channels:
- Reddit: listen, map pain points, draft helpful comments/posts, and queue them for approval. No spam, sockpuppets, or fake community behavior.
- X: daily founder-build thread, short demos, artifact receipts, and direct replies to relevant builders/investors. Drafts can be agent-generated; posting remains approved.
- Instagram/TikTok/Reels: clone the pacing and emotional structure of saved references, but rebuild original scripts and footage around Anticipy.
- Networking: use targeted, deduped outreach from the existing summer networking scout.

Immediate outreach:
- Harper Reed: draft a concise Startupfest follow-up to "Sure. Find me!"
- Robotics Center: answer their stage/demo/visit-goal questions.
- Omi/Nik: ask for the cleanest hardware transcript integration path.
- Mariane/Founders Bay: schedule around the July 27-31 San Francisco meeting window.
- Corey Grace: prepare a specific ask and reason for relevance before reaching out.
- Zed Fellows: keep a separate, deduped status list with next action and deadline.

Marketing agent shape:
- Inputs: approved ICP, saved video references, Reddit/X search terms, known no-go claims, founder voice examples.
- Outputs: ranked opportunities, draft replies, draft posts, short-form scripts, daily queue.
- Human gate: Omar approves final posts, DMs, purchases, registrations, and any claim about capability/security.

## Travel And Ops

Business cards:
- Buy thick cards only after the one-line positioning and demo URL/QR are final.
- Suggested spec: 32pt or 700gsm, matte or soft-touch, black/white restrained design, QR to local/demo landing page.
- No purchase without owner approval.

San Francisco:
- Default plan: cluster around July 27-31, 2026 unless at least 5 high-signal meetings justify an earlier trip.
- Next 48 hours: lock meeting targets, send tailored asks, and decide whether Startupfest or SF has the better immediate return.

## Next 48 Hours

0-6 hours:
- Keep local app running.
- Resolve the 3 pending approvals.
- Run one supervised dashboard ingest.
- Draft Harper Reed and Robotics Center replies.

6-18 hours:
- Identify hardware transcript source.
- Build or confirm the transcript-to-ingest bridge.
- Prepare a 60-second demo script and a 15-second short-form hook.
- Create the Reddit/X opportunity search list.

18-36 hours:
- Run a hardware or simulated-hardware transcript session.
- Exercise Twilio YES/NO with codes.
- Draft business card copy and QR target.
- Send the first approved outreach batch.

36-48 hours:
- Run the full suite again.
- Run a browser smoke test again.
- Decide SF timing using meeting count and quality.
- Freeze a "demoable Anticipy" checklist for the next three weeks.
