// THE WALL THAT KILLS ERRANDS.
//
// The agent runs inside the owner's own Chrome, with his own cookies, so most
// sites are already signed in and the whole problem is invisible — until it
// isn't. A utility portal, a warranty claim, a council form, a subscription
// cancellation: the long tail past "book a table" is full of sign-in pages,
// and the engine had no idea what one was. It saw an unfamiliar page, tried
// things, and eventually produced the generic stall:
//
//   "I spent 9 steps on <url> without getting anywhere, so I stopped instead
//    of flailing. The page is open for you."
//
// True, useless. He cannot tell from that sentence whether the site is broken,
// whether the agent is broken, or whether all it needed was his thumb. This
// file exists to turn that into ONE sentence he can act on in five seconds,
// and to distinguish the four walls that need four different answers:
//
//   password — a real credentials form. A password is the one thing this
//              product never types (agent_loop's protectedInput stops it
//              mechanically); recognising the wall and saying so IS the job.
//   sso      — "Continue with Google/Apple/Microsoft". Materially different:
//              he probably already has that session in this very browser, so
//              this is usually ONE TAP from resolved. Worth saying out loud
//              instead of burying it inside "it needs a login".
//   paywall  — money, not identity. Signing in cannot fix it. Saying "this
//              needs a paid subscription" is honest; looking broken is not.
//   captcha  — NOT OURS. agent_loop.js owns the challenge path end to end:
//              challengeFurniture (what the page renders) + challengeVerdict
//              (one model question, four states) + its hand-back. This file
//              has NO challenge judgement of its own; the caller injects the
//              verdict as deps.isChallenge so a challenge page can never be
//              mislabelled a login wall. See the record below the vocabulary.
//
// TWO RULES THIS FILE IS BUILT AROUND.
//
// 1. NO SITE LISTS. Not one hostname, not one "known login domain". Detection
//    reads the live page's own structure and words, exactly like
//    externalControlSemantics does for consequential buttons. A list of login
//    hosts is a treadmill that is wrong the week after it is written.
// 2. FALSE POSITIVES ARE EXPENSIVE, FALSE NEGATIVES ARE MERELY DULL. Almost
//    every page on the web has a "Sign in" link in its header; a booking page
//    routinely offers an optional "create a password"; an account page shows
//    password controls while perfectly signed in. Calling any of those a wall
//    would park a run that was working and text him about nothing. A wall is a
//    page whose PURPOSE is the wall — the content is gated. So the evidence is
//    weighed, the negatives carry real weight, and below threshold this
//    function says null rather than guessing.

// ---------------------------------------------------------------------------
// Vocabulary. Words the PAGE uses about itself — never a site, never a task.
// ---------------------------------------------------------------------------

// "Sign in", "Log in", "Sign on", "Login". Anchored: a button labelled
// "Sign in to see prices" is still an auth action, but "Design in progress"
// is not, and a bare /log ?in/ finds the second.
const AUTH_ACTION = /^\s*(?:(?:sign|log)\s*-?\s*(?:in|on)|log-?in|sign-?in|authenticate|continue\s+with\s+password|use\s+(?:my\s+)?password)\b/i;
const SIGN_OUT = /^\s*(?:(?:sign|log)\s*-?\s*out|logout|sign-?out|end\s+session)\b/i;
// Fields that identify a person. Read off the field's own label/name, which is
// where every site on earth already says this.
const IDENTIFIER = /\b(?:e-?mail|e-?mail\s*address|user\s*-?\s*name|username|user\s*id|login|account\s*(?:number|id|name)|member\s*(?:number|id)|customer\s*(?:number|id)|phone|mobile)\b/i;
const PASSWORD_WORD = /\b(?:password|passcode|pass\s*phrase|passphrase|pin)\b/i;
// A payment field is ALSO redacted by page_map as sensitive. Card details are
// not a login wall, and confusing the two would tell him to "sign in" while
// the page is asking for a card.
const CARD_WORD = /\b(?:card|cvv|cvc|ccv|expiry|expiration|security\s*code|name\s+on\s+card)\b/i;
// A one-time code is redacted as sensitive too, and it is somebody else's
// problem on purpose: side_trip.js owns the OTP wall and can often clear it
// without the owner at all. Claiming it as a password wall would replace a
// self-healing path with a text message.
const CODE_WORD = /\b(?:one[\s_-]?time|otp|verification\s*code|security\s*code|2fa|mfa|authenticat(?:or|ion)\s*code|code\s*(?:we\s*)?sent)\b/i;

