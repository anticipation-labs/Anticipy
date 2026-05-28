# Bot fingerprint hardening (W2 research)

Date: 2026-05-28T04:02Z
Author: W2 (Claude Opus 4.7)
Status: ADVISORY. Do not apply. W3 reviews and applies after sign-off.

## TL;DR

Latest canary run `state/v7/bot_detection_20260528T040200Z` shows **REAL_HUMAN_BROWSER on all 3 sites** (sannysoft passed=4 failed=0, areyouheadless headless=false, creepjs headless=0% stealth=0%). No live failures. This document is forward-defensive: small posture tightening so a future Chrome update or stricter detector (PerimeterX, DataDome, Cloudflare Turnstile v2) does not flip us.

Confirmed via CDP fingerprint probe (`/tmp/probe_fingerprint.py`) on Chrome 148.0.7778.179, the cloned-real-profile Chrome on 9222:

- navigator.webdriver = `false`  (clean)
- plugins.length = 5 (PDF Viewer, Chrome PDF Viewer, Chromium PDF Viewer, Microsoft Edge PDF Viewer, WebKit built-in PDF)  (clean)
- navigator.languages = `["en-US","en"]`  (clean)
- chrome.app + chrome.csi + chrome.loadTimes all present  (clean)
- chrome.runtime missing  (acceptable, real Chrome without an extension also lacks this)
- WebGL unmasked vendor = "Google Inc. (Apple)" / renderer = ANGLE Metal Apple M2  (clean, matches a real M2 user)
- Notifications coherence: both `Notification.permission` and `permissions.query({name:'notifications'})` return `denied`  (coherent, real)
- No `$cdc_` keys, no `selenium*` keys  (clean)
- userAgent does not contain "HeadlessChrome"  (clean)

## Signals that COULD flag us under stricter detectors

None of these flagged the current canaries. Listed in priority order if hardening is ever applied.

### 1. window.outerWidth / window.outerHeight = 0 in background-created tabs

