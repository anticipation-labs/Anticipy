# Realistic Exemplar Test Sites for the Universal Surface Runtime

Date: 2026-05-26
Owner: Anticipy V7, browser action engine.

## Selection criteria

Anticipy needs sites that exercise the browser-agent runtime the way production sites would. The bar is:

1. Legal and explicit invitation to drive aggressively. No ToS violation, no IP ban risk.
2. Realistic bot-detection level (none, low, or fingerprint-only). We deliberately exclude Cloudflare-walled targets like `demo.opencart.com` and `fakestoreapi.com` because they are not representative of a normal Gmail or Calendar flow and they will only test our anti-bot stack.
3. Real multi-step flows (auth, navigation, list, detail, write, confirm).
4. Surface coverage across the categories the universal runtime promises: form-heavy, table-heavy, canvas/SVG, SPA, iframe, modal-heavy, file-upload, drag-drop, shadow DOM, dynamic-loading.
5. Public, stable, deterministic credentials. No setup theater.

We dropped from the candidate list: `realworld.cypress.io` (DNS NXDOMAIN, not a hosted demo, lives in the cypress-realworld-app repo), `ecommerce-playground.lambdatest.io` (host timed out on TCP connect, treat as flaky), `demo.opencart.com` (Cloudflare turnstile challenge on the bare GET), `demo.applitools.com` (Vercel security checkpoint on bare GET), `fakestoreapi.com` (Cloudflare 526 invalid SSL). These are evidence in `/tmp/oc.html`, `/tmp/at.html`, `/tmp/fs.html`, `/tmp/lt.html` collection failures.

## The ten chosen sites

### 1. saucedemo.com (Swag Labs)

URL: https://www.saucedemo.com
Public credentials (rendered into the login page footer by the SPA): `standard_user`, `locked_out_user`, `problem_user`, `performance_glitch_user`, `error_user`, `visual_user`. Password for all: `secret_sauce`. Source: https://saucelabs.com/resources/blog/saucedemo-com-step-by-step-walkthrough.
What it tests well: classic e-commerce SPA built with React, login then product list then cart then checkout then confirm. The six user types give us deterministic failure modes (the locked-out user blocks login, the problem user injects misordered product images, the performance user adds artificial 5s waits). Excellent for validating retry policy and confirm-card behavior.
Bot detection: none. `meta robots noindex` only, no rate limit, no CAPTCHA. The page is a single React bundle (`/static/js/main.bcf4bc5f.js`), so the DOM only exists post-render.
Primitives exercised: type, click, select (sort dropdown), keyboard navigation, modal/menu open and close. No file upload, no iframe.
Action sequence: navigate, type username, type password, click Login, click Add-to-cart on two items, click cart icon, click Checkout, fill first name and last name and zip, click Continue, click Finish, assert order-complete header.
Gotchas: SPA hydration delay, so wait for `[data-test="login-button"]` before typing. `performance_glitch_user` makes flows look broken when it is actually intentional latency. The hash-style URL handling (the inline script that splits `?key=val~and~key=val`) means deep links need decoding.

### 2. automationexercise.com

URL: https://automationexercise.com
Public credentials: none required; signup is open. We can create disposable accounts with arbitrary emails. The site even exposes an REST API list at `/api_list` and a documented set of 26 test cases at `/test_cases` (Register User, Login User with correct email and password, Login User with incorrect email and password, Logout User, Register User with existing email, Contact Us Form, Verify Test Cases Page, Verify All Products and product detail page, Search Product, ... through Add Products in Cart, Verify Product quantity in Cart, Place Order: Register while Checkout, Place Order: Register before Checkout, Place Order: Login before Checkout, Remove Products From Cart, ...).
What it tests well: the only candidate in the set that combines a full signup-to-payment flow with categorized product browsing and brand filtering. It tests our cookie persistence and our handling of multi-step forms across distinct routes.
Bot detection: none. Plain server-rendered PHP-ish stack with Bootstrap, no Cloudflare, no JS challenge.
Primitives exercised: type, click, select, checkbox, radio, file upload (contact-us page accepts an attachment), modal (subscription confirmation), redirect-heavy navigation, table rendering on cart page.
Action sequence: navigate to `/signup`, fill email and name, complete the long account-creation form (date of birth selects, newsletter checkboxes, address fields), click Create Account, hit Continue, add three products from `/products`, navigate to `/view_cart`, click Proceed to Checkout, fill billing, place order with the mock card number `4111111111111111`, assert success page.
Gotchas: occasional injected interstitial ads via Google AdSense which can steal the click. Use a request-interceptor to block ad domains or use a viewport that pushes the ads off-screen.

