# Build 161 — interaction repairs

Source branch: cloudflare-backend. Build161 confirmed VALID and IN_BETA_TESTING by Apple query34105899086. Brain reply repairs remain a separate, ongoing
change and are not claimed by this iOS release.

## Changed behavior

- Reply fields reserve keyboard space. Editing a task hides the unrelated
  composer and microphone control. The waiting banner opens the actual task.
- Send preserves a durable submission identity and exact card/question/version.
  Accepted answers get a receipt; uncertain writes reconcile the exact event.
- Typed messages and app/SMS replies appear in the thread. `anticipy_text`
  responses now render alongside proactive `anticipy_says` messages.
- Long answers have an expandable preview. Listening cards are scrollable with
  bounded titles and full-detail sheets; controls stay outside their content.
- Canonical source-event IDs replace duplicate transcript-derived work cards,
  including when the task finishes. Identical wording does not merge jobs.
- Expensive speaker model loading/inference runs on a serial background queue;
  Stop tails follow the same ordered delivery path. Account switches invalidate
  pending voice callbacks. Unchanged feed polls no longer publish equal arrays.
- Optional calendar/contact offers use an authenticated model judgment with
  recent conversation. Capitalization and keyword rules were removed. Offers
  stay inline until the person chooses Review access. Permission remains optional.

## Verification

- Full pre-change iOS suite passed on build 160.
- Full final iOS suite passed on build 161; both project build numbers agree.
- Full simulator build succeeded. Real UI walk covered fresh onboarding,
  optional permissions declined, waiting-banner navigation, typed task answer,
  software keyboard, Send and its accepted receipt. The real local brain
  consumed the answer and the app displayed its persisted response.
- Slow injected speaker inference preserved callback order, dropped a previous
  account's callback and left the main run loop responsive (63 ticks observed).
- Full Worker suite and TypeScript typecheck passed.
- Context route tests covered authentication, owner isolation, duplicate calls,
  consent, malformed model output, outage and revocation during a provider call.
- Fourteen varied real-model context cases passed. Fenced JSON handling was
  repaired after the first run exposed provider response-format variation.
- Browser extension: all 94 suites passed. This is not proof that every website
  or the owner's installed browser works; those live journeys remain ongoing.

Evidence: context-model-results.json; ignored local logs under work/audit with
prefix overnight-. Model/HTTP traces contain synthetic fixtures and remain local.
Physical-device freeze timing and the capture screen during actual live microphone
input have not yet been measured. Do not call the entire app issue-free.

## Adversarial review

Reviewed keyboard geometry in Simulator, account-switch callbacks, retry identity,
multiple tasks with identical words, terminal-task provenance, unavailable models,
quoted injection, actual people named with ordinary words, and default permissions.
The screenshot's specific wording is an evaluation example, never a routing rule.

## Build162 and browser0.16.0

- Typed replies follow the message just sent; a reader scrolling older content
  is left in place with a New reply control. Typed answers no longer inflate
  the ambient “nothing needed” count.
- Fresh-account first utterances can offer useful optional context; historical
  lines loaded on launch cannot.
- Browser update instructions now explain that Reload does not download new
  files and provide a direct setup link, including while already paired.
- Adversarial simulator use exposed a layout loop when the New reply banner
  disappeared above a lazily estimated feed. Main-thread sample showed repeated
  LazySubviewPlacements and100% CPU. The bounded current feed now uses measured
  rows; the scroll follows the banner update. Same tap and subsequent typing
  completed, and a natural cancellation reached the real local model/backend.
- Final162 full iOS logic suites and simulator build passed. Both source build
  numbers are162. Physical-device profiling still remains unproven.
- Real Chrome appointment test first submitted FIVE incomplete forms, because
  wrapping labels were absent from the model's field context and the effect
  fence compared before the scope check cleared a value.0.16.0 includes native
  labels/aria-labelledby and checks the FINAL payload on click and Enter. The
  same task then saved exactly one appointment with the requested start and end.
- Six real-DOM naming cases pass. Both error-injection final-payload regressions
  pass.94 extension suites passed. Separate comparison, capacity, login-wall
  and injection browser tasks passed using real Chrome and a metered model.
- The extension archive will be published with this source; existing unpacked
  personal Chrome installations still require replacing their files/reloading.
  Browser security policy blocked the management page, so it was not bypassed.
