# Cross-app auth: design

Owner: Omar. Drafted 2026-05-29. Status: brainstorm, not committed.

The pendant has to drive Epic, Procore, Salesforce, Canvas, SimplePractice, TheraNest, OpenTable, Resy, custom law-firm matter systems, and the long tail of SaaS the user is already signed into. No service APIs (Omar rule). Browser navigation only. The login wall is the gating problem for almost every action that is not Google Search or Wikipedia.

## 1. What ships today

The current surface stack is the CDP bridge at `scripts/v7/anticipy_bridge_fallback_cdp.py:1-1169` plus the action-engine dispatcher at `engine/app/action_engine/cdp_dispatcher.py:1-340`. Architecture in plain terms:

- A long-running Python process exposes `127.0.0.1:7777` and speaks a tiny HTTP surface (`/status`, `/surface-proof`, `/surface-command`). See `anticipy_bridge_fallback_cdp.py:825-1122`.
- On boot it probes `http://localhost:9222/json/version` (`anticipy_bridge_fallback_cdp.py:137-158`). When CDP is alive it opens a single persistent WebSocket to `ws://localhost:9222/devtools/browser/<guid>` and multiplexes every command over that one socket (`_CDPClient` class at `anticipy_bridge_fallback_cdp.py:225-394`). Per-tab calls use `Target.attachToTarget(flatten=true)` to get a sessionId rather than opening a per-tab WS.
- Tabs are opened via `Target.createTarget(background=true)` so navigation does not steal OS focus (`anticipy_bridge_fallback_cdp.py:434-451`). In-place reuse: if a page with the same scheme+netloc is already open, the bridge calls `Page.navigate` on that target instead of opening a new tab (`_cdp_navigate` at `anticipy_bridge_fallback_cdp.py:517-574`).
- Click and type are JS injections via `Runtime.evaluate` against a `document.querySelector` (`anticipy_bridge_fallback_cdp.py:595-650`). The dispatcher in `cdp_dispatcher.py:155-230` does the alternate motion path: real `Input.dispatchMouseEvent` with Bezier paths and `Input.dispatchKeyEvent` with Gaussian inter-char delays for sites where pure JS injection trips bot checks.
- An AppleScript fallback exists for the case where CDP is unavailable (`anticipy_bridge_fallback_cdp.py:712-820`), but AppleScript brings windows to the front and needs the user to enable "Allow JavaScript from Apple Events," so it is a last resort.

The Chrome that 9222 points at is launched by the user's launchd job with `--remote-debugging-port=9222 --remote-allow-origins=http://localhost:*` against a real Chrome `--user-data-dir`. Per the V6 dispatcher note at `scripts/v6/dispatch_planner.sh:24`, Chrome 136+ refuses `--remote-debugging-port` against the actual default profile directory, so the working setup is the user opening their everyday Chrome with the debugging port flag, NOT a clone. That gives us cookies and logged-in sessions for every app the user already uses, for free.

Isolation today: the only isolation is "we open background tabs." There is no tab-ownership tagging. If the user is on a Gmail tab and the agent calls `_cdp_navigate` against `https://mail.google.com/...`, the in-place reuse logic at `anticipy_bridge_fallback_cdp.py:528-554` will hijack the user's tab and overwrite the URL. That is a real bug for the cross-app use case and is the first thing to fix.

The legacy Patchright path at `engine/app/browser.py:18-200` and `engine/app/agent.py:1100-1170` is a separate world. It launches its own Chromium with a per-user-id profile under `BROWSER_PROFILE_BASE`. We are NOT shipping that for the user-facing flow because it requires re-login per site, but it is the right shape for sandbox runs and for any flow where we explicitly do not want to touch the user's real Chrome.

## 2. Five approaches to "logged-in everywhere"

### 2a. One Chrome user-data-dir per app
Run a dedicated Chrome process per target app, each with `--user-data-dir=~/.anticipy/profiles/<app>/`, each on its own debugging port. Cleanest isolation: a flaky cookie in Salesforce cannot poison Epic. Heaviest cost: each profile is 300-500 MB on disk, each Chrome instance is 400-800 MB of RAM at idle, and the user has to sign into each app once per profile. Reasonable upper bound is maybe 8-10 profiles on a 16 GB Mac before we are swapping. The pendant ships on a $30 mini-PC eventually, so this approach does not survive the hardware transition.