### 3. the-internet.herokuapp.com (Sauce Labs / Tau "The Internet")

URL: https://the-internet.herokuapp.com
Public credentials: Form Auth `tomsmith` / `SuperSecretPassword!`; Basic Auth and Digest Auth both `admin` / `admin`.
What it tests well: 44 isolated challenge pages, each surfacing one quirky UI primitive. Treat this as the unit-test layer for the runtime. Pages of note: `/drag_and_drop`, `/dynamic_loading`, `/frames`, `/nested_frames`, `/shadowdom`, `/upload`, `/download`, `/javascript_alerts`, `/windows`, `/horizontal_slider`, `/key_presses`, `/context_menu`, `/large` (large DOM stress), `/slow` (slow resource load), `/redirector`, `/tinymce` (WYSIWYG iframe), `/challenging_dom`, `/dropdown`, `/hovers`, `/infinite_scroll`, `/checkboxes`, `/tables`, `/disappearing_elements`, `/entry_ad`, `/exit_intent`.
Bot detection: none, intentionally permissive. Hosted on Heroku free dynos so cold-start latency is real and useful to test.
Primitives exercised: every input primitive plus iframe and shadow DOM plus alert and dialog plus drag and drop plus file upload and download plus basic and digest auth.
Action sequence (one chosen sub-flow): GET `/login`, type username, type password, click Login, assert `/secure` redirect, click Logout, assert flash message; then GET `/drag_and_drop` and drag column A onto column B and assert order swap.
Gotchas: drag-and-drop here uses HTML5 events; Playwright and Puppeteer differ on whether `dispatchEvent` works versus `mouse.down`-`mouse.move`-`mouse.up`. The `/large` page hits 50000 DOM nodes which exposes naive querySelectorAll loops.

### 4. demoqa.com

URL: https://demoqa.com
Public credentials: register your own at `/register` (open signup). Book store API token issued on login at `/Account/v1/Login`.
What it tests well: six categorized panels: Elements, Forms, Alerts/Frames/Windows, Widgets, Interactions, Book Store Application. Best site for SVG and progress-bar widgets, date pickers (jQuery UI), draggable and resizable elements, modal stacks, and a real Book Store API behind a real auth wall.
Bot detection: none. Heavy Google AdSense though (a known annoyance).
Primitives exercised: every primitive on the menu, including resizable, sortable, selectable, slider, progress bar, tabs, accordions, autocomplete, date picker, color picker (via Widgets), file upload and download (Elements), tools tip, browser windows, alerts.
Action sequence: navigate to `/login`, register an account, log in, navigate to `/books`, search for a book, click Add To Your Collection, navigate to `/profile`, assert the book is in your shelf.
Gotchas: AdSense iframes occupy real viewport space and will absorb clicks unless filtered. The site loads jQuery and the entire jQuery UI bundle, so initial paint is slow on cold cache. Use a content-blocker config when running headless.

### 5. juice-shop.herokuapp.com (OWASP Juice Shop)

URL: https://juice-shop.herokuapp.com
Public credentials: register your own; admin credential is intentionally exposed in challenge 4 (`admin@juice-sh.op` / `admin123`) but use real signup for normal flows.
What it tests well: Angular SPA with a real Express backend, real `/api/*` endpoints, basket persistence, JWT auth, file upload (complaint form), challenge tracker that scores progress. Closest to a real production SPA in feel.
Bot detection: none in the Heroku-hosted variant. The Express layer logs but does not throttle.
Primitives exercised: SPA navigation via Angular Router, modal stacks (cookie banner, welcome dialog, language picker), drag-and-drop on items, file upload via the complaint form, basket and address books, JWT-aware fetch in localStorage.
Action sequence: dismiss the welcome dialog, dismiss the cookie banner, click Account then Login then Not yet a customer, fill email and password and security question, log in, search for "apple", add Apple Juice to basket, click basket, click Checkout, choose address, choose payment, Place your order, assert order confirmation.
Gotchas: three modals fire on first load and they must be dismissed in order. Cold dynos add 10-15s to first fetch. The API responses contain CSRF tokens we have to round-trip.

