import { expect, test } from "@playwright/test";

const LOCAL_ENGINE = "http://127.0.0.1:8731";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
  "Access-Control-Allow-Headers": "content-type,authorization",
  "Content-Type": "application/json",
};

test("audio upload feeds the post-ASR path without starting live mic", async ({
  page,
  baseURL,
}) => {
  let liveMicStarted = false;
  let uploadBytes = 0;

  await page.addInitScript(() => {
    const expiresAt = Math.floor(Date.now() / 1000) + 60 * 60;
    const session = {
      access_token: "test-access-token",
      refresh_token: "test-refresh-token",
      expires_at: expiresAt,
      expires_in: 60 * 60,
      token_type: "bearer",
      user: {
        id: "00000000-0000-0000-0000-000000000001",
        aud: "authenticated",
        role: "authenticated",
        email: "stranger@example.com",
        app_metadata: { provider: "email", providers: ["email"] },
        user_metadata: {},
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      },
    };
    const serialized = JSON.stringify(session);
    window.localStorage.setItem("sb-auth-token", serialized);
    window.localStorage.setItem("supabase.auth.token", serialized);

    const originalGetItem = Storage.prototype.getItem;
    Storage.prototype.getItem = function getItem(key: string) {
      if (typeof key === "string" && /^sb-.+-auth-token$/.test(key)) {
        return serialized;
      }
      return originalGetItem.call(this, key);
    };
  });

  await page.route("**/api/app/state", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        account: { status: "ready", detail: "signed in" },
        download: { status: "ready", detail: "available" },
        onboarding: {
          chrome: { status: "ready", detail: "ready" },
          microphone: { status: "ready", detail: "not needed for upload" },
          autonomy: { status: "ready", detail: "ready" },
        },
        engine: { status: "ready", detail: "ready" },
        proposals: { status: "ready", detail: "ready" },
        safety: { detail: "ready" },
      }),
    });
  });

  await page.route(`${LOCAL_ENGINE}/**`, async (route) => {
    const request = route.request();
    const url = new URL(request.url());

    if (request.method() === "OPTIONS") {
      await route.fulfill({ status: 204, headers: corsHeaders });
      return;
    }

    const json = async (status: number, body: Record<string, unknown>) => {
      await route.fulfill({
        status,
        headers: corsHeaders,
        body: JSON.stringify(body),
      });
    };

    if (url.pathname === "/health") {
      await json(200, { ok: true });
      return;
    }
    if (url.pathname === "/api/state") {
      await json(200, {
        key_ok: true,
        provisioned: true,
        onboarded: true,
        profile: { name: "Casey Stranger" },
      });
      return;
    }
    if (url.pathname === "/api/provision") {
      await json(200, { ok: true });
      return;
    }
    if (url.pathname === "/api/listen/start") {
      liveMicStarted = true;
      await json(500, { error: "microphone permission should not be requested" });
      return;
    }
    if (url.pathname === "/api/listen/upload") {
      uploadBytes = request.postDataBuffer()?.byteLength ?? 0;
      await json(200, { source: "upload-asr", bytes: uploadBytes });
      return;
    }
    if (url.pathname === "/api/listen/status") {
      await json(200, {
        on: false,
        windows: 1,
        recent: [
          {
            transcript: uploadBytes ? "uploaded audio transcript" : "",
            outcome: "NO_ACTION",
          },
        ],
        pending: null,
      });
      return;
    }

    await json(404, { error: `unexpected local engine path ${url.pathname}` });
  });

  await page.goto(new URL("/app", baseURL ?? "http://127.0.0.1:3000").toString());
  await page.locator("nav").getByRole("button", { name: "Listen" }).click();

  await expect(page.getByText("Engine live")).toBeVisible();

  await page.locator('input[type="file"]').setInputFiles({
    name: "voice-note.mp3",
    mimeType: "audio/mpeg",
    buffer: Buffer.from("ID3 uploaded audio bytes"),
  });

  await expect.poll(() => uploadBytes).toBeGreaterThan(0);
  expect(liveMicStarted).toBe(false);
  await expect(page.getByText(/audio upload -> upload-asr bytes=\d+/)).toBeVisible();
  await expect(page.getByText(/microphone permission/i)).toHaveCount(0);
});