### 2b. Single profile, dedicated "Anticipy" tab group
Keep using the user's real Chrome on 9222. Add a tab-group naming convention: every tab the agent opens is added to the Chrome tab group titled "Anticipy" with color `blue`. The extension code already implements this at `extension_v4/background.js:504-517`. The agent only operates on tabs in that group. The user's tabs in any other group are off-limits. Costs nothing extra in RAM or disk, costs the user's mental model of "one extra group at the right edge of my tab bar." Risk: if the user manually drags a tab into the Anticipy group we will start clicking around in it. Mitigate with a per-tab data attribute (see section 5).

### 2c. Shadow Chrome on a hidden macOS Space
Launch a second Chrome instance with its own debugging port, headful, but parked on a macOS Space the user never sees. Cookies are copied from the user's real profile on first launch (`cp -R ~/Library/Application Support/Google/Chrome/Default ~/.anticipy/shadow-profile/Default`). The agent operates entirely in the hidden space. The user's main Chrome is untouched. Tradeoff: cookies copied at install time go stale, so we need to re-sync them on every session refresh, and Chrome sometimes refuses to share a profile across two running processes (the SingletonLock check at `engine/app/agent.py:1109-1116`). The "two Chromes, one profile" failure mode is documented and ugly.

### 2d. Headless Chrome with stolen cookies
Run headless Chromium with the user's cookies imported via `chrome.cookies.getAll` from a tiny extension installed in the user's real Chrome, transferred via native messaging, and reinjected with `Network.setCookie` over CDP. Smallest footprint, fastest cold start. Major problems: many auth flows use `HttpOnly` cookies plus session storage plus IndexedDB plus localStorage tied to a specific browser fingerprint, and the headless Chrome will fail JS device-fingerprint checks (`navigator.webdriver`, missing GPU, missing audio context). DataDome and Akamai catch headless almost immediately. Worth it for read-only data extraction from sites that do not bot-check. Not viable for Salesforce, Epic, or anything with mature anti-fraud.

### 2e. Hybrid (recommended primary)
Default path is approach **2b** (real Chrome, Anticipy tab group). Sensitive auth steps (initial sign-in, MFA challenge, password reset) spawn an isolated context using approach **2a** for that single app, opens it visibly in the user's Spaces, lets the user complete the wall, and then the cookie state for that app is captured back into the main profile via `Network.getAllCookies` on the isolated context and `Network.setCookie` on the main profile. After auth completes the isolated context is torn down. Day-to-day automation stays in the user's real Chrome where the cookies already are. Initial onboarding and re-login flows go through the isolated path. This minimizes both surprise (the user does not see weird new tabs in their main Chrome during day-to-day use) and disk cost (no permanent per-app profiles).

The remaining hard cases: apps where the auth domain is shared (Salesforce Lightning, where login is at `login.salesforce.com` but the org is at `mycompany.lightning.force.com`) need a per-org cookie-namespace map. That belongs in a small JSON registry, one entry per supported app, version-controlled.

## 3. MFA handling

The Twilio scaffolding already exists at `engine/app/product/login_wall_responder.py:1-278`. Current behavior is "place an outbound voice call that tells the user to type the password into the open browser window." For the cross-app case the call needs to do more.

### 3a. SMS / push / 6-digit MFA
When the engine detects an MFA prompt (URL substring match against a small registry, plus DOM check for `input[autocomplete="one-time-code"]` or `input[inputmode="numeric"][maxlength="6"]`), it places a Twilio call. The TwiML says: "Anticipy is signing into Epic for you. It needs the 6-digit code from your phone. After the beep, read me the code, one digit at a time." Twilio `<Gather input="speech" speechTimeout="auto" hints="zero one two three four five six seven eight nine">` captures the user's spoken code, posts the speech result to a callback at `127.0.0.1:7777/mfa-code`, the engine validates it is 6 digits, calls `_cdp_type` against the prompt input, and submits. Total wall time: 8-15 seconds.

Hardening: Twilio's speech recognition is noisy on numbers. Set the prompt format to "zero seven three two zero zero" rather than "seventy-three thousand two hundred." Confirm the captured digits back to the user before submitting ("I heard 0 7 3 2 0 0, sending. Hang up to cancel."). If confirmation times out, retry once, then halt with "I could not read the code, please type it yourself."

