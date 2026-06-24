/* =========================================================
   ANTICIPY — the sign-in / sign-up screen (the front door)
   Vanilla JS. Loaded after auth.js. Renders the premium gate,
   drives sign in / sign up / sign out / "check your email" /
   honest errors, and exposes:

     Anticipy.gate.protect({ onReady })   -> gate the page; calls
        onReady(session) once a real session exists, after fading
        the gate out. If already signed in, onReady runs immediately
        and no gate is shown.

     Anticipy.gate.mountChip(container)    -> the signed-in chip
        (email + Sign out) for a topbar.

   The screen IS the product's atmosphere — cream paper, ink serif
   lead, one gold hairline. Never a console-style form.
   ========================================================= */
(function () {
  "use strict";

  var ANTICIPY = (window.Anticipy = window.Anticipy || {});
  var auth = ANTICIPY.auth;

  var REDUCED =
    window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }

  /* Map Supabase's auth errors to calm, human, honest lines — never raw.
     We stay specific where we can (bad password, unconfirmed, rate-limit)
     and fall back to a plain reassurance otherwise. */
  function humanError(err, mode) {
    var msg = (err && (err.message || err.error_description || err.error) || "").toString();
    var low = msg.toLowerCase();
    var status = err && err.status;

    if (!auth || !auth.available || low.indexOf("auth_unavailable") >= 0) {
      return "I can’t reach sign-in right now. Check your connection and try again.";
    }
    if (low.indexOf("invalid login") >= 0 || low.indexOf("invalid credentials") >= 0) {
      return "That email and password don’t match. Try again, or create an account.";
    }
    if (low.indexOf("email not confirmed") >= 0 || low.indexOf("not confirmed") >= 0) {
      return "This account isn’t confirmed yet — check your email for the link I sent.";
    }
    if (low.indexOf("already registered") >= 0 || low.indexOf("already been registered") >= 0 || low.indexOf("user already") >= 0) {
      return "There’s already an account with this email. Sign in instead.";
    }
    if (low.indexOf("password") >= 0 && (low.indexOf("least") >= 0 || low.indexOf("short") >= 0 || low.indexOf("6") >= 0)) {
      return "Pick a password with at least 6 characters.";
    }
    if (low.indexOf("valid email") >= 0 || low.indexOf("invalid email") >= 0) {
      return "That doesn’t look like an email address. Mind checking it?";
    }
    if (status === 429 || low.indexOf("rate limit") >= 0 || low.indexOf("too many") >= 0) {
      return "A few too many tries. Give it a minute, then try again.";
    }
    if (low.indexOf("network") >= 0 || low.indexOf("failed to fetch") >= 0) {
      return "I couldn’t reach the server. Check your connection and try again.";
    }
    // honest fallback — state that something went wrong without faking detail
    return mode === "signup"
      ? "Something went wrong creating your account. Try again in a moment."
      : "Something went wrong signing in. Try again in a moment.";
  }

  function looksLikeEmail(v) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);
  }

  /* =========================================================
     The gate element + its three faces: FORM, CONFIRM.
     ========================================================= */
  function buildGate() {
    var gate = el("div", "auth-gate");
    gate.setAttribute("role", "dialog");
    gate.setAttribute("aria-modal", "true");
    gate.setAttribute("aria-label", "Sign in to Anticipy");

    var col = el("div", "auth-column");
    gate.appendChild(col);

    // quiet spine
    var rail = el("div", "auth-rail");
    rail.setAttribute("aria-hidden", "true");
    rail.appendChild(el("span", "auth-rail-line"));
    rail.appendChild(el("span", "auth-rail-dot"));
    col.appendChild(rail);

    /* ---- FORM face ---- */
    var form = el("form", "auth-form");
    form.setAttribute("novalidate", "");

    var eyebrow = el("p", "auth-eyebrow auth-reveal-item", "Welcome");
    var headline = el("h1", "auth-headline auth-reveal-item", "Sign in to Anticipy.");
    var sub = el("p", "auth-sub auth-reveal-item",
      "Your day, your accounts, your decisions — gathered behind one quiet door. This is just so I know it’s you.");
    form.appendChild(eyebrow);
    form.appendChild(headline);
    form.appendChild(sub);

    // email
    var emailField = el("div", "auth-field auth-reveal-item");
    var emailLabel = el("label", "auth-field-label", "Email");
    emailLabel.setAttribute("for", "auth-email");
    var emailInput = el("input", "auth-input");
    emailInput.type = "email";
    emailInput.id = "auth-email";
    emailInput.name = "email";
    emailInput.autocomplete = "email";
    emailInput.placeholder = "you@example.com";
    emailInput.setAttribute("aria-label", "Email");
    emailField.appendChild(emailLabel);
    emailField.appendChild(emailInput);
    form.appendChild(emailField);

    // password
    var passField = el("div", "auth-field auth-reveal-item");
    var passLabel = el("label", "auth-field-label", "Password");
    passLabel.setAttribute("for", "auth-password");
    var passInput = el("input", "auth-input");
    passInput.type = "password";
    passInput.id = "auth-password";
    passInput.name = "password";
    passInput.autocomplete = "current-password";
    passInput.placeholder = "••••••••";
    passInput.setAttribute("aria-label", "Password");
    var reveal = el("button", "auth-reveal", "Show");
    reveal.type = "button";
    reveal.setAttribute("aria-label", "Show password");
    reveal.addEventListener("click", function () {
      var showing = passInput.type === "text";
      passInput.type = showing ? "password" : "text";
      reveal.textContent = showing ? "Show" : "Hide";
      reveal.setAttribute("aria-label", showing ? "Show password" : "Hide password");
    });
    passField.appendChild(passLabel);
    passField.appendChild(passInput);
    passField.appendChild(reveal);
    form.appendChild(passField);

    // submit
    var actions = el("div", "auth-actions auth-reveal-item");
    var submit = el("button", "auth-submit");
    submit.type = "submit";
    var submitLabel = el("span", null, "Sign in");
    submit.appendChild(submitLabel);
    submit.appendChild(el("span", "auth-spinner"));
    actions.appendChild(submit);
    form.appendChild(actions);

    // message line (errors / quiet notes)
    var msg = el("p", "auth-msg");
    msg.setAttribute("aria-live", "polite");
    form.appendChild(msg);

    // mode switch
    var switchP = el("p", "auth-switch auth-reveal-item");
    var switchText = el("span", null, "New to Anticipy? ");
    var switchBtn = el("button", "auth-switch-btn", "Create an account");
    switchBtn.type = "button";
    switchP.appendChild(switchText);
    switchP.appendChild(switchBtn);
    form.appendChild(switchP);

    // footnote
    form.appendChild(el("p", "auth-footnote",
      "Anticipy never spends your money, or your trust, without asking. Signing in only tells me who you are."));

    col.appendChild(form);

    /* ---- CONFIRM face (check your email) ---- */
    var confirm = el("div", "auth-confirm");
    confirm.hidden = true;
    var mark = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    mark.setAttribute("class", "auth-confirm-mark");
    mark.setAttribute("viewBox", "0 0 32 32");
    mark.setAttribute("aria-hidden", "true");
    mark.innerHTML = '<path d="M4 9 L16 18 L28 9 M4 8 h24 v16 h-24 z"/>';
    confirm.appendChild(mark);
    confirm.appendChild(el("p", "auth-eyebrow", "One last step"));
    confirm.appendChild(el("h1", "auth-confirm-headline", "Check your email to confirm."));
    var confBody = el("p", "auth-confirm-body");
    confBody.appendChild(document.createTextNode("I sent a confirmation link to "));
    var confEmail = el("span", "auth-confirm-email", "");
    confBody.appendChild(confEmail);
    confBody.appendChild(document.createTextNode(". Open it, and you’re in — this screen will let you sign in after."));
    confirm.appendChild(confBody);
    confirm.appendChild(el("p", "auth-confirm-body auth-msg is-quiet",
      "No email after a minute? Check spam, or try creating the account again."));
    var backWrap = el("p", "auth-confirm-back");
    var backBtn = el("button", "auth-switch-btn", "Back to sign in");
    backBtn.type = "button";
    backWrap.appendChild(backBtn);
    confirm.appendChild(backWrap);
    col.appendChild(confirm);

    return {
      gate: gate,
      form: form,
      confirm: confirm,
      confEmail: confEmail,
      emailInput: emailInput,
      passInput: passInput,
      submit: submit,
      submitLabel: submitLabel,
      msg: msg,
      eyebrow: eyebrow,
      headline: headline,
      sub: sub,
      passLabel: passLabel,
      reveal: reveal,
      switchText: switchText,
      switchBtn: switchBtn,
      backBtn: backBtn,
    };
  }

  /* =========================================================
     Drive one gate instance.
     ========================================================= */
  function driveGate(refs, onSignedIn) {
    var mode = "signin"; // or "signup"
    var busy = false;

    function setMsg(text, kind) {
      refs.msg.textContent = text || "";
      refs.msg.className = "auth-msg" + (text ? " is-" + (kind || "error") : "");
    }

    function setBusy(b) {
      busy = b;
      refs.submit.classList.toggle("is-busy", b);
      refs.submit.disabled = b;
      refs.emailInput.disabled = b;
      refs.passInput.disabled = b;
    }

    function applyMode() {
      if (mode === "signup") {
        refs.eyebrow.textContent = "Welcome";
        refs.headline.textContent = "Create your Anticipy.";
        refs.sub.textContent =
          "One account holds everything I learn for you. Pick an email and a password — that’s all I need to get started.";
        refs.submitLabel.textContent = "Create account";
        refs.passInput.autocomplete = "new-password";
        refs.switchText.textContent = "Already have an account? ";
        refs.switchBtn.textContent = "Sign in";
      } else {
        refs.eyebrow.textContent = "Welcome";
        refs.headline.textContent = "Sign in to Anticipy.";
        refs.sub.textContent =
          "Your day, your accounts, your decisions — gathered behind one quiet door. This is just so I know it’s you.";
        refs.submitLabel.textContent = "Sign in";
        refs.passInput.autocomplete = "current-password";
        refs.switchText.textContent = "New to Anticipy? ";
        refs.switchBtn.textContent = "Create an account";
      }
      setMsg("");
    }

    refs.switchBtn.addEventListener("click", function () {
      if (busy) return;
      mode = mode === "signin" ? "signup" : "signin";
      applyMode();
      refs.emailInput.focus();
    });

    refs.backBtn.addEventListener("click", function () {
      refs.confirm.hidden = true;
      refs.form.hidden = false;
      mode = "signin";
      applyMode();
      refs.emailInput.focus();
    });

    function showConfirm(email) {
      refs.confEmail.textContent = email;
      refs.form.hidden = true;
      refs.confirm.hidden = false;
    }

    refs.form.addEventListener("submit", function (e) {
      e.preventDefault();
      if (busy) return;
      var email = (refs.emailInput.value || "").trim();
      var password = refs.passInput.value || "";

      if (!looksLikeEmail(email)) {
        setMsg("That doesn’t look like an email address. Mind checking it?");
        refs.emailInput.focus();
        return;
      }
      if (!password || password.length < 6) {
        setMsg(mode === "signup"
          ? "Pick a password with at least 6 characters."
          : "Enter your password to continue.");
        refs.passInput.focus();
        return;
      }
      if (!auth || !auth.available) {
        setMsg(humanError(new Error("auth_unavailable"), mode));
        return;
      }

      setBusy(true);
      setMsg("");

      var op = mode === "signup"
        ? auth.signUp(email, password)
        : auth.signIn(email, password);

      op.then(function (data) {
        setBusy(false);
        if (mode === "signup" && (!data || !data.session)) {
          // confirmation required: no session yet, a mail was sent
          showConfirm(email);
          return;
        }
        // a live session exists (sign-in, or autoconfirm sign-up) -> proceed
        if (data && data.session) {
          onSignedIn(data.session);
        } else {
          // signed in with no session object returned: re-read it
          auth.currentSession().then(function (s) {
            if (s) onSignedIn(s);
            else setMsg(humanError(new Error("no session"), mode));
          });
        }
      }).catch(function (err) {
        setBusy(false);
        setMsg(humanError(err, mode));
      });
    });

    applyMode();
  }

  /* Stagger the gate's own lines in (independent of the page reveal system). */
  function revealGate(refs) {
    var items = refs.gate.querySelectorAll(".auth-reveal-item");
    if (REDUCED) {
      Array.prototype.forEach.call(items, function (n) { n.classList.add("is-in"); });
      return;
    }
    Array.prototype.forEach.call(items, function (n, i) {
      n.style.transitionDelay = (i * 0.07) + "s";
    });
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        Array.prototype.forEach.call(items, function (n) { n.classList.add("is-in"); });
      });
    });
  }

  /* =========================================================
     PUBLIC: protect(opts)
     ========================================================= */
  function protect(opts) {
    opts = opts || {};
    var onReady = typeof opts.onReady === "function" ? opts.onReady : function () {};
    // LOCAL single-user OWNER mode (127.0.0.1/localhost): the engine is open and there's one default
    // brain — skip the sign-in gate entirely (no requireAuth, no onChange-reload). Sign-in is the cloud
    // experience. This prevents the flash/reload loop that the no-session onChange listener caused locally.
    if (/^https?:$/.test(location.protocol) &&
        (location.hostname === "127.0.0.1" || location.hostname === "localhost")) {
      onReady(null);
      return;
    }
    var shown = false;
    var refs = null;

    function showGate() {
      if (shown) return;
      shown = true;
      refs = buildGate();
      document.body.appendChild(refs.gate);
      document.body.classList.add("auth-locked");
      driveGate(refs, function (session) {
        proceed(session);
      });
      // fade in + reveal
      requestAnimationFrame(function () {
        refs.gate.classList.add("is-in");
        revealGate(refs);
      });
      setTimeout(function () {
        if (refs && refs.emailInput) refs.emailInput.focus();
      }, REDUCED ? 0 : 500);
    }

    function removeGate(then) {
      if (!refs) { if (then) then(); return; }
      document.body.classList.remove("auth-locked");
      refs.gate.classList.remove("is-in");
      var g = refs.gate;
      setTimeout(function () {
        if (g && g.parentNode) g.parentNode.removeChild(g);
        if (then) then();
      }, REDUCED ? 0 : 600);
    }

    var proceeded = false;
    function proceed(session) {
      if (proceeded) return;
      proceeded = true;
      removeGate(function () {
        onReady(session);
      });
    }

    // requireAuth resolves with a session (now or after sign-in). If signed
    // out, it calls onSignedOut so we raise the gate.
    auth.requireAuth({ onSignedOut: showGate }).then(function (session) {
      proceed(session);
    });
  }

  /* =========================================================
     PUBLIC: mountChip(container)
     A quiet "you@example.com · Sign out" chip for a topbar.
     ========================================================= */
  function mountChip(container) {
    if (!container) return;
    // LOCAL owner mode: no sign-in chip and — critically — no onChange→reload listener (that listener
    // reloads whenever there's no signed-in user, which locally is always, causing the flash loop).
    if (/^https?:$/.test(location.protocol) &&
        (location.hostname === "127.0.0.1" || location.hostname === "localhost")) {
      return;
    }
    var u = auth && auth.available ? auth.user() : null;
    var email = u && u.email ? u.email : "";

    container.innerHTML = "";
    var chip = el("span", "auth-chip");
    if (email) {
      var em = el("span", "auth-chip-email", email);
      em.title = email;
      chip.appendChild(em);
      chip.appendChild(el("span", null, "·"));
    }
    var out = el("button", "auth-chip-signout", "Sign out");
    out.type = "button";
    out.addEventListener("click", function () {
      out.disabled = true;
      out.textContent = "Signing out…";
      auth.signOut().then(function () {
        location.reload(); // back to the gate, cleanly
      }).catch(function () {
        location.reload();
      });
    });
    chip.appendChild(out);
    container.appendChild(chip);

    // keep the chip honest if auth state changes elsewhere
    if (auth && auth.available) {
      auth.onChange(function () {
        var nu = auth.user();
        if (!nu) { location.reload(); }
      });
    }
  }

  ANTICIPY.gate = { protect: protect, mountChip: mountChip };
})();