### 6. parabank.parasoft.com

URL: https://parabank.parasoft.com/parabank/index.htm
Public credentials: register an account via `/register.htm` with arbitrary username, or use the documented seeded user `john` / `demo`.
What it tests well: legacy banking app: server-rendered JSPs with the session ID in the URL (`;jsessionid=...`), a transaction table, transfer-funds form, bill-pay form, an Admin Page where the seeded ledger can be reset. Excellent surface for our table-extraction and session-cookie handling.
Bot detection: none, but the jsessionid in the URL is the trap; it changes on every navigation if cookies are disabled.
Primitives exercised: form post with hidden fields, table read and parse, dropdown select for "from account" and "to account", date input, pagination of transaction history.
Action sequence: open `/index.htm`, log in as `john`/`demo`, click Transfer Funds, transfer $25 from one account to another, click Find Transactions, search by amount, assert the new transaction row.
Gotchas: the jsessionid URL pattern means caching prior URLs is dangerous; always anchor selectors on the form name, not on the href. The Admin page can reset data, which is great for repeatable tests but be polite.

### 7. demoblaze.com

URL: https://www.demoblaze.com
Public credentials: register your own; throwaway accounts are normal here.
What it tests well: pure Bootstrap modal-driven UX. Login, signup, contact, about-us, and order placement are all modals over the same page. This is the canonical modal-heavy surface in the test-site landscape.
Bot detection: none.
Primitives exercised: modal open and close, modal stack (sign in opens over the page, place-order opens over the cart), nav bar dropdowns, card grid, dynamic price calc in cart.
Action sequence: click Sign up, register, click Log in, sign in, click a phone category, click a product card, click Add to cart, dismiss the alert, click Cart, click Place Order, fill modal form, click Purchase, capture the success modal with the order number.
Gotchas: each Add-to-cart fires a `window.alert` that must be auto-accepted, otherwise the navigation freezes. The site uses an unauthenticated `/addtocart` POST whose payload includes the product id and the JWT, so we have to read localStorage for the token.

### 8. bot.sannysoft.com (bot-detection canary)

URL: https://bot.sannysoft.com
Public credentials: none.
What it tests well: the Intoli bot-detection test matrix plus FpScanner. Renders a table of pass/fail rows for WebDriver, Chrome flag presence, Permissions, Plugins Length, Languages, WebGL Vendor, navigator.platform, broken-image probe, and more. Lets us detect regressions in our anti-fingerprint configuration of the runtime (whether stealth flags are still enabled).
Bot detection: this site IS the detector. The point is to score ourselves against it every cycle.
Primitives exercised: read-only DOM scrape; no input. We just navigate, wait for the table to populate, and extract the row results.
Action sequence: navigate, wait 3 seconds for the JS-driven tests to finish, snapshot the `#user-agent-result`, `#webdriver-result`, `#chrome-result`, `#permissions-result`, `#plugins-length-result`, `#languages-result`, `#webgl-vendor-result`, `#webgl-renderer-result`, `#broken-image-dimensions-result`, and the Fp-Scanner table. Assert that the count of `failed` cells is below a threshold we set for ourselves.
Gotchas: the page itself injects scripts from cdnjs, jsdelivr, and yandex.ru. Yandex Metrika can be aggressive in some regions; we should block it at the network layer so the timing measurements stay clean.

### 9. arh.antoinevastel.com/bots/areyouheadless (secondary bot canary)

