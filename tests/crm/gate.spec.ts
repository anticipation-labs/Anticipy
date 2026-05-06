import { test, expect } from "@playwright/test";

test("password gate blocks the dashboard until correct password", async ({ page, context }) => {
  await context.clearCookies();
  await page.goto("/crm");
  await expect(page.getByRole("heading", { name: "CRM" })).toBeVisible();

  // Wrong password.
  await page.locator('input[type="password"]').fill("not-it");
  await page.getByRole("button", { name: "Unlock" }).click();
  await expect(page.getByText("Wrong password")).toBeVisible();

  // Right password.
  await page.locator('input[type="password"]').fill(process.env.CRM_PASSWORD ?? "123");
  await page.getByRole("button", { name: "Unlock" }).click();
  await expect(page.getByRole("heading", { name: "Who are you?" })).toBeVisible({ timeout: 10_000 });
});

test("name picker lets us pick a user and shows the dashboard", async ({ page, context }) => {
  await context.clearCookies();
  await page.goto("/crm");
  await page.locator('input[type="password"]').fill(process.env.CRM_PASSWORD ?? "123");
  await page.getByRole("button", { name: "Unlock" }).click();
  await expect(page.getByRole("heading", { name: "Who are you?" })).toBeVisible({ timeout: 10_000 });
  await page.getByRole("button", { name: /Omar/ }).click();
  await expect(page.getByRole("heading", { name: /Hi, Omar/ })).toBeVisible({ timeout: 10_000 });
});
