/* =========================================================
   ANTICIPY — ONBOARDING wiring
   Served same-origin from http://127.0.0.1:8787 — every fetch
   is a bare relative path. Real fetch + try/catch. The UI shows
   exactly what the engine returns: scraped is read, needs_login
   is honest, an empty dossier stays empty. Never red, never faked.
   ========================================================= */
(function () {
  "use strict";

  var REDUCED = window.matchMedia &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* ----- engine field -> human label ----- */
  var SURFACE_LABEL = {
    gmail_inbox: "Gmail",
    gmail_sent: "Gmail",
    calendar: "Calendar",
    contacts: "Contacts",
    linkedin: "LinkedIn"
  };
  var LAYER_NAME = {
    1: "Layer one · a first pass",
    2: "Layer two · going deeper",
    3: "Layer three · deeper still",
    4: "Layer four · the last pass"
  };
  var STEP_MARKER = {
    intro: "one of four",
    allow: "two of four",
    loop: "three of four",
    dossier: "four of four"
  };

  /* ----- tiny DOM helpers ----- */
  function $(sel, root) { return (root || document).querySelector(sel); }
  function $all(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function uniqueLabels(keys) {
    var seen = {}, out = [];
    (keys || []).forEach(function (k) {
      var lbl = SURFACE_LABEL[k] || k;
      if (!seen[lbl]) { seen[lbl] = 1; out.push(lbl); }
    });
    return out;
  }

  /* ----- the one network helper: relative path, JSON, honest errors ----- */
  function api(path, opts) {
    opts = opts || {};
    var init = { method: opts.method || "GET", headers: {} };
    if (opts.body !== undefined) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(opts.body);
    }
    return fetch(path, init).then(function (res) {
      if (!res.ok) {
        var e = new Error("engine_status_" + res.status);
        e.status = res.status;
        throw e;
      }
      return res.json();
    });
  }

  /* ----- reveal stagger (welcome-page [data-reveal]) ----- */
  function revealScreen(screen) {
    var items = $all("[data-reveal]", screen);
    if (REDUCED) {
      items.forEach(function (n) { n.classList.add("is-in"); });
      return;
    }
    items.forEach(function (n, i) {
      n.classList.remove("is-in");
      n.style.setProperty("--reveal-delay", (i * 0.09) + "s");
    });
    // next frame so the transition runs
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        items.forEach(function (n) { n.classList.add("is-in"); });
      });
    });
  }

  /* ----- screen router ----- */
  var screens = {};
  $all(".ob-screen").forEach(function (s) { screens[s.getAttribute("data-screen")] = s; });
  var stepMarkerEl = $("[data-step-marker]");

  function goTo(name) {
    Object.keys(screens).forEach(function (k) {
      var s = screens[k];
      if (k === name) {
        s.hidden = false;
        s.classList.add("is-active");
      } else {
        s.hidden = true;
        s.classList.remove("is-active");
      }
    });
    if (stepMarkerEl && STEP_MARKER[name]) stepMarkerEl.textContent = STEP_MARKER[name];
    window.scrollTo(0, 0);
    revealScreen(screens[name]);
  }

  /* =========================================================
     "Open the Anticipy browser" — the local debuggable Chrome the
     scrape drives over CDP. We surface the honest intent; the engine
     owns the actual cdp_url. We POST /onboard/scan to nudge the
     extension/bridge when present (returns triggered:false calmly
     when nothing is connected — never an error to the user).
     ========================================================= */
  function openAnticipyBrowser(ev) {
    if (ev) ev.preventDefault();
    api("/onboard/scan", { method: "POST", body: { services: [] } })
      .catch(function () { /* calm: nothing connected to drive; no error shown */ });
  }
  $all("[data-open-browser]").forEach(function (a) {
    a.addEventListener("click", openAnticipyBrowser);
  });

  /* =========================================================
     SCREEN 0 · THE WARM INTRO
     ========================================================= */
  (function intro() {
    var beginBtn = $("[data-begin]");
    var learnToggle = $("[data-learn-toggle]");
    var learnDetail = $("[data-learn-detail]");

    if (learnToggle && learnDetail) {
      learnToggle.addEventListener("click", function () {
        var open = learnDetail.classList.toggle("is-open");
        if (open) learnDetail.hidden = false;
        learnToggle.setAttribute("aria-expanded", open ? "true" : "false");
      });
    }
    if (beginBtn) {
      beginBtn.addEventListener("click", function () {
        goTo("allow");
        loadPermissions();
      });
    }
  })();

  /* =========================================================
     SCREEN 1 · THE ALLOW GATE
     GET  /onboard/permissions -> {services, any_allowed}
     POST /onboard/permissions {service, allowed} -> same state
     ========================================================= */
  var allowRows = $("[data-allow-rows]");
  var gateNext = $("[data-gate-next]");
  var gateAside = $("[data-gate-aside]");
  var permsLoaded = false;

  function checkMark() {
    return '<svg class="confirm-check" viewBox="0 0 16 16" aria-hidden="true">' +
      '<path d="M3 8.5l3.2 3.2L13 4.8" /></svg>';
  }

  function renderAllowState(state, animate) {
    var services = (state && state.services) || [];
    allowRows.innerHTML = "";

    services.forEach(function (svc, i) {
      var row = el("div", "ob-row");
      var txt = el("div", "ob-row-text");
      txt.appendChild(el("p", "ob-row-name", svc.label || svc.service));
      txt.appendChild(el("p", "ob-row-why", svc.why || ""));
      row.appendChild(txt);

      var ctl = el("div", "ob-allow-ctl");
      var bloom = el("span", "ob-allow-bloom");
      ctl.appendChild(bloom);

      var btn;
      if (svc.allowed) {
        btn = el("button", "ob-allow-on");
        btn.type = "button";
        btn.innerHTML = "Allowed" + checkMark();
        btn.setAttribute("aria-pressed", "true");
      } else {
        btn = el("button", "ob-allow-off");
        btn.type = "button";
        btn.textContent = "Allow";
        btn.setAttribute("aria-pressed", "false");
      }
      btn.setAttribute("aria-label",
        (svc.allowed ? "Allowed: " : "Allow ") + (svc.label || svc.service));
      btn.addEventListener("click", function () {
        toggleService(svc.service, !svc.allowed, ctl);
      });
      ctl.appendChild(btn);
      row.appendChild(ctl);

      allowRows.appendChild(row);

      if (animate && !REDUCED) {
        row.classList.add("is-dealing");
        setTimeout(function () {
          row.classList.add("is-settling");
        }, 60 + i * 90);
      }
    });

    syncGate(!!state.any_allowed);
  }

  function syncGate(anyAllowed) {
    if (anyAllowed) {
      gateNext.disabled = false;
      gateAside.hidden = true;
    } else {
      gateNext.disabled = true;
      gateAside.hidden = false;
    }
  }

  function toggleService(service, allowed, ctl) {
    api("/onboard/permissions", { method: "POST", body: { service: service, allowed: allowed } })
      .then(function (state) {
        // fire the gold breath behind the pill on an affirmative
        if (allowed && ctl) {
          var bloom = ctl.querySelector(".ob-allow-bloom");
          if (bloom && !REDUCED) {
            bloom.classList.remove("is-bloom");
            void bloom.offsetWidth;
            bloom.classList.add("is-bloom");
          }
        }
        renderAllowState(state, false);
      })
      .catch(function () {
        // engine offline: leave the row as-is, state stays honest (no fake toggle)
        showAllowOffline();
      });
  }

  function showAllowOffline() {
    if (!allowRows.querySelector(".ob-engine-line")) {
      var line = el("p", "ob-engine-line",
        "I can't reach the engine right now — it's not logged in, that's all. Start it and try again.");
      allowRows.innerHTML = "";
      allowRows.appendChild(line);
    }
    syncGate(false);
  }

  function loadPermissions() {
    if (permsLoaded) return;
    api("/onboard/permissions")
      .then(function (state) {
        permsLoaded = true;
        renderAllowState(state, true);
      })
      .catch(function () {
        showAllowOffline();
      });
  }

  if (gateNext) {
    gateNext.addEventListener("click", function () {
      if (gateNext.disabled) return;
      goTo("loop");
      runLoop();
    });
  }

  /* =========================================================
     SCREEN 2 · THE LOOP
     POST /onboard/loop {max_layers:4} -> full run
     Show a breathing "reading" state, then stage layers[] in
     one at a time. Honest: nothing shown the response didn't hold.
     ========================================================= */
  var loopLive = $("[data-loop-live]");
  var loopLayers = $("[data-loop-layers]");
  var loopTail = $("[data-loop-tail]");
  var loopEmpty = $("[data-loop-empty]");
  var loopOffline = $("[data-loop-offline]");
  var tailBody = $("[data-tail-body]");
  var thinkLine = $("[data-think-line]");
  var THINK_LINES = ["Opening Gmail…", "Reading your calendar…", "Meeting the people who matter…"];
  var thinkTimer = null;
  var loopResult = null;

  function startThinking() {
    if (REDUCED || !thinkLine) return;
    var i = 0;
    thinkTimer = setInterval(function () {
      thinkLine.classList.add("is-fading");
      setTimeout(function () {
        i += 1;
        thinkLine.textContent = i < THINK_LINES.length ? THINK_LINES[i] : "Still reading…";
        thinkLine.classList.remove("is-fading");
      }, 400);
    }, 2200);
  }
  function stopThinking() {
    if (thinkTimer) { clearInterval(thinkTimer); thinkTimer = null; }
  }

  function resetLoopView() {
    stopThinking();
    loopLayers.innerHTML = "";
    loopLive.hidden = false;
    loopTail.hidden = true;
    loopEmpty.hidden = true;
    loopOffline.hidden = true;
    if (thinkLine) { thinkLine.textContent = THINK_LINES[0]; thinkLine.classList.remove("is-fading"); }
  }

  // The felt one-liner is honest: when a pass read nothing, it says so — never
  // "I'm seeing your week" over an empty read. Progress lines only when something landed.
  function feltLine(conf, readAny) {
    if (!readAny) return "Nothing landed on this pass — I need you signed in first.";
    if (conf >= 0.7) return "I have a clear picture of you now.";
    if (conf >= 0.4) return "This is coming together.";
    return "I'm starting to see the shape of your week.";
  }

  function buildLayerCard(layer) {
    var card = el("article", "ob-layer");

    card.appendChild(el("p", "card-eyebrow", (LAYER_NAME[layer.layer] || ("Layer " + layer.layer)).toUpperCase()));

    var rows = el("div", "ob-layer-rows");

    // Read row
    var readLabels = uniqueLabels(layer.scraped);
    var readAny = readLabels.length > 0;
    var readRow = el("div", "ob-layer-row");
    readRow.appendChild(el("span", "ob-layer-label", "Read"));
    if (readAny) {
      readRow.appendChild(el("p", "ob-layer-val", readLabels.join(" · ")));
    } else {
      readRow.appendChild(el("p", "ob-layer-val ob-layer-val--soft", "Nothing readable yet."));
    }
    rows.appendChild(readRow);

    // Still to do row (omit entirely when empty — silence reads as resolved)
    var needLabels = uniqueLabels(layer.needs_login);
    if (needLabels.length) {
      var needRow = el("div", "ob-layer-row");
      needRow.appendChild(el("span", "ob-layer-label", "Still to do"));
      var needText = needLabels.map(function (l) { return l + " — not signed in yet"; }).join(", ");
      needRow.appendChild(el("p", "ob-layer-val ob-layer-val--soft", needText));
      rows.appendChild(needRow);
    }
    card.appendChild(rows);

    // divider + felt one-liner (honest about an empty read)
    var div = el("div", "card-divider");
    card.appendChild(div);
    var conf = Number(layer.confidence) || 0;
    card.appendChild(el("p", "ob-layer-felt", feltLine(conf, readAny)));

    // confidence tick (gold hairline ∝ confidence) — NO fake floor: an empty read draws nothing
    var tick = el("span", "ob-layer-tick");
    card.appendChild(tick);

    return { card: card, divider: div, tick: tick, confidence: conf, readAny: readAny };
  }

  function stageLayers(layers, done) {
    var i = 0;
    var STEP = REDUCED ? 0 : 700;

    function next() {
      if (i >= layers.length) {
        finishLoop(done);
        return;
      }
      var built = buildLayerCard(layers[i]);
      loopLayers.appendChild(built.card);
      if (!REDUCED) built.card.classList.add("is-dealing");
      requestAnimationFrame(function () {
        built.card.classList.add("is-settling");
        setTimeout(function () {
          built.divider.classList.add("is-draw");
          // tick width ∝ confidence — but an empty read draws NO hairline (no fake progress)
          var w = built.readAny ? Math.max(0.06, Math.min(1, built.confidence)) : 0;
          built.tick.style.width = (w * 100) + "%";
        }, REDUCED ? 0 : 280);
      });
      i += 1;
      setTimeout(next, STEP);
    }
    next();
  }

  function finishLoop(done) {
    loopResult && renderTailOrAdvance();
  }

  function renderTailOrAdvance() {
    var r = loopResult;
    var scrapedAny = (r.layers || []).some(function (L) { return (L.scraped || []).length; });
    var dossier = r.dossier || {};
    var dossierEmpty = !dossier || Object.keys(dossier).length === 0;

    // honest floor: nothing readable at all
    if (!scrapedAny && dossierEmpty) {
      loopEmpty.hidden = false;
      return;
    }

    if (r.done) {
      // engine: "Here's what I learned about you — confirm and we're set."
      setTimeout(function () {
        goTo("dossier");
        renderDossier(r);
      }, REDUCED ? 0 : 600);
      return;
    }

    // not done -> some accounts weren't signed in: an invitation, never an error
    var needLabels = uniqueLabels(r.needs_login);
    if (tailBody) {
      tailBody.textContent =
        "That's fine — I built your profile from what I could read. To go deeper, sign into " +
        "these in the Anticipy browser and I'll do another pass: " +
        (needLabels.length ? needLabels.join(", ") + "." : "the accounts above.");
    }
    loopTail.hidden = false;
  }

  function runLoop() {
    resetLoopView();
    startThinking();
    api("/onboard/loop", { method: "POST", body: { max_layers: 4 } })
      .then(function (r) {
        stopThinking();
        loopResult = r;
        loopLive.hidden = true;

        var layers = r.layers || [];
        if (!layers.length) {
          // ok:false (no service allowed) or empty run -> honest floor
          loopEmpty.hidden = false;
          return;
        }
        stageLayers(layers, r.done);
      })
      .catch(function () {
        stopThinking();
        loopLive.hidden = true;
        loopOffline.hidden = false;
      });
  }

  // tail actions
  $all("[data-loop-again]").forEach(function (b) {
    b.addEventListener("click", function () { runLoop(); });
  });
  var loopContinue = $("[data-loop-continue]");
  if (loopContinue) {
    loopContinue.addEventListener("click", function () {
      // proceed with whatever was learned — never force a complete read
      if (loopResult) { goTo("dossier"); renderDossier(loopResult); }
    });
  }
  var loopRetry = $("[data-loop-retry]");
  if (loopRetry) {
    loopRetry.addEventListener("click", function () {
      openAnticipyBrowser();
      runLoop();
    });
  }

  /* =========================================================
     SCREEN 3 · THE DOSSIER CONFIRM
     Render only present fields. Never an empty section header.
     ========================================================= */
  var dossierBody = $("[data-dossier-body]");
  var dossierCard = $("[data-dossier-card]");
  var confTick = $("[data-conf-tick]");
  var confCaption = $("[data-conf-caption]");
  var gapsWrap = $("[data-gaps]");
  var gapsList = $("[data-gaps-list]");
  var confirmBtn = $("[data-confirm]");
  var correctBtn = $("[data-correct]");
  var editHint = $("[data-edit-hint]");
  var dossierStage = $("[data-dossier-stage]");
  var completeBlock = $("[data-complete]");

  function divider() { return el("div", "card-divider is-draw"); }

  // an editable text node (note-field underline-on-focus idiom)
  function editable(text, key, sub) {
    var span = el("span", "ob-edit");
    span.setAttribute("contenteditable", "false");
    span.setAttribute("data-edit-key", key);
    if (sub != null) span.setAttribute("data-edit-sub", sub);
    span.textContent = text;
    return span;
  }

  function confCaptionText(conf) {
    if (conf >= 0.7) return "I'm confident in this.";
    if (conf >= 0.4) return "This is a good start — it'll sharpen as I learn more.";
    return "Early days — correct me freely.";
  }

  function renderDossier(result) {
    var d = result.dossier || {};
    var conf = Number(result.confidence) || 0;
    dossierBody.innerHTML = "";

    var sections = [];

    // identity (serif lead)
    var ident = d.identity || {};
    if (ident.name || ident.role || ident.location || ident.email) {
      var idWrap = el("div", "ob-section");
      if (ident.name) {
        var nameLine = el("p", "ob-ident-name");
        nameLine.appendChild(editable(ident.name, "identity.name"));
        idWrap.appendChild(nameLine);
      }
      var metaBits = [];
      if (ident.role) metaBits.push("role");
      if (ident.location) metaBits.push("location");
      if (metaBits.length) {
        var meta = el("p", "ob-ident-meta");
        if (ident.role) meta.appendChild(editable(ident.role, "identity.role"));
        if (ident.role && ident.location) meta.appendChild(document.createTextNode(" · "));
        if (ident.location) meta.appendChild(editable(ident.location, "identity.location"));
        idWrap.appendChild(meta);
      }
      if (ident.email) {
        var em = el("p", "ob-ident-email");
        em.appendChild(editable(ident.email, "identity.email"));
        idWrap.appendChild(em);
      }
      sections.push(idWrap);
    }

    // work
    if (d.work) {
      var workWrap = el("div", "ob-section");
      workWrap.appendChild(el("p", "card-eyebrow", "WORK"));
      var workP = el("p", "ob-section-text");
      workP.appendChild(editable(d.work, "work"));
      workWrap.appendChild(workP);
      sections.push(workWrap);
    }

    // people
    if (Array.isArray(d.people) && d.people.length) {
      var pplWrap = el("div", "ob-section");
      pplWrap.appendChild(el("p", "card-eyebrow", "THE PEOPLE WHO MATTER"));
      d.people.forEach(function (person, idx) {
        if (!person || !person.name) return;
        var line = el("p", "ob-person");
        line.appendChild(editable(person.name, "people.name", idx));
        if (person.relationship) {
          line.appendChild(document.createTextNode(" — "));
          var rel = editable(person.relationship, "people.relationship", idx);
          rel.classList.add("ob-person-rel");
          line.appendChild(rel);
        }
        if (person.why_they_matter) {
          var why = editable(person.why_they_matter, "people.why", idx);
          why.classList.add("ob-person-why");
          line.appendChild(why);
        }
        pplWrap.appendChild(line);
      });
      sections.push(pplWrap);
    }

    // family
    if (Array.isArray(d.family) && d.family.filter(Boolean).length) {
      var famWrap = el("div", "ob-section");
      famWrap.appendChild(el("p", "card-eyebrow", "FAMILY"));
      var famP = el("p", "ob-inline");
      famP.textContent = d.family.filter(Boolean).join(", ");
      famWrap.appendChild(famP);
      sections.push(famWrap);
    }

    // tools (lighter weight — inferred)
    if (Array.isArray(d.tools) && d.tools.filter(Boolean).length) {
      var toolWrap = el("div", "ob-section");
      toolWrap.appendChild(el("p", "card-eyebrow", "TOOLS"));
      var toolP = el("p", "ob-inline ob-inline--light");
      toolP.textContent = d.tools.filter(Boolean).join(" · ");
      toolWrap.appendChild(toolP);
      sections.push(toolWrap);
    }

    // act_on_sites — never a list; one quiet line only when present
    if (Array.isArray(d.act_on_sites) && d.act_on_sites.filter(Boolean).length) {
      var noteWrap = el("div", "ob-section");
      noteWrap.appendChild(el("p", "ob-noted", "I also noted where I might help you online later."));
      sections.push(noteWrap);
    }

    // assemble with hairline dividers between sections
    sections.forEach(function (sec, i) {
      if (i > 0) dossierBody.appendChild(divider());
      dossierBody.appendChild(sec);
    });

    // if dossier had nothing usable, say so plainly (no empty card)
    if (!sections.length) {
      dossierBody.appendChild(el("p", "ob-body ob-body--soft",
        "I couldn't pull a profile together from what I could read — let's go over it on a quick call."));
    }

    // confidence hairline + caption
    confCaption.textContent = confCaptionText(conf);
    requestAnimationFrame(function () {
      // no fake floor: zero confidence draws no hairline
      var w = conf > 0 ? Math.max(0.06, Math.min(1, conf)) : 0;
      confTick.style.width = (w * 100) + "%";
    });

    // gaps
    var gaps = (result.gaps || []).filter(Boolean);
    if (gaps.length) {
      gapsList.innerHTML = "";
      gaps.forEach(function (g) { gapsList.appendChild(el("li", null, g)); });
      gapsWrap.hidden = false;
    } else {
      gapsWrap.hidden = true;
    }
  }

  // correction: make fields inline-editable in place (never a destructive reject)
  var editing = false;
  if (correctBtn) {
    correctBtn.addEventListener("click", function () {
      editing = !editing;
      dossierCard.classList.toggle("is-editing", editing);
      $all(".ob-edit", dossierBody).forEach(function (n) {
        n.setAttribute("contenteditable", editing ? "true" : "false");
      });
      editHint.hidden = !editing;
      correctBtn.textContent = editing ? "Done fixing" : "Something's off — let me fix it";
      if (editing) {
        var first = dossierBody.querySelector(".ob-edit");
        if (first) first.focus();
      }
    });
  }

  // confirm: the single gold act — persist any edits, then fly the card out
  if (confirmBtn) {
    confirmBtn.addEventListener("click", function () {
      if (confirmBtn.classList.contains("is-done")) return;
      confirmBtn.classList.add("is-done");
      persistCorrections();

      if (!REDUCED) {
        dossierCard.classList.add("is-bloom");
      }
      setTimeout(function () {
        dossierStage.style.display = "none";
        completeBlock.hidden = false;
        revealScreen(screens.dossier);
      }, REDUCED ? 60 : 520);
      if (!REDUCED) {
        setTimeout(function () { dossierCard.classList.add("is-confirm-out"); }, 120);
      }
    });
  }

  // edits amend memory via the existing owner-ingest write path (a quiet note;
  // the engine already wrote the dossier — corrections amend it). Best-effort,
  // never blocks the calm completion.
  function persistCorrections() {
    if (!editing) return;
    var notes = [];
    $all(".ob-edit", dossierBody).forEach(function (n) {
      var key = n.getAttribute("data-edit-key");
      var val = (n.textContent || "").trim();
      if (key && val) notes.push(key.replace(/\./g, " ") + ": " + val);
    });
    if (!notes.length) return;
    var text = "Correction to my profile — " + notes.join("; ") + ".";
    api("/owner/ingest", {
      method: "POST",
      body: { text: text, source: "app", meta: { onboarding_correction: true } }
    }).catch(function () { /* calm: a correction that can't reach the engine is not an error here */ });
  }

  /* ----- first paint ----- */
  goTo("intro");
})();
