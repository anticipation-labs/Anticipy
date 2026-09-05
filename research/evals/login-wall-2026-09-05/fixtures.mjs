// THE GOLDEN SET for the wall question (Audit #70).
//
// Every page map that extension/tests/test_login_wall.mjs used to pin against
// sixteen vocabulary regexes, carried over with the token the model is expected
// to answer — so the judgement that left the regexes is measured where it now
// lives: in a model, against the live transport (overnight/login_wall_gate.py).
// The offline suite (extension/tests/test_wall_is_not_a_word_match.mjs) uses
// the same fixtures for what it CAN pin: the trigger, the cache key, the shape
// of what is sent, and the four-state read of each expected token.
//
// Fixtures are in the EXACT shape page_map.js produces:
//   [idx] <role> label [state] (extra) @(x,y)
// with sensitive inputs redacted, marked, and absent from `fields`.
//
// Three of the old fixtures are NOT here, on purpose, because their old
// verdict came from the vocabulary rather than from anything a person would
// call the truth: the signed-in security page with its "Sign out" removed (the
// regex called that a wall; a change-password page is not a credentials form),
// a /login page offering only "Continue with email" (the door is one click
// further on, and either token is defensible), and every CAPTCHA page —
// agent_loop's looksLikeCaptcha runs before this question and owns them.
// A golden set carries what is unambiguous, or it measures the labeller.

export const SENSITIVE = "(sensitive field — never fill)";
let seq = 0;
const el = (role, label, extra = "") =>
  `[${seq}] <${role}> ${label}${extra} @(600,${120 + 40 * seq++})`;
const map = (parts) => { seq = 0; return parts(); };
const field = (index, label, type, over = {}) =>
  ({ index, name: label.toLowerCase().replace(/\s+/g, "_"), label, type,
     required: true, readOnly: false, value: "", ...over });

