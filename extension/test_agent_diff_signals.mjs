// Unit test for BrowserAgent.diffSignals (extension/agent.js)
// Exercises the pure-function behavior of the page-signal diff used by the
// effect-of-action verification path. Runs in plain Node — no browser, no
// Chrome APIs touched. Run with:  node extension/test_agent_diff_signals.mjs

import { BrowserAgent } from "./agent.js";

const passes = [];
const fails = [];

function expectEqual(name, got, expected) {
  if (got === expected) {
    passes.push(name);
    console.log("✓", name);
  } else {
    fails.push(name);
    console.log("✗", name);
    console.log("  expected:", JSON.stringify(expected));
    console.log("  got:     ", JSON.stringify(got));
  }
}

function expectIncludes(name, got, ...needles) {
  const missing = needles.filter(n => !got.includes(n));
  if (missing.length === 0) {
    passes.push(name);
    console.log("✓", name);
  } else {
    fails.push(name);
    console.log("✗", name);
    console.log("  got:    ", JSON.stringify(got));
    console.log("  missing:", JSON.stringify(missing));
  }
}

const baseSignals = {
  url: "https://example.com/",
  title: "Example",
  bodyTextLen: 1000,
  topHeading: "Welcome",
  buttonCount: 5,
  inputCount: 2,
  linkCount: 30,
  formCount: 1,
  hasModal: false,
  bodyFingerprint: "abc123",
};

// 1. Identical signals → no diff
expectEqual(
  "identical signals → empty diff",
  BrowserAgent.diffSignals(baseSignals, { ...baseSignals }),
  ""
);

// 2. Null inputs → empty diff
expectEqual("null before → empty diff", BrowserAgent.diffSignals(null, baseSignals), "");
expectEqual("null after → empty diff", BrowserAgent.diffSignals(baseSignals, null), "");

// 3. URL change — the most common signal of progress
expectIncludes(
  "URL change is reported",
  BrowserAgent.diffSignals(baseSignals, { ...baseSignals, url: "https://example.com/products" }),
  "URL:", "example.com/", "example.com/products"
);

// 4. Title change
expectIncludes(
  "title change is reported",
  BrowserAgent.diffSignals(baseSignals, { ...baseSignals, title: "Products — Example" }),
  "Title:", "Example", "Products"
);

// 5. Top-heading change (content-page identity)
expectIncludes(
  "top-heading change is reported",
  BrowserAgent.diffSignals(baseSignals, { ...baseSignals, topHeading: "Search Results" }),
  "Top heading:", "Welcome", "Search Results"
);

// 6. Body content delta — significant grow
expectIncludes(
  "body grew by significant amount",
  BrowserAgent.diffSignals(baseSignals, { ...baseSignals, bodyTextLen: 5000 }),
  "Body content:", "+4000"
);

// 7. Body content delta — significant shrink (e.g., results page → 404)
expectIncludes(
  "body shrunk significantly",
  BrowserAgent.diffSignals(baseSignals, { ...baseSignals, bodyTextLen: 200 }),
  "Body content:", "-800"
);

// 8. Body delta below threshold (50 chars) → not reported as size change,
//    but if the fingerprint changed, that IS reported as SPA route.
expectEqual(
  "tiny body delta + same fingerprint → no diff",
  BrowserAgent.diffSignals(
    baseSignals,
    { ...baseSignals, bodyTextLen: 1030 }
  ),
  ""
);
expectIncludes(
  "tiny body delta + DIFFERENT fingerprint → SPA route reported",
  BrowserAgent.diffSignals(
    baseSignals,
    { ...baseSignals, bodyTextLen: 1030, bodyFingerprint: "DIFFERENT" }
  ),
  "Body content changed (SPA route or partial update)"
);

// 9. Element count deltas
expectIncludes(
  "button count delta is reported",
  BrowserAgent.diffSignals(baseSignals, { ...baseSignals, buttonCount: 8 }),
  "Elements:", "+3 buttons"
);
expectIncludes(
  "negative button delta is reported",
  BrowserAgent.diffSignals(baseSignals, { ...baseSignals, buttonCount: 2 }),
  "Elements:", "-3 buttons"
);
expectIncludes(
  "multiple element deltas",
  BrowserAgent.diffSignals(baseSignals, { ...baseSignals, buttonCount: 8, linkCount: 50, formCount: 2 }),
  "+3 buttons", "+20 links", "+1 forms"
);

// 10. Modal appeared / closed
expectIncludes(
  "modal appeared",
  BrowserAgent.diffSignals(baseSignals, { ...baseSignals, hasModal: true }),
  "modal/dialog appeared"
);
expectIncludes(
  "modal closed",
  BrowserAgent.diffSignals(
    { ...baseSignals, hasModal: true },
    baseSignals
  ),
  "Modal/dialog closed"
);

// 11. Multi-signal diff (typical post-click after a successful navigation
//     to a search results page)
const beforeClick = { ...baseSignals, url: "https://google.com/", title: "Google" };
const afterClick = {
  ...baseSignals,
  url: "https://google.com/search?q=cats",
  title: "cats - Google Search",
  bodyTextLen: 5000,
  topHeading: "cats - Wikipedia",
  buttonCount: 8,
  linkCount: 80,
  bodyFingerprint: "newpage",
};
expectIncludes(
  "multi-signal diff captures all changes",
  BrowserAgent.diffSignals(beforeClick, afterClick),
  "URL:", "Title:", "Top heading:", "Body content:", "+3 buttons", "+50 links"
);

// 12. THE KEY CASE: action ran (success:true) but page DIDN'T change.
//     diff should be empty — the loop will surface this as
//     "→ effect: NONE — page didn't visibly change" so the LLM re-strategizes.
expectEqual(
  "successful action that did nothing observable → empty diff (the silent-stall signal)",
  BrowserAgent.diffSignals(baseSignals, baseSignals),
  ""
);

// 13. Diff length stays bounded — even on huge before/after we don't blow
//     up the LLM context.
const giant = { ...baseSignals, title: "x".repeat(500), topHeading: "y".repeat(500) };
const diff = BrowserAgent.diffSignals(baseSignals, giant);
if (diff.length < 400) {
  passes.push("giant titles → diff stays bounded");
  console.log("✓ giant titles → diff stays bounded (length=" + diff.length + ")");
} else {
  fails.push("giant titles unbounded");
  console.log("✗ giant titles unbounded — length=" + diff.length);
}

console.log("\n" + passes.length + "/" + (passes.length + fails.length) + " passed");
if (fails.length) {
  process.exit(1);
}
