// The exact bytes the extension would send for each golden fixture, one JSON
// object per line: { name, expect, goal, system, user }.
//
// overnight/login_wall_gate.py runs this and posts what it prints, so the
// live leg measures the prompt login_wall.js builds — not a Python paraphrase
// of it that could drift. The fence is fixed here because a gate's evidence
// should be reproducible; in the extension it is minted per call.
//
// Run: node research/evals/login-wall-2026-09-05/messages.mjs
import { wallMessages } from "../../../extension/login_wall.js";
import { FIXTURES } from "./fixtures.mjs";

for (const fixture of FIXTURES) {
  const [system, user] = wallMessages(fixture.state, fixture.goal, "golden-2026-09-05");
  process.stdout.write(JSON.stringify({
    name: fixture.name, expect: fixture.expect, goal: fixture.goal,
    system: system.content, user: user.content,
  }) + "\n");
}
