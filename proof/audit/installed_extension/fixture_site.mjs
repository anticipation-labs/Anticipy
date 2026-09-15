// The venue fixture the browser job visits: the same two-hop / scroll pages
// proof/audit/check_browser_frame_clicks.mjs serves through Playwright routes,
// now on a real loopback origin so an INSTALLED extension can reach them.
// A click on the widget button POSTs /__clicked, so the click is recorded by
// the site, not inferred from the extension's own words.
//
//   node proof/audit/installed_extension/fixture_site.mjs --port 8797
import { createServer } from "node:http";

const arg = (n, d) => { const i = process.argv.indexOf(`--${n}`); return i > 0 ? process.argv[i + 1] : d; };
const PORT = Number(arg("port", "8797"));
const ORIGIN = `http://127.0.0.1:${PORT}`;
const STYLE = "<style>body{font:18px system-ui;margin:0;padding:24px}button{font:inherit;padding:12px 20px;display:block;margin:12px 0}</style>";
const RECORD = `<script>function __fixtureClicked(id){fetch("/__clicked?id="+encodeURIComponent(id),{method:"POST"}).catch(()=>{});document.body.insertAdjacentHTML("beforeend","<p id=slots>Slots: 7pm, 8pm</p>")}</script>`;
const widget = STYLE + RECORD + `<h2>Booking widget</h2><p>Pick a slot.</p><button id="target" onclick="__fixtureClicked('widget-target')">Reveal slots</button>`;
const pages = {
  "/widget": widget,
  "/wrapper": STYLE + `<div style="height:150px">wrapper chrome</div><iframe src="${ORIGIN}/widget" style="width:600px;height:300px;margin-left:200px"></iframe>`,
  "/scroll": STYLE + `<h1>Venue</h1><a href="${ORIGIN}/scroll#menu">Menu</a><div style="height:1400px"></div><iframe id="frame" src="${ORIGIN}/widget" style="width:600px;height:400px;border:1px solid #999"></iframe><div style="height:1400px"></div>`,
  "/two-hop": STYLE + `<h1>Venue</h1><a href="${ORIGIN}/two-hop#menu">Menu</a><div style="height:900px"></div><iframe id="wrapper" src="${ORIGIN}/wrapper" style="width:900px;height:520px;border:1px solid #999"></iframe><div style="height:900px"></div>`,
  "/plain": STYLE + RECORD + `<h1>Venue</h1><p>Opening hours below.</p><button id="target" onclick="__fixtureClicked('plain-target')">Reveal slots</button>`,
};
const clicks = [];
const server = createServer((req, res) => {
  const url = new URL(req.url, ORIGIN);
  if (req.method === "POST" && url.pathname === "/__clicked") {
    clicks.push({ id: url.searchParams.get("id"), at: Date.now(), referer: req.headers.referer || "" });
    res.writeHead(204); res.end(); return;
  }
  if (url.pathname === "/__clicks") { res.writeHead(200, { "content-type": "application/json" }); res.end(JSON.stringify(clicks)); return; }
  if (url.pathname === "/__reset" && req.method === "POST") { clicks.length = 0; res.writeHead(204); res.end(); return; }
  const body = pages[url.pathname];
  if (!body) { res.writeHead(404); res.end("no such fixture"); return; }
  res.writeHead(200, { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" });
  res.end(body);
});
server.listen(PORT, "127.0.0.1", () => console.log(JSON.stringify({ site: ORIGIN })));
