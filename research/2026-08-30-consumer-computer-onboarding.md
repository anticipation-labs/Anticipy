# Consumer computer onboarding — 2026-08-30

## What is wrong today

- Browser setup is a long Railway guide, but the live pairing code appears on
  a separate `chrome-extension://` page. The guide cannot show whether the
  extension is installed or linked.
- On iPhone, browser pairing is buried in Settings and the setup URL only has
  an “open” action. Moving the setup from the phone to a computer means copying
  a URL by hand.
- The Mac connector opens a ZIP on the iPhone. An iPhone cannot install it and
  there is no hosted Mac setup page to send to a Mac.
- First run ends before either computer surface is offered, despite both being
  part of the product the person has just installed.

## The shipped shape

1. First run ends on an optional **Your computer** beat. It has two compact
   cards: Browser and Mac app. Each card can open its hosted setup page or send
   that page through the native iOS share sheet (AirDrop, Messages, Mail, and
   any other installed share destination). Browser pairing remains available
   on the same screen, and skipping the entire beat remains possible.
2. `/setup.html` becomes the single browser installation and pairing surface.
   When the Anticipy extension is present on that page, an extension bridge
   publishes only three setup facts into the trusted page: installed, current
   one-time pairing code, and linked. The page shows the code and changes to a
   linked receipt without a refresh.
3. The extension still owns the browser identity, private agent credential and
   one-time code. The web page cannot mint, claim or reassign an agent and never
   receives an owner session. The signed-in iPhone remains the only caller that
   can bind the code to an account, preserving `guard.pb.js`'s tenant binding.
4. `/mac.html` becomes the matching Mac setup surface. On a phone it leads with
   the system share action; on a Mac it leads with the notarized download and
   the short install/permission/sign-in path.
5. Settings routes to the same two hosted pages and native share actions. There
   is one ceremony per connector rather than onboarding copy and Settings copy
   drifting apart.

## Proof required before calling it shipped

- The first-run route and copy gates pass with the new optional beat.
- The iOS app compiles and the visual walk reaches both connector subpages.
- The extension package contains the bridge, passes its focused bridge gate,
  and its full test suite remains green.
- A staged Railway deploy serves both setup pages and the current extension and
  notarized Mac archives; live bytes are checked after deployment.
- A pushed iOS build is not called available until App Store Connect accepts it.
