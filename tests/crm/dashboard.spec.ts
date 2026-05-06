import { test, expect } from "@playwright/test";
import { signIn } from "./_helpers";

test("dashboard renders the six cards", async ({ page, context }) => {
  await signIn(page, context);
  await page.goto("/crm");
  await expect(page.getByRole("heading", { name: /Hi, Omar/ })).toBeVisible({ timeout: 10_000 });
  await expect(page.getByText("Voice memo")).toBeVisible();
  await expect(page.getByText("New expense")).toBeVisible();
  await expect(page.getByText("Burn this month")).toBeVisible();
  await expect(page.getByText("Your todos")).toBeVisible();
  await expect(page.getByText("Shared todos")).toBeVisible();
  await expect(page.getByText("Recent agent events")).toBeVisible();
});
