/* =========================================================
   ANTICIPY — interactions
   Scroll reveals · mode dial · access form · looping demo
   One thing moves at a time. Slow easing, then stillness.
   ========================================================= */

(function () {
  "use strict";

  const prefersReduced = window.matchMedia(
    "(prefers-reduced-motion: reduce)"
  ).matches;

  /* ---------- Scroll reveal ---------- */
  function initReveal() {
    const items = document.querySelectorAll("[data-reveal]");
    if (prefersReduced || !("IntersectionObserver" in window)) {
      items.forEach((el) => el.classList.add("is-in"));
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-in");
            io.unobserve(entry.target);
          }
        });
      },
      { threshold: 0.18, rootMargin: "0px 0px -8% 0px" }
    );
    items.forEach((el) => io.observe(el));

    // Beats also carry the gold entry tick
    document.querySelectorAll(".beat").forEach((el) => {
      const bo = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting) {
              entry.target.classList.add("is-in");
              bo.unobserve(entry.target);
            }
          });
        },
        { threshold: 0.3 }
      );
      bo.observe(el);
    });
  }

  /* ---------- Three modes dial ---------- */
  function initDial() {
    const node = document.querySelector("[data-dial-node]");
    const cards = document.querySelectorAll(".mode-card");
    if (!node || !cards.length) return;

    // Three positions across the track: 1/6, 1/2, 5/6
    const positions = ["16.66%", "50%", "83.33%"];

    function moveTo(i) {
      node.style.left = positions[i] || positions[1];
    }

    // Default rests on Regular (index 1)
    moveTo(1);

    cards.forEach((card) => {
      const i = parseInt(card.getAttribute("data-mode"), 10);
      card.addEventListener("mouseenter", () => moveTo(i));
      card.addEventListener("focusin", () => moveTo(i));
    });

    const wrap = document.querySelector(".mode-cards");
    if (wrap) {
      wrap.addEventListener("mouseleave", () => moveTo(1));
    }
  }

  /* ---------- Access form ---------- */
  function initForm() {
    const form = document.querySelector(".access-form");
    if (!form) return;
    const row = form.querySelector("[data-access-row]");
    const success = form.querySelector("[data-access-success]");
    const next = form.querySelector("[data-access-next]");
    const input = form.querySelector(".access-input");

    form.addEventListener("submit", (e) => {
      e.preventDefault();
      const value = (input.value || "").trim();
      // gentle validity check; no harsh error states
      if (!value || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) {
        input.focus();
        return;
      }
      row.classList.add("is-collapsing");
      window.setTimeout(() => {
        row.hidden = true;
        success.hidden = false;
        // force reflow so the transition fires
        void success.offsetWidth;
        success.classList.add("is-show");
        // surface the real path INTO the guided setup (onboard.html)
        if (next) {
          next.hidden = false;
          void next.offsetWidth;
          next.classList.add("is-show");
        }
      }, 500);
    });
  }

  /* =========================================================
     THE LOOPING MICRO-DEMO CARD
     Heard → Understood → Asking → Confirm → Rest → reset
     ~9s loop, crossfade reset. Real receipt, not a UI panel.
     ========================================================= */

  // A rotating set of real, human, messy lines so the loop feels alive.
  const SCENES = [
    {
      heard: "ugh I still need to book the dentist for Thursday",
      title: "Book dentist — Thursday afternoon",
      sub: "Dr. Lansing · 2:30 PM hold found",
      ask: "Confirm the 2:30 booking?",
      stamp: "Booked · just now",
    },
    {
      heard: "holding off on that big invoice for now, it can wait",
      title: "Pause the Q3 invoice to Brightline",
      sub: "$8,400 · draft kept, not sent",
      ask: "Hold the invoice until you say go?",
      stamp: "Held · just now",
    },
    {
      heard: "remind me to actually call mom back this weekend",
      title: "Call Mom — Saturday morning",
      sub: "Reminder set · 10:00 AM",
      ask: "Set the Saturday reminder?",
      stamp: "Set · just now",
    },
  ];

  function buildCardMarkup() {
    return [
      '<div class="demo-card" data-card>',
      '  <p class="demo-heard" data-heard>',
      '    <span class="heard-dot" data-heard-dot></span>',
      '    <span class="heard-text" data-heard-text></span>',
      "  </p>",
      '  <div class="demo-task" data-task>',
      '    <p class="demo-task-title" data-task-title></p>',
      '    <p class="demo-task-sub" data-task-sub></p>',
      "  </div>",
      '  <div class="demo-divider" data-divider></div>',
      '  <div class="demo-ask" data-ask>',
      '    <p class="demo-ask-q" data-ask-q></p>',
      '    <button class="demo-confirm" data-confirm type="button" tabindex="-1" aria-hidden="true">',
      '      <svg class="confirm-check" viewBox="0 0 16 16" aria-hidden="true"><path d="M3 8.5 L6.5 12 L13 4.5"/></svg>',
      '      <span data-confirm-label>Confirm</span>',
      "    </button>",
      "  </div>",
      '  <p class="demo-stamp" data-stamp></p>',
      "</div>",
    ].join("\n");
  }

  function typeText(el, text, done) {
    el.textContent = "";
    let i = 0;
    const speed = 34; // ms per char — soft, unhurried
    function tick() {
      if (i <= text.length) {
        el.textContent = text.slice(0, i);
        i++;
        window.setTimeout(tick, speed);
      } else if (done) {
        done();
      }
    }
    tick();
  }

  function runDemo(mount) {
    mount.innerHTML = buildCardMarkup();

    const card = mount.querySelector("[data-card]");
    const heard = mount.querySelector("[data-heard]");
    const heardDot = mount.querySelector("[data-heard-dot]");
    const heardText = mount.querySelector("[data-heard-text]");
    const task = mount.querySelector("[data-task]");
    const taskTitle = mount.querySelector("[data-task-title]");
    const taskSub = mount.querySelector("[data-task-sub]");
    const divider = mount.querySelector("[data-divider]");
    const ask = mount.querySelector("[data-ask]");
    const askQ = mount.querySelector("[data-ask-q]");
    const confirm = mount.querySelector("[data-confirm]");
    const confirmLabel = mount.querySelector("[data-confirm-label]");
    const stamp = mount.querySelector("[data-stamp]");

    let sceneIndex = 0;
    const timers = [];
    const after = (ms, fn) => timers.push(window.setTimeout(fn, ms));
    const clearAll = () => {
      timers.forEach(clearTimeout);
      timers.length = 0;
    };

    function resetVisual() {
      heard.classList.remove("is-dim", "typing-done");
      heardDot.classList.remove("is-pulse");
      heardText.textContent = "";
      task.classList.remove("is-show");
      taskTitle.textContent = "";
      taskSub.textContent = "";
      divider.classList.remove("is-draw");
      ask.classList.remove("is-show");
      askQ.textContent = "";
      confirm.classList.remove("is-done");
      confirmLabel.textContent = "Confirm";
      stamp.classList.remove("is-show");
      stamp.textContent = "";
      card.classList.remove("is-settle", "is-rest");
    }

    function playScene() {
      const s = SCENES[sceneIndex];
      resetVisual();

      // 1. HEARD (0–2s): type the messy line, pulse the gold dot
      after(150, () => {
        typeText(heardText, s.heard, () => {
          heard.classList.add("typing-done");
          heardDot.classList.add("is-pulse");
        });
      });

      // 2. UNDERSTOOD (~2.2s): dim the speech, resolve the clean task
      after(2300, () => {
        heard.classList.add("is-dim");
        taskTitle.textContent = s.title;
        taskSub.textContent = s.sub;
        task.classList.add("is-show");
      });

      // 3. ASKING (~4.2s): draw divider, show the question + gold pill
      after(4200, () => {
        divider.classList.add("is-draw");
      });
      after(4500, () => {
        askQ.textContent = s.ask;
        ask.classList.add("is-show");
      });

      // 4. CONFIRM (~6.4s): pill fills, check draws, label → Done, settle
      after(6400, () => {
        confirm.classList.add("is-done");
        confirmLabel.textContent = "Done";
        card.classList.add("is-settle");
      });
      after(6900, () => {
        card.classList.remove("is-settle");
        stamp.textContent = s.stamp;
        stamp.classList.add("is-show");
      });

      // 5. REST (~7.5s): soft fade to 92%, then crossfade reset
      after(7600, () => {
        card.classList.add("is-rest");
      });
      after(8600, () => {
        card.classList.remove("is-rest");
        sceneIndex = (sceneIndex + 1) % SCENES.length;
        playScene();
      });
    }

    if (prefersReduced) {
      // Static, finished state — no motion, still tells the story
      const s = SCENES[0];
      heardText.textContent = s.heard;
      heard.classList.add("typing-done", "is-dim");
      heardDot.classList.add("is-pulse");
      taskTitle.textContent = s.title;
      taskSub.textContent = s.sub;
      task.classList.add("is-show");
      divider.classList.add("is-draw");
      askQ.textContent = s.ask;
      ask.classList.add("is-show");
      confirm.classList.add("is-done");
      confirmLabel.textContent = "Done";
      stamp.textContent = s.stamp;
      stamp.classList.add("is-show");
      return;
    }

    playScene();

    // Pause the loop when the card is fully off-screen, resume on return.
    if ("IntersectionObserver" in window) {
      let running = true;
      const vis = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting && !running) {
              running = true;
              sceneIndex = 0;
              playScene();
            } else if (!entry.isIntersecting && running) {
              running = false;
              clearAll();
            }
          });
        },
        { threshold: 0 }
      );
      vis.observe(card);
    }
  }

  /* ---------- Place the demo card (hero on desktop, own band on mobile) ---------- */
  function initDemo() {
    let mount = document.querySelector("[data-demo-mount]");

    // On narrow screens, create a dedicated band before the footer CTA.
    const narrow = window.matchMedia("(max-width: 920px)");

    function place() {
      const heroMount = document.querySelector(".hero-presence [data-demo-mount]");
      let band = document.querySelector(".demo-band");

      if (narrow.matches) {
        if (!band) {
          band = document.createElement("section");
          band.className = "demo-band";
          band.setAttribute("aria-label", "A glimpse of Anticipy at work");
          const bandMount = document.createElement("div");
          bandMount.className = "demo-mount";
          bandMount.setAttribute("data-demo-mount-mobile", "");
          band.appendChild(bandMount);
          const footerCta = document.getElementById("footer-cta");
          footerCta.parentNode.insertBefore(band, footerCta);
          runDemo(bandMount);
        }
      }
      // Always run the hero-mounted card (hidden via CSS on narrow, but cheap).
      if (heroMount && !heroMount.dataset.ran) {
        heroMount.dataset.ran = "1";
        runDemo(heroMount);
      }
    }

    place();
  }

  /* ---------- Quiet placeholder links ----------
     Links whose destination isn't wired yet point at "#". Left alone they
     yank the page to the top — a cheap, jarring tell. Until they're real,
     swallow the jump so the page stays composed. */
  function initQuietLinks() {
    document.querySelectorAll('a[href="#"]').forEach((a) => {
      a.addEventListener("click", (e) => e.preventDefault());
    });
  }

  /* ---------- Boot ---------- */
  function boot() {
    initReveal();
    initDial();
    initForm();
    initDemo();
    initQuietLinks();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
