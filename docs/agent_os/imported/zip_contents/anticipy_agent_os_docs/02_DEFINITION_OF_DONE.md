# 02 — Definition of Done

## Full product done

A normal user goes to the hosted Anticipy website, sees a download button, downloads the branded app, opens Anticipy Execute, completes onboarding, and then uses the assistant in real life.

Done means all of this works:

1. **Download:** hosted site has a clear download button for Anticipy Execute.
2. **Install/open:** the app opens without a developer terminal.
3. **Onboarding:** it asks the user questions, installs/connects the Chrome extension/local bridge, and explains permissions.
4. **Profile build:** it opens the user’s own logged-in Chrome, discovers/scrapes authorized sources, and builds a profile.
5. **Clarification:** it asks/calls the user for missing/uncertain facts.
6. **Connection mesh:** it maps the user’s tools: Gmail/Outlook, Calendar, CRM, Slack, legal/accounting tools, browser-only sites.
7. **Main page:** the user can start listening, paste a transcript, upload MP3/audio, or use live mic/device later.
8. **Active listening:** the same engine processes everything: transcript, MP3, mic, SMS, browser, email, calendar, CRM.
9. **Memory:** it remembers people, commitments, preferences, work context, and unresolved loops.
10. **Intent:** it detects real tasks even when they are not phrased as commands.
11. **Vents/jokes:** it does not act on vents, sarcasm, jokes, or emotional noise.
12. **Prepare and park:** it automatically performs harmless prep and parks final irreversible steps.
13. **API arm:** it acts through direct integrations when available.
14. **Browser arm:** it acts in the user’s real Chrome when APIs are missing.
15. **Voice/text arm:** it closes loops by text/call when appropriate.
16. **Receipts:** it proves actions by independently re-reading artifacts.
17. **Five-day proof:** the user lives with it for five real days and trusts it.

## Done for the current build sprint

The next sprint is not the whole company. It is the smallest full-stack owner product that proves the hard middle.

Sprint done means:

1. User can launch the local/downloaded app.
2. User can onboard enough to create a basic profile and connection mesh.
3. User can paste/upload a messy day transcript.
4. Anticipy remembers candidate commitments without firing unsafe triggers.
5. Anticipy infers structured work from those memories.
6. Anticipy prepares at least three reversible artifacts:
   - calendar hold,
   - Gmail/email draft,
   - browser-prepared item/form/cart/return flow.
7. Anticipy parks them as “ready for approval.”
8. User approval executes only whitelisted reversible actions or finalizes only the explicitly approved safe action.
9. Every executed action has independent read-back.
10. Skeptic agents fail to break the slice on vents, sarcasm, stale state, money, wrong account, and self-attestation.

## Things that do not count as done

- “The engine could do it.”
- “The test is green.”
- “The builder says it works.”
- “It worked in a mock.”
- “The UI exists but is not wired.”
- “The browser agent can read but not prepare.”
- “The app builds but cannot be downloaded/opened by a normal user.”
- “The transcript path works but the memory/action handoff does not.”

## Receipt standards

A receipt is a human-openable artifact:

- Calendar event re-read by ID.
- Gmail draft re-read by ID.
- Browser page screenshot + DOM state + URL proving the cart/form is prepared.
- Phone call/SMS log read from provider.
- Profile facts with source links/screenshots/confidence.
- App download installed and launched.
- Test transcript with expected vs actual, including false-actions and misses.

No receipt, no done.
