import { test, expect } from "@playwright/test";
import { signIn } from "./_helpers";

test("todos page lets us create + delete a todo via API", async ({ page, context }) => {
  await signIn(page, context);
  await page.goto("/crm/todos");
  await expect(page.getByRole("heading", { name: "Todos" })).toBeVisible();

  const usersRes = await page.request.get("/api/crm/users");
  const me = (await usersRes.json()).users[0];
  const created = await page.request.post("/api/crm/todos", {
    data: {
      title: "Smoke test todo",
      assignee_user_id: me.id,
      priority: "normal",
    },
    headers: { "x-crm-user-id": me.id, "x-crm-user-name": me.name },
  });
  expect(created.ok()).toBeTruthy();
  const j = await created.json();
  const id = j.todo.id;

  await page.reload();
  await expect(page.getByText("Smoke test todo")).toBeVisible({ timeout: 10_000 });

  const del = await page.request.delete(`/api/crm/todos/${id}`);
  expect(del.status()).toBe(204);
});
