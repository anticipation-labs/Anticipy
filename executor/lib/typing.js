// Realistic human typing cadence + Bezier mouse curves. Per the
// v-final-prototype master prompt: μ=180ms σ=60ms inter-keystroke
// interval. This pattern is what makes the executor look like the user
// rather than an automation tool to bot-detection systems (DataDome,
// Cloudflare BotProtect).

// Gaussian sample via Box-Muller. Returns a finite number ≥ 0.
function gaussian(meanMs, stdMs) {
  // Two uniforms in (0,1)
  const u1 = Math.max(Number.MIN_VALUE, Math.random());
  const u2 = Math.random();
  const z = Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2);
  const v = meanMs + stdMs * z;
  return Math.max(0, v);
}

const DEFAULTS = Object.freeze({
  meanMs: 180,
  stdMs: 60,
  burstChance: 0.05,         // 5% chance of typing a 2-char burst with ~30ms gap
  pauseChance: 0.04,         // 4% chance of a longer pause (thinking)
  pauseMeanMs: 600,
  pauseStdMs: 200,
});

// Async generator yielding `{ char, delayBeforeMs }` for each input char.
async function* typingPlan(text, opts = {}) {
  const cfg = { ...DEFAULTS, ...opts };
  let lastIsBurst = false;
  for (let i = 0; i < text.length; i++) {
    let delay;
    if (lastIsBurst) {
      // Tail of a burst — short delay
      delay = gaussian(30, 10);
      lastIsBurst = false;
    } else if (Math.random() < cfg.pauseChance && i > 4) {
      delay = gaussian(cfg.pauseMeanMs, cfg.pauseStdMs);
    } else if (Math.random() < cfg.burstChance && i + 1 < text.length) {
      delay = gaussian(cfg.meanMs, cfg.stdMs);
      lastIsBurst = true;
    } else {
      delay = gaussian(cfg.meanMs, cfg.stdMs);
    }
    yield { char: text[i], delayBeforeMs: delay };
  }
}

// Send characters via CDP Input.dispatchKeyEvent at human pace.
async function typeIntoTab(cdp, tab, text, opts = {}) {
  const send = await cdp.attach(tab);
  for await (const { char, delayBeforeMs } of typingPlan(text, opts)) {
    await new Promise((r) => setTimeout(r, delayBeforeMs));
    // Two-step send: keyDown then keyUp to mirror real typing.
    await send('Input.dispatchKeyEvent', {
      type: 'keyDown',
      text: char,
      key: char,
      unmodifiedText: char,
    });
    await send('Input.dispatchKeyEvent', {
      type: 'keyUp',
      key: char,
    });
  }
}

// Bezier-curve mouse movement helper — used for hover/click on canvas
// areas where the agent wants to look more human than a snap-click.
function bezierPath(x0, y0, x1, y1, { points = 24, jitter = 4 } = {}) {
  // 2 random control points biased toward the line, with small jitter.
  const cx1 = x0 + (x1 - x0) * 0.33 + (Math.random() - 0.5) * jitter * 4;
  const cy1 = y0 + (y1 - y0) * 0.33 + (Math.random() - 0.5) * jitter * 4;
  const cx2 = x0 + (x1 - x0) * 0.66 + (Math.random() - 0.5) * jitter * 4;
  const cy2 = y0 + (y1 - y0) * 0.66 + (Math.random() - 0.5) * jitter * 4;
  const out = [];
  for (let i = 0; i <= points; i++) {
    const t = i / points;
    const u = 1 - t;
    const x = u * u * u * x0 + 3 * u * u * t * cx1 + 3 * u * t * t * cx2 + t * t * t * x1;
    const y = u * u * u * y0 + 3 * u * u * t * cy1 + 3 * u * t * t * cy2 + t * t * t * y1;
    out.push([x + (Math.random() - 0.5) * jitter, y + (Math.random() - 0.5) * jitter]);
  }
  return out;
}

async function moveAndClick(cdp, tab, fromX, fromY, toX, toY, { points = 24 } = {}) {
  const send = await cdp.attach(tab);
  const path = bezierPath(fromX, fromY, toX, toY, { points });
  for (const [x, y] of path) {
    await send('Input.dispatchMouseEvent', {
      type: 'mouseMoved', x, y, button: 'none',
    });
    await new Promise((r) => setTimeout(r, gaussian(15, 5)));
  }
  await send('Input.dispatchMouseEvent', { type: 'mousePressed', x: toX, y: toY, button: 'left', clickCount: 1 });
  await new Promise((r) => setTimeout(r, gaussian(60, 20)));
  await send('Input.dispatchMouseEvent', { type: 'mouseReleased', x: toX, y: toY, button: 'left', clickCount: 1 });
}

module.exports = { gaussian, typingPlan, typeIntoTab, bezierPath, moveAndClick, DEFAULTS };