Observation: when a tab is created via `Target.createTarget {background: true}` and probed before it is ever foregrounded, both `outerWidth` and `outerHeight` report 0. Real Chrome returns the chrome-frame-inclusive window dimensions (1440 + chrome chrome, e.g. 1440x900 for a maximized 13" Mac).

Risk: low for now. None of the three public canaries probe outer dimensions while the tab is offscreen. CreepJS reads them only after focus. But Cloudflare Turnstile v2 and DataDome read this signal in their server-side scoring.

Fix (NO restart): inject a per-tab CDP `Page.addScriptToEvaluateOnNewDocument` shim via the bridge that runs on every new background target:

```js
// Spoofs outer dimensions to match inner + a plausible chrome height (74px on Mac).
// Only spoofs when outer is 0 (i.e. background tab). Real foreground tabs untouched.
(() => {
  const realOuterW = window.outerWidth;
  const realOuterH = window.outerHeight;
  if (realOuterW === 0 || realOuterH === 0) {
    Object.defineProperty(window, 'outerWidth',  { get: () => window.innerWidth });
    Object.defineProperty(window, 'outerHeight', { get: () => window.innerHeight + 74 });
  }
})();
```

Why this does NOT introduce a new bot signal: defineProperty getters look like every other getter on `window`. Stealth-plugin uses the same pattern in `window.outerdimensions` evasion and that ships clean against creepjs and fingerprint.com. We avoid the over-spoof trap of always overriding (which would flag real foreground tabs as inconsistent).

Apply via: per-target `Page.addScriptToEvaluateOnNewDocument` right after `Target.createTarget`. Bridge change only. No Chrome restart.

### 2. chrome.runtime missing

Observation: `window.chrome` exists, `window.chrome.app` + `window.chrome.csi` + `window.chrome.loadTimes` all exist (correct for normal Chrome), but `window.chrome.runtime` is `undefined`.

Risk: low. Real Chrome without an active extension messaging context can also lack `chrome.runtime.id`. Sannysoft does not flag this in 2026. But the puppeteer-extra-stealth `chrome.runtime` evasion explicitly fills this in, and some modern detectors (sift.com, Castle.io) score the absence.

Fix: inject a minimal shim:

```js
if (window.chrome && !window.chrome.runtime) {
  window.chrome.runtime = {
    OnInstalledReason: {INSTALL:'install', UPDATE:'update', CHROME_UPDATE:'chrome_update', SHARED_MODULE_UPDATE:'shared_module_update'},
    OnRestartRequiredReason: {APP_UPDATE:'app_update', OS_UPDATE:'os_update', PERIODIC:'periodic'},
    PlatformArch: {ARM:'arm', ARM64:'arm64', MIPS:'mips', MIPS64:'mips64', X86_32:'x86-32', X86_64:'x86-64'},
    PlatformNaclArch: {ARM:'arm', MIPS:'mips', MIPS64:'mips64', X86_32:'x86-32', X86_64:'x86-64'},
    PlatformOs: {ANDROID:'android', CROS:'cros', LINUX:'linux', MAC:'mac', OPENBSD:'openbsd', WIN:'win'},
    RequestUpdateCheckStatus: {NO_UPDATE:'no_update', THROTTLED:'throttled', UPDATE_AVAILABLE:'update_available'}
  };
}
```

Why this does NOT introduce a new bot signal: the shape matches the upstream Chromium enum exactly (sourced from chromium/src `chrome.runtime` IDL). Detectors checking `typeof chrome.runtime.OnInstalledReason.INSTALL === 'string'` will pass. We omit the `connect`, `sendMessage`, `getManifest` functions because faking those introduces detectable Proxy traps; real Chrome without an extension also doesn't expose them in this context.

### 3. Add `--disable-blink-features=AutomationControlled` to the launch plist

Observation: Chrome started with `--remote-debugging-port=9222` does NOT automatically enable the AutomationControlled blink feature in modern Chrome (since ~Chrome 120). The plist currently does NOT pass `--enable-automation`, so we are already clean. But adding the explicit `--disable-blink-features=AutomationControlled` is belt-and-suspenders against future Chrome regressions where remote-debugging implicitly turns it on.

Why this does NOT introduce a new bot signal: this is the single most common stealth flag in 2026, used by every legitimate auto-login / kiosk / RPA tool. Detectors cannot fingerprint its presence because it has no DOM-visible side effect.

CAUTION: this requires a Chrome restart, which violates R4 hard rule "DON'T restart Chrome." Defer to a planned maintenance window. Document in `state/v7/bot_fingerprint_hardening.md` only; W3 schedules a restart with Omar's explicit sign-off when convenient.

### 4. Strip the "HeadlessChrome" token defensively (not currently present)

Observation: current UA is `Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36`. No `HeadlessChrome` token. Clean.

Risk: zero today. Documented only so that if Chrome ever ships a `--headless=new` regression that leaks the token into headful mode, we have a remediation plan: CDP `Network.setUserAgentOverride` per session, OR `--user-agent="<above string>"` in the launch plist.

Do NOT apply unless the canary actually flips. Over-spoofing UA when the real UA is already correct creates a new tell: detectors compare the JS `navigator.userAgent` against the HTTP `User-Agent` header. If those differ, that mismatch is itself a strong bot signal.

## Anti-patterns to AVOID (over-hardening that creates bot signals)

These are commonly seen in low-quality stealth scripts. We deliberately do NOT do these:

1. **Do not** delete `navigator.webdriver` with `delete navigator.webdriver`. The deletion changes the property descriptor in a way detectors can fingerprint via `Object.getOwnPropertyDescriptor(Navigator.prototype, 'webdriver')`.
2. **Do not** spoof `hardwareConcurrency` to a "common" value like 4 or 8 across all sessions. Real users have variance. Spoofing to a constant across IPs creates a cohort signature.
3. **Do not** randomize `navigator.plugins`. The 5-PDF-viewer set is the M148 Chrome default; randomizing it makes us NON-default and therefore suspicious.
4. **Do not** add `--no-sandbox` or `--disable-web-security` for any reason. Both are headless-cluster smells and Cloudflare's bot detection flags them in TLS-fingerprint pre-flight.
5. **Do not** inject Proxy traps around `navigator` or `chrome.runtime`. Detectors check `'' + navigator.permissions.query` for `'function permissions() { [native code] }'` and Proxy returns the Proxy's toString instead.
6. **Do not** randomize WebGL renderer. Real M2 Macs ALL return `ANGLE (Apple, ANGLE Metal Renderer: Apple M2, Unspecified Version)`. Randomizing this puts us in the long tail of "weird GPU strings" which is itself flagged.

## Recommended apply order (for W3)

1. PRIORITY 1: Outer-dimensions shim on background tabs only (item 1). Bridge change. No restart. Test via probe rerun after change.
2. PRIORITY 2: `chrome.runtime` shim (item 2). Bridge change. No restart.
3. PRIORITY 3 (defer): `--disable-blink-features=AutomationControlled` plist add (item 3). Requires Chrome restart, schedule with Omar.
4. SKIP unless canary flips: UA override (item 4).

After each step, re-run `scripts/v7/bot_detection_canary.sh` AND the fingerprint probe to confirm no regression on any of the 3 canary sites AND confirm tab leakage stays 0.

## Sources

- sannysoft test source: https://bot.sannysoft.com/ (lists every probe the page runs)
- areyouheadless: https://arh.antoinevastel.com/bots/areyouheadless
- creepjs: https://abrahamjuliot.github.io/creepjs
- puppeteer-extra-plugin-stealth evasions list (20 modules): https://github.com/berstend/puppeteer-extra/tree/master/packages/puppeteer-extra-plugin-stealth/evasions
- Chrome command-line flag catalogue (peter.sh, sourced from Chromium): https://peter.sh/experiments/chromium-command-line-switches/
- Headless cat-n-mouse test corpus: https://github.com/paulirish/headless-cat-n-mouse