export const FIXTURES = [
  // ---- POSITIVE: a dedicated sign-in page (a utility portal, the long tail)
  {
    name: "login_page", expect: "PASSWORD",
    goal: "download my latest bill from the hydro portal",
    state: {
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
    },
  },
  // ---- POSITIVE: a login modal thrown up mid-errand. page_map scopes the map
  // to the open dialog, so these few controls ARE what a person sees.
  //
  // The old fixture also offered "Continue as guest" — and the regexes still
  // called it a wall. Measured live on 2026-09-05 the model answered NONE
  // three times out of three, which is the right answer: a guest checkout is
  // a way through that needs nobody's thumb. The guest link is gone from this
  // fixture so it asks the question it means to; the finding is recorded in
  // FINDINGS.md.
  {
    name: "login_modal", expect: "PASSWORD",
    goal: "order the waxed trail boots that are in my bag",
    state: {
      url: "https://shop-example.com/cart",
      title: "Your bag | Shop Example",
      overlay: true,
      elements: map(() => [
        el("button", "Close"),
        el("textbox", "Email"),
        el("textbox", "Password", ` ${SENSITIVE}`),
        el("button", "Log in"),
        el("link", "Forgot password?", " [href=/account/reset]"),
      ].join("\n")),
      text: "Log in to check out Email Password Log in Forgot password?",
      fields: [field(1, "Email", "email")],
    },
  },
  // ---- POSITIVE: provider buttons and nothing to type
  {
    name: "sso_page", expect: "SSO Google",
    goal: "open my TradesLed invoices and find the one for the Harbour job",
    state: {
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
    },
  },
  // ---- POSITIVE: money, not identity
  {
    name: "paywall", expect: "PAYWALL",
    goal: "read the water rates ruling article and tell me what changed",
    state: {
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
    },
  },
  // ---- NEGATIVE: every shop on earth has this link in its header
  {
    name: "shop_with_signin_link", expect: "NONE",
    goal: "find the price of the waxed trail boot",
    state: {
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
    },
  },
  // ---- NEGATIVE: the optional account beside the real errand
  {
    name: "booking_with_optional_password", expect: "NONE",
    goal: "reserve a table for two at Harbour Grill on the 22nd at 7pm",
    state: {
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
    },
  },
  // ---- NEGATIVE: signed in, on a page made of password controls
  {
    name: "signed_in_security_page", expect: "NONE",
    goal: "check whether two-factor sign-in is turned on for my portal account",
    state: {
      url: "https://portal-example.ca/account/security",
      title: "Security — Example Portal",
      overlay: false,
      elements: map(() => [
        el("link", "Sign out", " [href=/logout]"),
        el("textbox", "Current password", ` ${SENSITIVE}`),
        el("textbox", "New password", ` ${SENSITIVE}`),
        el("textbox", "Confirm new password", ` ${SENSITIVE}`),
        el("button", "Update password"),
        el("link", "Two-factor authentication", " [href=/account/security/2fa]"),
      ].join("\n")),
      text: "Security Current password New password Confirm new password Update password "
        + "Two-factor authentication: off",
      fields: [],
    },
  },
  // ---- NEGATIVE: a provider button on a page that is selling, not gating
  {
    name: "marketing_landing", expect: "NONE",
    goal: "find out what TradesLed charges per month",
    state: {
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
    },
  },
  // ---- POSITIVE: the badge that once cost a live booking. A login modal on a
  // page carrying only the legally-required reCAPTCHA disclosure: the badge is
  // not a challenge, and the modal IS the wall.
  {
    name: "login_modal_with_recaptcha_badge", expect: "PASSWORD",
    goal: "hold a table for two at Harbour Grill tonight",
    state: {
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
    },
  },
  // ---- NEGATIVE: a one-time code is sensitive too, and side_trip.js owns it
  {
    name: "one_time_code", expect: "NONE",
    goal: "finish checking out the order in my bag",
    state: {
      url: "https://shop-example.com/verify",
      title: "Enter your code",
      overlay: false,
      elements: map(() => [
        el("textbox", "Verification code", ` ${SENSITIVE}`),
        el("button", "Continue"),
      ].join("\n")),
      text: "We sent a one-time code to your email. Enter your code Continue",
      fields: [],
    },
  },
  // ---- NEGATIVE: a card form wears the same mark
  {
    name: "payment_form", expect: "NONE",
    goal: "pay for the order in my bag",
    state: {
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
    },
  },
  // ---- NEGATIVE: a readable article that sells subscriptions in its footer
  {
    name: "free_article", expect: "NONE",
    goal: "tell me how the council voted on the bridge",
    state: {
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
    },
  },
  // ---- POSITIVE: the booking form with the errand stripped off it
  {
    name: "just_the_form", expect: "PASSWORD",
    goal: "reserve a table for two at Harbour Grill on the 22nd at 7pm",
    state: {
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
    },
  },
  // ---- POSITIVE: the shop's header link turned into the page's own form
  {
    name: "shop_wall", expect: "PASSWORD",
    goal: "find the price of the waxed trail boot",
    state: {
      url: "https://shop-example.com/account/login",
      title: "Sign in | Shop Example",
      overlay: false,
      elements: map(() => [
        el("textbox", "Email"),
        el("textbox", "Password", ` ${SENSITIVE}`),
        el("button", "Sign in"),
      ].join("\n")),
      text: "Sign in Email Password Sign in Create an account",
      fields: [field(0, "Email", "email")],
    },
  },
  // ---- POSITIVE: the marketing page's provider button on a gated page
  {
    name: "gated_app", expect: "SSO Google",
    goal: "find out what TradesLed charges per month",
    state: {
      url: "https://tradesled-example.com/login",
      title: "TradesLed — invoicing for trades",
      overlay: false,
      elements: map(() => [el("button", "Sign up with Google")].join("\n")),
      text: "Sign up with Google",
      fields: [],
    },
  },
  // ---- POSITIVE: the organisation IS the provider
  {
    name: "work_or_school", expect: "SSO ORGANISATION",
    goal: "open the shared drive and find the Q3 invoice list",
    state: {
      url: "https://app-example.com/login",
      title: "Sign in",
      overlay: false,
      elements: map(() => [el("button", "Sign in with your work or school account")].join("\n")),
      text: "Sign in with your work or school account",
      fields: [],
    },
  },
  // ---- NEGATIVE: an account chooser the agent can click itself
  {
    name: "account_chooser", expect: "NONE",
    goal: "open my TradesLed invoices and find the one for the Harbour job",
    state: {
      url: "https://accounts-example.com/signin/chooser",
      title: "Choose an account",
      overlay: false,
      elements: map(() => [
        el("button", "Jose Cruz jose@example.com"),
        el("button", "Use another account"),
      ].join("\n")),
      text: "Choose an account to continue to TradesLed",
      fields: [],
    },
  },
  // ---- POSITIVE: a bare <input type=password> with no label of its own
  {
    name: "unlabelled_password", expect: "PASSWORD",
    goal: "download my latest bill from the portal",
    state: {
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
    },
  },
  // ---- NEGATIVE: a form only the AGENT needs to fill
  {
    name: "check_in", expect: "NONE",
    goal: "check in for my flight tomorrow, booking reference K7Q2ZP, surname Cruz",
    state: {
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
    },
  },
  // ---- POSITIVE: both walls at once — money outranks the form
  {
    name: "stacked_paywall_over_login", expect: "PAYWALL",
    goal: "read the story and tell me what it says about the rates",
    state: {
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
    },
  },
  // ---- POSITIVE: thin evidence — one provider button on a bare app page
  {
    name: "thin_sso", expect: "SSO Google",
    goal: "open my TradesLed dashboard and read this week's totals",
    state: {
      url: "https://tool-example.com/app",
      title: "TradesLed",
      overlay: false,
      elements: map(() => [el("button", "Continue with Google")].join("\n")),
      text: "Continue with Google",
      fields: [],
    },
  },
  // ---- NEGATIVE: THE AUDIT'S OWN EXAMPLE. "Members only" plus "$45 per year"
  // in the sidebar of a permit form scored 3 + 1 = 4 = WALL under the regexes,
  // and the errand was abandoned as a paywall one step from done.
  {
    name: "permit_form_members_only_sidebar", expect: "NONE",
    goal: "apply for a residential parking permit for 18 Kestrel Row, plate ABC 123",
    state: {
      url: "https://city-example.ca/permits/parking/apply",
      title: "Apply for a parking permit — City Example",
      overlay: false,
      elements: map(() => [
        el("link", "Sign in", " [href=/account/login]"),
        el("textbox", "Street address"),
        el("textbox", "Licence plate"),
        el("combobox", "Zone", ' (use select action; options: "A", "B"*, "C")'),
        el("checkbox", "I confirm the details are accurate", " [unchecked]"),
        el("button", "Submit application"),
        el("link", "Members only parking permits", " [href=/permits/members]"),
      ].join("\n")),
      text: "Apply for a residential parking permit. Street address Licence plate Zone. "
        + "I confirm the details are accurate. Submit application. "
        + "Members only parking permits — $45 per year. Resident permits are free for "
        + "the first vehicle.",
      fields: [field(1, "Street address", "text"), field(2, "Licence plate", "text"),
               field(3, "Zone", "select-one", { value: "B" })],
    },
  },
];
