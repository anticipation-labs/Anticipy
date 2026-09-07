import assert from "node:assert/strict";
import { FakeD1, asD1 } from "./fake-d1.ts";
import { issueToken } from "../src/pb/auth.ts";
import { contextRequest, parseContextVerdict } from "../src/routes/context_request.ts";

const db = new FakeD1();
const env = { DB: asD1(db), ANTICIPY_AUTH_SECRET: "context-request-test" };
const stamp = new Date().toISOString().replace("T", " ");
for (const id of ["contextowner001", "contextowner002"]) {
  db.db.prepare(`INSERT INTO owners (id,created,updated,email,emailVisibility,verified,password,tokenKey,phone,legacy_uuid)
    VALUES (?,?,?,?,0,0,'',?,'','')`).run(id, stamp, stamp, id + "@example.invalid", id + "-key");
}
const token = await issueToken(env, "contextowner001", "contextowner001-key");
function event(id: string, text: string, owner = "contextowner001") {
  db.db.prepare("INSERT INTO events (id,owner_ref,device_id,kind,text,created,updated) VALUES (?,?,'context-test','transcript',?,?,?)")
    .run(id, owner, text, stamp, stamp);
}
event("greetingevent01", "How are you? Good, yourself? I'm good.");
event("privateevent001", "Another owner's private conversation", "contextowner002");
const req = (id = "greetingevent01", auth = token, sources = ["contacts", "calendar"]) =>
  new Request("https://api.anticipy.ai/me/context-request", { method: "POST",
    headers: { Authorization: auth, "content-type": "application/json" },
    body: JSON.stringify({ eventID: id, availableSources: sources, owner: "contextowner002" }) });
assert.equal((await contextRequest(req(undefined, ""), env)).status, 401);
assert.equal((await contextRequest(req("privateevent001"), env)).status, 404);
assert.equal((await contextRequest(req(undefined, token, ["mail"]), env)).status, 400);
let calls = 0;
const judge = async (_env: unknown, messages: { role: string; content: unknown }[]) => {
  calls++;
  const data = JSON.parse(String(messages[1].content));
  assert.ok(data.conversation.some((row: { text: string }) => row.text.includes("How are you?")));
  assert.ok(!JSON.stringify(data).includes("Another owner's"));
  return '{"verdict":"unnecessary"}';
};
assert.deepEqual(await (await contextRequest(req(), env, judge)).json(), { verdict: "unnecessary" });
assert.deepEqual(await (await contextRequest(req(), env, judge)).json(), { verdict: "unnecessary" });
assert.equal(calls, 1, "repeated feed reads cannot re-spend a judgment");

event("contextneeded01", "Which colleague named Priya did I promise to follow up with?");
const requestJudge = async () => JSON.stringify({ verdict: "request", source: "contacts", subject: "Priya",
  reason: "Contact names may help identify the colleague you mentioned." });
assert.equal((await (await contextRequest(req("contextneeded01"), env, requestJudge)).json() as any).subject, "Priya");
assert.deepEqual(await (await contextRequest(req("contextneeded01", token, ["calendar"]), env, requestJudge)).json(),
  { verdict: "unavailable" }, "cached judgment cannot override a changed device grant");
for (const raw of ["nonsense", "null", "[]", '{"verdict":"sure"}',
  '{"verdict":"request","source":"contacts"}', '{"verdict":"request","source":"mail","reason":"test"}']) {
  assert.deepEqual(parseContextVerdict(raw, ["calendar", "contacts"]), { verdict: "unavailable" });
}
event("modeloutage0001", "A normal sentence.");
assert.deepEqual(await (await contextRequest(req("modeloutage0001"), env, async () => { throw Error("offline"); })).json(),
  { verdict: "unavailable" }, "model failure cannot invent a permission need");
event("revokedwhile001", "Could these calendar events help?");
const revoked = await contextRequest(req("revokedwhile001"), env, async () => {
  db.db.prepare("UPDATE owners SET tokenKey='revoked' WHERE id='contextowner001'").run();
  return '{"verdict":"request","source":"calendar","reason":"Check the existing events."}';
});
assert.equal(revoked.status, 401, "late provider results cannot survive credential revocation");
console.log("Context request: identity, conversational evidence, idempotency, consent, malformed models and revocation passed");