URL: https://arh.antoinevastel.com/bots/areyouheadless
Public credentials: none.
What it tests well: independent second opinion. Antoine Vastel runs the Fp-Collect and Fp-Scanner libraries that several commercial bot-detection products derive from. The endpoint renders a single verdict "You are not Chrome headless" in green or "You are Chrome headless" in red, and `/bots/` exposes the full fingerprint table.
Bot detection: this site IS the second detector.
Primitives exercised: read-only DOM scrape, same shape as sannysoft.
Action sequence: navigate to `/bots/areyouheadless`, wait 2 seconds for `areuheadless.js` to compute, read the text of `#res > p`, assert it equals "You are not Chrome headless". Then navigate to `/bots/`, wait for the `#fp` and `#scanner` tables to populate, extract all `Consistent`/`Unsure`/`Inconsistent` rows.
Gotchas: the verdict can flip per-region because of IP heuristics in fingerprint-scan.com signals; the result we trust is the local headless detection only. Cookies are dropped via the embedded `analytics.js`, which should be allowed (the test correlates).

### 10. httpbin.org

URL: https://httpbin.org
Public credentials: Basic Auth examples are `/basic-auth/{user}/{passwd}` so any pair works. Cookie examples use `/cookies/set?key=value`.
What it tests well: the runtime's network primitives end of the contract. Every HTTP verb, every status code, gzip and deflate, basic-auth and digest-auth, cookies, redirects, streaming, image fetches, the HTML form at `/forms/post` that POSTs to `/post`, request-headers echo. This is the contract test for our HTTP layer when a flow needs us to call APIs directly rather than drive UI.
Bot detection: none.
Primitives exercised: navigation, form submission to non-HTML endpoint, file upload via `/post`, response capture (JSON), 3xx redirect chains, 401 and 407 flows, cookie persistence.
Action sequence: GET `/forms/post`, fill the customer-name input, pick checkboxes, type a comment, click Submit; assert the response page echoes our payload exactly. Then GET `/basic-auth/foo/bar` with credentials in URL, assert 200.
Gotchas: httpbin runs on Heroku and is community-maintained; uptime is usually fine but if it 503s, the Postman fork `https://postman-echo.com` is a drop-in substitute for the API surface (no HTML form, though).

## Tier-1 must-test recommendations

These three give us 80 percent of the surface coverage and they never gate on third-party infra:

1. saucedemo.com. The integration smoke for the SPA path. Cheap, deterministic, six injected failure modes.
2. the-internet.herokuapp.com. The unit-test layer for every individual primitive (iframe, shadow DOM, drag-drop, file upload, dialog, basic auth). Run a fast subset every cycle, the full 44-page sweep nightly.
3. automationexercise.com. The end-to-end signup-to-payment flow. The only candidate that exercises a multi-form journey across distinct routes with real form persistence.

## Bot-detection canary recommendation

bot.sannysoft.com every cycle. One navigate, one DOM read, one scoring assertion. If our pass rate drops, our anti-fingerprint config regressed and we must investigate before any flow on a real site (Gmail, Calendar, OpenTable) silently degrades. Run arh.antoinevastel.com weekly as a second opinion.

## Sources

- saucedemo SPA confirmed via curl with gzip decompress; React bundle at `/static/js/main.bcf4bc5f.js`; users listed at https://saucelabs.com/resources/blog/saucedemo-com-step-by-step-walkthrough
- the-internet challenge list curl-fetched from https://the-internet.herokuapp.com
- demoqa categories from https://demoqa.com plus the API at `/Account/v1/Login`
- automationexercise test cases curl-fetched from https://automationexercise.com/test_cases (Test Cases 1 through 26)
- juice-shop confirmed live with a fresh API response at https://juice-shop.herokuapp.com/api/Quantitys
- parabank login form and register form curl-fetched from https://parabank.parasoft.com/parabank/index.htm and `/register.htm`
- demoblaze fetched at https://www.demoblaze.com, modal IDs `signInModalLabel`, `logInModalLabel`, `videoModalLabel` confirmed
- bot.sannysoft.com test rows fetched directly
- arh.antoinevastel.com Fp-Scanner table fetched directly from `/bots/` and `/bots/areyouheadless`
- httpbin form endpoint at https://httpbin.org/forms/post
