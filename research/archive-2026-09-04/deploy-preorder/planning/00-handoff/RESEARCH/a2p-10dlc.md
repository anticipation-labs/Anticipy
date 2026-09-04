# Twilio A2P 10DLC unblock plan for Anticipation Labs Inc

Date: 2026-05-30. Account: AC6139... Number: +16196584447 (San Diego, SMS+MMS+Voice). Current state per `planning/00-handoff/TWILIO_DELIVERY_TEST.md`: Customer Profile in draft, 0 Brands, 0 Messaging Services, every US SMS fails with error 30034.

**Sourcing caveat**: WebFetch and WebSearch returned API errors for every URL attempted in this session ("model does not support effort parameter" on Twilio, TCR, Bandwidth, Telnyx, Plivo). Deliverable is based on (a) repo Phase 4 telemetry in `TWILIO_DELIVERY_TEST.md` and (b) the established A2P 10DLC process unchanged since 2024. Verify current pricing in Console > Trust Hub before submitting.

## 1. Step-by-step submission checklist (strict order)

1. Confirm Anticipation Labs Inc is a registered US C-corp/LLC with a valid EIN. (Sole-prop lane mostly deprecated; treat unavailable.)
2. Finish the draft **Customer Profile** in Trust Hub. Submit for review.
3. After Profile is approved, submit **A2P Brand Registration** (Standard or Low-Volume Standard).
4. Create **Messaging Service** named "Anticipy Pre-Confirm and Receipts".
5. Add +16196584447 to the Service's Sender Pool. Sticky Sender ON.
6. Submit **Campaign** on the approved Brand. Use case: **Mixed** (Customer Care + Account Notification). Attach 5 sample messages.
7. Wait for TCR + MNO carrier approval (AT&T, T-Mobile, Verizon).
8. Test send via the **Messaging Service SID** (not raw From number). Expect delivered, no 30034.

## 2. Cost breakdown (USD)

| Item                                   | One-time | Monthly |
|---|---|---|
| Customer Profile review                | $0       | $0      |
| Brand Registration (Standard)          | $44      | $0      |
| Brand vetting (Aegis, optional)        | $40      | $0      |
| Brand Registration (Low-Volume Standard) | $4     | $0      |
| Campaign (Standard, Mixed)             | $15      | $10     |
| Campaign (Low-Volume Standard)         | $1.50    | $1.50   |
| Phone number rental (+16196584447)     | $0       | $1.15   |
| Per-message MNO fees                   | n/a      | $0.0025–$0.005/segment, metered in normal Twilio pricing |
| **Total, Low-Volume path**             | **~$5.50** | **~$2.65** |
| **Total, Standard path**               | **$59–$99** | **$11.15–$13** |

**Recommended**: Low-Volume Standard. Inc legal basis keeps trust score high; $4 Brand + $1.50 Campaign keeps spend negligible. Cap ~6,000 segments/day, plenty for beta. Upgrade to full Standard later without re-registering.

## 3. Realistic timeline (draft Profile → first delivered US SMS)

| Stage                         | Best   | Typical            | Worst |
|---|---|---|---|
| Customer Profile review       | <1 hr  | 1–2 business days  | 5 days |
| Brand Registration            | 1 hr   | 1 business day     | 7 days |
| Campaign + MNO approval       | 4 hr   | 3–5 business days  | 14 days |
| **End-to-end**                | **~1 day** | **5–7 business days** | **3 weeks** |

T-Mobile is slowest of the three MNOs.

## 4. Exact form fields

### 4a. Customer Profile (Trust Hub)
- Business Name: `Anticipation Labs Inc` (must match EIN exactly)
- Business Type: Private Corporation (or LLC)
- Registration ID Type: EIN; Number: 9-digit
- Country: US; Industry: Technology / Software
- Website: `https://www.anticipy.ai` (must be live, must have a Privacy Policy that names SMS)
- Address: HQ as on SoS filing (no PO box for Standard)
- Authorized Rep: name, title, work email at @anticipy.ai (NOT gmail), work phone E.164

**Common rejections**: gmail email for the AR, address mismatch with EIN, no privacy policy mentioning SMS.

### 4b. Brand Registration
- Reuses all Profile fields
- Brand Name: `Anticipy` (consumer-facing)
- Vertical: Technology
- Entity Type: Private for-profit
- Support Email: `support@anticipy.ai`; Support Phone: E.164
- Optional Vetting ($40, Aegis): raises T-Mobile cap from 2k to 200k segments/day. Skip if you stay Low-Volume.

### 4c. Campaign
- Name: `Anticipy Receipts and Pre-Confirms`
- Brand: the approved Brand above
- Use Case: **Mixed** → Customer Care + Account Notification
- Description (≤160 chars): "Anticipy texts users transaction receipts, pre-action confirmations for irreversible tasks, and time-sensitive nudges they explicitly opted into during signup."
- Message Flow: describe the consent UI (see §6)
- Help Response: `Anticipy: For help, email support@anticipy.ai or visit https://www.anticipy.ai/help. Msg&data rates may apply. Reply STOP to unsubscribe.`
- Opt-Out Keywords: STOP, STOPALL, UNSUBSCRIBE, CANCEL, END, QUIT
- Opt-Out Response: `You are unsubscribed from Anticipy. No more messages will be sent. Reply START to resubscribe.`
- Opt-In Keywords: START, UNSTOP
- Number Pool: No; Embedded Link: Yes; Embedded Phone: No; Age-gated: No; Affiliate Marketing: No; Direct Lending: No
- Sample messages: see §5

**One Mixed campaign covers all three Anticipy message types (receipt + pre-confirm + nudge).** Two campaigns would double the monthly fee with no throughput benefit.

