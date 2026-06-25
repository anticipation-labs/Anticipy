/* =========================================================
   ANTICIPY — THE APP SCREEN ("The Board")
   Vanilla JS. No build step. Wired to the live local engine.

   The app is the welcome page's looping demo card, made real:
   one calm column, a swipeable deck of cards, and the autonomy
   dial in the corner. The only loud thing is the one gold "yes",
   and money always stops and waits.
   ========================================================= */
(function () {
  "use strict";

  /* ---------- engine base + optional owner token ----------
     There is no CORS middleware on the engine, so same-origin is the
     happy path: serve app.html from http://127.0.0.1:8787 and ENGINE is "".
     When opened from a different origin we still try 127.0.0.1:8787; the
     calm "engine is resting" state covers any block gracefully. */
  var SAME_ORIGIN = /^https?:$/.test(location.protocol) &&
    (location.hostname === "127.0.0.1" || location.hostname === "localhost");
  // Off-origin (the hosted Vercel site), talk to the cloud engine on Railway — NOT the visitor's own
  // laptop. Overridable via window.ANTICIPY_ENGINE_URL. (Always the full HTTPS host, never a :port.)
  var ENGINE = SAME_ORIGIN ? "" : (window.ANTICIPY_ENGINE_URL || "https://engine-production-eb43.up.railway.app");

  // Optional owner token: window.ANTICIPY_OWNER_TOKEN or ?token=… or localStorage.
  var OWNER_TOKEN =
    (window.ANTICIPY_OWNER_TOKEN || "") ||
    (new URLSearchParams(location.search).get("token") || "") ||
    (function () { try { return localStorage.getItem("anticipy_owner_token") || ""; } catch (e) { return ""; } })();

  var MODES = ["limited", "regular", "full_send"]; // cautious -> trusting (UI order)
  var MODE_LABEL = { limited: "Limited", regular: "Regular", full_send: "Full-Send" };
  var MODE_DESC = {
    limited: "Prepares everything. Acts only on your yes.",
    regular: "Handles the small, safe things. Asks on what matters.",
    full_send: "Moves fast for you — still stops for money and the irreversible.",
  };

  var EYEBROW = { ask: "Needs you", blocked: "Left for you", do: "Handled", remember: "Noted" };
  // sort: decisions first (ask), then money (blocked), then receipts (do), then facts (remember)
  var DISP_ORDER = { ask: 0, blocked: 1, do: 2, remember: 3 };

  var REDUCED = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ---------- DOM refs ---------- */
  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var deckEl = $("[data-deck]");
  var emptyEl = $("[data-empty]");
  var actionsEl = $("[data-actions]");
  var asideEl = $("[data-aside]");
  var fieldEl = $("#listen-field");
  var fieldWrap = $("[data-listen-wrap]");
  var submitBtn = $("[data-submit]");
  var listenBtn = $("[data-listen]");

  /* ---------- state ---------- */
  var cards = [];               // ordered board (array of card objects)
  var dismissed = {};           // locally archived (do/remember) by id
  var notes = {};               // local notes by card id (carried in next ingest meta)
  var currentMode = "regular";
  var engineUp = true;
  var resolving = false;
  var retryTimer = null;

  /* =========================================================
     small helpers
     ========================================================= */
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  /* The engine identifies the caller by a Bearer token. We send the signed-in
     Supabase user's access token on EVERY call (resolved fresh per request so a
     refreshed token is always current). A legacy owner token, if present, is the
     fallback for local/admin dev. authHeader() lives in the shared auth.js. */
  function authHeader() {
    var a = (window.Anticipy && window.Anticipy.auth) || null;
    if (a && typeof a.authHeader === "function") {
      return a.authHeader().then(function (h) {
        // Prefer the signed-in user's token; fall back to a configured owner token.
        if (h && h.Authorization) return h;
        return OWNER_TOKEN ? { Authorization: "Bearer " + OWNER_TOKEN } : {};
      });
    }
    return Promise.resolve(OWNER_TOKEN ? { Authorization: "Bearer " + OWNER_TOKEN } : {});
  }

  function api(path, opts) {
    opts = opts || {};
    return authHeader().then(function (auth) {
      var h = { "Content-Type": "application/json" };
      if (auth && auth.Authorization) h["Authorization"] = auth.Authorization;
      return fetch(ENGINE + path, {
        method: opts.method || "GET",
        headers: h,
        body: opts.body ? JSON.stringify(opts.body) : undefined,
      });
    }).then(function (r) {
      // A 401 means the engine no longer trusts this caller — drop to sign-in.
      if (r.status === 401) { onUnauthorized(); throw new Error("HTTP 401"); }
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    });
  }

  /* On a 401 from the engine: the session is gone or rejected. Raise the gate
     once (it reloads into a signed-out state cleanly). Guarded so a burst of
     in-flight calls all 401'ing only triggers one transition. */
  var droppedToSignIn = false;
  function onUnauthorized() {
    if (droppedToSignIn) return;
    droppedToSignIn = true;
    var a = (window.Anticipy && window.Anticipy.auth) || null;
    var g = (window.Anticipy && window.Anticipy.gate) || null;
    function raise() {
      if (g && typeof g.protect === "function") {
        g.protect({ onReady: function () { location.reload(); } });
      } else {
        location.reload();
      }
    }
    // sign the (now-invalid) session out first so the gate starts clean
    if (a && typeof a.signOut === "function") {
      a.signOut().then(raise).catch(raise);
    } else {
      raise();
    }
  }
  function relTime(ts) {
    if (!ts) return "just now";
    var d = (typeof ts === "number" ? ts : Date.parse(ts));
    if (isNaN(d)) return "just now";
    var s = Math.max(0, Math.round((Date.now() - d) / 1000));
    if (s < 60) return "just now";
    var m = Math.round(s / 60);
    if (m < 60) return m + " min ago";
    var h = Math.round(m / 60);
    if (h < 24) return h + (h === 1 ? " hour ago" : " hours ago");
    var dd = Math.round(h / 24);
    return dd + (dd === 1 ? " day ago" : " days ago");
  }
  var CHECK_SVG =
    '<svg class="confirm-check" viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8.5l3 3 6.5-7"/></svg>';

  /* derive a short, legible "Confirm → …" hint from the card's action/route */
  function actionHint(card) {
    var a = (card.action || "").toLowerCase();
    var r = (card.route || "").toLowerCase();
    if (a.indexOf("message") >= 0 || a === "draft_or_confirm_message") return "Confirm → sends the draft";
    if (a.indexOf("calendar") >= 0 || a.indexOf("event") >= 0) return "Confirm → books it";
    if (a.indexOf("reminder") >= 0 || a.indexOf("open_loop") >= 0) return "Confirm → sets the reminder";
    if (a.indexOf("purchase") >= 0 || a.indexOf("cart") >= 0) return "Confirm → preps it, no payment";
    if (a.indexOf("research") >= 0 || a.indexOf("find") >= 0) return "Confirm → looks it up";
    if (a.indexOf("note") >= 0) return "Confirm → writes the note";
    if (r === "browser") return "Confirm → handles it on the web";
    if (r === "voice_text") return "Confirm → reaches out";
    return "Confirm → handles it";
  }

  /* sort the board: decisions first, then by disposition order */
  function sortBoard() {
    cards.sort(function (a, b) {
      var oa = DISP_ORDER[a.disposition] != null ? DISP_ORDER[a.disposition] : 9;
      var ob = DISP_ORDER[b.disposition] != null ? DISP_ORDER[b.disposition] : 9;
      return oa - ob;
    });
  }

  /* the live, visible deck: drop dismissed + resolved-away cards */
  function visibleCards() {
    return cards.filter(function (c) {
      if (dismissed[c.id]) return false;
      var st = (c.status || "open");
      // declined / removed cards leave the surface
      if (st === "declined") return false;
      return true;
    });
  }

  /* =========================================================
     RENDER — deck
     ========================================================= */
  function renderDeck(dealNew) {
    var vis = visibleCards();

    // empty / engine states
    if (!engineUp) {
      deckEl.innerHTML = "";
      actionsEl.hidden = true;
      renderEngineResting();
      return;
    }
    if (vis.length === 0) {
      deckEl.innerHTML = "";
      actionsEl.hidden = true;
      renderEmpty(false);
      return;
    }
    var anyDecision = vis.some(function (c) { return c.disposition === "ask" || c.disposition === "blocked"; });
    if (!anyDecision) {
      // only receipts/facts left — softer empty, but keep cards flickable behind
      renderEmpty(true);
    } else {
      emptyEl.hidden = true;
    }

    // build the top three cards (top + 2 peeking)
    var existing = {};
    Array.prototype.forEach.call(deckEl.children, function (n) { existing[n.dataset.id] = n; });
    deckEl.innerHTML = "";

    var top = vis.slice(0, 3);
    top.forEach(function (card, i) {
      var node = buildCardNode(card, i);
      deckEl.appendChild(node);
      if (i === 0) {
        attachDrag(node, card);
        // draw the divider on settle
        requestAnimationFrame(function () {
          var dv = node.querySelector(".card-divider");
          if (dv) dv.classList.add("is-draw");
        });
      }
      if (dealNew && !existing[card.id]) {
        node.classList.add("is-dealing");
        requestAnimationFrame(function () {
          node.classList.add("is-settling");
          setTimeout(function () { node.classList.remove("is-dealing"); }, 20 + i * 70);
        });
      }
    });

    renderActionRow(top[0]);
  }

  function buildCardNode(card, depth) {
    var n = el("article", "deck-card");
    n.dataset.id = card.id;
    n.dataset.depth = String(depth);

    n.appendChild(el("span", "card-bloom"));

    var eyebrow = el("p", "card-eyebrow", EYEBROW[card.disposition] || "Needs you");
    n.appendChild(eyebrow);

    var title = el("p", "card-title" + (card.disposition === "remember" ? " card-title--quiet" : ""),
      card.title || "(untitled)");
    n.appendChild(title);

    // why (omit if empty), not shown on remember (the fact is its own reason)
    if (card.reason && card.disposition !== "remember") {
      n.appendChild(el("p", "card-why", card.reason));
    }

    // money line for blocked
    if (card.disposition === "blocked") {
      n.appendChild(el("p", "card-money-line", "This one costs money, so it’s yours to make."));
    }

    // divider
    n.appendChild(el("div", "card-divider"));

    if (card.disposition === "do") {
      // HANDLED receipt — a stamp, not a decision
      var stamp = el("div", "card-stamp");
      stamp.innerHTML = CHECK_SVG;
      var stampedAt = card._stampedAt || Date.now();
      stamp.appendChild(el("span", null, "Done — " + relTime(stampedAt)));
      n.appendChild(stamp);
    }

    // source line ("heard:")
    if (card.source_text) {
      var src = el("p", "card-source is-clamped");
      var lbl = el("span", "heard-label", "heard:");
      var txt = el("span", "heard-text", card.source_text);
      src.appendChild(lbl);
      src.appendChild(txt);
      n.appendChild(src);
      var toggle = el("button", "card-source-toggle", "show all");
      toggle.type = "button";
      toggle.addEventListener("click", function (e) {
        e.stopPropagation();
        var clamped = src.classList.toggle("is-clamped");
        toggle.textContent = clamped ? "show all" : "show less";
      });
      n.appendChild(toggle);
    }

    // action verb hint (asks only)
    if (card.disposition === "ask") {
      n.appendChild(el("p", "card-action-hint", actionHint(card)));
    }

    // drag edges
    n.appendChild(el("span", "drag-edge drag-edge--yes"));
    n.appendChild(el("span", "drag-edge drag-edge--no"));

    // in-card note field
    var note = el("div", "note-field");
    var inner = el("div", "note-field-inner");
    var input = el("input", "note-input");
    input.type = "text";
    input.placeholder = "Add a note…";
    input.setAttribute("aria-label", "Add a note to " + (card.title || "this card"));
    if (notes[card.id]) input.value = notes[card.id];
    input.addEventListener("click", function (e) { e.stopPropagation(); });
    input.addEventListener("keydown", function (e) {
      e.stopPropagation();
      if (e.key === "Enter") { e.preventDefault(); submitNote(card, input, note); }
    });
    inner.appendChild(input);
    inner.appendChild(el("span", "note-input-underline"));
    note.appendChild(inner);
    note.appendChild(el("p", "note-confirm", "Noted."));
    n.appendChild(note);

    return n;
  }

  function submitNote(card, input, noteEl) {
    notes[card.id] = input.value.trim();
    var conf = noteEl.querySelector(".note-confirm");
    if (conf) {
      conf.classList.add("is-show");
      setTimeout(function () { conf.classList.remove("is-show"); }, 2000);
    }
  }

  /* =========================================================
     RENDER — the four verbs (reflect top card disposition)
     ========================================================= */
  function renderActionRow(card) {
    actionsEl.innerHTML = "";
    actionsEl.hidden = false;
    if (!card) { actionsEl.hidden = true; return; }
    var disp = card.disposition;

    if (disp === "ask") {
      actionsEl.appendChild(makeConfirm(card));
      actionsEl.appendChild(makeDeny(card, "Not now"));
      actionsEl.appendChild(makeAllow(card));
      actionsEl.appendChild(makeNote(card));
    } else if (disp === "blocked") {
      // money: CONFIRM + DENY only; ALLOW disabled (money always asks)
      actionsEl.appendChild(makeConfirm(card));
      actionsEl.appendChild(makeDeny(card, "Not now"));
      var allow = makeAllow(card);
      allow.disabled = true;
      allow.title = "Money always asks — in every mode.";
      actionsEl.appendChild(allow);
      actionsEl.appendChild(makeNote(card));
    } else if (disp === "do") {
      // receipt: Undo (decline) + Note. No confirm.
      actionsEl.appendChild(makeDeny(card, "Undo"));
      actionsEl.appendChild(makeNote(card));
    } else if (disp === "remember") {
      // a fact: Note + Forget. Nothing runs.
      actionsEl.appendChild(makeNote(card));
      actionsEl.appendChild(makeForget(card));
    }
  }

  /* an accessible label that names the action AND the card it acts on, so a
     screen reader announces e.g. "Confirm: Book dentist — Thursday afternoon".
     The visible label stays short; the aria-label carries the full intent. */
  function ariaFor(verb, card) {
    var title = (card && card.title) ? card.title : "this card";
    return verb + ": " + title;
  }

  function makeConfirm(card) {
    var b = el("button", "act-confirm");
    b.type = "button";
    b.innerHTML = "Confirm " + CHECK_SVG;
    b.setAttribute("aria-label", ariaFor("Confirm", card));
    b.addEventListener("click", function () { doResolve(card, true, "confirm"); });
    return b;
  }
  function makeDeny(card, label) {
    var b = el("button", "act-deny", label);
    b.type = "button";
    // label may be "Not now" / "Undo" — name the intent for a screen reader
    b.setAttribute("aria-label", ariaFor(label === "Undo" ? "Undo" : "Decline", card));
    b.addEventListener("click", function () { doResolve(card, false, "deny"); });
    return b;
  }
  function makeAllow(card) {
    var b = el("button", "act-allow", "Let this kind run on its own");
    b.type = "button";
    b.setAttribute("aria-label", ariaFor("Allow this kind to run on its own", card));
    b.addEventListener("click", function () { doAllow(card); });
    return b;
  }
  function makeNote(card) {
    var b = el("button", "act-note", "Note");
    b.type = "button";
    b.setAttribute("aria-label", ariaFor("Add a note", card));
    b.addEventListener("click", function () { toggleNote(card); });
    return b;
  }
  function makeForget(card) {
    var b = el("button", "act-deny", "Forget this");
    b.type = "button";
    b.setAttribute("aria-label", ariaFor("Forget", card));
    b.addEventListener("click", function () { localDismiss(card, "up"); });
    return b;
  }

  function toggleNote(card) {
    var node = topNode();
    if (!node || node.dataset.id !== card.id) return;
    var nf = node.querySelector(".note-field");
    if (!nf) return;
    var open = nf.classList.toggle("is-open");
    if (open) {
      var input = nf.querySelector(".note-input");
      if (input) setTimeout(function () { input.focus(); }, 60);
    }
  }

  function topNode() { return deckEl.querySelector('.deck-card[data-depth="0"]'); }

  /* =========================================================
     ACTIONS — resolve / allow / dismiss
     ========================================================= */
  function setBusy(b) {
    resolving = b;
    actionsEl.classList.toggle("is-busy", b);
  }

  // The engine keys resolve on the REAL ask id, which for standard "execute_owner_task" asks is
  // card.execution.ask_id, NOT card.id. Posting card.id silently returned {resolved:false} and the
  // UI faked the checkmark anyway (a "never fake done" violation). Use the real id, and verify.
  function askIdOf(card) {
    return (card && card.execution && card.execution.ask_id) ? card.execution.ask_id : card.id;
  }

  // CONFIRM / DENY / UNDO -> POST /resolve {ask_id, approved}
  function doResolve(card, approved, kind) {
    if (resolving) return;
    var node = topNode();
    if (!node || node.dataset.id !== card.id) return;
    setBusy(true);
    clearAside();

    api("/resolve", { method: "POST", body: { ask_id: askIdOf(card), approved: approved } })
      .then(function (res) {
        // NEVER fake success: only celebrate if the engine actually resolved it.
        if (res && res.resolved === false) {
          setBusy(false);
          showAside("Hmm — I couldn’t lock that in. Pull to refresh and try again.");
          return;
        }
        if (approved) {
          // affirming: bloom + gold check + fly up
          playConfirm(node);
          removeCardLocal(card.id);
          flyOut(node, "confirm", function () { afterResolve(); });
        } else {
          // quiet sweep aside (deny / undo)
          card.status = "declined";
          removeCardLocal(card.id);
          flyOut(node, "deny", function () { afterResolve(); });
        }
      })
      .catch(function () {
        setBusy(false);
        // spring back: card stays, calm inline line (no red)
        showAside("Couldn’t reach the engine — try again.");
      });
  }

  // ALLOW -> confirm this instance, then nudge the global dial one notch up
  function doAllow(card) {
    if (resolving) return;
    if (card.disposition === "blocked") return; // never on money
    var node = topNode();
    if (!node || node.dataset.id !== card.id) return;
    setBusy(true);
    clearAside();

    api("/resolve", { method: "POST", body: { ask_id: askIdOf(card), approved: true } })
      .then(function (res) {
        if (res && res.resolved === false) {  // never fake done
          setBusy(false);
          showAside("Hmm — I couldn’t lock that in. Try again.");
          return null;  // sentinel: do not proceed to celebrate
        }
        playConfirm(node);
        // bump dial one notch up (limited -> regular -> full_send)
        var idx = MODES.indexOf(currentMode);
        var next = MODES[Math.min(MODES.length - 1, idx + 1)];
        var bump = (next !== currentMode)
          ? api("/owner/autonomy_mode", { method: "POST", body: { mode: next } })
              .then(function (r) {
                setMode((r && r.mode) || next, /*thread*/ true);
              })
              .catch(function () { /* dial bump failed — confirm still stands */ })
          : Promise.resolve();
        return bump.then(function () { return "ok"; });
      })
      .then(function (ok) {
        if (ok !== "ok") return;  // didn't resolve — already handled, don't fake it
        removeCardLocal(card.id);
        flyOut(node, "confirm", function () { afterResolve(); });
        showAside("On it — and I’ll handle these kinds myself now. You can always pull the dial back.");
        setTimeout(clearAside, 4200);
      })
      .catch(function () {
        setBusy(false);
        showAside("Couldn’t reach the engine — try again.");
      });
  }

  // local-only dismiss for do/remember (no endpoint)
  function localDismiss(card, dir) {
    var node = topNode();
    if (!node || node.dataset.id !== card.id) return;
    dismissed[card.id] = true;
    flyOut(node, dir === "up" ? "dismiss" : "deny", function () { afterResolve(); });
  }

  function removeCardLocal(id) {
    cards = cards.filter(function (c) { return c.id !== id; });
  }

  function afterResolve() {
    setBusy(false);
    renderDeck(false);
  }

  /* =========================================================
     MOTION
     ========================================================= */
  function playConfirm(node) {
    // light the one gold "yes": draw the check on the Confirm button, bloom behind the card
    var cb = actionsEl.querySelector(".act-confirm");
    if (cb) cb.classList.add("is-done");
    node.classList.add("is-bloom");
  }
  function flyOut(node, kind, done) {
    node.classList.remove("is-dragging");
    if (REDUCED) {
      node.style.transition = "opacity 0.2s linear";
      node.style.opacity = "0";
      setTimeout(done, 200);
      return;
    }
    var cls = kind === "confirm" ? "is-confirm-out"
      : kind === "dismiss" ? "is-dismiss-up"
        : "is-deny-out";
    if (kind === "confirm") node.style.transform = "translateX(-50%) translateY(-4px)";
    requestAnimationFrame(function () { node.classList.add(cls); });
    setTimeout(done, 480);
  }

  /* =========================================================
     SWIPE — pointer drag on the top card
     drag-right past 40% = CONFIRM, drag-left past 40% = DENY,
     drag-up on do/remember = dismiss. Below threshold springs back.
     ========================================================= */
  function attachDrag(node, card) {
    var startX = 0, startY = 0, dx = 0, dy = 0, dragging = false, axis = null;
    var width = 360;
    var yesEdge = node.querySelector(".drag-edge--yes");
    var noEdge = node.querySelector(".drag-edge--no");
    var allowVertical = (card.disposition === "do" || card.disposition === "remember");

    function down(e) {
      if (resolving) return;
      // ignore drags starting on interactive controls
      if (e.target.closest("button, input, .card-source-toggle")) return;
      dragging = true; axis = null;
      startX = e.clientX; startY = e.clientY;
      width = node.getBoundingClientRect().width || 360;
      node.classList.add("is-dragging");
      node.setPointerCapture && node.setPointerCapture(e.pointerId);
    }
    function move(e) {
      if (!dragging) return;
      dx = e.clientX - startX;
      dy = e.clientY - startY;
      if (!axis) {
        if (Math.abs(dx) > 6 || Math.abs(dy) > 6) {
          axis = Math.abs(dx) >= Math.abs(dy) ? "x" : "y";
        } else return;
      }
      if (axis === "x") {
        var rot = (dx / width) * 6;
        node.style.transform = "translateX(calc(-50% + " + dx + "px)) rotate(" + rot + "deg)";
        var ratio = Math.min(1, Math.abs(dx) / (width * 0.4));
        if (dx > 0) { yesEdge.style.opacity = String(ratio); noEdge.style.opacity = "0"; }
        else { noEdge.style.opacity = String(ratio); yesEdge.style.opacity = "0"; }
      } else if (axis === "y" && allowVertical && dy < 0) {
        node.style.transform = "translateX(-50%) translateY(" + dy + "px)";
      }
    }
    function up(e) {
      if (!dragging) return;
      dragging = false;
      node.classList.remove("is-dragging");
      yesEdge.style.opacity = "0";
      noEdge.style.opacity = "0";
      var threshold = width * 0.4;
      if (axis === "x" && dx > threshold) {
        // CONFIRM (for do cards there's no confirm — spring back instead)
        if (card.disposition === "ask" || card.disposition === "blocked") {
          node.style.transform = "";
          doResolve(card, true, "confirm");
          return;
        }
      } else if (axis === "x" && dx < -threshold) {
        if (card.disposition === "ask" || card.disposition === "blocked") {
          node.style.transform = "";
          doResolve(card, false, "deny");
          return;
        }
        if (allowVertical) { node.style.transform = ""; localDismiss(card, "left"); return; }
      } else if (axis === "y" && allowVertical && dy < -threshold) {
        node.style.transform = "";
        localDismiss(card, "up");
        return;
      }
      // spring back
      node.classList.add("is-settling");
      node.style.transform = "translateX(-50%)";
      setTimeout(function () { node.classList.remove("is-settling"); node.style.transform = ""; }, 480);
    }

    node.addEventListener("pointerdown", down);
    node.addEventListener("pointermove", move);
    node.addEventListener("pointerup", up);
    node.addEventListener("pointercancel", up);
  }

  /* =========================================================
     EMPTY / ENGINE-RESTING STATES
     ========================================================= */
  function renderEmpty(softer) {
    emptyEl.hidden = false;
    emptyEl.innerHTML = "";
    var head = el("p", "framing", softer ? "Nothing left for you to decide." : "You’re all caught up.");
    emptyEl.appendChild(head);
    emptyEl.appendChild(el("p", "empty-line",
      softer ? "I handled the rest. Flick through if you’d like to see."
        : "Hand over your day above whenever you’re ready."));
    emptyEl.appendChild(el("span", "empty-dot"));
  }

  function renderEngineResting() {
    emptyEl.hidden = false;
    emptyEl.innerHTML = "";
    emptyEl.appendChild(el("p", "empty-line empty-line--engine",
      "The engine is resting. Anticipy runs on your own machine — start it to pick up your day."));
    emptyEl.appendChild(el("span", "empty-dot"));
  }

  function showAside(msg) { asideEl.textContent = msg; asideEl.hidden = false; }
  function clearAside() { asideEl.hidden = true; asideEl.textContent = ""; }

  /* =========================================================
     ZONE 1 — listen / paste
     ========================================================= */
  function autoGrow() {
    fieldEl.style.height = "auto";
    fieldEl.style.height = Math.min(fieldEl.scrollHeight, 8 * 1.7 * 18) + "px";
  }
  fieldEl.addEventListener("input", autoGrow);
  fieldEl.addEventListener("keydown", function (e) {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") { e.preventDefault(); handOver(); }
  });
  submitBtn.addEventListener("click", handOver);

  // Listen affordance — visual-only promise of the pendant (wires nothing yet)
  listenBtn.addEventListener("click", function () {
    var on = listenBtn.classList.toggle("is-listening");
    listenBtn.setAttribute("aria-pressed", String(on));
    // data-listen hook left for a future /listen/start
  });

  function handOver() {
    var text = (fieldEl.value || "").trim();
    if (!text) return;
    clearAside();
    fieldWrap.classList.add("is-thinking");
    submitBtn.disabled = true;
    var think = el("span", "listen-think");
    submitBtn.parentNode.insertBefore(think, submitBtn);

    var meta = {};
    // carry any local notes forward as a side-channel
    if (Object.keys(notes).length) meta.notes = notes;

    api("/owner/ingest", {
      method: "POST",
      body: { text: text, source: "transcript", execute_actions: true, meta: meta },
    })
      .then(function (res) {
        fieldEl.value = "";
        autoGrow();
        mergeCards((res && res.cards) || []);
        renderDeck(true);
        var ignored = (res && res.ignored_line_count) || 0;
        if (ignored > 0) {
          showAside(ignored + (ignored === 1 ? " line was just life — left it be." : " lines were just life — left them be."));
        }
      })
      .catch(function () {
        engineUp = false;
        renderDeck(false);
        scheduleRetry();
      })
      .then(function () {
        fieldWrap.classList.remove("is-thinking");
        submitBtn.disabled = false;
        if (think.parentNode) think.parentNode.removeChild(think);
      });
  }

  function mergeCards(incoming) {
    var byId = {};
    cards.forEach(function (c) { byId[c.id] = c; });
    incoming.forEach(function (c) {
      if (!c || !c.id) return;
      if (byId[c.id]) {
        // refresh in place
        Object.assign(byId[c.id], c);
      } else {
        if (c.disposition === "do") c._stampedAt = Date.now();
        cards.push(c);
        byId[c.id] = c;
      }
    });
    sortBoard();
  }

  /* =========================================================
     ZONE 3 — autonomy dial
     ========================================================= */
  var dialNode = $("[data-dial-node]");
  var dialDesc = $("[data-dial-desc]");
  var dialBrake = $("[data-dial-brake]");
  var dialStops = Array.prototype.slice.call(document.querySelectorAll(".dial-stop"));
  var pillModeEl = $("[data-dial-pill-mode]");
  var pillBtn = $("[data-dial-pill-btn]");
  var sheetEl = $("[data-dial-sheet]");
  var sheetScrim = $("[data-dial-sheet-scrim]");
  var sheetStops = Array.prototype.slice.call(document.querySelectorAll(".dial-sheet-stop"));

  function modePercent(mode) {
    var idx = MODES.indexOf(mode); // 0,1,2
    return idx <= 0 ? 0 : idx === 1 ? 50 : 100;
  }

  function setMode(mode, thread) {
    if (MODES.indexOf(mode) < 0) mode = "regular";
    currentMode = mode;
    // desktop node
    dialNode.style.left = modePercent(mode) + "%";
    if (thread && !REDUCED) {
      dialNode.classList.remove("is-thread");
      void dialNode.offsetWidth;
      dialNode.classList.add("is-thread");
    }
    dialStops.forEach(function (s) { s.classList.toggle("is-active", s.dataset.mode === mode); });
    sheetStops.forEach(function (s) { s.classList.toggle("is-active", s.dataset.mode === mode); });
    dialDesc.textContent = MODE_DESC[mode];
    dialBrake.hidden = (mode !== "full_send");
    if (pillModeEl) pillModeEl.textContent = MODE_LABEL[mode];
  }

  function chooseMode(mode) {
    if (mode === currentMode) { closeSheet(); return; }
    var prev = currentMode;
    setMode(mode, false); // optimistic
    api("/owner/autonomy_mode", { method: "POST", body: { mode: mode } })
      .then(function (r) { setMode((r && r.mode) || mode, false); })
      .catch(function () { setMode(prev, false); /* rollback, silently */ });
    closeSheet();
  }

  dialStops.forEach(function (s) {
    s.addEventListener("click", function () { chooseMode(s.dataset.mode); });
  });
  sheetStops.forEach(function (s) {
    s.addEventListener("click", function () { chooseMode(s.dataset.mode); });
  });
  if (pillBtn) pillBtn.addEventListener("click", openSheet);
  if (sheetScrim) sheetScrim.addEventListener("click", closeSheet);

  function openSheet() { sheetEl.hidden = false; requestAnimationFrame(function () { sheetEl.classList.add("is-open"); }); }
  function closeSheet() {
    if (!sheetEl) return;
    sheetEl.classList.remove("is-open");
    setTimeout(function () { sheetEl.hidden = true; }, 400);
  }

  /* =========================================================
     LOAD + RETRY
     ========================================================= */
  function setToday() {
    var d = new Date();
    var months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    var v = $("[data-today]");
    if (v) v.textContent = "· " + d.getDate() + " " + months[d.getMonth()];
  }

  function loadAll() {
    return Promise.all([
      api("/owner/cards?limit=50").catch(function () { return null; }),
      api("/owner/autonomy_mode").catch(function () { return null; }),
    ]).then(function (res) {
      var cardsRes = res[0], modeRes = res[1];
      if (cardsRes == null && modeRes == null) {
        engineUp = false;
        renderDeck(false);
        scheduleRetry();
        return;
      }
      engineUp = true;
      if (retryTimer) { clearInterval(retryTimer); retryTimer = null; }
      if (modeRes && modeRes.mode) setMode(modeRes.mode, false);
      if (cardsRes && Array.isArray(cardsRes.cards)) {
        cards = cardsRes.cards.filter(function (c) { return c && c.id; }).map(function (c) {
          if (c.disposition === "do" && !c._stampedAt) c._stampedAt = Date.now();
          return c;
        });
        sortBoard();
      }
      renderDeck(false);
    });
  }

  function scheduleRetry() {
    if (retryTimer) return;
    retryTimer = setInterval(function () {
      api("/health").then(function () {
        // engine returned — reload the board, cards fade in
        engineUp = true;
        clearInterval(retryTimer); retryTimer = null;
        loadAll();
      }).catch(function () { /* still resting */ });
    }, 4000);
  }

  /* ---------- boot ---------- */
  // Gate the Board behind sign-in. Anticipy.gate.protect shows the sign-in
  // screen when signed out and only calls onReady once a real session exists;
  // if already signed in, onReady runs immediately and no gate is shown.
  function bootApp() {
    setToday();
    autoGrow();
    // surface the signed-in chip (email + Sign out) in the topbar
    var chipSlot = $("[data-auth-chip]");
    if (chipSlot && window.Anticipy && window.Anticipy.gate) {
      window.Anticipy.gate.mountChip(chipSlot);
    }
    // confirm liveness before first paint, then load the board
    api("/health")
      .then(function () { engineUp = true; return loadAll(); })
      .catch(function () { engineUp = false; renderDeck(false); scheduleRetry(); });
  }

  if (window.Anticipy && window.Anticipy.gate && typeof window.Anticipy.gate.protect === "function") {
    window.Anticipy.gate.protect({ onReady: bootApp });
  } else {
    // auth layer missing (CDN blocked): boot the board anyway so the app isn't
    // bricked — engine calls just go out without a token and the engine answers
    // (or 401s honestly). Never a blank screen.
    bootApp();
  }
})();
