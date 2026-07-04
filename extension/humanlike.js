// Anticipy humanlike motion + timing — JS port of DEV-FINAL
// engine/app/action_engine/humanlike.py (Bezier mouse curves + Gaussian-sampled
// inter-event delays). Makes CDP Input.dispatch* human-timed instead of teleported,
// which neutralizes the #1 remaining bot tell (robotic timing) per final/browser/PLAN.md §4.
//
// Dual-loaded, exactly like engine_client.js:
//   - MV3 service worker: `importScripts("humanlike.js")` exposes these as globals.
//   - Node test harness: `require("./humanlike.js")` reads module.exports.
// Pure math only (no chrome.*, no DOM), so it is unit-testable headlessly.

// Standard-normal sampler via Box-Muller (cached spare). Mean 0, std 1.
let _gaussSpare = null;
function _stdNormal() {
  if (_gaussSpare !== null) { const s = _gaussSpare; _gaussSpare = null; return s; }
  let u = 0, v = 0;
  while (u === 0) u = Math.random();
  while (v === 0) v = Math.random();
  const mag = Math.sqrt(-2.0 * Math.log(u));
  _gaussSpare = mag * Math.sin(2.0 * Math.PI * v);
  return mag * Math.cos(2.0 * Math.PI * v);
}
function _normal(mean, std) { return mean + std * _stdNormal(); }
function _clamp(v, lo, hi) { return v < lo ? lo : (v > hi ? hi : v); }

// Sample one inter-event delay (ms): Gaussian, clamped. Mirrors humanlike.gaussian_delay.
function gaussianDelay(mean, std, clampMin, clampMax) {
  return _clamp(_normal(mean, std), clampMin, clampMax);
}

// Cubic Bezier from (x0,y0)->(x1,y1) with two control points offset perpendicular to the
// path by ~curvature*length (random arc sign), small per-point jitter, and Gaussian per-point
// delays (15ms mean, 5ms std, clamped [5,50]). Mirrors humanlike.bezier_path.
// Returns nPoints+1 points: [{ x, y, delayMs }] — delayMs is the wait BEFORE dispatching that point.
function bezierPath(x0, y0, x1, y1, nPoints, curvature) {
  nPoints = (nPoints == null) ? 30 : nPoints;
  curvature = (curvature == null) ? 0.10 : curvature;
  const dx = x1 - x0, dy = y1 - y0;
  const length = Math.max(1.0, Math.hypot(dx, dy));
  const perpX = -dy / length, perpY = dx / length;
  const sign = Math.random() < 0.5 ? 1.0 : -1.0;
  const offset = curvature * length;
  const r = () => 0.7 + Math.random() * 0.6; // uniform(0.7, 1.3)
  const cx1 = x0 + dx * 0.33 + sign * perpX * offset * r();
  const cy1 = y0 + dy * 0.33 + sign * perpY * offset * r();
  const cx2 = x0 + dx * 0.66 + sign * perpX * offset * r();
  const cy2 = y0 + dy * 0.66 + sign * perpY * offset * r();
  const out = [];
  for (let i = 0; i <= nPoints; i++) {
    const t = i / nPoints, u = 1.0 - t;
    let bx = u * u * u * x0 + 3 * u * u * t * cx1 + 3 * u * t * t * cx2 + t * t * t * x1;
    let by = u * u * u * y0 + 3 * u * u * t * cy1 + 3 * u * t * t * cy2 + t * t * t * y1;
    bx += _normal(0, 0.5);
    by += _normal(0, 0.5);
    out.push({ x: bx, y: by, delayMs: gaussianDelay(15.0, 5.0, 5.0, 50.0) });
  }
  return out;
}

// One delay (ms) per character, with occasional "thinking" pauses. Mirrors
// humanlike.typing_inter_char_delays: normal(90,40) clamp[30,250], and after the 5th char a
// 4% chance of a longer pause normal(600,200) clamp[200,1500]. Returns len(text) floats.
function typingInterCharDelays(text) {
  const delays = [];
  for (let i = 0; i < text.length; i++) {
    let d;
    if (i > 4 && Math.random() < 0.04) d = _clamp(_normal(600.0, 200.0), 200.0, 1500.0);
    else d = gaussianDelay(90.0, 40.0, 30.0, 250.0);
    delays.push(d);
  }
  return delays;
}

// Node test harness imports this; the service worker reads it as a global (importScripts).
if (typeof module !== "undefined" && module.exports) {
  module.exports = { bezierPath, gaussianDelay, typingInterCharDelays };
}
