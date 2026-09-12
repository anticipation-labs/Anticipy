// A TRUSTED CLICK INTO AN EMBEDDED WIDGET LANDS WHERE THE WIDGET IS NOW.
//
// Two defects, both measured in real Chrome on 2026-09-12 with the shipped
// loop and a synthetic page (scratchpad reproduction, then this pin):
//
//   1. elementCenter added the iframe's MAP-TIME viewport position to a
//      CLICK-TIME in-frame centre. __anticipyCenter scrolls the control into
//      view, and Chrome propagates that scroll to the parent document, so the
//      recorded position was stale by exactly the parent's scroll delta. The
//      click was dispatched at y=1654 in a 700px viewport while the button
//      was live at y 326-375; the widget received nothing; the run said done.
//   2. A widget inside a src-less wrapper frame (srcdoc/about:blank shells
//      that consent managers and some payment embeds build) was given
//      `frameOffsets[parent] || {x:0,y:0}` — a confidently WRONG offset, its
//      rect inside the wrapper treated as top-page coordinates — instead of
//      an unknown one.
//
// The repair keeps a per-frame chain {parent, src} at map time and re-measures
// every hop's <iframe> box AFTER the in-frame centre call, child to parent to
// the top page. Any hop it cannot measure makes the answer inFrameOnly, never
// a partial sum. This suite drives the exported elementCenter through the real
// readFrames (via readPageForRecovery) with a scripted chrome.scripting that
// answers per frame, so the arithmetic is the module's own.
//
// Run: node extension/tests/test_subframe_click_geometry.mjs
import { installChrome } from "./chrome_mock.mjs";
const harness = installChrome();
const { elementCenter, readPageForRecovery } = await import("../agent_loop.js");

let failures = 0;
const check = (name, ok, detail = "") => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}${ok || !detail ? "" : "\n     " + detail}`);
  if (!ok) failures++;
};

const WIDGET = "https://widget.fixture.invalid/book";
const WRAPPER = "https://wrapper.fixture.invalid/shell";
const TAB = 7;

// The page, as readFrame would report it per frame, and the iframe boxes as
// they are RIGHT NOW (mutable, so a test can scroll the parent between the
// map and the click the way __anticipyCenter does in real Chrome).
function scripted(world) {
  const centers = [];
  chrome.scripting.executeScript = async ({ target, func, args = [] }) => {
    const src = String(func);
    const frameIds = target.allFrames
      ? Object.keys(world.frames).map(Number)
      : target.frameIds ? target.frameIds : [0];
    // readFrame: every frame answers with its own map and its own iframes.
    if (src.includes("__anticipyMapPage")) {
      return frameIds.map((frameId) => {
        const f = world.frames[frameId];
        return { frameId, result: { url: f.url, title: "", w: f.w ?? 1000, h: f.h ?? 700,
          elements: f.elements || "", text: "", fields: [], sugg: { lists: [] },
          iframes: (f.iframes || []).map((i) => ({ src: i.src, ...i.box() })), frames: [], widgets: [] } };
      });
    }
    // __anticipyCenter inside the frame the index resolves to: the control's
    // in-frame centre, and the SCROLL it causes in the parent.
    if (src.includes("__anticipyCenter")) {
      const frameId = frameIds[0];
      const f = world.frames[frameId];
      if (f.onCenter) f.onCenter();
      centers.push(frameId);
      return [{ frameId, result: f.center }];
    }
    // The fresh iframe box read: `(wanted) => ... querySelectorAll("iframe")`.
    if (src.includes('querySelectorAll("iframe")') && args.length === 1) {
      const frameId = frameIds[0];
      const f = world.frames[frameId];
      const matching = (f.iframes || []).filter((i) => i.src === args[0]);
      if (matching.length !== 1) return [{ frameId, result: null }];
      const b = matching[0].box();
      return [{ frameId, result: { x: b.x, y: b.y } }];
    }
    return [{ frameId: frameIds[0], result: null }];
  };
  return centers;
}

// --- 1. Document scroll between map and click ------------------------------
{
  let parentScrollY = 0;
  const world = { frames: {
    0: { url: "https://site.fixture.invalid/scroll", elements: "[0] <a> Menu @(10,10)",
         iframes: [{ src: WIDGET, box: () => ({ x: 24, y: 1512 - parentScrollY, w: 600, h: 400 }) }] },
    1: { url: WIDGET, elements: "[0] <button> Reveal slots @(94,142)",
         // Centring the control scrolls the PARENT by 1305 — what real Chrome
         // did in the measured run — then reports the in-frame centre.
         onCenter: () => { parentScrollY = 1305; }, center: { x: 94, y: 142 } },
  } };
  const centers = scripted(world);
  const map = await readPageForRecovery(TAB);
  check("scroll: the widget's controls are on the map under the embedded-widget slot",
        /EMBEDDED WIDGET/.test(map.elements) && /\[1000\]/.test(map.elements), map.elements);
  const c = await elementCenter(TAB, 1000);
  check("scroll: the in-frame centre was read (and it scrolled the parent)", centers.length === 1 && parentScrollY === 1305);
  check("scroll: the click point is the fresh sum, not the map-time one",
        c && !c.inFrameOnly && c.x === 24 + 94 && c.y === (1512 - 1305) + 142,
        `got ${JSON.stringify(c)}; stale sum would be (118,1654), fresh is (118,349)`);
}

// --- 2. A src-less wrapper between the page and the widget ------------------
{
  const world = { frames: {
    0: { url: "https://site.fixture.invalid/nested", elements: "[0] <a> Menu @(10,10)",
         // The wrapper is srcdoc: the top page reports an iframe with NO src.
         iframes: [{ src: "", box: () => ({ x: 250, y: 120, w: 900, h: 520 }) }] },
    1: { url: "about:srcdoc", elements: "[0] <div> wrapper chrome @(0,0)",
         iframes: [{ src: WIDGET, box: () => ({ x: 200, y: 150, w: 600, h: 300 }) }] },
    2: { url: WIDGET, elements: "[0] <button> Reveal slots @(94,142)", center: { x: 94, y: 142 } },
  } };
  scripted(world);
  const map = await readPageForRecovery(TAB);
  const idx = Number((map.elements.match(/\[(\d+)\] <button> Reveal slots/) || [])[1]);
  check("nested: the widget button is on the map", Number.isInteger(idx) && idx >= 1000, map.elements);
  const c = await elementCenter(TAB, idx);
  check("nested: an unmatched ancestor makes the point UNKNOWN, never (0,0)+rect",
        c && c.inFrameOnly === true && c.x === 94 && c.y === 142,
        `got ${JSON.stringify(c)}; the old code answered (294,292) — the wrapper's inner rect as if top-page`);
}

