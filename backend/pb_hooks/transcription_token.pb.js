/// <reference path="../pb_data/types.d.ts" />

// A signed-in iPhone exchanges the server-held Deepgram key for a short-lived
// JWT. The vendor key never enters the app, logs, PocketBase records, or source.
// Deepgram permits the websocket established with this token to outlive the
// token itself, so 60 seconds is ample for connection setup and limits the
// value of an intercepted response.
routerAdd("POST", "/transcription/token", (e) => {
  if (!e.auth) return e.json(401, { error: "sign in first" });
  const key = $os.getenv("DEEPGRAM_API_KEY") || "";
  if (!key) return e.json(503, { error: "transcription is not configured" });
  try {
    const response = $http.send({
      url: "https://api.deepgram.com/v1/auth/grant",
      method: "POST",
      headers: {
        "Authorization": "Token " + key,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ ttl_seconds: 60 }),
      timeout: 15,
    });
    const token = response.json && response.json.access_token;
    if (response.statusCode < 200 || response.statusCode >= 300 || !token) {
      console.log("transcription token: Deepgram refused exchange:", response.statusCode);
      return e.json(502, { error: "transcription token unavailable" });
    }
    return e.json(200, { access_token: token, expires_in: 60 });
  } catch (error) {
    console.log("transcription token: exchange failed:", String(error && error.name || "error"));
    return e.json(502, { error: "transcription token unavailable" });
  }
});
