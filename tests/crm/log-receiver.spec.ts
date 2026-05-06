import { test, expect } from "@playwright/test";
import { signIn } from "./_helpers";

test("POST /api/log writes a row and the feed shows it", async ({ page, context }) => {
  await signIn(page, context);
  const summary = `e2e ping ${Date.now()}`;
  const r = await page.request.post("/api/log", {
    data: {
      agent_name: "manual",
      action: "e2e_test",
      summary,
    },
  });
  expect(r.ok()).toBeTruthy();
  const j = await r.json();
  expect(j.event_id).toBeTruthy();

  await page.goto("/crm/feed");
  await expect(page.getByText(summary)).toBeVisible({ timeout: 10_000 });
});

test("POST /api/log rejects unauthenticated callers", async ({ request }) => {
  const r = await request.post("/api/log", {
    data: { agent_name: "x", action: "y", summary: "z" },
  });
  expect(r.status()).toBe(401);
});
