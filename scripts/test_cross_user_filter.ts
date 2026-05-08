/**
 * Tests the extension's intentBelongsToUs() filter logic in isolation.
 * Replicates the predicate exactly so we can verify it correctly drops
 * cross-user broadcasts even when the IDs are subtly close.
 *
 * The actual function lives in extension/background.js and depends on
 * chrome.storage.local — we replicate its exact comparison here.
 */

interface ApiConfig {
  userId?: string | null;
}

interface BroadcastIntent {
  user_id?: string | null;
  id?: string;
}

// Lift the predicate from extension/background.js verbatim:
function intentBelongsToUs(intent: BroadcastIntent | null, apiConfig: ApiConfig | null): boolean {
  if (!intent || typeof intent !== "object") return false;
  const incomingUserId = intent.user_id;
  if (!incomingUserId) return false;
  const ourUserId = apiConfig?.userId;
  if (!ourUserId) return false;
  return incomingUserId === ourUserId;
}

interface Case {
  name: string;
  intent: BroadcastIntent | null;
  apiConfig: ApiConfig | null;
  expect: boolean;
}

const CASES: Case[] = [
  {
    name: "happy: same user matches",
    intent: { user_id: "user-A", id: "i1" },
    apiConfig: { userId: "user-A" },
    expect: true,
  },
  {
    name: "different user dropped",
    intent: { user_id: "user-B", id: "i1" },
    apiConfig: { userId: "user-A" },
    expect: false,
  },
  {
    name: "missing user_id on incoming dropped",
    intent: { id: "i1" } as BroadcastIntent,
    apiConfig: { userId: "user-A" },
    expect: false,
  },
  {
    name: "null user_id on incoming dropped",
    intent: { user_id: null, id: "i1" },
    apiConfig: { userId: "user-A" },
    expect: false,
  },
  {
    name: "empty string user_id dropped",
    intent: { user_id: "", id: "i1" },
    apiConfig: { userId: "user-A" },
    expect: false,
  },
  {
    name: "no apiConfig dropped (anon extension)",
    intent: { user_id: "user-A", id: "i1" },
    apiConfig: null,
    expect: false,
  },
  {
    name: "apiConfig with no userId dropped (legacy install)",
    intent: { user_id: "user-A", id: "i1" },
    apiConfig: { userId: null },
    expect: false,
  },
  {
    name: "intent null dropped",
    intent: null,
    apiConfig: { userId: "user-A" },
    expect: false,
  },
  {
    name: "near-match prefix collision dropped",
    intent: { user_id: "user-A-evil-suffix", id: "i1" },
    apiConfig: { userId: "user-A" },
    expect: false,
  },
  {
    name: "near-match suffix collision dropped",
    intent: { user_id: "evil-prefix-user-A", id: "i1" },
    apiConfig: { userId: "user-A" },
    expect: false,
  },
  {
    name: "exact UUID match passes",
    intent: { user_id: "84c4e876-caf3-44ee-89f0-137c50455a2a", id: "i1" },
    apiConfig: { userId: "84c4e876-caf3-44ee-89f0-137c50455a2a" },
    expect: true,
  },
  {
    name: "single-char-different UUID dropped",
    intent: { user_id: "84c4e876-caf3-44ee-89f0-137c50455a2b", id: "i1" },
    apiConfig: { userId: "84c4e876-caf3-44ee-89f0-137c50455a2a" },
    expect: false,
  },
  {
    name: "type confusion: number user_id dropped",
    intent: { user_id: 12345 as unknown as string, id: "i1" },
    apiConfig: { userId: "12345" },
    expect: false, // strict equality between number and string fails — good
  },
  {
    name: "case-sensitive: different case dropped",
    intent: { user_id: "USER-A", id: "i1" },
    apiConfig: { userId: "user-A" },
    expect: false,
  },
];

let pass = 0;
let fail = 0;
for (const c of CASES) {
  const got = intentBelongsToUs(c.intent, c.apiConfig);
  if (got === c.expect) {
    console.log(`  ✓ ${c.name}`);
    pass += 1;
  } else {
    console.log(`  ✗ ${c.name}: expected ${c.expect} got ${got}`);
    fail += 1;
  }
}
console.log(`\n${pass}/${pass + fail} passed`);
process.exit(fail > 0 ? 1 : 0);
