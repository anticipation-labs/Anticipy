import { test, expect } from "@playwright/test";
import { signIn } from "./_helpers";

test("expenses page opens the new-expense panel", async ({ page, context }) => {
  await signIn(page, context);
  await page.goto("/crm/expenses");
  await expect(page.getByRole("heading", { name: "Expenses" })).toBeVisible();
  await page.getByRole("button", { name: "+ New expense" }).click();
  await expect(page.getByRole("heading", { name: "New expense" })).toBeVisible();
  await expect(page.getByText(/Drop receipt photos here/)).toBeVisible();
});

test("expenses export endpoint returns a CSV", async ({ page, context }) => {
  await signIn(page, context);
  const res = await page.request.get("/api/crm/expenses/export?format=csv");
  expect(res.ok()).toBeTruthy();
  expect(res.headers()["content-type"]).toContain("text/csv");
});
