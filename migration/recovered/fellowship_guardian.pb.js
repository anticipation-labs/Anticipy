/// <reference path="../pb_data/types.d.ts" />
//
// GUARDIAN CONSENT — the one thing between a 13-17 year old and being paid.
//
// WHY THIS IS ITS OWN FILE AND ITS OWN PATH. The page has to live under
// /fellows/* because that is one of only four prefixes the anticipy.ai
// rewrites forward to this backend — /fellowships, /fellowship-growth-learning,
// /fellows/* and /r/*. Everything else 404s at the edge, which is exactly how
// the old /setup?f= guardian link came to send parents nowhere. Serving the
// page from a route rather than pb_public is what makes it reachable with no
// change to the website repo and no Vercel deploy.
//
// JSVM ISOLATION: every handler redeclares its own helpers. A const at file
// top-level is NOT visible inside a routerAdd callback in this runtime. That
// is not a style choice here, it is the difference between working and a 500.
//
// THE TOKEN IS NOT THE REFERRAL CODE. The referral code is public — it is in
// the link the fellow posts publicly — so accepting consent on the strength of
// it would let any stranger who saw that link declare themselves a child's
// guardian. A separate single-purpose token is minted on demand, only its hash
// is stored, and minting a new one invalidates the last.

const GUARDIAN_TERMS_VERSION = "2026-08-22";

// --------------------------------------------------------------------------
// POST /fellows/guardian/link   (authenticated as the fellow)
// Mints a fresh guardian link for the fellow to send to their parent. The raw
// token is returned exactly once, here, to the fellow who owns it.
// --------------------------------------------------------------------------
routerAdd("POST", "/fellows/guardian/link", (e) => {
  const sha256 = (s) => $security.sha256(s);
  const site = $os.getenv("ANTICIPY_SITE_URL") || "https://www.anticipy.ai";

  const token = e.request.header.get("X-Fellow-Token") || "";
  if (!token) return e.json(401, { reauth: true });
  let fellow = null;
  try { fellow = e.app.findFirstRecordByFilter("fellows", "session_hash = {:h}", { h: sha256(token) }); } catch (_) {}
  if (fellow && fellow.getString("status") === "removed") fellow = null;
  if (!fellow) return e.json(401, { reauth: true });

  if (fellow.getString("age_band") === "18_plus") {
    return e.json(200, { ok: false, message: "You're 18 or over, so there's no guardian step." });
  }
  if (fellow.getString("parental_consent") === "confirmed") {
    return e.json(200, { ok: true, done: true,
      message: "Already done — " + (fellow.getString("guardian_name") || "your guardian") + " completed this." });
  }

  const chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789";
  let raw = "";
  for (let i = 0; i < 48; i++) raw += chars.charAt(Math.floor(Math.random() * chars.length));
  fellow.set("guardian_token_hash", sha256(raw));
  try { e.app.save(fellow); }
  catch (_) { return e.json(200, { ok: false, message: "Couldn't make that link. Try once more?" }); }

  return e.json(200, { ok: true, url: site + "/fellows/guardian?t=" + raw });
});