// --- 3. The same wrapper, but resolvable: the chain sums every hop fresh ---
{
  let parentScrollY = 0;
  const world = { frames: {
    0: { url: "https://site.fixture.invalid/nested-src", elements: "[0] <a> Menu @(10,10)",
         iframes: [{ src: WRAPPER, box: () => ({ x: 250, y: 120 - parentScrollY, w: 900, h: 520 }) }] },
    1: { url: WRAPPER, elements: "[0] <div> wrapper chrome @(0,0)",
         iframes: [{ src: WIDGET, box: () => ({ x: 200, y: 150, w: 600, h: 300 }) }] },
    2: { url: WIDGET, elements: "[0] <button> Reveal slots @(94,142)",
         onCenter: () => { parentScrollY = 100; }, center: { x: 94, y: 142 } },
  } };
  scripted(world);
  const map = await readPageForRecovery(TAB);
  const idx = Number((map.elements.match(/\[(\d+)\] <button> Reveal slots/) || [])[1]);
  const c = await elementCenter(TAB, idx);
  check("two hops: every iframe box is re-measured after the centre call",
        c && !c.inFrameOnly && c.x === 250 + 200 + 94 && c.y === (120 - 100) + 150 + 142,
        `got ${JSON.stringify(c)}; expected (544,312)`);
}

// --- 4. A hop that cannot be measured at click time -> inFrameOnly ----------
{
  let gone = false;
  const world = { frames: {
    0: { url: "https://site.fixture.invalid/torn", elements: "[0] <a> Menu @(10,10)",
         iframes: [{ src: WIDGET, box: () => ({ x: 24, y: 300, w: 600, h: 400 }) }] },
    1: { url: WIDGET, elements: "[0] <button> Reveal slots @(94,142)", center: { x: 94, y: 142 } },
  } };
  scripted(world);
  await readPageForRecovery(TAB);
  // Between the map and the click the page replaced the widget with a second
  // copy: two iframes now match the src, and "exactly one" is the rule.
  world.frames[0].iframes.push({ src: WIDGET, box: () => ({ x: 24, y: 900, w: 600, h: 400 }) });
  gone = true;
  const c = await elementCenter(TAB, 1000);
  check("ambiguous hop: two frames with the widget's src -> no coordinate, in-frame path",
        gone && c && c.inFrameOnly === true, `got ${JSON.stringify(c)}`);
}