### 3b. Authenticator app codes
TOTP codes in Google Authenticator are NOT on a phone notification that the user can dictate quickly. The user has to open the Authenticator app, find the right entry, read the 6 digits. UX flow: Twilio call says "Anticipy needs the code from your Salesforce Authenticator. Open the app, find Salesforce, read the code." Wait. Same `<Gather>` flow as 3a. Practical wait time is closer to 20-30 seconds. The user being able to do this in a meeting is the constraint; see 3c.

Alternative for power users: offer to mirror their TOTP secret into a local-only `~/.anticipy/totp.kdbx` (KeePass format, encrypted with a key in the macOS keychain). Engine generates the code locally without calling the user. Privacy stance: we store the seed only with explicit user opt-in per service, never silently, and never sync it off the device. This is the only place where "store credentials" is on the table, and only for TOTP seeds, never for passwords.

### 3c. User in a meeting, cannot take a call
The Twilio call attempt sets a 20-second answer deadline. On no-answer, the engine falls back to a phone push notification (via APNs on the Anticipy iOS app, when we have one) or an iMessage via `osascript` calling Messages (`engine/app/product/login_wall_responder.py:155-173` already has the `say` fallback shape, extend with `osascript -e 'tell application "Messages" ...'`). The notification offers two actions: "I'll do it now" and "Try again in 15 minutes." If the user picks "now," the engine re-attempts the Twilio call. If "later," the engine schedules a retry and returns control to whatever else it was doing. For ambient pendant flows where the action was background-priority anyway, "later" is fine. For foreground requests ("draft this email now"), the user already knows the action is in flight, so we degrade gracefully to "queued, will retry."

### 3d. Phone-call MFA (rare but real)
Some banks and Epic deployments dial the user's registered phone with a robocaller, asks them to press a digit to confirm. We cannot intercept that call. The Twilio call from us says "Epic is calling you separately to confirm. Press the digit they ask for. I will wait." Wait for the page state to change (poll for absence of the MFA challenge selector with a 90-second timeout). This is a halt under Omar's autonomy rule if it fails; do not retry.

## 4. CAPTCHA

The existing `engine/app/captcha.py:1-365` is already pretty good. The strategy ladder is detect (`detect_captcha_in_page` at `captcha.py:59-104`) → NopeCHA extension wait (loaded via Chrome args at `engine/app/agent.py:1149-1158`) → playwright-recaptcha audio challenge → Capsolver → 2Captcha → user fallback.

