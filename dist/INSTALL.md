# Anticipy Chrome Extension — Installation

## Side-loading (Developer Mode)

1. Open Chrome and navigate to `chrome://extensions/`
2. Enable **Developer mode** (toggle in top right)
3. Click **Load unpacked**
4. Select the folder: `dist/anticipy-extension/`
5. The Anticipy extension will appear with a gold "A" icon

## What it does

- Connects to Anticipy's real-time backend via Supabase
- Shows Chrome notifications when new actions are inferred from your conversations
- Displays last 5 actions in the popup
- Can execute DOM actions on web pages (click, fill, navigate)

## Usage

1. Click the Anticipy icon in Chrome toolbar to see the popup
2. Green dot = connected to Anticipy backend
3. Open `https://www.anticipy.ai/engine` to start recording conversations
4. Actions will appear as Chrome notifications and in the popup

## Troubleshooting

- If the status dot is red, try refreshing the extension (click the refresh icon on `chrome://extensions/`)
- Make sure you're connected to the internet
- The extension auto-reconnects every 24 seconds if disconnected
