# Anticipy (macOS app)

True native SwiftUI app — the window. Built to the Anticipy design system
(dark-first, SF Pro, single champagne accent, 8pt grid). Three screens in order:
**Onboarding → Connect → Main** (proactive-first). Polished but inert in the
scaffold — nothing thinks here; everything routes through the engine.

Built with **Swift Package Manager** (no Xcode required — Command Line Tools +
the SwiftUI SDK are enough).

## Build

```bash
bash scripts/build_app.sh        # compiles + assembles dist/Anticipy.app
```

## Run

```bash
open dist/Anticipy.app
```

The left rail previews the three screens. Feature buttons (Begin, the connect
tiles, record controls, the side-door text box) are intentionally inert.