For the cross-app flow:
- We hit CAPTCHA most often on first-time sign-in from a new IP (every app), on password reset, and on any account-recovery wall. We hit them rarely once the session cookie is established.
- Route to user when: site policy forbids automated CAPTCHA solving (Cloudflare's terms explicitly disallow), or the CAPTCHA is interactive (image-grid "select all traffic lights"), or all three automated providers fail in series.
- Route to NopeCHA/2Captcha when: invisible reCAPTCHA, hCaptcha, Turnstile, where the user does not even see a challenge most of the time. These are allowed by Omar's rules because the provider is a generic CAPTCHA-solving utility, not a service API for one of the user's apps.

Open question: NopeCHA is loaded as a Chrome extension. In the real-Chrome path on 9222 we cannot inject extensions into the user's running Chrome from outside. The fix is to bundle NopeCHA into a tiny unpacked-extension shim that gets installed once at Anticipy install time. Add to the installer at `installer/install.sh`.

## 5. Tab isolation

The agent must never type into a tab the user owns. The mechanism:

1. Every tab the agent opens gets a `chrome.runtime.connectNative`-set property: `data-anticipy-owned="<task_id>"`. Set via `Runtime.evaluate("document.documentElement.dataset.anticipyOwned = '<id>'")` right after `Target.createTarget`.
2. Before any `_cdp_click` or `_cdp_type`, the dispatcher checks that the target tab's `document.documentElement.dataset.anticipyOwned` is set and matches a known task. If not, refuse to act and log a "user tab almost touched" event.
3. The in-place navigation reuse logic at `anticipy_bridge_fallback_cdp.py:528-554` must be removed for the cross-app path. Reusing the user's existing Gmail tab to send a different draft is wrong. Always open a new tab in the Anticipy tab group instead.
4. On the Chrome side, the agent calls `chrome.tabs.group` against tabs it opens (already implemented in `extension_v4/background.js:504-517`), naming the group "Anticipy" and coloring it blue. The user gets one visual indicator at the right edge of their tab bar that shows agent activity.
5. The pendant Mac app shows a top-bar status line: "Anticipy has 2 tabs open: Salesforce, Gmail." Clicking it focuses the tab group.

## 6. Bot detection

Sites that block headless: Salesforce Lightning (mild, mostly invisible reCAPTCHA), Epic MyChart (DataDome on patient portal), Resy (heavy DataDome), OpenTable (PerimeterX/HUMAN), Amazon (homegrown). Sites that do not bot-check meaningfully: Procore, SimplePractice, TheraNest, Canvas, most college LMSs, most small-business law-firm matter systems.

Patchright/stealth flags that work today (`engine/app/agent.py:1135-1148`): `--disable-blink-features=AutomationControlled`, real user-agent string, real window size, `--use-gl=swiftshader` for GPU fingerprint. Patchright already handles `navigator.webdriver` removal, plugin fingerprint, WebGL renderer string spoofing.

What patchright cannot beat: behavioral biometrics on Akamai sites that track mouse-path entropy and inter-keystroke timing distributions. Our `engine/app/action_engine/cdp_dispatcher.py:155-230` Bezier+Gaussian motion is the right shape, but the parameter distributions need fitting against real user telemetry to actually match (today they are educated guesses).

Sites we will refuse in V1: heavy bot-walled consumer apps where the user is not paying for API access and we cannot pass even with full stealth. Tentative refuse list: Ticketmaster, StubHub, anything behind Kasada. Document the refusal explicitly to the user when they ask for it ("I can't drive Ticketmaster, they block automated browsers. Try buying directly.").

## 7. Session refresh

Sessions expire on a schedule that varies wildly per app. Salesforce default is 12 hours, Epic is often 5-30 minutes, Procore is 8 hours, Canvas is "as long as the tab is open." Two paths:

### 7a. Warm pings
A small background daemon, separate from the action engine, makes one GET per app per N hours against a known cheap authenticated endpoint (`/api/v1/sobjects/User/me` style, except we hit a UI URL since we cannot use APIs). For Salesforce, hit `/lightning/page/home` and check the response is 200 with HTML, not the login page. For Epic, hit `/MyChart/Home/Index`. Schedule per app: half the session timeout. The daemon runs as a launchd job, separate plist, only fires when the engine is running and the user is at the machine.

### 7b. Just-in-time re-login
When the engine actually tries to do something and gets bounced to a login wall, the responder at `engine/app/product/login_wall_responder.py:239-278` fires. With the MFA flow in section 3, the re-login round trip is 15-30 seconds. For "draft this email," that is annoying but acceptable. For "what is on my schedule," it is too slow. So we use **7a for read-heavy apps** (Salesforce, Epic, calendar systems) and **7b for write-heavy apps** (compose, send, submit).

Combined: a per-app config file (`engine/config/auth_profiles/<app>.json`) declares warm-ping URL, warm-ping interval, MFA detection selectors, and login wall detection rules. Adding a new app means writing one of these. That is the unit of "Anticipy supports this SaaS."

## 8. Open problems

- **Per-org Salesforce/Epic instances.** Same app, different login subdomain per customer. The KNOWN_LOGIN_HOSTS map at `engine/app/product/login_wall_responder.py:33-60` will not scale. Need a pattern-match registry.
- **Banks and brokerages.** Almost every flow eventually wants "schedule the bill payment." Browser automation against Chase, Schwab, Fidelity is plausible but the bot detection is the heaviest in the world. Maybe out of scope for V1, write the refusal down.
- **Concurrent agent + user in same app.** User is reading Salesforce in tab A, agent wants to update a record. Two writes can conflict at the API layer (Salesforce optimistic concurrency). Open a fresh background tab, do the work, close the tab. If a concurrency error fires, surface it to the user.
- **2FA recovery codes.** Some users have only paper recovery codes, no app. We cannot dictate them. If the registered MFA method fails, halt and ask user to log in manually.
- **HIPAA in Epic.** Even though we are browser-driving and not API-calling, we are still processing PHI. Need a compliance review before shipping to a single hospital. Block until reviewed.
- **Native desktop apps.** Some critical EHRs (Cerner PowerChart, some Epic Hyperspace deployments) are not browser-based. Out of scope for the cross-app-auth thread, but worth flagging that pure-Chrome will not cover 100% of healthcare even with perfect auth.
