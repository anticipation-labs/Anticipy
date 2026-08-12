/// <reference path="../pb_data/types.d.ts" />

// The phone fetches its transcription key here, so the cloud ears work
// without a human ever copy-pasting an API key — and rotating the key is one
// env change, no app update. The gate is the same two credentials the data
// API accepts: the shared service token, or a signed-in account.
routerAdd("GET", "/ears/key", (e) => {
  const svc = $os.getenv("ANTICIPY_SERVICE_TOKEN");
  let allowed = false;
  if (svc && e.request.header.get("X-Anticipy-Token") === svc) allowed = true;
  if (!allowed) {
    try {
      if (e.auth) allowed = true;
    } catch (_) {}
  }
  // Local dev without a service token configured stays open, matching the
  // guard hook's behaviour for the rest of the API.
  if (!svc) allowed = true;
  if (!allowed) return e.json(403, { error: "forbidden" });
  const key = $os.getenv("DEEPGRAM_API_KEY") || "";
  return e.json(200, { deepgram_key: key });
});
