# Anticipy Extension ("the hands")

Chrome MV3 stub. On load it connects to the local engine (`/health` +
`/extension/hello`) and reports **connected** (see the toolbar popup). No real
browser driving yet — that lands in the action chunk.

## Load unpacked (manual)

1. Start the engine (see `../engine/README.md`) on `127.0.0.1:8787`.
2. Chrome → `chrome://extensions` → enable Developer mode → **Load unpacked** →
   select this `extension/` folder.
3. Click the Anticipy toolbar icon — the popup shows "connected · engine vX".

## Test (headless)

Runs the extension's real connect logic (`engine_client.js`) against a freshly
booted engine:

```bash
bash scripts/test_extension.sh
```
