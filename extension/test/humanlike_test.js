// Isolated unit test for extension/humanlike.js — the Bezier + Gaussian motion port.
// Pure math, no Chrome / DOM, so it runs headlessly: `node humanlike_test.js`.
// Proves the ported motion has the shape cdpClick/cdpType rely on.
const assert = require("assert");
const { bezierPath, gaussianDelay, typingInterCharDelays } = require("../humanlike.js");

// 1) bezierPath returns nPoints+1 points, starts at the source, ends at the target, and each
//    point carries a delay clamped to the humanlike [5,50]ms window.
{
  const N = 30;
  const path = bezierPath(100, 200, 640, 480, N, 0.10);
  assert.strictEqual(path.length, N + 1, "path should have nPoints+1 samples");
  // endpoints (allow small jitter, which is normal(0,0.5) -> a few px at most)
  assert.ok(Math.abs(path[0].x - 100) < 6 && Math.abs(path[0].y - 200) < 6, "path starts at source");
  assert.ok(Math.abs(path[N].x - 640) < 6 && Math.abs(path[N].y - 480) < 6, "path ends at target");
  for (const pt of path) {
    assert.ok(Number.isFinite(pt.x) && Number.isFinite(pt.y), "coords finite");
    assert.ok(pt.delayMs >= 5.0 && pt.delayMs <= 50.0, "per-point delay clamped to [5,50]");
  }
  // the curve should bow off the straight line (control points offset perpendicular)
  let maxDev = 0;
  const dx = 640 - 100, dy = 480 - 200, len = Math.hypot(dx, dy);
  for (const pt of path) {
    const dev = Math.abs((pt.x - 100) * dy - (pt.y - 200) * dx) / len; // perpendicular distance
    if (dev > maxDev) maxDev = dev;
  }
  assert.ok(maxDev > 2, "path should arc, not teleport straight (maxDev=" + maxDev.toFixed(1) + ")");
}

// 2) zero-length move (click where the cursor already is) stays put and never NaNs.
{
  const path = bezierPath(300, 300, 300, 300, 30, 0.10);
  for (const pt of path) assert.ok(Number.isFinite(pt.x) && Number.isFinite(pt.y), "no NaN on zero move");
}

// 3) gaussianDelay always respects its clamp bounds across many samples.
{
  for (let i = 0; i < 5000; i++) {
    const d = gaussianDelay(80, 30, 30, 200);
    assert.ok(d >= 30 && d <= 200, "gaussianDelay within clamp");
  }
}

// 4) typingInterCharDelays returns one delay per char; every delay is a positive, bounded number.
{
  const text = "tomsmith@example.com the quick brown fox";
  const delays = typingInterCharDelays(text);
  assert.strictEqual(delays.length, text.length, "one delay per character");
  for (const d of delays) assert.ok(d >= 30 && d <= 1500, "char delay within [30,1500]ms");
  assert.strictEqual(typingInterCharDelays("").length, 0, "empty text -> no delays");
}

console.log("PASS humanlike: bezier shape + clamped gaussian + per-char typing delays");