### 4d. Messaging Service
- Sender Pool: +16196584447
- Sticky Sender: ON (required for the YES/NO/EDIT reply pattern in `sms_pre_confirm.py`)
- Inbound webhook: `https://www.anticipy.ai/api/twilio/sms-inbound` (exists at `src/app/api/twilio/sms-inbound/route.ts`)
- Status callback: `https://www.anticipy.ai/api/twilio/status` (exists)
- Compliance > A2P Campaign: attach the approved campaign

## 5. Sample message templates (paste these into the campaign)

These mirror Anticipy's actual production wording from `engine/app/product/sms_pre_confirm.py` (`build_proposal_text` line 408, `expire_pending` line 1326). Register what you actually send. Carriers reject when the sample differs from production.

**Sample 1, Receipt (Account Notification)**
> Anticipy: Thanks for your pre-order. Order #ANT-12345 for the Anticipy pendant ($149.99) is confirmed and ships August 2026. Manage at https://anticipy.ai/orders. Reply HELP for help, STOP to stop.

**Sample 2, Pre-Confirm with reply (Customer Care)**
> Anticipy: I drafted an email to lara@example.com about the Friday call. Preview: "Hi Lara, confirming 2pm Friday at the cafe." Reply YES to send, EDIT to change, STOP to stop.

**Sample 3, Wake-up nudge (Account Notification)**
> Anticipy: You asked me to remind you to send the Q3 budget to Joe. I drafted it and saved it to your Gmail. Open Anticipy on your Mac to send. Reply STOP to stop.

**Sample 4, Expiry follow-up (Customer Care)**
> Anticipy: No reply, so I saved it as a Gmail draft. Open Anticipy on your Mac to send it whenever you are ready. Reply STOP to stop.

**Sample 5, Help response (mandatory)**
> Anticipy: For help, email support@anticipy.ai or visit https://www.anticipy.ai/help. Msg&data rates may apply. Reply STOP to unsubscribe.

Every sample carries `Anticipy:` prefix and `Reply STOP`. Reviewers reject samples that omit either.

## 6. Opt-in flow Anticipy must ship before submitting

The campaign reviewer will visit anticipy.ai. If they cannot find SMS consent UI, the campaign rejects with `consent flow not found` (most common rejection reason). Ship before submitting:
- A page or in-app screen with an unchecked-by-default `Send confirmations to my phone` toggle and phone-number input
- Consent text adjacent to the input: "By providing your number you agree to receive transaction, confirmation, and account messages from Anticipy. Message frequency varies. Msg&data rates may apply. Reply HELP for help, STOP to opt out. See anticipy.ai/privacy and anticipy.ai/terms."
- `/privacy` page with a section titled "SMS / Text Messaging" stating phone numbers and SMS opt-in consent will not be shared or sold to third parties for marketing
- `/terms` page covering the same
- Screenshot the consent UI; URL or screenshot may go in the campaign description field

## 7. Anticipy-specific notes

- `build_proposal_text` (line 408) keeps a fixed scaffold with variable verb/recipient/subject/preview. Carriers fine that; they reject only when the **brand name** varies. Keep `Anticipy:` everywhere.
- Channel router fires SMS+email together. Email is CAN-SPAM, not A2P; no impact on approval.
- The broker (`/api/twilio/relay`) centralises sends through one Anticipy-owned number. Correct. Do not let stranger DMG installs BYO Twilio creds for outbound; they hit unregistered-number 30034.
- `TWILIO_NOTIFY_TO`, `TWILIO_TEST_TO_REAL_NUMBER_E164` (`sms_pre_confirm.py:489`) are dev-only. Keep out of prod env.

## 8. Acceleration and fallbacks

- **Twilio "Fast Track"**: no public product. Only Enterprise ($5k+/yr commit) gets CSM escalation.
- **Toll-free verification (parallel lane)**: Provision a +1 (800/833/844/855/866/877/888), submit Toll-Free Verification (not TCR). $0 Twilio fee. Approval 3–4 weeks (slower than 10DLC), 3 msg/sec (vs 10), less personal for Donna-style nudges. Failure code 30032, same block kind. Useful only to avoid Inc legal review.
- **Alternative carriers** if Twilio drags past 2 weeks:
  - **Telnyx**: Brand $4, Campaign $1.50/mo, provider review often 24–48h. Port from Twilio: 5–10 days. Same TCR+MNO backend.
  - **Bandwidth**: lower per-msg at scale, slower account onboarding.
  - **Plivo**: similar to Telnyx, smaller carrier network.
  - **Sinch/MessageBird**: enterprise-focused, longer onboarding.
- **Reality check**: all four go through TCR Brand/Campaign and the 5–7 day MNO review. Switching saves at most 1–2 days of provider-side review, not the TCR/MNO chain. Only true bypass is toll-free, with its own multi-week wait.

## 9. Concrete next actions for Omar today

1. Decide path: **Low-Volume Standard** ($5.50 one-time, ~$3/mo). Recommended.
2. Twilio Console → Trust Hub → finish the draft Customer Profile.
3. Ship the opt-in UI on anticipy.ai (§6). 30-min frontend task.
4. Submit Customer Profile. Wait for approval (same day typical).
5. Submit Brand Registration (Low-Volume Standard).
6. Create Messaging Service, attach +16196584447, point inbound at `/api/twilio/sms-inbound`.
7. Submit Mixed Campaign with the 5 samples in §5.
8. Wait 3–5 business days for MNO approval.
9. Test send to an opted-in real number via the Messaging Service SID. If 30034 persists, fix the broker (`src/app/api/twilio/relay/route.ts`) to use `messagingServiceSid`, not `from`.

End-to-end budget: **~$5.50 one-time, ~$3/mo, 5–7 business days.**
