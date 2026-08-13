/// <reference path="../pb_data/types.d.ts" />

// Private account discovery for the brain supervisor. The ordinary owners
// collection correctly allows a signed-in person to list only themselves; a
// backend-wide shared-token request is not an auth-model login and therefore
// cannot use that list route. This endpoint exposes only the two identifiers
// needed to start an isolated worker — never email, phone, password metadata,
// tokens, or profile fields.
routerAdd("GET", "/worker/owners", (e) => {
  const expected = $os.getenv("ANTICIPY_SERVICE_TOKEN") || "";
  const supplied = e.request.header.get("X-Anticipy-Token") || "";
  if (!expected || supplied !== expected) {
    return e.json(403, { error: "forbidden" });
  }

  const q = e.request.url.query();
  const page = Math.max(1, parseInt(q.get("page") || "1", 10));
  const perPage = Math.max(1, Math.min(200, parseInt(q.get("perPage") || "200", 10)));
  const offset = (page - 1) * perPage;
  const rows = e.app.findRecordsByFilter("owners", "id != ''", "+id", perPage, offset);
  const total = e.app.countRecords("owners");
  const items = rows.map((row) => ({
    id: row.id,
    legacy_uuid: row.getString("legacy_uuid") || "",
  }));
  return e.json(200, {
    page: page,
    perPage: perPage,
    totalItems: total,
    totalPages: Math.max(1, Math.ceil(total / perPage)),
    items: items,
  });
});