// --- 5. What __anticipyCenter says about the point survives the frame walk --
{
  const world = { frames: {
    0: { url: "https://site.fixture.invalid/covered", elements: "[0] <a> Menu @(10,10)",
         iframes: [{ src: WIDGET, box: () => ({ x: 24, y: 300, w: 600, h: 400 }) }] },
    1: { url: WIDGET, elements: "[0] <button> Reveal slots @(94,142)",
         center: { x: 94, y: 142, coveredBy: "div#interstitial" } },
  } };
  scripted(world);
  await readPageForRecovery(TAB);
  const c = await elementCenter(TAB, 1000);
  check("a covered point inside a frame is still reported covered on the way out",
        c && c.coveredBy === "div#interstitial" && c.x === 118 && c.y === 442, `got ${JSON.stringify(c)}`);
}

// --- 7. A wrapper with NO controls of its own still links the chain ---------
// Measured in real Chrome (proof/audit/check_browser_frame_clicks.mjs,
// "two-hop", 2026-09-12): a shell frame holding nothing but the next iframe
// is not a mapped subframe (nothing to map), and the chain used to be written
// only for mapped subframes — so the widget inside it never reached the top
// page and every click took the in-frame path.
{
  const world = { frames: {
    0: { url: "https://site.fixture.invalid/two-hop", elements: "[0] <a> Menu @(10,10)",
         iframes: [{ src: WRAPPER, box: () => ({ x: 24, y: 300, w: 900, h: 520 }) }] },
    1: { url: WRAPPER, elements: "",   // the shell: no controls at all
         iframes: [{ src: WIDGET, box: () => ({ x: 200, y: 150, w: 600, h: 300 }) }] },
    2: { url: WIDGET, elements: "[0] <button> Reveal slots @(94,142)", center: { x: 94, y: 142 } },
  } };
  scripted(world);
  const map = await readPageForRecovery(TAB);
  const idx = Number((map.elements.match(/\[(\d+)\] <button> Reveal slots/) || [])[1]);
  check("empty shell: the widget button is still on the map", Number.isInteger(idx) && idx >= 1000, map.elements);
  const c = await elementCenter(TAB, idx);
  check("empty shell: the chain runs through a wrapper that mapped no controls",
        c && !c.inFrameOnly && c.x === 24 + 200 + 94 && c.y === 300 + 150 + 142,
        `got ${JSON.stringify(c)}; expected (318,592) — inFrameOnly means the shell hop was never recorded`);
}

// --- 8. Frame ids say nothing about depth: a child numbered below its parent -
{
  const world = { frames: {
    0: { url: "https://site.fixture.invalid/two-hop-ids", elements: "[0] <a> Menu @(10,10)",
         iframes: [{ src: WRAPPER, box: () => ({ x: 24, y: 300, w: 900, h: 520 }) }] },
    // The widget answered FIRST (lower id); its parent shell answered after.
    3: { url: WIDGET, elements: "[0] <button> Reveal slots @(94,142)", center: { x: 94, y: 142 } },
    9: { url: WRAPPER, elements: "", iframes: [{ src: WIDGET, box: () => ({ x: 200, y: 150, w: 600, h: 300 }) }] },
  } };
  scripted(world);
  const map = await readPageForRecovery(TAB);
  const idx = Number((map.elements.match(/\[(\d+)\] <button> Reveal slots/) || [])[1]);
  const c = await elementCenter(TAB, idx);
  check("out-of-order ids: the chain is resolved to a fixpoint, not in id order",
        c && !c.inFrameOnly && c.x === 318 && c.y === 592, `got ${JSON.stringify(c)}`);
}

// --- 6. The main frame is untouched by any of this --------------------------
{
  const world = { frames: { 0: { url: "https://site.fixture.invalid/plain", elements: "[0] <button> Go @(10,10)",
                                 center: { x: 40, y: 50 } } } };
  scripted(world);
  await readPageForRecovery(TAB);
  const c = await elementCenter(TAB, 0);
  check("main frame: the centre passes through unchanged", c && c.x === 40 && c.y === 50 && !c.inFrameOnly);
}

console.log(`\nsubframe click geometry: ${failures ? failures + " FAILED" : "all passed"}`);
process.exit(failures ? 1 : 0);
