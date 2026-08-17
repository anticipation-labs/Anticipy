// /auth/claim adopts pre-accounts rows onto a new account. The uuid it adopts
// them on has to be the one recorded on THAT account at sign-up.
//
// It was not. The hook read legacy_uuid straight from the request body and
// never once looked at auth.legacy_uuid, so the evidence its own header
// comment described was never checked. And the uuid is not a secret: it is
// agents.owner, which guard.pb.js's anonymous pair-code lookup returns in
// full. Read it off a stranger's pair code, sign up a throwaway account, post
// it here, and their owner_profile row — name, email, phone, birthday, facts —
// moved to the throwaway. Then sms.pb.js, which resolves an inbound number
// through owner_profile before owners, started filing that person's "yes, go
// ahead" texts under the stranger.
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const src = readFileSync(
  join(here, "..", "..", "backend", "pb_hooks", "claim_legacy.pb.js"), "utf8");

let failures = 0;
const check = (name, ok) => {
  console.log(`${ok ? "PASS" : "FAIL"}: ${name}`);
  if (!ok) failures++;
};

let handler = null;
{
  const globals = { routerAdd: (method, path, fn) => {
    if (method === "POST" && path === "/auth/claim") handler = fn;
  } };
  const names = Object.keys(globals);
  new Function(...names, src)(...names.map((n) => globals[n]));
}
check("the claim route is registered", typeof handler === "function");

const VICTIM_UUID = "3F8A1C22-VICTIM-PHONE-UUID";

// One call through the real hook against a fake instance holding the victim's
// unclaimed legacy rows plus two accounts (so the events branch, which needs a
// single-account instance, stays out of the way).
function claim({ accountId, accountUUID, sentUUID }) {
  const saved = [];
  const rowsFor = (table) => {
    const owned = { jobs: 2, owner_profile: 1, segments: 3, agents: 1 }[table] || 0;
    return Array.from({ length: owned }, (_, i) => ({
      id: `${table}-${i}`,
      _table: table,
      set: (f, v) => { saved.push({ table, field: f, value: v }); },
    }));
  };
  let outcome = null;
  const e = {
    auth: {
      id: accountId,
      getString: (f) => (f === "legacy_uuid" ? accountUUID : ""),
    },
    requestInfo: () => ({ body: { legacy_uuid: sentUUID } }),
    json: (status, payload) => { outcome = { status, payload }; },
    app: {
      findRecordsByFilter: (table, filter, _sort, _limit, _offset, params) => {
        if (table === "owners") return [{ id: "acct-one" }, { id: "acct-two" }];
        if (table === "events") return [];
        // The rows only exist for the uuid that actually made them.
        if (!params || params.u !== VICTIM_UUID) return [];
        if (filter.indexOf("owner_ref = ''") < 0) return [];
        return rowsFor(table);
      },
      save: () => {},
    },
  };
  handler(e);
  return { outcome, saved };
}

// ---- the attack ----
const attacker = claim({
  accountId: "attacker_account",
  accountUUID: "AAAA-THROWAWAY-PHONE-UUID",
  sentUUID: VICTIM_UUID,
});
check("a uuid that is not the account's own is refused",
  attacker.outcome?.status === 403);
check("the refusal moves no rows at all",
  attacker.saved.length === 0);
check("the refusal names the device, not the account it failed to reach",
  /device/i.test(String(attacker.outcome?.payload?.message || "")) &&
  !String(attacker.outcome?.payload?.message || "").includes(VICTIM_UUID));

// An account that never recorded a uuid has nothing to claim ON, which is the
// same refusal and not a free pass.
const blank = claim({
  accountId: "blank_account", accountUUID: "", sentUUID: VICTIM_UUID,
});
check("an account with no recorded device cannot claim one",
  blank.outcome?.status === 403 && blank.saved.length === 0);

// ---- the real person, whose history must still come across ----
const owner = claim({
  accountId: "victim_account", accountUUID: VICTIM_UUID, sentUUID: VICTIM_UUID,
});
check("the device's own account still claims its rows",
  owner.outcome?.status === 200 && owner.outcome?.payload?.ok === true);
check("every claimed row is stamped with the caller's account id",
  owner.saved.length === 7 &&
  owner.saved.every((s) => s.field === "owner_ref" && s.value === "victim_account"));
check("all four legacy tables are carried across, agents included",
  ["jobs", "owner_profile", "segments", "agents"]
    .every((t) => owner.saved.some((s) => s.table === t)));
check("the counts returned match the rows actually moved",
  owner.outcome?.payload?.claimed?.jobs === 2 &&
  owner.outcome?.payload?.claimed?.segments === 3 &&
  owner.outcome?.payload?.claimed?.agents === 1);

// A client that sends no uuid at all (nothing to prove, nothing to claim) is
// not an attacker and must not be answered with a 403.
const silent = claim({
  accountId: "quiet_account", accountUUID: VICTIM_UUID, sentUUID: "",
});
check("a claim with no uuid is still a plain 200 with nothing claimed",
  silent.outcome?.status === 200 && silent.saved.length === 0);

if (failures) { console.error(`test_claim_legacy_binding: ${failures} failed`); process.exit(1); }
console.log("test_claim_legacy_binding: all passed");
