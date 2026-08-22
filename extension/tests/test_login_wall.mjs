// A sign-in page is the most ordinary thing on the web and it was killing
// errands. The engine had no name for one: it landed on a login form, tried
// things, and produced "I spent 9 steps on <url> without getting anywhere" —
// from which nobody can tell whether the site is broken, the agent is broken,
// or all it needed was a thumb.
//
// This suite is mostly NEGATIVES, on purpose. Calling a wall where there is
// none parks a run that was working and sends a text about nothing, which is
// strictly worse than the dull failure it replaces. So: a header "Sign in"
// link, an optional account on a booking form, and a signed-in account page
// full of password controls all have to come back null — and the reCAPTCHA
// badge that once cost a live booking has to stay out of the way.
//
// Run: node extension/tests/test_login_wall.mjs
import {
  detectsLoginWall, handBackSentence, canContinueAfterOwner, looksLikeChallenge,
} from "../login_wall.js";

let failures = 0;
const check = (name, ok, extra = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}${ok || !extra ? "" : ` — ${extra}`}`);
  if (!ok) failures++;
};

// --------------------------------------------------------------------------
// Fixtures in the EXACT shape page_map.js produces:
//   [idx] <role> label [state] (extra) @(x,y)
// with sensitive inputs redacted, marked, and absent from `fields`.
// --------------------------------------------------------------------------
const SENSITIVE = "(sensitive field — never fill)";
let seq = 0;
const el = (role, label, extra = "") =>
  `[${seq}] <${role}> ${label}${extra} @(600,${120 + 40 * seq++})`;
const map = (parts) => { seq = 0; return parts(); };
const field = (index, label, type, over = {}) =>
  ({ index, name: label.toLowerCase().replace(/\s+/g, "_"), label, type,
     required: true, readOnly: false, value: "", ...over });

// ---- POSITIVE: a dedicated sign-in page (a utility portal, the long tail) --
const LOGIN_PAGE = {
  url: "https://portal.hydro-example.ca/account/login",
  title: "Sign in | Hydro Example",
  overlay: false,
  elements: map(() => [
    el("link", "Skip to content", " [href=/#main]"),
    el("textbox", "Email address"),
    el("textbox", "Password", ` ${SENSITIVE}`),
    el("checkbox", "Remember me", " [unchecked]"),
    el("button", "Sign in"),
    el("link", "Forgot your password?", " [href=/account/reset]"),
    el("link", "Create an account", " [href=/account/register]"),
  ].join("\n")),
  text: "Sign in to My Account Email address Password Remember me Sign in "
    + "Forgot your password? Create an account",
  fields: [field(1, "Email address", "email")],
};

// ---- POSITIVE: a login modal thrown up mid-errand. page_map scopes the map
// to the open dialog, so these few controls ARE what a person sees.
const LOGIN_MODAL = {
  url: "https://shop-example.com/cart",
  title: "Your bag | Shop Example",
  overlay: true,
  elements: map(() => [
    el("button", "Close"),
    el("textbox", "Email"),
    el("textbox", "Password", ` ${SENSITIVE}`),
    el("button", "Log in"),
    el("link", "Continue as guest"),
  ].join("\n")),
  text: "Log in to check out Email Password Log in Continue as guest",
  fields: [field(1, "Email", "email")],
};

// ---- POSITIVE: provider buttons and nothing to type ----------------------
const SSO_PAGE = {
  url: "https://app.tradesled-example.com/",
  title: "Sign in to TradesLed",
  overlay: false,
  elements: map(() => [
    el("button", "Continue with Google"),
    el("button", "Continue with Apple"),
    el("button", "Continue with email"),
    el("link", "Terms", " [href=/terms]"),
  ].join("\n")),
  text: "Welcome back Continue with Google Continue with Apple Continue with email "
    + "By continuing you agree to our Terms.",
  fields: [],
};

// ---- POSITIVE: money, not identity --------------------------------------
const PAYWALL = {
  url: "https://news-example.com/2026/08/water-rates-ruling",
  title: "Water rates ruling — Example Post",
  overlay: false,
  elements: map(() => [
    el("link", "Home", " [href=/]"),
    el("button", "Subscribe"),
    el("link", "See plans", " [href=/subscribe]"),
    el("link", "Log in", " [href=/login]"),
  ].join("\n")),
  text: "Water rates ruling. The regulator ordered a review of standing charges. "
    + "You've reached your monthly limit of free articles. Subscribe for $4 a week "
    + "to continue reading. Already a subscriber? Log in.",
  fields: [],
};

// ---- POSITIVE: a challenge, which belongs to agent_loop.js ---------------
const CHALLENGE_PAGE = {
  url: "https://portal-example.gov/login",
  title: "Just a moment…",
  overlay: false,
  elements: map(() => [el("checkbox", "I'm not a robot", " [unchecked]")].join("\n")),
  text: "Checking your browser before you continue. Verify you are human.",
  fields: [],
};

// ---- NEGATIVE: every shop on earth has this link in its header -----------
const SHOP_WITH_SIGNIN_LINK = {
  url: "https://shop-example.com/collections/boots",
  title: "Boots | Shop Example",
  overlay: false,
  elements: map(() => [
    el("textbox", "Search products"),
    el("link", "Sign in", " [href=/account/login]"),
    el("link", "Bag (2)", " [href=/cart]"),
    el("link", "Waxed Trail Boot", " [href=/products/waxed-trail-boot]"),
    el("button", "Add to bag"),
    el("link", "Harbour Chelsea Boot", " [href=/products/harbour-chelsea]"),
    el("button", "Add to bag"),
    el("link", "Size guide", " [href=/pages/sizing]"),
  ].join("\n")),
  text: "Boots. 24 products. Waxed Trail Boot $189. Harbour Chelsea Boot $210. "
    + "Free shipping over $75. Returns within 30 days. Sign in for faster checkout.",
  fields: [field(0, "Search products", "search", { required: false })],
};

// ---- NEGATIVE: the optional account beside the real errand ---------------
const BOOKING_WITH_OPTIONAL_PASSWORD = {
  url: "https://tables-example.com/reserve/step2",
  title: "Reserve a table — Harbour Grill",
  overlay: false,
  elements: map(() => [
    el("textbox", "First name"),
    el("textbox", "Last name"),
    el("textbox", "Email"),
    el("textbox", "Phone"),
    el("combobox", "Party size", ' (use select action; options: "2"*, "3", "4")'),
    el("textbox", "Date",
      ' (date field — use select action with option in the exact format YYYY-MM-DD; currently "2026-08-22")'),
    el("textbox", "Time", ' (time field — use select action with option in the exact format HH:MM)'),
    el("textbox", "Create a password (optional)", ` ${SENSITIVE}`),
    el("checkbox", "Save my details for next time", " [unchecked]"),
    el("button", "Complete reservation"),
  ].join("\n")),
  text: "Reserve a table at Harbour Grill. Who's coming? Party size 2. "
    + "Create an account to save your details (optional). Complete reservation.",
  fields: [
    field(0, "First name", "text"), field(1, "Last name", "text"),
    field(2, "Email", "email"), field(3, "Phone", "tel"),
    field(4, "Party size", "select-one", { value: "2" }),
    field(5, "Date", "date", { value: "2026-08-22" }),
    field(6, "Time", "time"),
  ],
};

// ---- NEGATIVE: signed in, on a page made of password controls ------------
const SIGNED_IN_SECURITY_PAGE = {
  url: "https://portal-example.ca/account/security",
  title: "Security — Example Portal",
  overlay: false,
  elements: map(() => [
    el("link", "Sign out", " [href=/logout]"),
    el("textbox", "Current password", ` ${SENSITIVE}`),
    el("textbox", "New password", ` ${SENSITIVE}`),
    el("textbox", "Confirm new password", ` ${SENSITIVE}`),
    el("button", "Update password"),
  ].join("\n")),
  text: "Security Current password New password Confirm new password Update password",
  fields: [],
};

// ---- NEGATIVE: a provider button on a page that is selling, not gating ---
const MARKETING_LANDING = {
  url: "https://tradesled-example.com/",
  title: "TradesLed — invoicing for trades",
  overlay: false,
  elements: map(() => [
    el("link", "Features", " [href=/features]"),
    el("link", "Pricing", " [href=/pricing]"),
    el("button", "Sign up with Google"),
    el("button", "Book a demo"),
    el("textbox", "Work email"),
    el("link", "Read the docs", " [href=/docs]"),
  ].join("\n")),
  text: "Invoicing that closes the job. Quote on site, invoice before you leave, "
    + "chase nothing. Trusted by 4,000 trades. Quotes, invoices, reminders and "
    + "payments in one place. No card needed to start.",
  fields: [field(4, "Work email", "email", { required: false })],
};

// ---- NEGATIVE: the badge that once cost a live booking -------------------
// A login modal on a page carrying only the legally-required reCAPTCHA
// disclosure. The badge is not the wall: on 2026-08-16 matching the bare word
// parked a real reservation and texted about a CAPTCHA that did not exist.
const LOGIN_MODAL_WITH_RECAPTCHA_BADGE = {
  url: "https://tables-example.com/reserve",
  title: "Reserve a table — Harbour Grill",
  overlay: true,
  elements: map(() => [
    el("textbox", "Email"),
    el("textbox", "Password", ` ${SENSITIVE}`),
    el("button", "Sign in"),
    el("link", "Forgot password?", " [href=/reset]"),
  ].join("\n")),
  text: "Sign in to hold this table Email Password Sign in Forgot password? "
    + "This site is protected by reCAPTCHA and the Google Privacy Policy and "
    + "Terms of Service apply.",
  fields: [field(0, "Email", "email")],
};

// ==========================================================================
// 1. the positives
// ==========================================================================
{
  const a = detectsLoginWall(LOGIN_PAGE);
  check("a dedicated sign-in page is a password wall", a && a.kind === "password",
    JSON.stringify(a));
  check("it names the site, not the url", a && a.site === "portal.hydro-example.ca", a && a.site);
  check("and says it without hedging", a && a.sure === true, a && `score ${a.score}`);

  const b = detectsLoginWall(LOGIN_MODAL);
  check("a login modal mid-errand is a password wall", b && b.kind === "password",
    JSON.stringify(b));
  check("the modal wall names the site it is covering", b && b.site === "shop-example.com");

  const c = detectsLoginWall(SSO_PAGE);
  check("provider buttons and nothing to type is an sso wall", c && c.kind === "sso",
    JSON.stringify(c));
  check("the provider is read off the button's own words", c && c.provider === "Google",
    c && c.provider);
  check("every provider offered is reported", c
    && JSON.stringify(c.providers) === JSON.stringify(["Google", "Apple"]),
    c && JSON.stringify(c.providers));
  check('"Continue with email" is not a provider — it is the password path',
    c && !c.providers.some((p) => /mail/i.test(p)));

  const d = detectsLoginWall(PAYWALL);
  check("a metered wall is a paywall, not a login", d && d.kind === "paywall",
    JSON.stringify(d));
  check("and it records that a subscriber login exists", d && d.hasSignIn === true);

  const e = detectsLoginWall(CHALLENGE_PAGE);
  check("a human check defers to the existing challenge path", e && e.kind === "captcha",
    JSON.stringify(e));

  // The caller may inject agent_loop's looksLikeCaptcha so the running system
  // has exactly one challenge judgement. When it says no, we carry on reading.
  const injected = detectsLoginWall({ ...CHALLENGE_PAGE, text: "Email Password Sign in",
    elements: map(() => [
      el("textbox", "Email"),
      el("textbox", "Password", ` ${SENSITIVE}`),
      el("button", "Sign in"),
    ].join("\n")), fields: [field(0, "Email", "email")] }, { isChallenge: () => false });
  check("an injected challenge predicate is what decides", injected && injected.kind === "password",
    JSON.stringify(injected));
}

// ==========================================================================
// 2. THE NEGATIVES. A false positive parks a run that was working.
// ==========================================================================
{
  const shop = detectsLoginWall(SHOP_WITH_SIGNIN_LINK);
  check("a header Sign in LINK is not a wall", shop === null, JSON.stringify(shop));

  const booking = detectsLoginWall(BOOKING_WITH_OPTIONAL_PASSWORD);
  check("an optional account on a booking form is not a wall", booking === null,
    JSON.stringify(booking));

  const account = detectsLoginWall(SIGNED_IN_SECURITY_PAGE);
  check("a signed-in page full of password fields is not a wall", account === null,
    JSON.stringify(account));

  const landing = detectsLoginWall(MARKETING_LANDING);
  check("a provider button on a marketing page is not a wall", landing === null,
    JSON.stringify(landing));

  const badge = detectsLoginWall(LOGIN_MODAL_WITH_RECAPTCHA_BADGE);
  check("the reCAPTCHA badge is not a challenge", !looksLikeChallenge(LOGIN_MODAL_WITH_RECAPTCHA_BADGE));
  check("so the badge page is read as the password wall it is",
    badge && badge.kind === "password", JSON.stringify(badge));

  check("an empty state is not a wall", detectsLoginWall({}) === null);
  check("nothing is not a wall",
    detectsLoginWall(null) === null && detectsLoginWall(undefined) === null);

  // A one-time-code field is sensitive too, and side_trip.js owns that wall —
  // it can often clear it without the owner at all. Claiming it as a password
  // wall would replace a self-healing path with a text message.
  const otp = {
    url: "https://shop-example.com/verify",
    title: "Enter your code",
    overlay: false,
    elements: map(() => [
      el("textbox", "Verification code", ` ${SENSITIVE}`),
      el("button", "Continue"),
    ].join("\n")),
    text: "We sent a one-time code to your email. Enter your code Continue",
    fields: [],
  };
  check("a one-time-code wall is not a password wall", detectsLoginWall(otp) === null,
    JSON.stringify(detectsLoginWall(otp)));

  // A card form is redacted with the same marker. Telling him to "sign in"
  // while the page wants a card would be the wrong instruction entirely.
  const card = {
    url: "https://shop-example.com/checkout/payment",
    title: "Payment — Shop Example",
    overlay: false,
    elements: map(() => [
      el("textbox", "Card number", ` ${SENSITIVE}`),
      el("textbox", "Expiry", ` ${SENSITIVE}`),
      el("textbox", "Security code", ` ${SENSITIVE}`),
      el("textbox", "Name on card"),
      el("button", "Pay now"),
    ].join("\n")),
    text: "Payment Card number Expiry Security code Name on card Pay now",
    fields: [field(3, "Name on card", "text")],
  };
  check("a payment form is not a login wall", detectsLoginWall(card) === null,
    JSON.stringify(detectsLoginWall(card)));

  // A news site that mentions subscriptions in its footer is not a paywall.
  // Only a page WITHHOLDING its content is.
  const freeArticle = {
    url: "https://news-example.com/2026/08/free-story",
    title: "Council approves the bridge — Example Post",
    overlay: false,
    elements: map(() => [
      el("link", "Subscribe", " [href=/subscribe]"),
      el("link", "Log in", " [href=/login]"),
      el("link", "More local news", " [href=/local]"),
    ].join("\n")),
    text: "Council approves the bridge. The vote was 7-2 after a two-hour hearing. "
      + "Residents raised concerns about traffic on the approach road, which the "
      + "city says will be resolved by a new signal. Subscribe from $4 a week.",
    fields: [],
  };
  check("a readable article that sells subscriptions is not a paywall",
    detectsLoginWall(freeArticle) === null, JSON.stringify(detectsLoginWall(freeArticle)));
}

// ==========================================================================
// 2b. THE NEGATIVES ARE NEGATIVE FOR A REASON, not by accident.
//
// A test that passes because the fixture was never parsed protects nothing, so
// each negative is mutated by exactly the one property that makes it safe: put
// that property back and the wall must appear.
// ==========================================================================
{
  // Remove the Sign out control and the very same account page is a wall. That
  // is the site's own word on the session doing the work — nothing incidental.
  const noProof = {
    ...SIGNED_IN_SECURITY_PAGE,
    elements: SIGNED_IN_SECURITY_PAGE.elements.split("\n")
      .filter((l) => !/Sign out/.test(l)).join("\n"),
  };
  const flipped = detectsLoginWall(noProof);
  check("take away the Sign out control and it IS a wall",
    flipped && flipped.kind === "password", JSON.stringify(flipped));

  // Strip the errand off the booking page — its own fields and its own commit
  // button — and the leftover credentials form is a wall.
  const justTheForm = {
    url: "https://tables-example.com/account/login",
    title: "Sign in — Harbour Grill",
    overlay: false,
    elements: map(() => [
      el("textbox", "Email"),
      el("textbox", "Password", ` ${SENSITIVE}`),
      el("button", "Sign in"),
    ].join("\n")),
    text: "Sign in Email Password Sign in",
    fields: [field(0, "Email", "email")],
  };
  const bare = detectsLoginWall(justTheForm);
  check("the same form with the errand stripped off IS a wall",
    bare && bare.kind === "password" && bare.sure === true, JSON.stringify(bare));

  // And the shop: turn the header LINK into the page's own form and it flips.
  const shopWall = {
    ...SHOP_WITH_SIGNIN_LINK,
    url: "https://shop-example.com/account/login",
    title: "Sign in | Shop Example",
    elements: map(() => [
      el("textbox", "Email"),
      el("textbox", "Password", ` ${SENSITIVE}`),
      el("button", "Sign in"),
    ].join("\n")),
    text: "Sign in Email Password Sign in Create an account",
    fields: [field(0, "Email", "email")],
  };
  const shopFlipped = detectsLoginWall(shopWall);
  check("a link becomes a form and the shop IS a wall",
    shopFlipped && shopFlipped.kind === "password", JSON.stringify(shopFlipped));
  check('"Create an account" on a real sign-in page does not soften it',
    shopFlipped && shopFlipped.sure === true, shopFlipped && shopFlipped.why);

  // Give the marketing page the gating shape and its provider button flips too.
  const gatedApp = {
    ...MARKETING_LANDING,
    url: "https://tradesled-example.com/login",
    elements: map(() => [el("button", "Sign up with Google")].join("\n")),
    text: "Sign up with Google",
    fields: [],
  };
  const gatedFlipped = detectsLoginWall(gatedApp);
  check("the same provider button on a gated page IS an sso wall",
    gatedFlipped && gatedFlipped.kind === "sso", JSON.stringify(gatedFlipped));
}

// ==========================================================================
// 2c. the provider comes out of the button, whatever the button says
// ==========================================================================
{
  const gatedWith = (label) => detectsLoginWall({
    url: "https://app-example.com/login",
    title: "Sign in",
    overlay: false,
    elements: map(() => [el("button", label)].join("\n")),
    text: label,
    fields: [],
  });
  const cases = [
    ["Continue with Google", "Google"],
    ["continue with google", "Google"],
    ["Sign in with Apple", "Apple"],
    ["Log in with your Microsoft account", "Microsoft"],
    ["Continue with GitHub", "GitHub"],
    ["Continue with SSO", "SSO"],
    ["Sign in with your work or school account", "single sign-on"],
    ["Single sign-on", "single sign-on"],
  ];
  for (const [label, provider] of cases) {
    const got = gatedWith(label);
    check(`"${label}" -> ${provider}`, got && got.provider === provider,
      got ? got.provider : "no wall");
  }
  // Paths that are NOT a provider: naming one would send him hunting for a
  // button that does not exist.
  for (const label of ["Continue with email", "Continue with a magic link",
                       "Sign in with your phone number", "Continue with password"]) {
    check(`"${label}" is not a provider`, gatedWith(label) === null,
      JSON.stringify(gatedWith(label)));
  }

  // An account CHOOSER is not a wall: there is nothing only the owner can do,
  // and the agent can click a tile itself. Handing this back would ask him to
  // do the agent's job.
  const chooser = {
    url: "https://accounts-example.com/signin/chooser",
    title: "Choose an account",
    overlay: false,
    elements: map(() => [
      el("button", "Jose Cruz jose@example.com"),
      el("button", "Use another account"),
    ].join("\n")),
    text: "Choose an account to continue to TradesLed",
    fields: [],
  };
  check("an account chooser is not handed back", detectsLoginWall(chooser) === null,
    JSON.stringify(detectsLoginWall(chooser)));
}

// ==========================================================================
// 2d. shapes the page map really produces, and who wins when two walls stack
// ==========================================================================
{
  // A bare <input type=password> with no placeholder, no aria-label and no
  // <label for>: page_map redacts it and has NOTHING to call it, so the mapped
  // line carries only the marker. The word a person reads is still in the
  // page's own text, which is where the fallback looks.
  const unlabelled = {
    url: "https://portal-example.org/signin",
    title: "Portal",
    overlay: false,
    elements: map(() => [
      el("textbox", "Email"),
      el("textbox", "", ` ${SENSITIVE}`),
      el("button", "Sign in"),
    ].join("\n")),
    text: "Sign in Email Password Sign in",
    fields: [field(0, "Email", "email")],
  };
  const un = detectsLoginWall(unlabelled);
  check("a password field with no label of its own is still found",
    un && un.kind === "password", JSON.stringify(un));

  // An identifier the page already holds is worth one clause in the text: it
  // tells him how little is left to do.
  const prefilled = {
    ...unlabelled,
    fields: [field(0, "Email", "email", { value: "jose@example.com" })],
  };
  const pre = detectsLoginWall(prefilled);
  check("a filled identifier is reported", pre && pre.identifierFilled === true);
  check("and the sentence says so",
    /email already filled in/.test(handBackSentence(pre, { first_name: "Jose" })));
  check("an empty one is not claimed", un && un.identifierFilled === false);

  // A form only the AGENT needs to fill is not a wall. Surname plus booking
  // reference is exactly the long-tail errand this product exists for, and
  // handing it back would ask him to do the work he delegated.
  const checkIn = {
    url: "https://air-example.com/check-in",
    title: "Check in — Air Example",
    overlay: false,
    elements: map(() => [
      el("textbox", "Last name"),
      el("textbox", "Booking reference"),
      el("button", "Continue"),
      el("link", "Sign in to My Account", " [href=/account/login]"),
    ].join("\n")),
    text: "Check in for your flight. Last name Booking reference Continue. "
      + "Sign in to My Account.",
    fields: [field(0, "Last name", "text"), field(1, "Booking reference", "text")],
  };
  check("a reference-and-surname form is not a wall", detectsLoginWall(checkIn) === null,
    JSON.stringify(detectsLoginWall(checkIn)));

  // BOTH WALLS AT ONCE. A metered article puts up a modal offering a
  // subscriber login next to a Subscribe button. Money outranks the form: "just
  // sign in" is the one instruction that wastes his time if he has no
  // subscription, and the sentence still offers the login it saw.
  const stacked = {
    url: "https://news-example.com/2026/08/story",
    title: "Story — Example Post",
    overlay: true,
    elements: map(() => [
      el("textbox", "Email"),
      el("textbox", "Password", ` ${SENSITIVE}`),
      el("button", "Log in"),
      el("button", "Subscribe from $4 a week"),
    ].join("\n")),
    text: "You've reached your article limit. Subscribers only. Log in, or subscribe "
      + "from $4 a week to continue reading.",
    fields: [field(0, "Email", "email")],
  };
  const both = detectsLoginWall(stacked);
  check("money outranks the sign-in form when both are on screen",
    both && both.kind === "paywall", JSON.stringify(both));
  check("and the login it saw is still offered", both && both.hasSignIn === true);

  // A challenge in front of a login form is the challenge, not the login: he
  // would tap sign in and hit the same check.
  const challengeOverLogin = {
    url: "https://portal-example.org/signin",
    title: "Sign in | Portal",
    overlay: false,
    elements: map(() => [
      el("textbox", "Email"),
      el("textbox", "Password", ` ${SENSITIVE}`),
      el("button", "Sign in"),
    ].join("\n")),
    text: "Verify you are human before signing in. Email Password Sign in",
    fields: [field(0, "Email", "email")],
  };
  const over = detectsLoginWall(challengeOverLogin);
  check("a challenge in front of a login form defers to the challenge path",
    over && over.kind === "captcha", JSON.stringify(over));
}

// ==========================================================================
// 3. the sentence he reads on his phone
// ==========================================================================
{
  const owner = { first_name: "Jose", email: "jose@example.com" };

  const pw = handBackSentence(detectsLoginWall(LOGIN_PAGE), owner);
  console.log(`  password -> ${pw}`);
  check("the password sentence names the site", pw.includes("portal.hydro-example.ca"));
  check("names the wall", /password/i.test(pw));
  check("names the one thing he can do", /sign in there and say go/i.test(pw));
  check("and promises nothing is lost", /pick up exactly where I stopped/i.test(pw));
  check("it never claims to type a password", /never do/.test(pw));

  const sso = handBackSentence(detectsLoginWall(SSO_PAGE), owner);
  console.log(`  sso      -> ${sso}`);
  check("the sso sentence names the provider", sso.includes("Continue with Google"));
  check("mentions the alternative provider", /or Apple/.test(sso));
  check("says it is one tap", /one tap/.test(sso));
  check("and says why: he is probably already signed in", /already signed in to Google/.test(sso));

  const pay = handBackSentence(detectsLoginWall(PAYWALL), owner);
  console.log(`  paywall  -> ${pay}`);
  check("the paywall sentence says it is money, not a login",
    /paid subscription/.test(pay) && /not a login/.test(pay));
  check("offers the subscriber sign-in it saw", /already subscribe, sign in/.test(pay));
  check("and is honest that it may be unfinishable",
    /can't be finished without buying one/.test(pay));

  const cap = handBackSentence(detectsLoginWall(CHALLENGE_PAGE), owner);
  console.log(`  captcha  -> ${cap}`);
  check("the challenge sentence matches the words agent_loop already uses",
    /prove you're human/.test(cap) && /clear the check/.test(cap));

  check("no wall, nothing to say", handBackSentence(null, owner) === ""
    && handBackSentence(undefined) === "");

  // Without a name on file the sentence still has to read as English.
  const anon = handBackSentence(detectsLoginWall(SSO_PAGE), null);
  check("no first name still reads properly", /one tap\. Tap it on the tab/.test(anon), anon);
  check("with a first name it addresses him", /one tap\. Jose, tap it/.test(sso), sso);

  // Thin evidence must not sound certain. A single provider button on a bare
  // page is a wall worth mentioning; it is not a wall worth swearing to.
  const thin = detectsLoginWall({
    url: "https://tool-example.com/app",
    title: "TradesLed",
    overlay: false,
    elements: map(() => [el("button", "Continue with Google")].join("\n")),
    text: "Continue with Google",
    fields: [],
  });
  check("thin evidence is still reported", thin && thin.kind === "sso", JSON.stringify(thin));
  check("but not as a certainty", thin && thin.sure === false, thin && `score ${thin.score}`);
  check("and the sentence hedges", /looks like it only offers/
    .test(handBackSentence(thin, owner)), handBackSentence(thin, owner));

  // The sentence goes out by text message. It has to fit on a phone.
  for (const [kind, sentence] of [["password", pw], ["sso", sso], ["paywall", pay], ["captcha", cap]]) {
    check(`the ${kind} sentence is short enough to text (${sentence.length} chars)`,
      sentence.length > 60 && sentence.length < 420);
    check(`the ${kind} sentence leaks no url or query string`, !/https?:\/\//.test(sentence));
  }
}

// ==========================================================================
// 4. did his thumb actually work
// ==========================================================================
{
  const SIGNED_IN_DASHBOARD = {
    url: "https://portal.hydro-example.ca/account/overview",
    title: "Overview — Hydro Example",
    overlay: false,
    elements: map(() => [
      el("link", "Sign out", " [href=/logout]"),
      el("link", "View your bill", " [href=/account/bills]"),
      el("button", "Report an outage"),
    ].join("\n")),
    text: "Overview Account 4471 Balance $82.14 due 2026-09-02 View your bill",
    fields: [],
  };
  check("he signed in and the wall is gone -> carry on",
    canContinueAfterOwner(LOGIN_PAGE, SIGNED_IN_DASHBOARD) === true);

  const WRONG_PASSWORD = {
    ...LOGIN_PAGE,
    text: "Sign in to My Account That password was not recognised. Email address "
      + "Password Remember me Sign in Forgot your password?",
  };
  check("the same wall with an error is NOT cleared",
    canContinueAfterOwner(LOGIN_PAGE, WRONG_PASSWORD) === false);

  check("nothing was blocking, so nothing to clear",
    canContinueAfterOwner(SHOP_WITH_SIGNIN_LINK, SHOP_WITH_SIGNIN_LINK) === true);

  // Fails closed: an unreadable page after is not permission to resume, or the
  // run burns its budget walking back into the same wall and texts twice.
  check("an unreadable page after is not a clearance",
    canContinueAfterOwner(LOGIN_PAGE, null) === false
    && canContinueAfterOwner(LOGIN_PAGE, {}) === false);

  // He closed the modal and carried on shopping, signed in.
  const SHOP_SIGNED_IN = {
    url: "https://shop-example.com/cart",
    title: "Your bag | Shop Example",
    overlay: false,
    elements: map(() => [
      el("link", "Sign out", " [href=/account/logout]"),
      el("link", "Waxed Trail Boot", " [href=/products/waxed-trail-boot]"),
      el("button", "Checkout"),
    ].join("\n")),
    text: "Your bag Waxed Trail Boot $189 Subtotal $189 Checkout",
    fields: [],
  };
  check("the modal is gone and he is signed in -> carry on",
    canContinueAfterOwner(LOGIN_MODAL, SHOP_SIGNED_IN) === true);

  // He tapped the provider button and it bounced him back to the same screen.
  check("an sso wall that is still standing is not cleared",
    canContinueAfterOwner(SSO_PAGE, SSO_PAGE) === false);

  // He signed in but the site kept the modal up (some do, while it settles).
  // The site's own Sign out control is the last word on whether it took.
  const MODAL_OVER_SIGNED_IN = {
    ...LOGIN_MODAL,
    elements: map(() => [
      el("link", "Sign out", " [href=/account/logout]"),
      el("textbox", "Email"),
      el("textbox", "Password", ` ${SENSITIVE}`),
      el("button", "Log in"),
    ].join("\n")),
  };
  check("a sign-out control on the page is the site saying the session took",
    canContinueAfterOwner(LOGIN_MODAL, MODAL_OVER_SIGNED_IN) === true);

  // The password wall gave way to a code field: that is progress, and
  // side_trip.js owns what comes next.
  const OTP_AFTER_LOGIN = {
    url: "https://portal.hydro-example.ca/account/verify",
    title: "Enter your code",
    overlay: false,
    elements: map(() => [
      el("textbox", "Verification code", ` ${SENSITIVE}`),
      el("button", "Continue"),
    ].join("\n")),
    text: "We texted you a one-time code. Enter your code Continue",
    fields: [],
  };
  check("a password wall that became a code prompt has been cleared",
    canContinueAfterOwner(LOGIN_PAGE, OTP_AFTER_LOGIN) === true);

  // A paywall he did not pay for is still a paywall.
  check("an unpaid paywall is not cleared", canContinueAfterOwner(PAYWALL, PAYWALL) === false);
}

// ==========================================================================
// 5. no site lists, no domain recipes — the guarantee, enforced here too
// ==========================================================================
{
  const src = await import("node:fs").then((fs) =>
    fs.readFileSync(new URL("../login_wall.js", import.meta.url), "utf8"));
  const code = src.split("\n").filter((l) => !/^\s*(\/\/|\*|\/\*)/.test(l)).join("\n");
  // A provider NAMED IN CODE would be a lookup table by another name: the
  // provider must always come out of the button the site drew.
  for (const brand of ["google", "apple", "microsoft", "facebook", "okta", "auth0", "github"]) {
    check(`no code line names ${brand}`, !new RegExp(brand, "i").test(code));
  }
  check("no hostname literal anywhere in code",
    !/["'][a-z0-9-]+\.(?:com|ca|org|net|io|co\.uk)["']/i.test(code));
  check("nothing switches on a hostname", !/hostname\s*===/.test(code));
}

if (failures) {
  console.error(`test_login_wall: ${failures} check(s) failed`);
  process.exit(1);
}
console.log("test_login_wall: all passed");
