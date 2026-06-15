# Anticipy Execute (macOS app)

A real launcher app — **opening it boots the local engine + web interface and opens
the working owner UI** (input doors, task board, approve/do, receipts). No longer the
inert scaffold: double-click → the whole flow comes up.

Built with **Swift Package Manager** (no Xcode required — Command Line Tools are
enough). The interface opens in the default browser because an embedded native webview
needs full Xcode/WebKit; the flow is identical.

## Build

```bash
bash scripts/build_app.sh        # compiles + assembles dist/Anticipy.app (bundles boot.sh)
```

## Run

```bash
open dist/Anticipy.app            # boots engine(:8787) + UI(:3000) if needed, opens the interface
```

## Honest status / what's left

- **Works (dev preview):** opening the app boots the engine + UI from the repo on THIS
  Mac and opens the real owner interface. Verified: launching it brings :8787 + :3000 up
  and serves the working UI.
- **Remaining packaging (the "anybody can download it" gap):** bundle the engine (a frozen
  Python runtime) + a prebuilt UI *inside* the .app so it runs without the repo, then
  **Apple-sign + notarize** (needs Omar's Apple Developer ID). Until then the download is an
  unsigned dev preview (right-click → Open), and the launcher boots from the repo path.