// page_map redacts sensitive inputs and marks them with this exact phrase (and
// keeps them OUT of state.fields entirely), so this marker — not a `type` we
// never receive — is how a password field is visible to us at all.
const SENSITIVE_MARK = "(sensitive field — never fill)";

// "Continue with X" / "Sign in with X". The provider comes out of the button's
// OWN text; there is no table of providers anywhere in this file.
const SSO_PHRASE = /\b(?:continue|proceed|sign\s*-?\s*in|log\s*-?\s*in|sign\s*-?\s*up|register|authenticate)\s+(?:with|using|via)\s+(.{1,40}?)\s*$/i;
// "with email" / "with a password" is the ordinary credentials path wearing the
// same sentence shape. Naming it as a provider would tell him to tap a Google
// button that does not exist.
const NOT_A_PROVIDER = /^(?:an?\s+|your\s+|my\s+)?(?:e-?mail(?:\s*address)?|phone(?:\s*number)?|mobile|sms|text(?:\s*message)?|password|passcode|magic\s*link|link|code|otp|username|user\s*name)\b/i;
// SSO that names no provider because the organisation IS the provider.
const FEDERATED = /\b(?:single\s*sign[\s-]?on|\bsso\b|saml|openid|identity\s*provider|work\s*(?:or\s*school\s*)?account|organi[sz]ation(?:'s|al)?\s*account|company\s*account)\b/i;

// Money gating its own content. The gating phrase is REQUIRED for a paywall
// verdict: every news site mentions subscriptions somewhere, and only a gated
// one says the content is being withheld.
const MONEY_GATE = /\b(?:to\s+(?:continue|keep)\s+reading|to\s+read\s+(?:this|the\s+(?:full|rest))|reached\s+your\s+(?:\w+\s+){0,3}limit|(?:you(?:'ve| have)\s+read\s+(?:all|your))|subscribers?\s+only|members?\s+only|for\s+subscribers|subscribe\s+to\s+(?:read|continue|unlock|view|listen|watch)|unlock\s+(?:this|the\s+full|unlimited)|this\s+(?:article|story|content|video|episode)\s+is\s+(?:for|reserved|available\s+to)|out\s+of\s+free\s+(?:articles|stories)|free\s+article\s+limit)\b/i;
const SUBSCRIPTION_WORD = /\b(?:subscri(?:be|ption|ber)|free\s+trial|start\s+(?:your\s+)?trial|choose\s+(?:a\s+)?plan|see\s+plans|pricing|upgrade|premium|paywall|membership)\b/i;
const PRICE = /(?:[$€£¥]\s?\d|\b\d+(?:[.,]\d{2})?\s*(?:usd|eur|gbp|cad)\b)|\b(?:per|a|\/)\s*(?:month|week|year|mo|yr)\b/i;
const SUBSCRIBE_ACTION = /^\s*(?:subscribe|start\s+(?:your\s+)?(?:free\s+)?trial|see\s+(?:all\s+)?plans?|choose\s+(?:a\s+)?plan|view\s+plans?|upgrade|become\s+a\s+member|join\s+now|get\s+(?:unlimited|premium|full)\b)/i;

// An account being CREATED alongside the real errand. Booking and checkout
// forms offer this constantly, and the password field they add is optional
// furniture next to the actual task — never a wall.
const OPTIONAL_ACCOUNT = /\(\s*optional\s*\)|\boptional\b|\bif\s+you\s+(?:want|wish|like)\b|\bcreate\s+(?:an?\s+)?(?:account|password|login)\b|\bsave\s+(?:my|your)\s+details\b|\bfor\s+next\s+time\b|\bsign\s+up\s+for\s+(?:an?\s+)?account\b|\balso\s+create\b/i;

// URL and title shapes that say "this page IS the door". Path structure, not a
// host: /login, /sessions/new, /oauth/authorize, /u/login all mean the same
// thing on every stack that has ever shipped, and none of them names a site.
const AUTH_PATH = /(?:^|\/)(?:log-?in|sign-?in|sign-?on|signin|login|auth|authorize|authorization|oauth2?|openid|sso|saml|session|sessions\/new|account\/log-?in|u\/log-?in|users\/sign_in|identity|idp|adfs)(?:\/|$|[?#])/i;
const AUTH_TITLE = /^(?:\s*)(?:sign\s*-?\s*in|log\s*-?\s*in|login|sign\s*on|authentication|authenticate|welcome\s+back|account\s+log-?in)\b|\b(?:sign\s*-?\s*in|log\s*-?\s*in)\s*(?:[|\u2013\u2014-]|to\b)/i;

// WHAT WAS HERE UNTIL 2026-09-05 (audit #71), and why it is gone.
//
//     const CHALLENGE = /\bare\s+you\s+a\s+robot\b|\bi'?m\s+not\s+a\s+robot\b|
//                        verify\s+(?:that\s+)?you(?:'re|\s+are)\s+(?:a\s+)?human|
//                        verify\s+you\s+are\s+human|checking\s+your\s+browser|
//                        just\s+a\s+moment|unusual\s+traffic|
//                        (?:complete|solve|pass)\s+the\s+(?:captcha|security\s+check|challenge)|
//                        select\s+all\s+(?:images|squares)/i
//     function stripBadge(text)          -> text minus "protected by recaptcha…",
//                                           "recaptcha privacy/terms…", "privacy - terms"
//     export function looksLikeChallenge(state)
//       -> CHALLENGE over stripBadge(url + title + text[:2000]), or a
//          /captcha|/challenge|/sorry URL path
//
// This was the default `isChallenge` of detectsLoginWall: a second English
// phrase list deciding the same question agent_loop.js's looksLikeCaptcha
// decided, with a DIFFERENT membership ("pass the security check" was here
// and not there), and the loop called detectsLoginWall without injecting
// anything — so the running system held two keyword verdicts on one
// question, which the comment above this regex said must never exist. Law 1:
// whether a page is asking a person to prove they are human is what the page
// MEANS, and no list of phrases may decide it.
//
// Now there is exactly one judgement, and it is not in this file:
// agent_loop.js's challengeVerdict — asked only when the page RENDERS a
// challenge provider's frame or widget (challengeFurniture, a which-host
// check on iframe origin), answered by a model in four states, compared by
// the loop as a ceiling — is injected as deps.isChallenge. With nothing
// injected this file has no verdict and raises no captcha fence: it judges
// the page on its own structural evidence. stripBadge went with the regex —
// the disclosure it stripped ("protected by reCAPTCHA and the Google Privacy
// Policy and Terms of Service apply") matches none of the remaining money,
// price or optional-account expressions, so nothing below changes.

// ---------------------------------------------------------------------------
// Reading the page map. state = { url, title, elements, text, fields, overlay }
// where `elements` is newline-separated
//   [idx] <role> label [state] (extra) @(x,y)
// ---------------------------------------------------------------------------

function site(url) {
  try { return new URL(String(url)).hostname.replace(/^www\./, ""); }
  catch (_) { return "the site"; }
}

/// One mapped control, split far enough to reason about. The label may itself
/// contain brackets or parentheses, so this does not try to parse perfectly —
/// it keeps the label prefix for anchored matching and the whole remainder for
/// marker matching, which is all any rule below needs.
function controls(state) {
  return String(state?.elements || "").split("\n")
    .map((raw) => {
      const head = raw.match(/^\[(\d+)\]\s*<([^>]*)>\s*(.*)$/);
      if (!head) return null;
      const rest = head[3].replace(/\s*@\(-?\d+,-?\d+\)\s*$/, "");
      // Everything up to the first bracketed/parenthesised annotation is the
      // label page_map read off the element.
      const label = rest.split(/\s+[[(]/)[0].trim();
      return { index: Number(head[1]), role: head[2].trim().toLowerCase(), label, rest, raw };
    })
    .filter(Boolean);
}

function fieldsOf(state) {
  return Array.isArray(state?.fields) ? state.fields.filter(Boolean) : [];
}

function fieldText(field) {
  return `${field?.label || ""} ${field?.name || ""}`;
}

/// The password field, as it actually reaches us: redacted, absent from
/// state.fields, present only as a marked control. Card and one-time-code
/// fields wear the same mark, so they are subtracted by their own words.
function credentialField(state, cs) {
  const marked = cs.filter((c) => c.rest.includes(SENSITIVE_MARK));
  if (!marked.length) return null;
  const named = marked.find((c) => PASSWORD_WORD.test(c.label) && !CARD_WORD.test(c.label));
  if (named) return named;
  // No label at all (a bare <input type=password> with no placeholder and no
  // aria-label maps to an empty label). Fall back to the page's own visible
  // words: the <label> element a person reads is in state.text even when the
  // input carries no attributes. Only count it when nothing else claims the
  // marked field.
  const ambiguous = marked.filter((c) =>
    !CARD_WORD.test(c.label) && !CODE_WORD.test(c.label) && !PASSWORD_WORD.test(c.label));
  if (!ambiguous.length) return null;
  const words = String(state?.text || "");
  if (PASSWORD_WORD.test(words) && !CODE_WORD.test(words)) return ambiguous[0];
  return null;
}

function identifierField(state, cs) {
  const field = fieldsOf(state).find((f) =>
    IDENTIFIER.test(fieldText(f))
    && !CARD_WORD.test(fieldText(f))
    && !CODE_WORD.test(fieldText(f))
    && /^(?:email|text|tel|number|textbox|input)$/i.test(String(f.type || "text")));
  if (field) return field;
  // Some sites label the box only in the DOM around it; the mapped control
  // still carries the label page_map resolved.
  return cs.find((c) => /^(?:textbox|combobox)$/.test(c.role)
    && IDENTIFIER.test(c.label) && !CARD_WORD.test(c.label) && !CODE_WORD.test(c.label)) || null;
}

/// A BUTTON, not a link. This distinction is the whole defence against the
/// header "Sign in" link that sits on almost every page on the web: a link
/// navigates somewhere else, a button submits the form in front of you.
function authSubmit(cs) {
  return cs.find((c) => /^(?:button|submit)$/.test(c.role) && AUTH_ACTION.test(c.label)) || null;
}

function signedInProof(cs) {
  return cs.find((c) => SIGN_OUT.test(c.label)) || null;
}

/// Providers, read out of the buttons' own words. "Continue with Google" ->
/// "Google". Never a lookup table.
function providerName(label) {
  const text = String(label || "").replace(/\s+/g, " ").trim();
  const withPhrase = text.match(SSO_PHRASE);
  if (withPhrase) {
    let tail = withPhrase[1].replace(/["'\u201c\u201d]/g, "").trim();
    if (NOT_A_PROVIDER.test(tail)) return null;
    tail = tail.replace(/^(?:an?|your|my)\s+/i, "")
      .replace(/\s+(?:account|id|login|instead|business|work)\b.*$/i, "")
      .trim();
    if (!tail || tail.length > 24) return null;
    // Federated wording can survive the tail cleanup only partially ("your
    // work or school account" -> "work or school"), so the whole label is
    // consulted: an organisation sign-in has no brand to name, and calling it
    // "Work Or School" would read like a product nobody has heard of.
    if (FEDERATED.test(`${tail} ${text}`)) {
      return tail.toUpperCase() === tail && /^[A-Z]{2,}$/.test(tail) ? tail : "single sign-on";
    }
    // Title-case a lowercase brand ("google" -> "Google"); leave "GitHub" and
    // "SSO" exactly as the site wrote them.
    return /[A-Z]/.test(tail) ? tail : tail.replace(/\b[a-z]/g, (c) => c.toUpperCase());
  }
  if (FEDERATED.test(text) && !PASSWORD_WORD.test(text)) return "single sign-on";
  return null;
}

function ssoOptions(cs) {
  const seen = new Set();
  const out = [];
  for (const c of cs) {
    if (!/^(?:button|submit|link|menuitem|tab)$/.test(c.role)) continue;
    const provider = providerName(c.label);
    if (!provider) continue;
    const key = provider.toLowerCase();
    if (seen.has(key)) continue;
    seen.add(key);
    out.push({ provider, control: c });
  }
  return out;
}

/// Is this page ABOUT the wall, or does it merely have a door in the corner?
///
/// Three independent readings, because any one of them alone is wrong
/// somewhere: the address (a /login path or a "Sign in" title is the site
/// telling us plainly), the overlay (page_map scopes the map to an open modal,
/// so an overlay full of auth controls IS what the person is looking at), and
/// the absence of anything else (no other fields, little text — the content
/// that should be here is not).
function purposeOfPage(state, cs) {
  const url = String(state?.url || "");
  const path = (() => { try { return new URL(url).pathname + new URL(url).search; } catch (_) { return url; } })();
  const address = AUTH_PATH.test(path) || AUTH_TITLE.test(String(state?.title || ""));
  const overlay = state?.overlay === true;
  const text = String(state?.text || "");
  const otherFields = fieldsOf(state).filter((f) =>
    !IDENTIFIER.test(fieldText(f)) && !PASSWORD_WORD.test(fieldText(f))
    && !/^(?:checkbox|radio|hidden|submit|button)$/i.test(String(f.type || "")));
  // A commit button for some OTHER errand ("Complete reservation", "Place
  // order") is the loudest possible evidence that the page's purpose is that
  // errand and the auth furniture is a side offer.
  const otherCommit = cs.find((c) => /^(?:button|submit)$/.test(c.role)
    && /\b(?:reserve|book|complete|place\s+order|checkout|pay|submit\s+(?:request|application|claim)|apply|schedule|confirm\s+(?:booking|reservation|appointment)|send\s+message)\b/i.test(c.label)
    && !AUTH_ACTION.test(c.label));
  const bare = otherFields.length <= 1 && text.length <= 900 && !otherCommit;
  const substantive = otherFields.length >= 3 || (!!otherCommit && otherFields.length >= 1)
    || (text.length > 2500 && !address);
  return { address, overlay, bare, substantive, otherFields, otherCommit };
}

// ---------------------------------------------------------------------------
// Weighing it
// ---------------------------------------------------------------------------

const WALL = 4;      // below this, say nothing
const SURE = 6;      // at or above this, say it without hedging

/**
 * What kind of wall, if any, is this page.
 *
 * @param {{url?:string,title?:string,elements?:string,text?:string,fields?:object[],overlay?:boolean}} state
 *        the page map from extension/page_map.js
 * @param {{isChallenge?:(state:object)=>boolean}} [deps] inject agent_loop's
 *        challenge verdict (() => verdict === CHALLENGE_BLOCKED) so there is
 *        exactly one challenge judgement in the running system. With nothing
 *        injected there is no verdict, and no captcha is ever reported.
 * @returns {{kind:"password"|"sso"|"paywall"|"captcha", site:string,
 *            provider?:string, providers?:string[], hasSignIn?:boolean,
 *            sure:boolean, score:number, why:string} | null}
 *          null means "not a wall" — including "not sure enough to say so".
 */
export function detectsLoginWall(state, deps = {}) {
  const s = state && typeof state === "object" ? state : {};
  if (!s.url && !s.elements && !s.text) return null;
  const here = site(s.url);
  const cs = controls(s);

  // 1. A challenge is agent_loop's, not ours. Checked first so a robot check
  //    that happens to sit in front of a login form can never be reported as
  //    "sign in" — he would tap sign in and hit the same check. No verdict
  //    injected means no verdict: this file never guesses one (audit #71).
  const isChallenge = typeof deps.isChallenge === "function" ? deps.isChallenge : () => false;
  if (isChallenge(s)) {
    return { kind: "captcha", site: here, sure: true, score: WALL,
             why: "the page is asking for a human check; the existing challenge path owns this" };
  }

  const purpose = purposeOfPage(s, cs);
  const proof = signedInProof(cs);
  // A sign-out control is the SITE saying the session is live, and nothing else
  // on a page outranks the site's own word on that. It matters because account
  // and security pages are MADE of password controls while perfectly signed in:
  // without this veto, "change your password" scores as a wall and he gets a
  // text asking him to sign in to a page he is already signed into. The one
  // exception is a modal, where page_map scopes the map to the dialog and any
  // Sign out in the header sits behind it.
  const vetoed = !!proof && !purpose.overlay;

  const words = `${s.title || ""} ${s.text || ""}`;

  // ---- money first. A subscription wall that also offers a subscriber login
  // must not be reported as a login wall: signing in cannot buy a plan, and
  // "just sign in" is the one instruction that would waste his time.
  const gate = MONEY_GATE.test(words);
  if (gate) {
    let score = 3;
    const why = ["the page says its content is withheld"];
    if (SUBSCRIPTION_WORD.test(words)) { score += 1; why.push("subscription wording"); }
    if (PRICE.test(words)) { score += 1; why.push("a price"); }
    const buy = cs.find((c) => /^(?:button|submit|link)$/.test(c.role) && SUBSCRIBE_ACTION.test(c.label));
    if (buy) { score += 1; why.push(`a "${buy.label}" control`); }
    if (score >= WALL) {
      const hasSignIn = !!cs.find((c) => AUTH_ACTION.test(c.label)) || !!credentialField(s, cs);
      return { kind: "paywall", site: here, hasSignIn, sure: score >= SURE, score,
               why: why.join(", ") };
    }
  }

  // ---- a real credentials form
  const password = credentialField(s, cs);
  if (password && !vetoed) {
    const identifier = identifierField(s, cs);
    let score = 3;
    const why = ["a password field"];
    if (identifier) { score += 1; why.push("an identifier field"); }
    if (authSubmit(cs)) { score += 1; why.push("a sign-in button"); }
    if (purpose.address) { score += 2; why.push("the page's own address says sign-in"); }
    if (purpose.overlay) { score += 1; why.push("it is a modal over the page"); }
    if (purpose.bare) { score += 1; why.push("nothing else on the page"); }
    // The booking/checkout case: an optional account offered beside the real
    // errand. Scoped tightly on purpose — nearly every genuine sign-in page
    // also carries a "Create an account" link, and reading that as "optional"
    // would hedge or discard the clearest wall there is. So the phrase counts
    // when it is on the PASSWORD FIELD'S OWN LABEL ("Create a password
    // (optional)"), or when the page is plainly there to do something else.
    const optionalAccount = OPTIONAL_ACCOUNT.test(password.label)
      || (OPTIONAL_ACCOUNT.test(words) && (purpose.substantive || !!purpose.otherCommit));
    if (optionalAccount) {
      score -= 3; why.push("but the account is offered as optional");
    }
    if (purpose.substantive) {
      score -= 2;
      why.push(purpose.otherCommit
        ? `but the page's own action is "${purpose.otherCommit.label}"`
        : "but the page is full of other content");
    }
    if (score >= WALL) {
      return { kind: "password", site: here, sure: score >= SURE, score,
               why: why.join(", "),
               identifierFilled: !!(identifier || {}).value };
    }
  }

  // ---- provider buttons and nothing to type
  const sso = ssoOptions(cs);
  if (sso.length && !vetoed && !password) {
    let score = 3;
    const why = [`"${sso[0].control.label}"`];
    if (sso.length > 1) { score += 1; why.push(`${sso.length} providers offered`); }
    if (purpose.address) { score += 2; why.push("the page's own address says sign-in"); }
    if (purpose.overlay) { score += 1; why.push("it is a modal over the page"); }
    if (purpose.bare) { score += 1; why.push("nothing else on the page"); }
    if (purpose.substantive) {
      score -= 2;
      why.push(purpose.otherCommit
        ? `but the page's own action is "${purpose.otherCommit.label}"`
        : "but the page is full of other content");
    }
    if (score >= WALL) {
      return { kind: "sso", site: here, provider: sso[0].provider,
               providers: sso.map((o) => o.provider), sure: score >= SURE, score,
               why: why.join(", ") };
    }
  }

  return null;
}

// ---------------------------------------------------------------------------
// What he reads on his phone
// ---------------------------------------------------------------------------

/**
 * The entire user-visible value of this module: one sentence naming the SITE,
 * the KIND of wall, and the ONE thing he can do about it. First person and no
 * jargon, matching the voice of every other hand-back in agent_loop.js — this
 * arrives as a text message, possibly while he is driving.
 */
export function handBackSentence(detection, ownerProfile = null) {
  if (!detection || !detection.kind) return "";
  const where = detection.site || "the site";
  const first = String((ownerProfile && ownerProfile.first_name) || "").trim();
  const you = first ? `${first}, ` : "";
  // Hedge when the evidence was thin. Claiming certainty we do not have is how
  // a person learns to stop trusting the sentence.
  const sure = detection.sure !== false;
  const says = (definite, hedged) => (sure ? definite : hedged);
  // Start of a fresh sentence: with his name in front of it, or capitalised.
  const asks = (rest) => (you ? `${you}${rest}` : rest.replace(/^[a-z]/, (c) => c.toUpperCase()));

  switch (detection.kind) {
    case "password":
      return `${says(`${where} wants a password before it will let me any further`,
                     `${where} looks like it wants a password before it will let me any further`)}`
        + `, and typing a password is the one thing I never do. I've left the tab open right on it`
        + `${detection.identifierFilled ? ", with your email already filled in" : ""} — `
        + `${you}sign in there and say go, and I'll pick up exactly where I stopped.`;

    case "sso": {
      const provider = detection.provider || "another account";
      const others = (detection.providers || []).filter((p) => p !== provider);
      const alt = others.length ? ` (or ${others.slice(0, 2).join(", or ")})` : "";
      return `${says(`${where} only offers "Continue with ${provider}"${alt}`,
                     `${where} looks like it only offers "Continue with ${provider}"${alt}`)}`
        + ` — there's no password to type, and you're very likely already signed in to ${provider}`
        + ` in this browser, so this is one tap. ${asks("tap it on the tab")}`
        + ` I left open and say go, and I'll carry straight on.`;
    }

    case "paywall":
      return `${says(`${where} has this behind a paid subscription`,
                     `${where} looks like it has this behind a paid subscription`)}`
        + `, not a login — so there's nothing I can sign into to get past it.`
        + (detection.hasSignIn
            ? ` If you already subscribe, sign in on the tab I left open and say go.`
            : ` The tab is open where it stopped.`)
        + ` If you don't have a subscription, this one can't be finished without buying one — tell me how you want to play it.`;

    case "captcha":
      // Deliberately the same words agent_loop.js already uses for a
      // challenge. Two different sentences for one situation reads like two
      // different products.
      return `${where} is asking for a "prove you're human" check, which I'm not allowed to click`
        + ` through. I've left the page open on it — ${you}clear the check and say go, and I'll carry on.`;

    default:
      return "";
  }
}

// ---------------------------------------------------------------------------
// Did his thumb actually work
// ---------------------------------------------------------------------------

/**
 * He signed in and told the agent to carry on. Did it take?
 *
 * Without this the resumed run maps the page, meets the same wall, and texts
 * him the same sentence — the exact "why does it keep stalling?" loop this
 * whole file exists to end. Pure comparison of two page maps, no side effects.
 *
 * Fails CLOSED: if the page after cannot be read, or the same wall is still
 * standing, the answer is no. Resuming into an unchanged wall costs a step
 * budget and a second text; staying parked costs one honest reply.
 */
export function canContinueAfterOwner(before, after, deps = {}) {
  const wasBlocked = detectsLoginWall(before, deps);
  if (!wasBlocked) return true;                      // nothing was in the way
  const now = after && typeof after === "object" ? after : null;
  if (!now || (!now.url && !now.elements && !now.text)) return false;
  const stillBlocked = detectsLoginWall(now, deps);
  if (!stillBlocked) return true;
  // A sign-out control on the page now is the site confirming the session
  // took, even while some auth furniture (a modal closing, a header) is still
  // mapped. detectsLoginWall already vetoes on this off-overlay; this covers
  // the overlay case, where the veto is deliberately withheld.
  if (signedInProof(controls(now))) return true;
  return false;
}
