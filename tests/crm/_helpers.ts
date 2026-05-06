import { Page, BrowserContext } from "@playwright/test";

/**
 * Skip the password screen by setting the gate cookie directly via the API
 * route, then pick a user via localStorage. Each test that needs an
 * "authed" CRM session calls signIn at the start.
 */
export async function signIn(page: Page, context: BrowserContext, name = "Omar") {
  await context.clearCookies();
  const res = await page.request.post("/api/crm/gate", {
    data: { password: process.env.CRM_PASSWORD ?? "123" },
  });
  if (!res.ok()) throw new Error(`Gate POST failed: ${res.status()}`);

  const usersRes = await page.request.get("/api/crm/users");
  const j = await usersRes.json();
  const u = (j.users || []).find((x: any) => x.name === name) || j.users?.[0];
  if (!u) throw new Error("No CRM users seeded");

  await page.addInitScript(
    ([id, n]) => {
      window.localStorage.setItem(
        "anticipy_crm_user",
        JSON.stringify({ id, name: n })
      );
    },
    [u.id, u.name]
  );
}