// --------------------------------------------------------------------------
// GET /fellows/guardian?t=   — the page the parent actually opens.
//
// Rendered from the hook rather than pb_public so it is reachable through the
// site's rewrites. Cream HIRE_THEME, same as every other programme surface.
// --------------------------------------------------------------------------
routerAdd("GET", "/fellows/guardian", (e) => {
  const sha256 = (s) => $security.sha256(s);
  const esc = (s) => String(s == null ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");

  let raw = "";
  try { raw = String(e.request.url.query().get("t") || ""); } catch (_) {}
  if (!raw) { try { raw = String(e.request.url.query.get("t") || ""); } catch (_) {} }
  if (!raw) {
    try {
      const q = String(e.request.url.rawQuery || e.request.url.query || "");
      const m = q.match(/(?:^|&)t=([^&]+)/);
      if (m) raw = decodeURIComponent(m[1]);
    } catch (_) {}
  }
  raw = raw.replace(/[^A-Za-z0-9]/g, "").slice(0, 64);

  let fellow = null;
  if (raw) {
    try { fellow = e.app.findFirstRecordByFilter("fellows", "guardian_token_hash = {:h}", { h: sha256(raw) }); } catch (_) {}
  }
  if (fellow && fellow.getString("status") === "removed") fellow = null;

  const first = fellow ? (String(fellow.getString("name") || "").trim().split(/\s+/)[0] || "your child") : "";
  const already = fellow && fellow.getString("parental_consent") === "confirmed";

  const HEAD = '<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">'
    + '<meta name="viewport" content="width=device-width, initial-scale=1">'
    + '<title>Anticipy — one step for a parent or guardian</title>'
    + '<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns=\'http://www.w3.org/2000/svg\' viewBox=\'0 0 32 32\'%3E%3Crect width=\'32\' height=\'32\' fill=\'%23FAF8F4\'/%3E%3Ccircle cx=\'16\' cy=\'16\' r=\'7\' fill=\'%23C8A97E\'/%3E%3C/svg%3E">'
    + '<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    + '<link href="https://fonts.googleapis.com/css2?family=DM+Serif+Display&family=Plus+Jakarta+Sans:wght@300;400;500;600&display=swap" rel="stylesheet">'
    + '<style>'
    + ':root{color-scheme:light;--ink:#171512;--ink-2:#6B665E;--paper:#FAF8F4;--paper-2:#F0EDE6;'
    + '--rule-2:#D6D0C4;--rule-3:#B6AC99;--accent:#C8A97E;--accent-ink:#8A6B44;--accent-ink-2:#7E6140;'
    + '--danger:#A33A3A;--ok:#2E6B4F;--field:#FFFFFF;'
    + "--serif:'DM Serif Display',Georgia,serif;--sans:'Plus Jakarta Sans',-apple-system,BlinkMacSystemFont,sans-serif;"
    + '--mono:ui-monospace,SFMono-Regular,Menlo,monospace}'
    + '*{box-sizing:border-box;margin:0;padding:0}'
    + 'body{background:var(--paper);color:var(--ink);font:300 17px/1.7 var(--sans);letter-spacing:.01em;'
    + '-webkit-font-smoothing:antialiased;padding:40px 24px 80px}'
    + 'main{max-width:620px;margin:0 auto}'
    + '.dot{width:7px;height:7px;border-radius:50%;background:var(--accent);display:inline-block;margin-right:9px}'
    + '.brand{font:400 15px/1 var(--serif)}'
    + '.rule38{width:38px;height:2px;background:var(--accent);margin:26px 0 18px}'
    + 'h1{font:400 clamp(30px,5.4vw,44px)/1.05 var(--serif);letter-spacing:-.035em}'
    + 'p{margin-top:14px;max-width:34em}.small{font-size:15.5px;color:var(--ink-2);line-height:1.65}'
    + '.tiny{font-size:13.5px;color:var(--ink-2);line-height:1.6;margin-top:10px}'
    + '.eyebrow{font-family:var(--mono);font-size:10.5px;letter-spacing:.14em;text-transform:uppercase;'
    + 'color:var(--accent-ink);display:block;margin-bottom:14px}'
    + '.card{background:var(--paper-2);border:1px solid var(--rule-2);border-radius:14px;padding:26px;margin-top:26px}'
    + '.card .eyebrow{color:var(--accent-ink-2)}'
    + '.rows{margin-top:8px;border-top:1px solid var(--rule-2)}'
    + '.row{padding:13px 0;border-bottom:1px solid var(--rule-2);font-size:15.5px;line-height:1.55}'
    + '.row b{font-weight:500}'
    + 'label{display:block;font-family:var(--mono);font-size:11px;letter-spacing:.12em;'
    + 'text-transform:uppercase;color:var(--accent-ink);margin:22px 0 6px}'
    + 'input[type=text],input[type=email]{background:transparent;border:0;border-bottom:1px solid var(--rule-2);'
    + 'color:var(--ink);padding:10px 0 12px;font:300 18px var(--sans);width:100%;outline:none;border-radius:0}'
    + 'input:focus{border-bottom-color:var(--accent-ink)}'
    + '.check{display:flex;gap:12px;align-items:flex-start;margin-top:26px;background:var(--field);'
    + 'border:1px solid var(--rule-3);border-radius:10px;padding:16px}'
    + '.check input{margin-top:4px;width:18px;height:18px;flex:none;accent-color:var(--accent-ink)}'
    + '.check span{font-size:15px;line-height:1.55}'
    + '.btn{display:inline-flex;align-items:center;justify-content:center;gap:10px;background:var(--ink);'
    + 'color:var(--paper);border:0;border-radius:999px;padding:17px 34px;font:600 16.5px/1 var(--sans);'
    + 'cursor:pointer;margin-top:26px;width:100%;text-decoration:none}'
    + '.btn:disabled{opacity:.55;cursor:default}'
    + '.msg{margin-top:12px;font-size:14.5px;min-height:20px;color:var(--ink-2)}'
    + '.msg.err{color:var(--danger)}.msg.ok{color:var(--ok)}'
    + ':focus-visible{outline:2px solid var(--accent-ink);outline-offset:3px}'
    + 'a{color:var(--accent-ink)}'
    + '</style></head><body><main>'
    + '<span class="brand"><span class="dot"></span>Anticipy</span>';

  const FOOT = '</main></body></html>';

  if (!fellow) {
    return e.html(200, HEAD + '<div class="rule38"></div>'
      + '<h1>This link has expired.</h1>'
      + '<p class="small">Guardian links are single-use and a new one replaces the last. Ask the '
      + 'person who sent it to open their fellowship page and tap <b>Get the link for my parent</b> '
      + 'again — it takes them a second.</p>'
      + '<p class="small">Nothing is lost, and nothing is wrong with their account.</p>'
      + '<p class="tiny">If you think you got this in error, write to '
      + '<a href="mailto:hello@anticipy.ai">hello@anticipy.ai</a>.</p>' + FOOT);
  }

  if (already) {
    return e.html(200, HEAD + '<div class="rule38"></div>'
      + '<h1>Already done.</h1>'
      + '<p class="small">' + esc(first) + '&rsquo;s payouts are switched on. There is nothing '
      + 'further for you to do, and we won&rsquo;t email you again about it.</p>' + FOOT);
  }

  return e.html(200, HEAD
    + '<div class="rule38"></div>'
    + '<span class="eyebrow">One step, about two minutes</span>'
    + '<h1>' + esc(first) + ' joined the Anticipy fellowship.</h1>'
    + '<p>They&rsquo;re learning how short video actually works, and everything in the course is '
    + 'already open to them. The only thing waiting on you is <b>getting paid</b> — that&rsquo;s '
    + 'the law about paying under-18s, not a rule of ours.</p>'

    + '<div class="card"><span class="eyebrow">What this is</span>'
    + '<div class="rows">'
    + '<div class="row"><b>What they do.</b> Make short videos about Anticipy on their own '
    + 'accounts, if they want to. Posting is always optional and there is no quota and no deadline.</div>'
    + '<div class="row"><b>What they earn.</b> $30 when somebody buys through their link. One '
    + 'payment, 30 days after the purchase, and we never take it back.</div>'
    + '<div class="row"><b>How it arrives.</b> A prepaid Visa card, sent to the email address you '
    + 'give below. No bank account and no ID is needed from your child — that is the whole '
    + 'reason we pay this way.</div>'
    + '<div class="row"><b>What we don&rsquo;t ask for.</b> No social security number, no bank '
    + 'details, no photo, no address, no school.</div>'
    + '</div></div>'

    + '<label for="g-name">Your full name</label>'
    + '<input type="text" id="g-name" autocomplete="name" placeholder="Alex Rivera">'
    + '<label for="g-email">Your email — this is where the card is sent</label>'
    + '<input type="email" id="g-email" autocomplete="email" inputmode="email" placeholder="you@example.com">'

    + '<div class="check"><input type="checkbox" id="g-affirm">'
    + '<span>I am ' + esc(first) + '&rsquo;s parent or legal guardian, I am over 18, and I accept '
    + 'these terms both on their behalf and in my own name as the person the money is paid to. '
    + 'I understand the reward is taxable income and that Anticipy does not give tax advice.</span></div>'

    + '<button class="btn" id="g-go">Switch on ' + esc(first) + '&rsquo;s payouts</button>'
    + '<div class="msg" id="g-msg" role="status"></div>'
    + '<p class="tiny">We keep your name, your email, the date, and which version of these terms '
    + 'you agreed to. That is all, and it is only so we can show this step happened. '
    + 'Questions: <a href="mailto:hello@anticipy.ai">hello@anticipy.ai</a>.</p>'

    + '<script>'
    + 'var T=' + JSON.stringify(raw) + ';'
    + 'function $(i){return document.getElementById(i)}'
    + 'function say(t,k){var m=$("g-msg");m.textContent=t||"";m.className="msg"+(t&&k?" "+k:"")}'
    + '$("g-go").addEventListener("click",function(){'
    + 'var n=$("g-name").value.trim(),em=$("g-email").value.trim(),a=$("g-affirm").checked;'
    + 'if(!n)return say("We need your name.","err");'
    + 'if(!/^[^\\s@]+@[^\\s@]+\\.[^\\s@]{2,}$/.test(em))return say("That email doesn\'t look right.","err");'
    + 'if(!a)return say("Please tick the box — it\'s the part that actually counts.","err");'
    + 'var b=this;b.disabled=true;b.textContent="One moment…";say("");'
    + 'fetch("/fellows/guardian",{method:"POST",headers:{"Content-Type":"application/json"},'
    + 'body:JSON.stringify({t:T,guardian_name:n,guardian_email:em,affirm:true})})'
    + '.then(function(r){return r.json()}).then(function(j){'
    + 'if(!j||!j.ok){b.disabled=false;b.textContent="Try that again";return say((j&&j.message)||"That didn\'t work.","err")}'
    + 'document.querySelector("main").innerHTML='
    + '\'<span class="brand"><span class="dot"></span>Anticipy</span><div class="rule38"></div>\''
    + '+\'<h1>Done — thank you.</h1><p class="small">\'+j.message+\'</p>\';'
    + '}).catch(function(){b.disabled=false;b.textContent="Try that again";say("We couldn\'t reach our end. Try once more.","err")});'
    + '});'
    + '</script>' + FOOT);
});

// --------------------------------------------------------------------------
// POST /fellows/guardian   {t, guardian_name, guardian_email, affirm}
//
// The write. Order matters: record the consent, THEN switch the money on, and
// only report success once the save has returned.
// --------------------------------------------------------------------------
routerAdd("POST", "/fellows/guardian", (e) => {
  const sha256 = (s) => $security.sha256(s);
  const TERMS = "2026-08-22";

  let body = {};
  try { body = e.requestInfo().body || {}; } catch (_) {}
  const raw = String(body.t || "").replace(/[^A-Za-z0-9]/g, "").slice(0, 64);
  const name = String(body.guardian_name || "").trim().slice(0, 120);
  const email = String(body.guardian_email || "").trim().toLowerCase().slice(0, 254);

  if (!raw) return e.json(200, { ok: false, message: "That link is missing something. Ask for a fresh one." });
  if (!name) return e.json(200, { ok: false, message: "We need your name." });
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(email)) {
    return e.json(200, { ok: false, message: "That email doesn't look right." });
  }
  // The affirmation is the whole point of the exercise. Without it there is no
  // consent, only a form submission.
  if (body.affirm !== true) {
    return e.json(200, { ok: false, message: "Please tick the box — it's the part that actually counts." });
  }

  let fellow = null;
  try { fellow = e.app.findFirstRecordByFilter("fellows", "guardian_token_hash = {:h}", { h: sha256(raw) }); } catch (_) {}
  if (fellow && fellow.getString("status") === "removed") fellow = null;
  if (!fellow) return e.json(200, { ok: false, message: "That link has expired. Ask for a fresh one." });

  if (fellow.getString("age_band") === "18_plus") {
    return e.json(200, { ok: false, message: "This account doesn't need a guardian step." });
  }
  if (fellow.getString("parental_consent") === "confirmed") {
    return e.json(200, { ok: true, message: "This was already done. Nothing further is needed." });
  }

  let ip = "";
  try {
    const xff = String(e.request.header.get("X-Forwarded-For") || "");
    if (xff) ip = xff.split(",")[0].trim();
  } catch (_) {}
  if (!ip) { try { ip = e.realIP() || ""; } catch (_) {} }

  fellow.set("guardian_name", name);
  fellow.set("guardian_email", email);
  fellow.set("guardian_consent_at", new Date().toISOString());
  fellow.set("guardian_consent_ip", ip);
  fellow.set("guardian_terms_version", TERMS);
  fellow.set("parental_consent", "confirmed");
  // The money switch. It is the ONLY thing this step unlocks — the learning was
  // never gated on it and never will be.
  fellow.set("code_active", true);
  // AND HOW IT ARRIVES. A minor may only ever be paid in stored value, so there
  // is exactly one legal answer here and the guardian has just accepted it in
  // writing. Set at consent as well as at signup because the payout rail refused
  // to send while this field was empty, and an account created before the
  // default existed would otherwise stay unpayable forever with every screen
  // saying it was ready.
  if (!fellow.getString("payout_method")) fellow.set("payout_method", "card");
  // Single-use: the token dies with the consent it carried.
  fellow.set("guardian_token_hash", "");

  try { e.app.save(fellow); }
  catch (_) {
    return e.json(200, { ok: false, message: "We couldn't save that. Nothing's lost — press it once more." });
  }

  try {
    const act = new Record(e.app.findCollectionByNameOrId("internal_activity"));
    act.set("actor", ""); act.set("actor_name", "Fellowships");
    act.set("action", "fellow.guardian_confirmed");
    act.set("subject", name + " confirmed guardianship for "
      + (fellow.getString("name") || fellow.getString("email")));
    act.set("ref", fellow.get("id"));
    e.app.save(act);
  } catch (_) {}

  const first = String(fellow.getString("name") || "").trim().split(/\s+/)[0] || "They";
  return e.json(200, { ok: true,
    message: first + "'s payouts are switched on. When something they make sells one, the card comes to "
      + email + " thirty days later. There is nothing else for you to do." });
});
