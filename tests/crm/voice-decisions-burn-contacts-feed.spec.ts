import { test, expect } from "@playwright/test";
import { signIn } from "./_helpers";

const PAGES: { url: string; heading: string }[] = [
  { url: "/crm/voice", heading: "Voice memos" },
  { url: "/crm/decisions", heading: "Decisions" },
  { url: "/crm/burn", heading: "Burn" },
  { url: "/crm/contacts", heading: "Contacts" },
  { url: "/crm/feed", heading: "Agent feed" },
  { url: "/crm/manufacturing", heading: "Manufacturing" },
  { url: "/crm/settings", heading: "Settings" },
];

for (const p of PAGES) {
  test(`${p.heading} renders`, async ({ page, context }) => {
    await signIn(page, context);
    await page.goto(p.url);
    await expect(page.getByRole("heading", { name: p.heading })).toBeVisible({
      timeout: 10_000,
    });
  });
}
